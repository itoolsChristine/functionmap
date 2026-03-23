"""Lazy per-project data loading with mtime-based freshness checks.

Loads _functions.json, _taxonomy.json, _meta.json, and _callgraph.json on demand.
Builds name index and category map for fast lookups.
Discovers third-party libraries and parses dependency cross-references.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

FUNCTIONMAP_DIR = Path.home() / ".claude" / "functionmap"

# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_registry: Optional[dict] = None
_registry_mtime: float = 0.0
_projects: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def get_registry() -> dict:
    """Load or return cached registry. Reloads if file changed on disk."""
    global _registry, _registry_mtime

    registry_path = FUNCTIONMAP_DIR / "_registry.json"
    if not registry_path.exists():
        _registry = {}
        return _registry

    current_mtime = registry_path.stat().st_mtime
    if _registry is not None and current_mtime <= _registry_mtime:
        return _registry

    with open(registry_path, "r", encoding="utf-8") as f:
        _registry = json.load(f)
    _registry_mtime = current_mtime
    return _registry


# ---------------------------------------------------------------------------
# Per-project loading
# ---------------------------------------------------------------------------

def get_project(name: str) -> Optional[dict]:
    """Load or return cached project data. Reloads if _functions.json changed.

    Works for main projects, sub-projects ("squimsh/output"), and
    third-party libraries ("third-party/jquery/2.1.4").

    Returns dict with keys: functions, taxonomy, meta, name_index, category_map, mtime.
    Returns None if project directory or _functions.json doesn't exist.
    """
    project_dir = _resolve_project_dir(name)
    if project_dir is None:
        return None

    functions_path = project_dir / "_functions.json"
    if not functions_path.exists():
        return None

    current_mtime = functions_path.stat().st_mtime

    if name in _projects and _projects[name]["mtime"] >= current_mtime:
        return _projects[name]

    # Load core data
    with open(functions_path, "r", encoding="utf-8") as f:
        functions = json.load(f)

    taxonomy = {}
    taxonomy_path = project_dir / "_taxonomy.json"
    if taxonomy_path.exists():
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            taxonomy = json.load(f)

    meta = {}
    meta_path = project_dir / "_meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    # Build name index: short_name.lower() -> list of indices
    name_index: dict[str, list[int]] = {}
    for i, fn in enumerate(functions):
        key = fn.get("short_name", "").lower()
        if key:
            name_index.setdefault(key, []).append(i)

    # Build category map: category_name -> list of indices
    category_map = _build_category_map(project_dir, functions)

    project_data = {
        "functions":    functions,
        "taxonomy":     taxonomy,
        "meta":         meta,
        "name_index":   name_index,
        "category_map": category_map,
        "mtime":        current_mtime,
    }
    _projects[name] = project_data
    return project_data


def get_callgraph(name: str) -> Optional[dict]:
    """Load call graph for a project. Loaded on demand (can be large)."""
    project_dir = _resolve_project_dir(name)
    if project_dir is None:
        return None

    callgraph_path = project_dir / "_callgraph.json"
    if not callgraph_path.exists():
        return None

    with open(callgraph_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_dependencies(project_name: str) -> list[str]:
    """Parse libraries.md for cross-project references.

    Looks for ../X.md links and returns the list of dependency project names.
    Returns empty list if no libraries.md or no cross-references found.
    """
    project_dir = _resolve_project_dir(project_name)
    if project_dir is None:
        return []

    lib_path = project_dir / "libraries.md"
    if not lib_path.exists():
        return []

    try:
        content = lib_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    # Extract ../projectname.md references
    deps = re.findall(r'\.\./([a-zA-Z0-9_-]+)\.md', content)
    return sorted(set(deps))


# ---------------------------------------------------------------------------
# Project listing (main + sub-projects + third-party)
# ---------------------------------------------------------------------------

def list_projects() -> list[dict]:
    """List all projects, sub-projects, and third-party libraries with metadata.

    Each entry includes:
    - name, root_path, function_count, generated_at
    - type: "project", "sub-project", or "third-party"
    - dependencies: list of dependency project names (main projects only)
    - library, version, used_by: third-party only
    - parent: sub-projects only
    """
    registry = get_registry()
    results = []

    # Main projects from registry
    for name, info in sorted(registry.items()):
        entry = {
            "name":           name,
            "type":           "project",
            "root_path":      info.get("root_path", ""),
            "function_count": info.get("function_count", 0),
            "generated_at":   info.get("generated_at", ""),
            "dependencies":   get_dependencies(name),
        }
        results.append(entry)

    # Sub-projects from _meta.json
    for name in list(registry.keys()):
        project_dir = _resolve_project_dir(name)
        if project_dir is None:
            continue
        meta_path = project_dir / "_meta.json"
        if not meta_path.exists():
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            for sub_name in meta.get("sub_projects", {}):
                sub_dir = project_dir / sub_name
                if sub_dir.exists() and (sub_dir / "_functions.json").exists():
                    sub_meta_path = sub_dir / "_meta.json"
                    sub_count = 0
                    if sub_meta_path.exists():
                        with open(sub_meta_path, "r", encoding="utf-8") as sf:
                            sub_meta = json.load(sf)
                            sub_count = sub_meta.get("function_count", 0)
                    results.append({
                        "name":           f"{name}/{sub_name}",
                        "type":           "sub-project",
                        "root_path":      meta["sub_projects"][sub_name].get("root_path", ""),
                        "function_count": sub_count,
                        "generated_at":   "",
                        "parent":         name,
                    })
        except (json.JSONDecodeError, KeyError):
            pass

    # Third-party libraries
    results.extend(_discover_third_party())

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_project_dir(name: str) -> Optional[Path]:
    """Resolve a project name to its directory under FUNCTIONMAP_DIR.

    Handles:
    - Main projects: "zendb" -> FUNCTIONMAP_DIR/zendb/
    - Sub-projects: "squimsh/output" -> FUNCTIONMAP_DIR/squimsh/output/
    - Third-party: "third-party/jquery/2.1.4" -> FUNCTIONMAP_DIR/third-party/jquery/2.1.4/
    """
    project_dir = FUNCTIONMAP_DIR / name.replace("/", os.sep)
    if project_dir.exists() and project_dir.is_dir():
        return project_dir
    return None


def _discover_third_party() -> list[dict]:
    """Scan third-party/_index.json and return library entries for list_projects()."""
    index_path = FUNCTIONMAP_DIR / "third-party" / "_index.json"
    if not index_path.exists():
        return []

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    results = []
    libraries = index_data.get("libraries", {})
    for lib_name, lib_info in sorted(libraries.items()):
        for version, ver_info in lib_info.get("versions", {}).items():
            # Only include versions that have actual function data
            tp_dir = FUNCTIONMAP_DIR / "third-party" / lib_name / version
            if not (tp_dir / "_functions.json").exists():
                continue

            results.append({
                "name":           f"third-party/{lib_name}/{version}",
                "type":           "third-party",
                "library":        lib_name,
                "version":        version,
                "function_count": ver_info.get("function_count", 0),
                "generated_at":   ver_info.get("mapped_at", ""),
                "used_by":        ver_info.get("used_by", []),
                "source_project": ver_info.get("source_project", ""),
            })

    return results


def get_project_overview(project_name: str) -> str:
    """Extract the overview section from a project's index markdown file.

    Returns the header content (title, function count, description) before the
    first category listing. Empty string if file doesn't exist.
    """
    # Try {project}.md in FUNCTIONMAP_DIR (handles main projects)
    md_file = FUNCTIONMAP_DIR / f"{project_name}.md"
    if not md_file.exists():
        # For sub-projects/third-party, check inside the project dir
        project_dir = _resolve_project_dir(project_name)
        if project_dir:
            # Look for any index-like .md file (e.g., jquery-2.1.4.md)
            candidates = [f for f in project_dir.glob("*.md")
                          if not f.name.startswith("_") and f.name != "libraries.md"
                          and "--" not in f.name]
            if not candidates:
                return ""
            # If there's only one non-category file, that's the index
            # Otherwise skip (ambiguous)
            if len(candidates) > 5:
                return ""
            md_file = candidates[0]
        else:
            return ""

    try:
        content = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    # Extract everything before the first "---" divider
    parts = content.split("\n---\n", 1)
    if parts:
        return parts[0].strip()
    return ""


def get_dependency_narrative(project_name: str) -> str:
    """Read the full libraries.md content for a project.

    Returns the dependency narrative text, or empty string if not found.
    """
    project_dir = _resolve_project_dir(project_name)
    if project_dir is None:
        return ""

    lib_path = project_dir / "libraries.md"
    if not lib_path.exists():
        return ""

    try:
        return lib_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def get_category_patterns(project_name: str, category_name: str) -> str:
    """Extract the 'Common Patterns' section from a category markdown file.

    Returns the patterns text (code examples, usage notes), or empty string
    if the category file doesn't exist or has no patterns section.
    """
    project_dir = _resolve_project_dir(project_name)
    if project_dir is None:
        return ""

    md_file = project_dir / f"{category_name}.md"
    if not md_file.exists():
        return ""

    try:
        content = md_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""

    # Extract everything between "## Common Patterns" and the next "---" divider
    pattern_match = re.search(
        r'^## Common Patterns\s*\n(.*?)(?=^---\s*$)',
        content,
        re.MULTILINE | re.DOTALL,
    )
    if pattern_match:
        return pattern_match.group(1).strip()

    return ""


def _build_category_map(project_dir: Path, functions: list[dict]) -> dict[str, list[int]]:
    """Build category -> function indices map by scanning category .md files.

    Category files are machine-generated with consistent format:
    - Filename: category--subcategory.md
    - Function entries start with ## heading matching short_name
    """
    category_map: dict[str, list[int]] = {}

    # Build reverse lookup: short_name -> list of indices (for matching)
    name_to_indices: dict[str, list[int]] = {}
    for i, fn in enumerate(functions):
        sn = fn.get("short_name", "")
        if sn:
            name_to_indices.setdefault(sn, []).append(i)

    # Scan .md files (skip _-prefixed files and libraries.md)
    for md_file in sorted(project_dir.glob("*.md")):
        fname = md_file.name
        if fname.startswith("_") or fname == "libraries.md":
            continue

        category_name = fname.removesuffix(".md")
        matched_indices: list[int] = []

        try:
            content = md_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # Extract function names from ## headings
        for m in re.finditer(r'^## (\w+)', content, re.MULTILINE):
            func_name = m.group(1)
            if func_name in ("Common", "Function"):
                continue  # Skip section headings like "## Common Patterns"
            indices = name_to_indices.get(func_name, [])
            matched_indices.extend(indices)

        if matched_indices:
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for idx in matched_indices:
                if idx not in seen:
                    seen.add(idx)
                    unique.append(idx)
            category_map[category_name] = unique

    return category_map
