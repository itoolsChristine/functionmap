"""Functionmap session-start hook: detect mapped project from working directory.

Scans ~/.claude/functionmap/*/_meta.json for a project whose root_path
matches the current working directory. Outputs a brief context message
telling Claude which project is mapped and what tools are available.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _get_dependencies(project_dir: Path) -> list[str]:
    """Parse libraries.md for cross-project references (../X.md links)."""
    lib_path = project_dir / "libraries.md"
    if not lib_path.exists():
        return []
    try:
        content = lib_path.read_text(encoding="utf-8")
        return sorted(set(re.findall(r'\.\./([a-zA-Z0-9_-]+)\.md', content)))
    except (OSError, UnicodeDecodeError):
        return []


def detect_project(cwd: str) -> str:
    """Check if cwd (or a parent) matches a mapped project's root_path."""
    functionmap_dir = Path.home() / ".claude" / "functionmap"
    if not functionmap_dir.exists():
        return ""

    cwd_path = Path(cwd).resolve()
    matches: list[dict] = []

    for meta_file in functionmap_dir.glob("*/_meta.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            root_path = Path(meta.get("root_path", "")).resolve()
            if cwd_path == root_path or root_path in cwd_path.parents:
                project_dir = meta_file.parent
                matches.append({
                    "project":        meta.get("project", project_dir.name),
                    "root_path":      str(root_path),
                    "function_count": meta.get("function_count", 0),
                    "dependencies":   _get_dependencies(project_dir),
                })
        except (json.JSONDecodeError, OSError):
            continue

    if not matches:
        return ""

    best = max(matches, key=lambda m: len(m["root_path"]))
    project = best["project"]
    fn_count = best["function_count"]
    deps = best["dependencies"]

    lines = [
        f"functionmap: Project '{project}' has a function map ({fn_count} functions).",
        "Use functionmap_search/categories/detail before implementing new code.",
    ]
    if deps:
        lines.append(f"Also search dependencies: {', '.join(deps)}")

    return "\n".join(lines)


if __name__ == "__main__":
    try:
        input_data = json.load(sys.stdin)
        cwd = input_data.get("cwd", "")
        if not cwd:
            sys.exit(0)

        result = detect_project(cwd)
        if result:
            print(result)
    except Exception:
        pass  # Never crash the hook
