#!/usr/bin/env python3
"""
functionmap.py — minimal function extractor for codebases

Scans source files and extracts function signatures with metadata.
Claude handles all categorization and organization.

Output: _functions.json with raw function data (no categories)
"""

from __future__ import annotations

__version__ = "1.0.0"

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import time
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# -----------------------------
# Configuration
# -----------------------------

DEFAULT_IGNORE_DIRS = {
    ".git", ".svn", ".hg",
    "node_modules", "vendor",
    "dist", "build", "out",
    ".idea", ".vscode", ".cache",
    "cache", "tmp", "temp",
    "logs", "log",
    "3rdParty",
}

DEFAULT_IGNORE_FILE_SUFFIXES = (
    ".min.js", ".min.css",
)

SUPPORTED_EXTS = {
    ".php": "php",
    ".inc": "php",
    ".phtml": "php",
    ".js": "js",
    ".cjs": "js",
    ".mjs": "js",
    ".jsx": "js",
    ".ts": "ts",
    ".tsx": "ts",
}


# -----------------------------
# Models
# -----------------------------

@dataclass
class FunctionDef:
    language: str
    kind: str
    name: str
    short_name: str
    namespace: Optional[str]
    class_name: Optional[str]
    visibility: Optional[str]
    is_static: bool
    is_async: bool
    params: str
    return_type: str
    file: str
    line_start: int
    line_end: int
    summary: str
    doc: str
    attributes: List[str]


# -----------------------------
# Utility helpers
# -----------------------------

def _now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _home_claude_dir() -> Path:
    home = Path(os.path.expanduser("~"))
    return home / ".claude"


def _functionmap_root(claude_dir: Path) -> Path:
    return claude_dir / "functionmap"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())
    s = re.sub(r"-{2,}", "-", s).strip("-").lower()
    return s or "project"


def _posix_rel(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except Exception:
        rel = path
    return rel.as_posix()


def _posix_path(p) -> str:
    """Convert a path to forward-slash format for JSON serialization."""
    return str(p).replace('\\', '/')


def _file_hash(path: Path) -> str:
    """SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def _content_hash(text: str) -> str:
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _extract_doc_summary(doc: str) -> str:
    if not doc:
        return ""
    lines = []
    for raw in doc.splitlines():
        line = raw.strip()
        line = re.sub(r"^/\*\*?", "", line)
        line = re.sub(r"\*/$", "", line)
        line = re.sub(r"^\*", "", line).strip()
        if line:
            lines.append(line)
    return lines[0] if lines else ""


def _extract_doc_return(doc: str) -> str:
    if not doc:
        return ""
    m = re.search(r"@return\s+([^\s*]+)", doc)
    return (m.group(1).strip() if m else "")


def _collect_signature(lines: List[str], start_idx0: int, start_col: int) -> Tuple[str, int]:
    """
    Collects text starting at (start_idx0,start_col) until we have:
      - balanced parentheses for the first (...) we encounter, AND
      - we then reach '{' or ';' (function body start or declaration end)
    Returns (signature_text, end_line_idx0).
    """
    text_parts: List[str] = []
    paren = 0
    seen_open = False
    in_sq = False
    in_dq = False
    esc = False

    i = start_idx0
    while i < len(lines):
        chunk = lines[i]
        if i == start_idx0:
            chunk = chunk[start_col:]
        text_parts.append(chunk)

        for ch in chunk:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if not in_dq and ch == "'":
                in_sq = not in_sq
                continue
            if not in_sq and ch == '"':
                in_dq = not in_dq
                continue
            if in_sq or in_dq:
                continue

            if ch == "(":
                paren += 1
                seen_open = True
            elif ch == ")":
                if paren > 0:
                    paren -= 1
            elif seen_open and paren == 0 and ch in "{;":
                return "\n".join(text_parts), i

        i += 1

    return "\n".join(text_parts), len(lines) - 1


# -----------------------------
# Source scanning
# -----------------------------

_DOCBLOCK_START_RE = re.compile(r"/\*\*")
_DOCBLOCK_END_RE = re.compile(r"\*/")


def scan_php(content: str) -> List[Tuple[Dict, int, int]]:
    """
    Returns list of (raw_info, line_start, line_end).
    """
    lines = content.splitlines()
    namespace = None

    class_stack: List[Tuple[str, int]] = []
    brace_depth = 0

    pending_doc: Optional[str] = None
    doc_acc: List[str] = []
    in_doc = False
    last_doc_ended_line: Optional[int] = None

    pending_attributes: List[str] = []

    results: List[Tuple[Dict, int, int]] = []

    class_re = re.compile(r"^\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_]\w*)\b")
    trait_re = re.compile(r"^\s*trait\s+([A-Za-z_]\w*)\b")
    interface_re = re.compile(r"^\s*interface\s+([A-Za-z_]\w*)\b")
    namespace_re = re.compile(r"^\s*namespace\s+([^;{]+)\s*[;{]")
    attribute_re = re.compile(r"^\s*#\[([^\]]+)\]")

    func_start_re = re.compile(
        r"""^\s*
        (?:(public|protected|private)\s+)?
        (?:(static)\s+)?
        function\s+
        ([A-Za-z_]\w*)\s*\(
        """,
        re.X,
    )

    for idx0, raw in enumerate(lines):
        i = idx0 + 1
        line = raw

        if namespace is None:
            m = namespace_re.match(line)
            if m:
                namespace = m.group(1).strip()

        attr_match = attribute_re.match(line)
        if attr_match:
            attr_name = attr_match.group(1).strip()
            pending_attributes.append(attr_name)
            continue

        if not in_doc and _DOCBLOCK_START_RE.search(line):
            in_doc = True
            doc_acc = [line]
            if _DOCBLOCK_END_RE.search(line) and line.find("*/") > line.find("/**"):
                in_doc = False
                pending_doc = "\n".join(doc_acc)
                last_doc_ended_line = i
        elif in_doc:
            doc_acc.append(line)
            if _DOCBLOCK_END_RE.search(line):
                in_doc = False
                pending_doc = "\n".join(doc_acc)
                last_doc_ended_line = i

        m = class_re.match(line) or trait_re.match(line) or interface_re.match(line)
        if m:
            cname = m.group(1)
            class_stack.append((cname, brace_depth))

        fm = func_start_re.match(line)
        if fm:
            vis = fm.group(1)
            is_static = bool(fm.group(2))
            fname = fm.group(3)

            sig_text, end_idx0 = _collect_signature(lines, idx0, fm.start(0))
            sig_one_line = re.sub(r"\s+", " ", sig_text.strip())

            sig_re = re.compile(
                r"""^\s*
                (?:(public|protected|private)\s+)?(?:(static)\s+)?function\s+
                ([A-Za-z_]\w*)\s*\((.*?)\)\s*
                (?:\:\s*([^\s{;]+))?
                """,
                re.X | re.S,
            )
            sm = sig_re.search(sig_text)
            params = (sm.group(4).strip() if sm else "")
            rtype = (sm.group(5).strip() if (sm and sm.group(5)) else "")

            if not rtype:
                rtype = _extract_doc_return(pending_doc or "") or "unknown"

            current_class = class_stack[-1][0] if class_stack else None
            kind = "method" if current_class else "function"
            full_name = f"{current_class}::{fname}" if current_class else fname

            doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""

            attrs = list(pending_attributes)
            pending_attributes = []
            pending_doc = None
            last_doc_ended_line = None

            results.append((
                {
                    "language": "php",
                    "kind": kind,
                    "name": full_name,
                    "short_name": fname,
                    "namespace": namespace,
                    "class_name": current_class,
                    "visibility": vis,
                    "is_static": is_static,
                    "is_async": False,
                    "params": params,
                    "return_type": rtype,
                    "doc": doc,
                    "attributes": attrs,
                },
                i,
                end_idx0 + 1,
            ))

        brace_depth += line.count("{") - line.count("}")
        while class_stack and brace_depth <= class_stack[-1][1]:
            class_stack.pop()

    return results


def scan_js_ts(content: str, language: str) -> List[Tuple[Dict, int, int]]:
    lines = content.splitlines()

    class_stack: List[Tuple[str, int]] = []
    brace_depth = 0

    pending_doc: Optional[str] = None
    doc_acc: List[str] = []
    in_doc = False
    last_doc_ended_line: Optional[int] = None

    results: List[Tuple[Dict, int, int]] = []

    class_re = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)\b")
    func_start_re = re.compile(r"^\s*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\*?\s+([A-Za-z_$][\w$]*)\s*\(")
    arrow_start_re = re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?\(?")
    method_start_re = re.compile(r"^\s*(?:async\s+)?(?:static\s+)?\*?(#?[A-Za-z_$][\w$]*)\s*\(")
    accessor_start_re = re.compile(r"^\s*(?:static\s+)?(get|set)\s+(#?[A-Za-z_$][\w$]*)\s*\(")
    proto_method_re = re.compile(r"^\s*([A-Za-z_$][\w$]*)\.prototype\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function")
    jquery_plugin_re = re.compile(r"^\s*\$\.fn\.([A-Za-z_$][\w$]*)\s*=\s*function")
    exports_func_re = re.compile(r"^\s*(?:module\.)?exports\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?function")

    for idx0, raw in enumerate(lines):
        i = idx0 + 1
        line = raw

        if not in_doc and _DOCBLOCK_START_RE.search(line):
            in_doc = True
            doc_acc = [line]
            if _DOCBLOCK_END_RE.search(line) and line.find("*/") > line.find("/**"):
                in_doc = False
                pending_doc = "\n".join(doc_acc)
                last_doc_ended_line = i
        elif in_doc:
            doc_acc.append(line)
            if _DOCBLOCK_END_RE.search(line):
                in_doc = False
                pending_doc = "\n".join(doc_acc)
                last_doc_ended_line = i

        m = class_re.match(line)
        if m:
            class_stack.append((m.group(1), brace_depth))

        m = func_start_re.match(line)
        if m:
            fname = m.group(1)
            sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))
            is_async = "async" in sig_text.split("function")[0]
            sm = re.search(r"function\*?\s+" + re.escape(fname) + r"\s*\((.*?)\)\s*(?::\s*([^{]+))?", sig_text, flags=re.S)
            params = (sm.group(1).strip() if sm else "")
            rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
            if not rtype:
                rtype = _extract_doc_return(pending_doc or "") or "unknown"

            current_class = class_stack[-1][0] if class_stack else None
            kind = "method" if current_class else "function"
            full_name = f"{current_class}::{fname}" if current_class else fname

            doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
            pending_doc = None
            last_doc_ended_line = None

            results.append((
                {
                    "language": language,
                    "kind": kind,
                    "name": full_name,
                    "short_name": fname,
                    "namespace": None,
                    "class_name": current_class,
                    "visibility": None,
                    "is_static": False,
                    "is_async": is_async,
                    "params": params,
                    "return_type": rtype,
                    "doc": doc,
                    "attributes": [],
                },
                i,
                end_idx0 + 1,
            ))

        m = arrow_start_re.match(line)
        if m:
            fname = m.group(1)
            sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))

            # Validate: RHS must contain => or function keyword (reject plain variable assignments)
            rhs_start = sig_text.find("=")
            rhs = sig_text[rhs_start + 1:] if rhs_start >= 0 else ""
            if "=>" not in rhs and "function" not in rhs:
                continue

            # Try arrow function pattern first
            sm = re.search(re.escape(fname) + r"\s*=\s*(?:async\s+)?\(?(.+?)\)?\s*(?::\s*([^=]+))?\s*=>", sig_text, flags=re.S)
            if not sm:
                # Try function expression pattern: const name = function(...)
                sm = re.search(re.escape(fname) + r"\s*=\s*(?:async\s+)?function\s*\(?(.*?)\)?\s*(?::\s*([^{]+))?", sig_text, flags=re.S)
            params = (sm.group(1).strip() if sm else "")
            rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
            is_async = "async" in sig_text
            if not rtype:
                rtype = _extract_doc_return(pending_doc or "") or "unknown"

            doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
            pending_doc = None
            last_doc_ended_line = None

            results.append((
                {
                    "language": language,
                    "kind": "function",
                    "name": fname,
                    "short_name": fname,
                    "namespace": None,
                    "class_name": None,
                    "visibility": None,
                    "is_static": False,
                    "is_async": is_async,
                    "params": params,
                    "return_type": rtype,
                    "doc": doc,
                    "attributes": [],
                },
                i,
                end_idx0 + 1,
            ))

        # --- Prototype methods: Constructor.prototype.method = function ---
        m = proto_method_re.match(line)
        if m:
            class_name = m.group(1)
            mname = m.group(2)
            sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))
            sm = re.search(r"function\s*\w*\s*\((.*?)\)\s*(?::\s*([^{]+))?", sig_text, flags=re.S)
            params = (sm.group(1).strip() if sm else "")
            rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
            is_async = "async" in sig_text.split("function")[0]
            if not rtype:
                rtype = _extract_doc_return(pending_doc or "") or "unknown"

            full_name = f"{class_name}.prototype.{mname}"

            doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
            pending_doc = None
            last_doc_ended_line = None

            results.append((
                {
                    "language": language,
                    "kind": "method",
                    "name": full_name,
                    "short_name": mname,
                    "namespace": None,
                    "class_name": class_name,
                    "visibility": None,
                    "is_static": False,
                    "is_async": is_async,
                    "params": params,
                    "return_type": rtype,
                    "doc": doc,
                    "attributes": [],
                },
                i,
                end_idx0 + 1,
            ))

        # --- jQuery plugins: $.fn.pluginName = function ---
        m = jquery_plugin_re.match(line)
        if m:
            pname = m.group(1)
            sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))
            sm = re.search(r"function\s*\(?(.*?)\)?\s*(?::\s*([^{]+))?", sig_text, flags=re.S)
            params = (sm.group(1).strip() if sm else "")
            rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
            if not rtype:
                rtype = _extract_doc_return(pending_doc or "") or "unknown"

            full_name = f"$.fn.{pname}"

            doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
            pending_doc = None
            last_doc_ended_line = None

            results.append((
                {
                    "language": language,
                    "kind": "function",
                    "name": full_name,
                    "short_name": pname,
                    "namespace": None,
                    "class_name": None,
                    "visibility": None,
                    "is_static": False,
                    "is_async": False,
                    "params": params,
                    "return_type": rtype,
                    "doc": doc,
                    "attributes": [],
                },
                i,
                end_idx0 + 1,
            ))

        # --- Module exports: module.exports.name = function / exports.name = function ---
        m = exports_func_re.match(line)
        if m:
            fname = m.group(1)
            sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))
            sm = re.search(r"function\s*\w*\s*\((.*?)\)\s*(?::\s*([^{]+))?", sig_text, flags=re.S)
            params = (sm.group(1).strip() if sm else "")
            rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
            is_async = "async" in sig_text.split("function")[0]
            if not rtype:
                rtype = _extract_doc_return(pending_doc or "") or "unknown"

            doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
            pending_doc = None
            last_doc_ended_line = None

            results.append((
                {
                    "language": language,
                    "kind": "function",
                    "name": fname,
                    "short_name": fname,
                    "namespace": None,
                    "class_name": None,
                    "visibility": None,
                    "is_static": False,
                    "is_async": is_async,
                    "params": params,
                    "return_type": rtype,
                    "doc": doc,
                    "attributes": [],
                },
                i,
                end_idx0 + 1,
            ))

        # --- Class methods: accessors and regular methods ---
        if class_stack:
            m = accessor_start_re.match(line)
            if m:
                accessor_type = m.group(1)  # "get" or "set"
                prop_name = m.group(2)
                sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))
                sm = re.search(re.escape(prop_name) + r"\s*\((.*?)\)\s*(?::\s*([^{]+))?\s*\{", sig_text, flags=re.S)
                params = (sm.group(1).strip() if sm else "")
                rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
                is_static = "static " in sig_text
                if not rtype:
                    rtype = _extract_doc_return(pending_doc or "") or "unknown"

                current_class = class_stack[-1][0]
                display_name = f"{accessor_type} {prop_name}"
                full_name = f"{current_class}::{display_name}"

                doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
                pending_doc = None
                last_doc_ended_line = None

                results.append((
                    {
                        "language": language,
                        "kind": "accessor",
                        "name": full_name,
                        "short_name": display_name,
                        "namespace": None,
                        "class_name": current_class,
                        "visibility": None,
                        "is_static": is_static,
                        "is_async": False,
                        "params": params,
                        "return_type": rtype,
                        "doc": doc,
                        "attributes": [],
                    },
                    i,
                    end_idx0 + 1,
                ))
            else:
                m = method_start_re.match(line)
                if m:
                    mname = m.group(1)
                    if mname in {
                        "constructor", "if", "for", "while", "switch", "catch",
                        "return", "throw", "typeof", "delete", "new", "await",
                        "yield", "void", "super", "do", "try", "else",
                        "import", "export", "class", "extends", "instanceof",
                        "in", "of", "get", "set",
                    }:
                        pass
                    else:
                        sig_text, end_idx0 = _collect_signature(lines, idx0, m.start(0))
                        sm = re.search(re.escape(mname) + r"\s*\((.*?)\)\s*(?::\s*([^{]+))?\s*\{", sig_text, flags=re.S)
                        params = (sm.group(1).strip() if sm else "")
                        rtype = (sm.group(2).strip() if (sm and sm.group(2)) else "")
                        is_async = sig_text.lstrip().startswith("async ")
                        is_static = "static " in sig_text
                        if not rtype:
                            rtype = _extract_doc_return(pending_doc or "") or "unknown"

                        current_class = class_stack[-1][0]
                        full_name = f"{current_class}::{mname}"

                        doc = (pending_doc or "") if (last_doc_ended_line is not None and (i - last_doc_ended_line) <= 2) else ""
                        pending_doc = None
                        last_doc_ended_line = None

                        results.append((
                            {
                                "language": language,
                                "kind": "method",
                                "name": full_name,
                                "short_name": mname,
                                "namespace": None,
                                "class_name": current_class,
                                "visibility": None,
                                "is_static": is_static,
                                "is_async": is_async,
                                "params": params,
                                "return_type": rtype,
                                "doc": doc,
                                "attributes": [],
                            },
                            i,
                            end_idx0 + 1,
                        ))

        brace_depth += line.count("{") - line.count("}")
        while class_stack and brace_depth <= class_stack[-1][1]:
            class_stack.pop()

    return results


def iter_source_files(root: Path, include_vendor: bool, ignore_dirs: Sequence[str]) -> Iterable[Path]:
    ignore = set(DEFAULT_IGNORE_DIRS)
    ignore.update(ignore_dirs)
    if include_vendor:
        ignore.discard("vendor")
        ignore.discard("node_modules")

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for fn in filenames:
            if any(fn.endswith(suf) for suf in DEFAULT_IGNORE_FILE_SUFFIXES):
                continue
            p = Path(dirpath) / fn
            ext = p.suffix.lower()
            if ext in SUPPORTED_EXTS:
                yield p


# -----------------------------
# Command functions
# -----------------------------

def _resolve_project_dir(project_name: str) -> Path:
    """Resolve project directory from project name."""
    base = _functionmap_root(_home_claude_dir())
    project_dir = base / project_name
    if not project_dir.exists():
        print(f"[functionmap] ERROR: Project '{project_name}' not found at {project_dir}", file=sys.stderr)
        raise SystemExit(2)
    return project_dir


def snapshot_prev(project_name: str) -> int:
    """Copy _functions.json to _functions.prev.json for later diffing."""
    project_dir = _resolve_project_dir(project_name)
    src = project_dir / "_functions.json"
    dst = project_dir / "_functions.prev.json"
    if not src.exists():
        print(f"[functionmap:snapshot] No _functions.json found for {project_name}")
        return 1
    dst.write_bytes(src.read_bytes())
    funcs = json.loads(_read_text(src))
    print(f"[functionmap:snapshot] Saved _functions.prev.json ({len(funcs)} functions)")
    return 0


def diff_report(project_name: str) -> int:
    """Compare _functions.prev.json with _functions.json and print delta."""
    project_dir = _resolve_project_dir(project_name)
    prev_path = project_dir / "_functions.prev.json"
    curr_path = project_dir / "_functions.json"

    if not prev_path.exists():
        print("[functionmap:diff] First map for this project -- no diff available.")
        return 0
    if not curr_path.exists():
        print("[functionmap:diff] No current _functions.json found.")
        return 1

    prev_funcs = json.loads(_read_text(prev_path))
    curr_funcs = json.loads(_read_text(curr_path))

    # B3 fix: use file::name::line_start as key to avoid collisions
    prev = {f"{f.get('file', '')}::{f.get('name', '')}::{f.get('line_start', 0)}": f for f in prev_funcs}
    curr = {f"{f.get('file', '')}::{f.get('name', '')}::{f.get('line_start', 0)}": f for f in curr_funcs}

    added = set(curr.keys()) - set(prev.keys())
    removed = set(prev.keys()) - set(curr.keys())

    # Signature changes: same key but different params or return type
    changed = []
    for key in set(curr.keys()) & set(prev.keys()):
        if (curr[key].get('params') != prev[key].get('params') or
                curr[key].get('return_type') != prev[key].get('return_type')):
            changed.append(key)

    print(f"[functionmap:diff] Diff: +{len(added)} new, -{len(removed)} removed, ~{len(changed)} modified")
    if added:
        print("  New (first 10):")
        for k in sorted(added)[:10]:
            print(f"    + {k}")
    if removed:
        print("  Removed (first 10):")
        for k in sorted(removed)[:10]:
            print(f"    - {k}")
    if changed:
        print("  Modified (first 10):")
        for k in sorted(changed)[:10]:
            print(f"    ~ {k}")

    # Cleanup snapshot
    prev_path.unlink()
    print("[functionmap:diff] Snapshot cleaned up.")
    return 0


def analyze_functions(project_name: str) -> int:
    """Print namespace/directory/class/language distribution."""
    from collections import Counter

    project_dir = _resolve_project_dir(project_name)
    funcs_path = project_dir / "_functions.json"
    if not funcs_path.exists():
        print(f"[functionmap:analyze] No _functions.json for {project_name}")
        return 1

    funcs = json.loads(_read_text(funcs_path))
    print(f"Project: {project_name}")
    print(f"Total functions: {len(funcs)}")

    # Namespace distribution
    ns_counts = Counter(f.get('namespace') or '(none)' for f in funcs)
    print(f"\nNamespaces ({len(ns_counts)}):")
    for ns, count in ns_counts.most_common(30):
        print(f"  {ns}: {count}")

    # Directory distribution
    dir_counts = Counter('/'.join(f['file'].replace('\\', '/').split('/')[:2]) for f in funcs)
    print(f"\nTop directories ({len(dir_counts)}):")
    for d, count in dir_counts.most_common(40):
        print(f"  {d}: {count}")

    # Class distribution
    cls_counts = Counter(f.get('class_name') or '(standalone)' for f in funcs)
    cls_named = len([c for c in cls_counts if c != '(standalone)'])
    print(f"\nTop classes ({cls_named}):")
    for cls, count in cls_counts.most_common(20):
        print(f"  {cls}: {count}")

    # Language distribution
    lang_counts = Counter(f.get('language', 'unknown') for f in funcs)
    print(f"\nLanguages: {dict(lang_counts)}")
    return 0


def preview_taxonomy(project_name: str) -> int:
    """Dry-run categorization and print coverage stats."""
    from collections import Counter

    project_dir = _resolve_project_dir(project_name)
    funcs_path = project_dir / "_functions.json"
    taxonomy_path = project_dir / "_taxonomy.json"

    if not funcs_path.exists():
        print(f"[functionmap:preview] No _functions.json for {project_name}")
        return 1
    if not taxonomy_path.exists():
        print(f"[functionmap:preview] No _taxonomy.json for {project_name}")
        return 1

    # Import categorize module
    tools_dir = _home_claude_dir() / "tools" / "functionmap"
    sys.path.insert(0, str(tools_dir))
    try:
        from categorize import load_taxonomy, categorize_function, is_third_party
    finally:
        sys.path.pop(0)

    taxonomy = load_taxonomy(project_dir)
    funcs = json.loads(_read_text(funcs_path))

    cats = Counter()
    third_party = 0
    for fn in funcs:
        if is_third_party(fn, taxonomy):
            third_party += 1
            continue
        top, sub = categorize_function(fn, taxonomy)
        cats[top] += 1

    first_party = len(funcs) - third_party
    print(f"Third-party excluded: {third_party}")
    print(f"Categories ({len(cats)}):")
    for cat, count in cats.most_common():
        pct = count * 100 // first_party if first_party > 0 else 0
        print(f"  {cat}: {count} ({pct}%)")
    return 0


def update_registry(project_name: str, meta_path: Optional[Path] = None) -> int:
    """Update _registry.json with file locking."""
    base = _functionmap_root(_home_claude_dir())
    registry_path = base / "_registry.json"
    lock_path = base / "_registry.lock"

    if meta_path is None:
        meta_path = base / project_name / "_meta.json"

    if not meta_path.exists():
        print(f"[functionmap:registry] No _meta.json for {project_name}")
        return 1

    # Acquire lock (retry up to 30s)
    locked = False
    for _attempt in range(60):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            locked = True
            break
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > 60:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            time.sleep(0.5)

    if not locked:
        print("[functionmap:registry] WARNING: Could not acquire lock after 30s, writing anyway")

    try:
        registry = {}
        if registry_path.exists():
            registry = json.loads(_read_text(registry_path) or '{}')

        meta = json.loads(_read_text(meta_path))
        entry = {
            'root_path': _posix_path(Path(meta.get('root_path', ''))),
            'generated_at': _now_iso(),
            'function_count': meta.get('function_count', 0),
        }

        # Preserve extra fields from existing entry
        existing = registry.get(project_name, {})
        for key in ('total_extracted', 'third_party_excluded', 'sub_projects'):
            if key in existing:
                entry[key] = existing[key]

        registry[project_name] = entry
        _write_text(registry_path, json.dumps(registry, indent=2))
        print(f"[functionmap:registry] Updated: {project_name}")
    finally:
        if locked:
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    return 0


def verify_functions(project_name: str) -> int:
    """Check that documented functions exist at their recorded locations."""
    base = _functionmap_root(_home_claude_dir())
    registry_path = base / "_registry.json"

    if not registry_path.exists():
        print("[functionmap:verify] No registry found; skipping.")
        return 0

    registry = json.loads(_read_text(registry_path) or '{}')
    meta = registry.get(project_name)
    if not meta:
        print(f"[functionmap:verify] Project '{project_name}' not in registry")
        return 1

    root = Path(meta.get('root_path', ''))
    functions_path = base / project_name / "_functions.json"

    if not functions_path.exists():
        print(f"[functionmap:verify] Missing {functions_path}")
        return 1

    functions = json.loads(_read_text(functions_path) or '[]')

    # Group by file
    by_file: Dict[str, list] = {}
    for f in functions:
        by_file.setdefault(f.get('file', ''), []).append(f)

    mismatches = []
    checked = 0
    files_missing = 0

    for rel_path, items in by_file.items():
        if not rel_path:
            continue

        file_path = root / rel_path

        if not file_path.exists():
            files_missing += 1
            for item in items[:3]:
                mismatches.append((rel_path, item.get('line_start', 0), item.get('name', '<unknown>'), 'FILE_MISSING'))
            continue

        try:
            lines = file_path.read_text(encoding='utf-8', errors='ignore').splitlines()
        except Exception:
            for item in items[:3]:
                mismatches.append((rel_path, item.get('line_start', 0), item.get('name', '<unknown>'), 'READ_FAIL'))
            continue

        for item in items:
            checked += 1
            line_num = max(1, int(item.get('line_start', 1)))

            start = max(0, line_num - 4)
            end = min(len(lines), line_num + 4)
            window = '\n'.join(lines[start:end])

            short_name = item.get('short_name', '') or ''
            language = item.get('language', '')

            found = False
            if short_name:
                if language == 'php':
                    pattern = r'\bfunction\s+' + re.escape(short_name) + r'\s*\('
                    found = bool(re.search(pattern, window))
                else:
                    patterns = [
                        r'\bfunction\*?\s+' + re.escape(short_name) + r'\s*\(',
                        re.escape(short_name) + r'\s*=\s*(?:async\s+)?function',
                        re.escape(short_name) + r'\s*=\s*\(',
                        r'\b' + re.escape(short_name) + r'\s*\(',
                        r'\.prototype\.' + re.escape(short_name) + r'\s*=',
                        r'\$\.fn\.' + re.escape(short_name) + r'\s*=',
                        r'(?:module\.)?exports\.' + re.escape(short_name) + r'\s*=',
                        r'\b(?:get|set)\s+' + re.escape(short_name) + r'\s*\(',
                    ]
                    found = any(re.search(p, window) for p in patterns)

            if not found:
                mismatches.append((rel_path, line_num, item.get('name', '<unknown>'), 'SIG_NOT_FOUND_NEAR_LINE'))

    print(f"[functionmap:verify] Project: {project_name}")
    print(f"[functionmap:verify] Root: {root}")
    print(f"[functionmap:verify] Functions checked: {checked}")
    print(f"[functionmap:verify] Files missing/unreadable: {files_missing}")
    print(f"[functionmap:verify] Signature mismatches: {len(mismatches)}")

    if mismatches:
        print("[functionmap:verify] First 30 mismatches:")
        for r in mismatches[:30]:
            print(f"  - {r[0]}:{r[1]} :: {r[2]} ({r[3]})")
        print("[functionmap:verify] NOTE: Systematic mismatches often mean the parser missed a pattern.")
    else:
        print("[functionmap:verify] All functions verified successfully!")

    return 0


def generate_hashes(project_name: str) -> int:
    """Generate _hashes.json from existing _meta.json and _functions.json without re-extracting."""
    project_dir = _resolve_project_dir(project_name)
    meta_path = project_dir / "_meta.json"
    funcs_path = project_dir / "_functions.json"

    if not meta_path.exists():
        print(f"[functionmap:hashes] No _meta.json for {project_name}")
        return 1
    if not funcs_path.exists():
        print(f"[functionmap:hashes] No _functions.json for {project_name}")
        return 1

    meta = json.loads(_read_text(meta_path))
    scan_root = Path(meta.get("root_path", ""))
    if not scan_root.exists():
        print(f"[functionmap:hashes] Root path does not exist: {scan_root}")
        return 1

    ignore_dirs = meta.get("ignore_dirs", [])
    include_vendor = meta.get("include_vendor", False)

    # Scan source files (just for hashing, no extraction)
    scanned_files = list(iter_source_files(scan_root, include_vendor, ignore_dirs))
    funcs_json_text = _read_text(funcs_path)

    write_hashes(project_dir, scan_root, scanned_files, funcs_json_text, project_name)
    print(f"[functionmap:hashes] Done. {project_name} is now ready for incremental updates.")
    return 0


def write_hashes(project_dir: Path, scan_root: Path, scanned_files: List[Path],
                 funcs_json_text: str, project_name: str) -> None:
    """Generate _hashes.json with file-level hashes for incremental updates."""
    # Count functions per file from the JSON text
    funcs_list = json.loads(funcs_json_text)
    funcs_by_file: Dict[str, int] = {}
    for f in funcs_list:
        rel = f.get('file', '')
        funcs_by_file[rel] = funcs_by_file.get(rel, 0) + 1

    files_dict: Dict[str, dict] = {}
    for p in scanned_files:
        rel = _posix_rel(p, scan_root)
        try:
            h = _file_hash(p)
            size = p.stat().st_size
        except Exception:
            continue
        files_dict[rel] = {
            "hash": h,
            "size": size,
            "function_count": funcs_by_file.get(rel, 0),
        }

    # Taxonomy hash
    taxonomy_path = project_dir / "_taxonomy.json"
    taxonomy_hash = None
    if taxonomy_path.exists():
        taxonomy_hash = _content_hash(_read_text(taxonomy_path))

    # Extractor hash -- detect when functionmap.py itself changes
    extractor_path = Path(__file__)
    extractor_hash = _file_hash(extractor_path) if extractor_path.exists() else ""

    hashes = {
        "version": 1,
        "generated_at": _now_iso(),
        "project": project_name,
        "root_path": _posix_path(scan_root),
        "key_format": "file::name::line_start",
        "taxonomy_hash": taxonomy_hash,
        "extractor_hash": extractor_hash,
        "functions_hash": _content_hash(funcs_json_text),
        "files": files_dict,
    }

    _write_text(project_dir / "_hashes.json", json.dumps(hashes, indent=2))
    print(f"[functionmap] Hashes: {len(files_dict)} files hashed -> _hashes.json")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="functionmap", add_help=True)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("target", help="Either a directory path OR a project name.")
    ap.add_argument("mode_or_path", nargs="?", default="", help="Either 'project' (scan CWD), or an explicit path.")
    ap.add_argument("--include-vendor", action="store_true", help="Include vendor/node_modules when scanning (default: ignored).")
    ap.add_argument("--ignore-dir", action="append", default=[], help="Additional directory names to ignore (repeatable).")
    ap.add_argument("--subproject", "--sub-project", action="append", default=[], dest="subprojects",
                     help="Path to a sub-project directory (repeatable). Each gets its own map under the parent.")
    ap.add_argument("--out-root", default="", help="Override output root (default: ~/.claude/functionmap).")
    ap.add_argument("--snapshot", action="store_true", help="Save _functions.json snapshot for diffing.")
    ap.add_argument("--diff", action="store_true", help="Compare previous and current functions.")
    ap.add_argument("--analyze", action="store_true", help="Print function distribution analysis.")
    ap.add_argument("--preview-taxonomy", action="store_true", help="Preview taxonomy coverage.")
    ap.add_argument("--update-registry", action="store_true", help="Update global registry.")
    ap.add_argument("--verify", action="store_true", help="Verify functions exist at recorded locations.")
    ap.add_argument("--generate-hashes", action="store_true", help="Generate _hashes.json from existing data (no re-extraction).")
    ap.add_argument("--subproject-only", action="store_true", dest="subproject_only",
                     help="Only process --subproject paths; skip parent project extraction entirely. Parent must already be mapped.")
    args = ap.parse_args(argv)

    # Command dispatch (if any command flag is set, run that command and exit)
    if args.snapshot:
        return snapshot_prev(args.target)
    if args.diff:
        return diff_report(args.target)
    if args.analyze:
        return analyze_functions(args.target)
    if args.preview_taxonomy:
        return preview_taxonomy(args.target)
    if args.update_registry:
        return update_registry(args.target)
    if args.verify:
        return verify_functions(args.target)
    if args.generate_hashes:
        return generate_hashes(args.target)

    claude_dir = _home_claude_dir()
    out_root = Path(args.out_root).expanduser() if args.out_root else _functionmap_root(claude_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    target = args.target
    mode = (args.mode_or_path or "").strip()

    scan_root: Optional[Path] = None
    project_name: Optional[str] = None

    # Parse arguments
    tpath = Path(target).expanduser()
    if tpath.exists() and tpath.is_dir():
        scan_root = tpath.resolve()
        project_name = _slugify(tpath.name)
    else:
        if mode.lower() == "project" or mode == "":
            project_name = _slugify(target)
            scan_root = Path.cwd().resolve()
        else:
            mpath = Path(mode).expanduser()
            if mpath.exists() and mpath.is_dir():
                project_name = _slugify(target)
                scan_root = mpath.resolve()

    if not scan_root or not scan_root.exists():
        print(f"[functionmap] ERROR: could not resolve scan root", file=sys.stderr)
        return 2

    assert project_name is not None
    project_dir = out_root / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # --subproject-only: skip parent extraction, process only subproject(s)
    if args.subproject_only:
        if not args.subprojects:
            print("[functionmap] ERROR: --subproject-only requires at least one --subproject path", file=sys.stderr)
            return 2

        # Load existing parent _meta.json (parent must already be mapped)
        parent_meta_path = project_dir / "_meta.json"
        if not parent_meta_path.exists():
            print(f"[functionmap] ERROR: Parent project not mapped yet (no _meta.json). Run /functionmap first.", file=sys.stderr)
            return 2

        existing_meta = json.loads(_read_text(parent_meta_path))
        existing_sub_projects = existing_meta.get("sub_projects", {})

        sub_projects_meta: Dict[str, dict] = {}
        for sp_path_str in args.subprojects:
            sp_root = Path(sp_path_str).expanduser().resolve()
            if not sp_root.exists() or not sp_root.is_dir():
                print(f"[functionmap] WARNING: Sub-project path not found: {sp_path_str}", file=sys.stderr)
                continue

            sp_name = _slugify(sp_root.name)
            sp_dir = project_dir / sp_name
            sp_dir.mkdir(parents=True, exist_ok=True)

            sp_files: List[Path] = list(iter_source_files(sp_root, args.include_vendor, args.ignore_dir))
            sp_funcs: List[FunctionDef] = []
            for p in sp_files:
                ext = p.suffix.lower()
                lang = SUPPORTED_EXTS.get(ext)
                if not lang:
                    continue
                rel = _posix_rel(p, sp_root)
                try:
                    content = _read_text(p)
                except Exception:
                    continue
                raw_funcs: List[Tuple[Dict, int, int]] = []
                if lang == "php":
                    raw_funcs = scan_php(content)
                elif lang in {"js", "ts"}:
                    raw_funcs = scan_js_ts(content, lang)
                for info, line_start, line_end in raw_funcs:
                    doc = info.get("doc") or ""
                    summary = _extract_doc_summary(doc)
                    sp_funcs.append(FunctionDef(
                        language=info["language"],
                        kind=info["kind"],
                        name=info["name"],
                        short_name=info["short_name"],
                        namespace=info.get("namespace"),
                        class_name=info.get("class_name"),
                        visibility=info.get("visibility"),
                        is_static=bool(info.get("is_static")),
                        is_async=bool(info.get("is_async")),
                        params=info.get("params") or "",
                        return_type=info.get("return_type") or "unknown",
                        file=rel,
                        line_start=line_start,
                        line_end=line_end,
                        summary=summary,
                        doc=doc,
                        attributes=info.get("attributes") or [],
                    ))

            sp_funcs_json = json.dumps([asdict(f) for f in sp_funcs], indent=2)
            _write_text(sp_dir / "_functions.json", sp_funcs_json)

            sp_meta = {
                "project": sp_name,
                "root_path": _posix_path(sp_root),
                "generated_at": _now_iso(),
                "file_count": len(sp_files),
                "function_count": len(sp_funcs),
                "include_vendor": args.include_vendor,
                "ignore_dirs": args.ignore_dir,
            }
            _write_text(sp_dir / "_meta.json", json.dumps(sp_meta, indent=2, sort_keys=True))
            write_hashes(sp_dir, sp_root, sp_files, sp_funcs_json, sp_name)

            sub_projects_meta[sp_name] = {
                "root_path": _posix_path(sp_root),
                "ignore_dirs": args.ignore_dir,
                "include_vendor": args.include_vendor,
            }

            print(f"[functionmap] Sub-project: {sp_name}")
            print(f"[functionmap]   Scanned:   {sp_root}")
            print(f"[functionmap]   Files:     {len(sp_files)}")
            print(f"[functionmap]   Functions: {len(sp_funcs)}")
            print(f"[functionmap]   Output:    {sp_dir / '_functions.json'}")

        # Merge new sub-projects into existing parent _meta.json (preserving other fields)
        existing_sub_projects.update(sub_projects_meta)
        existing_meta["sub_projects"] = existing_sub_projects
        _write_text(parent_meta_path, json.dumps(existing_meta, indent=2, sort_keys=True))

        print(f"[functionmap] Updated parent _meta.json with sub-projects: {', '.join(sub_projects_meta.keys())}")
        print(f"[functionmap] Next: Claude will design taxonomy and categorize the sub-project(s)")
        return 0

    # Scan files
    scanned_files: List[Path] = list(iter_source_files(scan_root, args.include_vendor, args.ignore_dir))

    funcs: List[FunctionDef] = []
    for p in scanned_files:
        ext = p.suffix.lower()
        lang = SUPPORTED_EXTS.get(ext)
        if not lang:
            continue
        rel = _posix_rel(p, scan_root)
        try:
            content = _read_text(p)
        except Exception:
            continue

        raw_funcs: List[Tuple[Dict, int, int]] = []
        if lang == "php":
            raw_funcs = scan_php(content)
        elif lang in {"js", "ts"}:
            raw_funcs = scan_js_ts(content, lang)

        for info, line_start, line_end in raw_funcs:
            doc = info.get("doc") or ""
            summary = _extract_doc_summary(doc)

            funcs.append(FunctionDef(
                language=info["language"],
                kind=info["kind"],
                name=info["name"],
                short_name=info["short_name"],
                namespace=info.get("namespace"),
                class_name=info.get("class_name"),
                visibility=info.get("visibility"),
                is_static=bool(info.get("is_static")),
                is_async=bool(info.get("is_async")),
                params=info.get("params") or "",
                return_type=info.get("return_type") or "unknown",
                file=rel,
                line_start=line_start,
                line_end=line_end,
                summary=summary,
                doc=doc,
                attributes=info.get("attributes") or [],
            ))

    # Write raw function data (NO CATEGORIZATION)
    funcs_json_text = json.dumps([asdict(f) for f in funcs], indent=2)
    _write_text(project_dir / "_functions.json", funcs_json_text)

    # Process sub-projects
    sub_projects_meta: Dict[str, dict] = {}
    for sp_path_str in args.subprojects:
        sp_root = Path(sp_path_str).expanduser().resolve()
        if not sp_root.exists() or not sp_root.is_dir():
            print(f"[functionmap] WARNING: Sub-project path not found: {sp_path_str}", file=sys.stderr)
            continue

        sp_name = _slugify(sp_root.name)
        sp_dir = project_dir / sp_name
        sp_dir.mkdir(parents=True, exist_ok=True)

        sp_files: List[Path] = list(iter_source_files(sp_root, args.include_vendor, args.ignore_dir))
        sp_funcs: List[FunctionDef] = []
        for p in sp_files:
            ext = p.suffix.lower()
            lang = SUPPORTED_EXTS.get(ext)
            if not lang:
                continue
            rel = _posix_rel(p, sp_root)
            try:
                content = _read_text(p)
            except Exception:
                continue
            raw_funcs: List[Tuple[Dict, int, int]] = []
            if lang == "php":
                raw_funcs = scan_php(content)
            elif lang in {"js", "ts"}:
                raw_funcs = scan_js_ts(content, lang)
            for info, line_start, line_end in raw_funcs:
                doc = info.get("doc") or ""
                summary = _extract_doc_summary(doc)
                sp_funcs.append(FunctionDef(
                    language=info["language"],
                    kind=info["kind"],
                    name=info["name"],
                    short_name=info["short_name"],
                    namespace=info.get("namespace"),
                    class_name=info.get("class_name"),
                    visibility=info.get("visibility"),
                    is_static=bool(info.get("is_static")),
                    is_async=bool(info.get("is_async")),
                    params=info.get("params") or "",
                    return_type=info.get("return_type") or "unknown",
                    file=rel,
                    line_start=line_start,
                    line_end=line_end,
                    summary=summary,
                    doc=doc,
                    attributes=info.get("attributes") or [],
                ))

        sp_funcs_json = json.dumps([asdict(f) for f in sp_funcs], indent=2)
        _write_text(sp_dir / "_functions.json", sp_funcs_json)

        sp_meta = {
            "project": sp_name,
            "root_path": _posix_path(sp_root),
            "generated_at": _now_iso(),
            "file_count": len(sp_files),
            "function_count": len(sp_funcs),
            "include_vendor": args.include_vendor,
            "ignore_dirs": args.ignore_dir,
        }
        _write_text(sp_dir / "_meta.json", json.dumps(sp_meta, indent=2, sort_keys=True))
        write_hashes(sp_dir, sp_root, sp_files, sp_funcs_json, sp_name)

        sub_projects_meta[sp_name] = {
            "root_path": _posix_path(sp_root),
            "ignore_dirs": args.ignore_dir,
            "include_vendor": args.include_vendor,
        }

        print(f"[functionmap] Sub-project: {sp_name}")
        print(f"[functionmap]   Scanned:   {sp_root}")
        print(f"[functionmap]   Files:     {len(sp_files)}")
        print(f"[functionmap]   Functions: {len(sp_funcs)}")
        print(f"[functionmap]   Output:    {sp_dir / '_functions.json'}")

    # Write metadata
    meta_json: dict = {
        "project": project_name,
        "root_path": _posix_path(scan_root),
        "generated_at": _now_iso(),
        "file_count": len(scanned_files),
        "function_count": len(funcs),
        "include_vendor": args.include_vendor,
        "ignore_dirs": args.ignore_dir,
    }
    if sub_projects_meta:
        meta_json["sub_projects"] = sub_projects_meta
    _write_text(project_dir / "_meta.json", json.dumps(meta_json, indent=2, sort_keys=True))

    # Write file hashes for incremental updates
    write_hashes(project_dir, scan_root, scanned_files, funcs_json_text, project_name)

    # Update global registry
    update_registry(project_name, project_dir / "_meta.json")

    print(f"[functionmap] Project:   {project_name}")
    print(f"[functionmap] Scanned:   {scan_root}")
    print(f"[functionmap] Files:     {len(scanned_files)}")
    print(f"[functionmap] Functions: {len(funcs)}")
    if sub_projects_meta:
        print(f"[functionmap] Sub-projects: {', '.join(sub_projects_meta.keys())}")
    print(f"[functionmap] Output:    {project_dir / '_functions.json'}")
    print(f"[functionmap] Next:      Claude will categorize and create function map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
