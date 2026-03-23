#!/usr/bin/env python3
"""
quickmap.py -- Hash-based incremental function map updater.

Compares file hashes to detect changes since the last full /functionmap run.
Only re-extracts functions from changed/new files, copies unchanged functions
from the previous _functions.json. Then re-runs categorization.

Requires a prior full /functionmap run (needs _hashes.json, _functions.json,
_taxonomy.json, _meta.json).

Usage:
    python quickmap.py --project my-project
    python quickmap.py --project my-project --ignore-dir tests
    python quickmap.py --project my-project --include-vendor
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Import shared utilities and scanners from functionmap.py
sys.path.insert(0, str(Path(__file__).parent))
from functionmap import (
    SUPPORTED_EXTS,
    FunctionDef,
    _content_hash,
    _extract_doc_summary,
    _file_hash,
    _functionmap_root,
    _home_claude_dir,
    _now_iso,
    _posix_path,
    _posix_rel,
    _read_text,
    _write_text,
    iter_source_files,
    resolve_root_path_glob,
    scan_js_ts,
    scan_php,
    update_registry,
    write_hashes,
)

# Import third-party library mapping (optional)
try:
    from thirdparty import (
        group_by_library,
        map_library,
        update_index as tp_update_index,
        get_project_libs,
        detect_new_third_party_files,
    )
    from categorize import is_third_party, load_taxonomy
    _has_thirdparty = True
except ImportError:
    _has_thirdparty = False


def _check_unmapped_third_party(
    project_dir: Path,
    project_name: str,
    functionmap_root: Path,
    force_remap: bool = False,
) -> List[str]:
    """Detect third-party libs in taxonomy that aren't yet mapped to shared location.

    Returns list of newly mapped library keys (e.g., ["fullcalendar/6.1.19"]).
    """
    if not _has_thirdparty:
        return []

    taxonomy_path = project_dir / "_taxonomy.json"
    funcs_path = project_dir / "_functions.json"
    meta_path = project_dir / "_meta.json"

    if not taxonomy_path.exists() or not funcs_path.exists():
        return []

    taxonomy = load_taxonomy(project_dir)
    funcs = json.loads(_read_text(funcs_path))

    source_root = ""
    if meta_path.exists():
        try:
            meta = json.loads(_read_text(meta_path))
            source_root = meta.get("root_path", "")
        except (json.JSONDecodeError, ValueError):
            pass

    third_party_funcs = [fn for fn in funcs if is_third_party(fn, taxonomy)]
    if not third_party_funcs:
        return []

    lib_groups = group_by_library(third_party_funcs, taxonomy, project_root=source_root)

    newly_mapped = []
    for key, group in lib_groups.items():
        if key == "_unresolved":
            continue
        lib_name = group["library"]
        version = group["version"]
        lib_dir = functionmap_root / "third-party" / lib_name / version

        if lib_dir.exists() and not force_remap:
            # Already mapped -- just ensure used_by is updated
            result = map_library(
                lib_name, version, group["functions"],
                project_name, functionmap_root, source_root=source_root,
            )
            continue

        result = map_library(
            lib_name, version, group["functions"],
            project_name, functionmap_root, source_root=source_root,
            force=force_remap,
        )
        if result:
            tp_update_index(functionmap_root, lib_name, version, result, project_name)
            newly_mapped.append(key)

    return newly_mapped


def _extract_functions_from_file(file_path: Path, scan_root: Path) -> List[dict]:
    """Extract functions from a single source file, returning dicts."""
    ext = file_path.suffix.lower()
    lang = SUPPORTED_EXTS.get(ext)
    if not lang:
        return []

    rel = _posix_rel(file_path, scan_root)
    try:
        content = _read_text(file_path)
    except Exception:
        return []

    raw_funcs = []
    if lang == "php":
        raw_funcs = scan_php(content)
    elif lang in {"js", "ts"}:
        raw_funcs = scan_js_ts(content, lang)

    results = []
    for info, line_start, line_end in raw_funcs:
        doc = info.get("doc") or ""
        summary = _extract_doc_summary(doc)
        fd = FunctionDef(
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
        )
        results.append(asdict(fd))
    return results


def _run_categorize(project_name: str) -> bool:
    """Run categorize.py as a subprocess. Returns True on success."""
    categorize_script = Path(__file__).parent / "categorize.py"
    if not categorize_script.exists():
        print(f"[quickmap] ERROR: categorize.py not found at {categorize_script}")
        return False

    result = subprocess.run(
        [sys.executable, str(categorize_script), "--project", project_name],
        capture_output=True,
        text=True,
    )

    if result.stdout:
        # Print categorize output but prefix for clarity
        for line in result.stdout.rstrip().split('\n'):
            print(line)

    if result.returncode != 0:
        print(f"[quickmap] ERROR: categorize.py failed (exit {result.returncode})")
        if result.stderr:
            print(result.stderr)
        return False

    return True


def _extractor_hash() -> str:
    """Hash functionmap.py to detect when extraction logic changes."""
    extractor_path = Path(__file__).parent / "functionmap.py"
    return _file_hash(extractor_path) if extractor_path.exists() else ""


def _process_project(project_dir: Path, project_name: str,
                     extra_ignore_dirs: Sequence[str] = (),
                     force_include_vendor: Optional[bool] = None) -> dict:
    """
    Run incremental update for a single project/sub-project directory.

    Returns a delta summary dict with keys:
        files_scanned, unchanged, changed, new, deleted,
        funcs_before, funcs_after, funcs_new, funcs_removed,
        changed_files (list of detail dicts), taxonomy_changed (bool),
        error (str or None)
    """
    summary = {
        "files_scanned": 0, "unchanged": 0, "changed": 0, "new": 0, "deleted": 0,
        "funcs_before": 0, "funcs_after": 0, "funcs_new": 0, "funcs_removed": 0,
        "changed_files": [], "taxonomy_changed": False, "error": None,
    }

    # Load prerequisite files
    hashes_path = project_dir / "_hashes.json"
    funcs_path = project_dir / "_functions.json"
    meta_path = project_dir / "_meta.json"
    taxonomy_path = project_dir / "_taxonomy.json"

    for required, label in [(hashes_path, "_hashes.json"), (funcs_path, "_functions.json"),
                            (meta_path, "_meta.json")]:
        if not required.exists():
            summary["error"] = f"Missing {label} -- run /functionmap first"
            return summary

    hashes_data = json.loads(_read_text(hashes_path))
    old_funcs = json.loads(_read_text(funcs_path))
    meta = json.loads(_read_text(meta_path))

    root_path = Path(meta.get("root_path", ""))
    if not root_path.exists():
        summary["error"] = f"Root path does not exist: {root_path}"
        return summary

    summary["funcs_before"] = len(old_funcs)

    # Determine scan config from _meta.json, merged with CLI overrides
    ignore_dirs = list(meta.get("ignore_dirs", []))
    for d in extra_ignore_dirs:
        if d not in ignore_dirs:
            ignore_dirs.append(d)

    include_vendor = meta.get("include_vendor", False)
    if force_include_vendor is not None:
        include_vendor = force_include_vendor

    # Check taxonomy change
    old_taxonomy_hash = hashes_data.get("taxonomy_hash")
    current_taxonomy_hash = None
    if taxonomy_path.exists():
        current_taxonomy_hash = _content_hash(_read_text(taxonomy_path))

    if old_taxonomy_hash != current_taxonomy_hash:
        summary["taxonomy_changed"] = True

    # Detect extractor code changes (new detection patterns, bug fixes, etc.)
    old_extractor_hash = hashes_data.get("extractor_hash")
    current_extractor_hash = _extractor_hash()
    extractor_changed = (old_extractor_hash is not None
                         and old_extractor_hash != current_extractor_hash)

    # Build old file hash lookup
    old_file_hashes = hashes_data.get("files", {})

    # Index old functions by file
    old_funcs_by_file: Dict[str, List[dict]] = {}
    for f in old_funcs:
        rel = f.get("file", "")
        old_funcs_by_file.setdefault(rel, []).append(f)

    # Scan current source files
    current_files = list(iter_source_files(root_path, include_vendor, ignore_dirs))
    summary["files_scanned"] = len(current_files)

    # Compute hashes and classify files
    current_file_map: Dict[str, Path] = {}
    current_hashes: Dict[str, str] = {}
    for p in current_files:
        rel = _posix_rel(p, root_path)
        current_file_map[rel] = p
        try:
            current_hashes[rel] = _file_hash(p)
        except Exception:
            continue

    old_files_set = set(old_file_hashes.keys())
    current_files_set = set(current_hashes.keys())

    # Classify files
    deleted_files = old_files_set - current_files_set
    new_files = current_files_set - old_files_set
    common_files = old_files_set & current_files_set
    changed_files = set()
    unchanged_files = set()

    if extractor_changed:
        # Extractor code changed -- re-extract everything to apply new patterns
        changed_files = common_files
        unchanged_files = set()
    else:
        for rel in common_files:
            old_hash = old_file_hashes.get(rel, {}).get("hash", "")
            if current_hashes.get(rel) == old_hash:
                unchanged_files.add(rel)
            else:
                changed_files.add(rel)

    summary["unchanged"] = len(unchanged_files)
    summary["changed"] = len(changed_files)
    summary["extractor_changed"] = extractor_changed
    summary["new"] = len(new_files)
    summary["deleted"] = len(deleted_files)

    # Build updated function list
    updated_funcs: List[dict] = []

    # Copy unchanged functions
    for rel in unchanged_files:
        if rel in old_funcs_by_file:
            updated_funcs.extend(old_funcs_by_file[rel])

    # Re-extract from changed files
    for rel in changed_files:
        p = current_file_map.get(rel)
        if p:
            new_file_funcs = _extract_functions_from_file(p, root_path)
            updated_funcs.extend(new_file_funcs)
            old_count = len(old_funcs_by_file.get(rel, []))
            new_count = len(new_file_funcs)
            summary["changed_files"].append({
                "file": rel,
                "funcs": new_count,
                "added": max(0, new_count - old_count),
                "removed": max(0, old_count - new_count),
                "is_new": False,
            })

    # Extract from new files
    for rel in new_files:
        p = current_file_map.get(rel)
        if p:
            new_file_funcs = _extract_functions_from_file(p, root_path)
            updated_funcs.extend(new_file_funcs)
            summary["changed_files"].append({
                "file": rel,
                "funcs": len(new_file_funcs),
                "added": len(new_file_funcs),
                "removed": 0,
                "is_new": True,
            })

    # Count delta
    summary["funcs_after"] = len(updated_funcs)
    summary["funcs_new"] = max(0, summary["funcs_after"] - summary["funcs_before"])
    summary["funcs_removed"] = max(0, summary["funcs_before"] - summary["funcs_after"])

    # Write updated _functions.json
    funcs_json_text = json.dumps(updated_funcs, indent=2)
    _write_text(funcs_path, funcs_json_text)

    # Update _meta.json
    meta["function_count"] = len(updated_funcs)
    meta["file_count"] = len(current_files)
    meta["generated_at"] = _now_iso()
    _write_text(meta_path, json.dumps(meta, indent=2, sort_keys=True))

    # Write updated hashes
    new_files_dict: Dict[str, dict] = {}
    funcs_by_file_count: Dict[str, int] = {}
    for f in updated_funcs:
        rel = f.get("file", "")
        funcs_by_file_count[rel] = funcs_by_file_count.get(rel, 0) + 1

    for rel, p in current_file_map.items():
        h = current_hashes.get(rel, "")
        try:
            size = p.stat().st_size
        except Exception:
            size = 0
        new_files_dict[rel] = {
            "hash": h,
            "size": size,
            "function_count": funcs_by_file_count.get(rel, 0),
        }

    new_hashes = {
        "version": 1,
        "generated_at": _now_iso(),
        "project": project_dir.name,
        "root_path": _posix_path(root_path),
        "key_format": "file::name::line_start",
        "taxonomy_hash": current_taxonomy_hash,
        "extractor_hash": current_extractor_hash,
        "functions_hash": _content_hash(funcs_json_text),
        "files": new_files_dict,
    }
    _write_text(hashes_path, json.dumps(new_hashes, indent=2))

    return summary


def _print_summary(project_name: str, summary: dict, sub_project: str = "") -> None:
    """Print human-readable delta summary."""
    prefix = f"[quickmap:{sub_project}]" if sub_project else "[quickmap]"

    if summary.get("error"):
        print(f"{prefix} ERROR: {summary['error']}")
        return

    label = f"{project_name}/{sub_project}" if sub_project else project_name
    print(f"{prefix} Project: {label}")
    print(f"{prefix} Files: {summary['files_scanned']} scanned, "
          f"{summary['unchanged']} unchanged, {summary['changed']} changed, "
          f"{summary['new']} new, {summary['deleted']} deleted")
    print(f"{prefix} Functions: {summary['funcs_before']} -> {summary['funcs_after']} "
          f"(+{summary['funcs_new']} new, -{summary['funcs_removed']} removed)")

    if summary["changed_files"]:
        print(f"{prefix} Changed files:")
        for cf in summary["changed_files"]:
            tag = "new file" if cf["is_new"] else f"{cf['added']} new, {cf['removed']} removed"
            print(f"{prefix}   {cf['file']}: {cf['funcs']} functions ({tag})")

    if summary.get("extractor_changed"):
        print(f"{prefix} Extractor: CHANGED (all files re-extracted with new detection patterns)")

    if summary["taxonomy_changed"]:
        print(f"{prefix} Taxonomy: CHANGED (categories will be regenerated)")
    else:
        print(f"{prefix} Taxonomy: unchanged")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="quickmap",
        description="Hash-based incremental function map updater.",
    )
    ap.add_argument("--project", required=True, help="Project name (must exist in functionmap).")
    ap.add_argument("--ignore-dir", action="append", default=[], help="Additional directories to ignore.")
    ap.add_argument("--include-vendor", action="store_true", help="Include vendor/node_modules.")
    ap.add_argument("--remap-third-party", action="store_true",
                    help="Force re-mapping of all third-party libs (even already mapped ones).")
    args = ap.parse_args(argv)

    project_name = args.project
    base = _functionmap_root(_home_claude_dir())
    project_dir = base / project_name

    if not project_dir.exists():
        print(f"[quickmap] ERROR: Project '{project_name}' not found at {project_dir}")
        print(f"[quickmap] Run /functionmap first to create the initial map.")
        return 2

    # Process main project
    print(f"[quickmap] === Main project: {project_name} ===")
    summary = _process_project(
        project_dir, project_name,
        extra_ignore_dirs=args.ignore_dir,
        force_include_vendor=args.include_vendor if args.include_vendor else None,
    )

    if summary.get("error"):
        _print_summary(project_name, summary)
        return 1

    _print_summary(project_name, summary)

    # Process sub-projects (if any declared in _meta.json)
    meta_path = project_dir / "_meta.json"
    sub_summaries: Dict[str, dict] = {}
    if meta_path.exists():
        meta = json.loads(_read_text(meta_path))
        sub_projects = meta.get("sub_projects", {})
        if isinstance(sub_projects, dict):
            for sub_name, sub_config in sub_projects.items():
                if not isinstance(sub_config, dict):
                    continue
                sub_root = sub_config.get("root_path", "")
                if not sub_root or not Path(sub_root).exists():
                    # Try auto-resolve via glob pattern
                    project_root = meta.get("root_path", "")
                    resolved = resolve_root_path_glob(sub_config, project_root) if project_root else None
                    if resolved:
                        print(f"[quickmap] Auto-resolved '{sub_name}' path: {sub_root} -> {resolved}")
                        sub_config["root_path"] = resolved
                        sub_root = resolved
                        # Update _meta.json with resolved path
                        meta["sub_projects"][sub_name]["root_path"] = resolved
                        _write_text(meta_path, json.dumps(meta, indent=2, sort_keys=True))
                        # Also update the sub-project's own _meta.json
                        sub_meta_path = (project_dir / sub_name) / "_meta.json"
                        if sub_meta_path.exists():
                            sub_meta = json.loads(_read_text(sub_meta_path))
                            sub_meta["root_path"] = resolved
                            _write_text(sub_meta_path, json.dumps(sub_meta, indent=2, sort_keys=True))
                    else:
                        print(f"[quickmap] WARNING: Sub-project '{sub_name}' root not found: {sub_root}")
                        if sub_config.get("root_path_glob"):
                            print(f"[quickmap]   Glob '{sub_config['root_path_glob']}' matched no directories")
                        continue

                sub_dir = project_dir / sub_name
                if not sub_dir.exists():
                    print(f"[quickmap] WARNING: Sub-project dir not found: {sub_dir}")
                    print(f"[quickmap] Run /functionmap with sub-project declaration first.")
                    continue

                print(f"\n[quickmap] === Sub-project: {sub_name} ===")
                sub_ignore = sub_config.get("ignore_dirs", [])
                sub_vendor = sub_config.get("include_vendor", False)
                sub_summary = _process_project(
                    sub_dir, sub_name,
                    extra_ignore_dirs=sub_ignore,
                    force_include_vendor=sub_vendor,
                )
                sub_summaries[sub_name] = sub_summary
                _print_summary(project_name, sub_summary, sub_project=sub_name)

    # Auto-detect new third-party libraries from newly added files
    if _has_thirdparty:
        new_file_paths = [cf["file"] for cf in summary.get("changed_files", [])
                          if cf.get("is_new")]
        if new_file_paths:
            taxonomy_path = project_dir / "_taxonomy.json"
            meta_path_check = project_dir / "_meta.json"
            if taxonomy_path.exists() and meta_path_check.exists():
                taxonomy_data = json.loads(_read_text(taxonomy_path))
                meta_data = json.loads(_read_text(meta_path_check))
                source_root = meta_data.get("root_path", "")

                new_rules = detect_new_third_party_files(
                    new_file_paths, taxonomy_data, source_root,
                )
                if new_rules:
                    # Add new rules to taxonomy
                    tp_rules = taxonomy_data.setdefault(
                        "routing_rules", {},
                    ).setdefault("third_party", [])
                    tp_rules.extend(new_rules)
                    _write_text(taxonomy_path, json.dumps(taxonomy_data, indent=2))

                    print(f"\n[quickmap] Auto-detected {len(new_rules)} new third-party libraries:")
                    for r in new_rules:
                        print(f"[quickmap]   {r['library']} {r['version']} "
                              f"(pattern: \"{r['pattern']}\")")
                    print(f"[quickmap] Rules added to _taxonomy.json")

    # Check for unmapped third-party libs before categorization
    if _has_thirdparty:
        print(f"\n[quickmap] Checking third-party libraries...")
        newly_mapped = _check_unmapped_third_party(
            project_dir, project_name, base,
            force_remap=args.remap_third_party,
        )
        if newly_mapped:
            print(f"[quickmap] Mapped {len(newly_mapped)} new third-party libraries:")
            for key in newly_mapped:
                print(f"[quickmap]   {key}")
        elif args.remap_third_party:
            print(f"[quickmap] No third-party libraries to remap")

    # Run categorization (always -- fast Python, regenerates all .md files)
    print(f"\n[quickmap] Running categorization...")
    cat_ok = _run_categorize(project_name)

    # Also categorize sub-projects
    for sub_name in sub_summaries:
        if not sub_summaries[sub_name].get("error"):
            # Sub-projects need their own categorize run if they have taxonomy
            sub_dir = project_dir / sub_name
            if (sub_dir / "_taxonomy.json").exists():
                print(f"[quickmap] Categorizing sub-project: {sub_name}")
                # Run categorize with --project pointing to the sub-project subfolder name
                # The categorizer expects the project name, which is the folder name
                # For sub-projects stored as {project}/{sub_name}/, we pass the full path
                sub_result = subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "categorize.py"),
                     "--project", f"{project_name}/{sub_name}"],
                    capture_output=True, text=True,
                )
                if sub_result.stdout:
                    for line in sub_result.stdout.rstrip().split('\n'):
                        print(line)

    # Update registry
    update_registry(project_name)

    # Count categories generated
    cat_files = list(project_dir.glob("*--*.md"))
    cat_count = len(cat_files)

    # Count uncategorized
    uncat_count = 0
    for cf in cat_files:
        if cf.name.startswith("uncategorized--"):
            try:
                content = _read_text(cf)
                # Count ## headers (each is a function)
                uncat_count += content.count("\n## ") + (1 if content.startswith("## ") else 0)
            except Exception:
                pass

    print(f"\n[quickmap] Categories regenerated: {cat_count}")
    if uncat_count > 0:
        print(f"[quickmap] Uncategorized: {uncat_count}")
    else:
        print(f"[quickmap] Uncategorized: 0")

    if not cat_ok:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
