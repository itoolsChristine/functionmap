#!/usr/bin/env python3
"""
thirdparty.py -- Shared third-party library mapping system.

Maps bundled third-party libraries (FullCalendar, Bootstrap, jQuery, etc.) into
shared function maps keyed by library name + version. If two projects bundle the
same jQuery version, only one set of maps exists. Each project's index references
the shared maps.

Called by categorize.py (full run) and quickmap.py (incremental).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import shared utilities
import sys
sys.path.insert(0, str(Path(__file__).parent))
from functionmap import _now_iso, _read_text, _write_text


# =============================================================================
# Library/version resolution
# =============================================================================

# Common version patterns in file paths
_VERSION_RE = re.compile(
    r'[-/]'                          # separator before version
    r'v?(\d+\.\d+(?:\.\d+)?'        # major.minor[.patch]
    r'(?:[-.](?:alpha|beta|rc|dev|pre|post|final|release|stable|RELEASE)'
    r'(?:[-.]?\d+)?)?)'              # optional pre-release suffix
)

# Library name patterns: known libraries and their canonical names
_KNOWN_LIBS = {
    'fullcalendar':    'fullcalendar',
    'bootstrap':       'bootstrap',
    'jquery':          'jquery',
    'video.js':        'videojs',
    'videojs':         'videojs',
    'video':           'videojs',
    'tinymce':         'tinymce',
    'tcpdf':           'tcpdf',
    'fpdi':            'fpdi',
    'fpdf':            'fpdf',
    'dflip':           'dflip',
    'lightbox':        'lightbox',
    'matchheight':     'jquery-matchheight',
    'jquery.matchheight': 'jquery-matchheight',
    'moxiemanager':    'moxiemanager',
    'moxiemanagerplugin': 'moxiemanager',
    'icomoon':         'icomoon',
    'flipbook':        'flipbook',
    'php.js':          'phpjs',
    'phpjs':           'phpjs',
    'select2':         'select2',
    'datatables':      'datatables',
    'moment':          'momentjs',
    'lodash':          'lodash',
    'underscore':      'underscore',
    'backbone':        'backbone',
    'angular':         'angular',
    'react':           'react',
    'vue':             'vue',
    'axios':           'axios',
    'chart.js':        'chartjs',
    'chartjs':         'chartjs',
    'd3':              'd3',
    'three':           'threejs',
    'three.js':        'threejs',
    'codemirror':      'codemirror',
    'ace':             'ace-editor',
    'ckeditor':        'ckeditor',
    'quill':           'quill',
    'sortablejs':      'sortablejs',
    'sortable':        'sortablejs',
    'flatpickr':       'flatpickr',
    'pikaday':         'pikaday',
    'toastr':          'toastr',
    'sweetalert':      'sweetalert',
    'swiper':          'swiper',
    'slick':           'slick',
    'owl.carousel':    'owl-carousel',
    'fancybox':        'fancybox',
    'magnific-popup':  'magnific-popup',
    'masonry':         'masonry',
    'isotope':         'isotope',
    'waypoints':       'waypoints',
    'scrollmagic':     'scrollmagic',
    'animate.css':     'animate-css',
    'popper':          'popper',
    'popper.js':       'popper',
    'tether':          'tether',
    'dropzone':        'dropzone',
    'cropper':         'cropper',
    'cropperjs':       'cropper',
    'leaflet':         'leaflet',
    'highcharts':      'highcharts',
    'echarts':         'echarts',
}


def parse_lib_version(pattern: str) -> Tuple[Optional[str], Optional[str]]:
    """Auto-detect library name and version from a taxonomy rule pattern.

    Examples:
        "fullcalendar-6.1.19"       -> ("fullcalendar", "6.1.19")
        "bower_components"          -> (None, None)  -- too generic
        "teach/assets/js/video.js"  -> ("videojs", None)
        "jquery-2.1.4.js"           -> ("jquery", "2.1.4")
        "bootstrap/3.3.7"           -> ("bootstrap", "3.3.7")
    """
    # Normalize separators
    normalized = pattern.replace("\\", "/").lower()
    # Strip regex escapes
    normalized = normalized.replace("\\/", "/")

    # Skip overly generic patterns
    generic_patterns = {
        'bower_components', 'node_modules', 'vendor', 'assets/lib',
        'assets/js', 'assets/css', '3rdparty', 'lib', 'libs',
    }
    if normalized.strip('/') in generic_patterns:
        return (None, None)

    # Try to extract version (use normalized to handle Windows backslashes)
    version_match = _VERSION_RE.search(normalized)
    version = version_match.group(1) if version_match else None

    # Try to find library name
    lib_name = None

    # Strategy 1: Check if any known library name appears in the pattern
    for known_key, canonical in _KNOWN_LIBS.items():
        if known_key in normalized:
            lib_name = canonical
            break

    # Strategy 2: Extract from path segments
    if not lib_name:
        # Split into path segments, strip file extensions from final segment only
        segments = normalized.split('/')
        if segments and '.' in segments[-1]:
            # Strip extension from filename only (not directory names like video.js)
            base, ext = segments[-1].rsplit('.', 1)
            if ext in ('js', 'php', 'ts', 'css'):
                segments[-1] = base
        # Remove common non-library segments
        skip_segments = {
            'assets', 'js', 'css', 'lib', 'libs', 'vendor', 'plugins',
            'teach', 'htdocs', 'bower_components', 'node_modules',
            'pdftest', 'src', 'dist', 'build',
        }
        meaningful = [s for s in segments if s and s not in skip_segments]

        if meaningful:
            # Take the last meaningful segment, strip version
            candidate = meaningful[-1]
            if version:
                candidate = candidate.replace(f'-{version}', '').replace(f'/{version}', '')
                candidate = candidate.replace(f'-v{version}', '').replace(f'/v{version}', '')
            candidate = candidate.strip('-').strip('/')
            if candidate and len(candidate) > 1:
                # Normalize to canonical if known
                lib_name = _KNOWN_LIBS.get(candidate, candidate)

    return (lib_name, version)


def resolve_library_info(rule: dict) -> Tuple[Optional[str], Optional[str]]:
    """Get library name + version from a taxonomy rule.

    Checks explicit `library`/`version` fields first,
    falls back to parse_lib_version(rule['pattern']).
    """
    # Explicit fields take priority
    lib = rule.get("library")
    ver = rule.get("version")
    if lib:
        return (lib, ver or "unknown")

    # Auto-detect from pattern
    pattern = rule.get("pattern", "")
    auto_lib, auto_ver = parse_lib_version(pattern)
    if auto_lib:
        return (auto_lib, auto_ver or "unknown")

    return (None, None)


# =============================================================================
# Smart version detection from package metadata files
# =============================================================================

# Metadata files to check, in priority order
_VERSION_FILES = [
    'package.json',      # Node/JS packages
    'composer.json',     # PHP packages
    'bower.json',        # Bower packages
    '.bower.json',       # Bower internal metadata
    'version.php',       # PHP version files
    'VERSION',           # Plain version file
    'VERSION.txt',       # Plain version file
]


def detect_version_from_filesystem(
    functions: List[dict],
    project_root: str,
) -> Optional[str]:
    """Detect library version by scanning package metadata files on disk.

    Given a list of functions belonging to a library, finds their common
    directory and looks for package.json, composer.json, bower.json, etc.
    in that directory and its parents (up to the project root).

    Returns the detected version string, or None if not found.
    """
    if not functions or not project_root:
        return None

    project_root_path = Path(project_root.replace("\\", "/"))
    if not project_root_path.exists():
        return None

    # Get file paths from functions and find common directory
    file_paths = sorted(set(fn["file"].replace("\\", "/") for fn in functions))
    common_prefix = _common_path_prefix(file_paths)

    # Build the absolute path to the library's directory
    if common_prefix:
        lib_dir = project_root_path / common_prefix.rstrip("/")
    else:
        # No common prefix -- try the directory of the first file
        first_file = file_paths[0]
        parts = first_file.rsplit("/", 1)
        lib_dir = project_root_path / parts[0] if len(parts) > 1 else project_root_path

    # Walk up from lib_dir, checking for version files.
    # Only walk up 2 levels max -- a library's package.json is always within 1-2
    # directories of its source code. Walking further hits project-level metadata.
    current = lib_dir
    levels_walked = 0
    max_levels = 1
    checked = set()
    while levels_walked <= max_levels:
        current_str = str(current)
        if current_str in checked:
            break
        checked.add(current_str)

        # Never check at or above the project root
        if current == project_root_path or current == project_root_path.parent:
            break

        if not current.exists():
            current = current.parent
            levels_walked += 1
            continue

        # At parent levels, plain text version files (VERSION, VERSION.txt,
        # version.php) are only trusted if the directory also has a JSON metadata
        # file (composer.json, package.json, bower.json). A VERSION file alongside
        # a composer.json is a library root; a lone VERSION file at a parent level
        # is likely a project-level file (e.g., htdocs/version).
        has_valid_json_metadata = False
        if levels_walked > 0:
            for jf in ('package.json', 'composer.json', 'bower.json', '.bower.json'):
                jf_path = current / jf
                if jf_path.exists():
                    # Also verify the JSON has a valid library name (no spaces)
                    # to avoid project-level metadata (e.g., "BII Canada Report Builder")
                    name = _extract_name_from_json(jf_path)
                    if name is not None:
                        has_valid_json_metadata = True
                        break

        for vfile in _VERSION_FILES:
            if levels_walked > 0 and not has_valid_json_metadata and vfile.lower() in ('version', 'version.txt', 'version.php'):
                continue

            candidate = current / vfile
            if not candidate.exists():
                continue

            version = _extract_version_from_file(candidate)
            if version:
                return version

        current = current.parent
        levels_walked += 1

    # Fallback: check for version comments in the first source file
    if file_paths:
        first_abs = project_root_path / file_paths[0]
        if first_abs.exists():
            version = _extract_version_from_source_header(first_abs)
            if version:
                return version

    return None


def _extract_version_from_file(path: Path) -> Optional[str]:
    """Extract version from a package metadata file."""
    name = path.name.lower()

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return None

    if name in ('package.json', 'composer.json', 'bower.json', '.bower.json'):
        return _extract_version_from_json(content)
    elif name == 'version.php':
        return _extract_version_from_php(content)
    elif name in ('version', 'version.txt'):
        # Plain text version file -- first line should be the version
        first_line = content.strip().split('\n')[0].strip()
        if re.match(r'^v?\d+\.\d+', first_line):
            return first_line.lstrip('v')

    return None


def _extract_version_from_json(content: str) -> Optional[str]:
    """Extract version from a JSON package file (package.json, composer.json, bower.json)."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return None

    # Reject project-level metadata: package names never have spaces
    # (npm, bower, composer all forbid them), but project names often do
    # e.g., "BII Canada Report Builder" in a project-level bower.json
    name = data.get("name")
    if isinstance(name, str) and ' ' in name:
        return None

    version = data.get("version")
    if isinstance(version, str) and version:
        # Strip leading 'v' if present
        return version.lstrip('v')

    return None


def _extract_version_from_php(content: str) -> Optional[str]:
    """Extract version from a PHP version file.

    Looks for patterns like:
        $version = '3.82';
        define('VERSION', '1.2.3');
        const VERSION = '1.2.3';
    """
    patterns = [
        r"(?:version|VERSION)\s*=\s*['\"]([^'\"]+)['\"]",
        r"define\s*\(\s*['\"](?:VERSION|version)['\"].*?['\"]([^'\"]+)['\"]",
    ]
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            val = m.group(1).strip()
            if re.match(r'^v?\d+\.\d+', val):
                return val.lstrip('v')
    return None


def _extract_version_from_source_header(path: Path) -> Optional[str]:
    """Extract version from source file header comments.

    Looks for patterns like:
        * Bootstrap: tooltip.js v3.3.5
        * jQuery v2.1.4
        * Video.js - v7.20.3
        @version 1.2.3
    """
    try:
        # Only read first 20 lines
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            header = ""
            for i, line in enumerate(f):
                if i >= 20:
                    break
                header += line
    except (OSError, PermissionError):
        return None

    # @version tag
    m = re.search(r'@version\s+v?(\d+\.\d+(?:\.\d+)?)', header)
    if m:
        return m.group(1)

    # "LibraryName v1.2.3" or "LibraryName - v1.2.3"
    # Process line-by-line to skip dependency declarations like "@requires jQuery v1.5 or later"
    for line in header.split('\n'):
        if re.search(r'require', line, re.IGNORECASE):
            continue
        m = re.search(r'[-\s]v(\d+\.\d+(?:\.\d+)?)', line)
        if m:
            return m.group(1)

    return None


# =============================================================================
# Library name detection from filesystem (second-pass fallback)
# =============================================================================

def _detect_library_from_files(
    functions: List[dict],
    project_root: str,
) -> Optional[str]:
    """Detect library name by examining the actual files on disk.

    This is the second-pass fallback for when rule pattern parsing can't
    identify the library. Uses three strategies:
      1. package.json / composer.json / bower.json 'name' field in the
         library's directory or any parent up to the project root
      2. Directory name matched against _KNOWN_LIBS
      3. Source file header comments (e.g., "Bootstrap v3.3.5", "Lightbox v2.11.4")
    """
    if not functions or not project_root:
        return None

    project_root_path = Path(project_root.replace("\\", "/"))
    if not project_root_path.exists():
        return None

    # Find common directory of these functions
    file_paths = sorted(set(fn["file"].replace("\\", "/") for fn in functions))
    common_prefix = _common_path_prefix(file_paths)

    if common_prefix:
        lib_dir = project_root_path / common_prefix.rstrip("/")
    else:
        first_file = file_paths[0]
        parts = first_file.rsplit("/", 1)
        lib_dir = project_root_path / parts[0] if len(parts) > 1 else project_root_path

    # Strategy 1+2: Walk up from lib_dir, check metadata files and directory names
    # Only walk up 2 levels max -- beyond that, we'd hit project-level metadata
    current = lib_dir
    levels_walked = 0
    max_levels = 1
    checked = set()
    while levels_walked <= max_levels:
        current_str = str(current)
        if current_str in checked:
            break
        checked.add(current_str)

        # Never check at or above the project root
        if current == project_root_path or current == project_root_path.parent:
            break

        if not current.exists():
            current = current.parent
            levels_walked += 1
            continue

        # Check metadata files for library name
        for meta_file in ('package.json', 'composer.json', 'bower.json', '.bower.json'):
            candidate = current / meta_file
            if not candidate.exists():
                continue

            name = _extract_name_from_json(candidate)
            if name:
                # Normalize through _KNOWN_LIBS
                canonical = _KNOWN_LIBS.get(name.lower(), name.lower())
                return canonical

        # Check directory name against _KNOWN_LIBS
        dir_name = current.name.lower()
        # Strip version suffix from directory name (e.g., "bootstrap-3.3.5" -> "bootstrap")
        stripped = re.sub(r'[-_]v?\d+\.\d+.*$', '', dir_name)
        if stripped in _KNOWN_LIBS:
            return _KNOWN_LIBS[stripped]
        if dir_name in _KNOWN_LIBS:
            return _KNOWN_LIBS[dir_name]

        current = current.parent
        levels_walked += 1

    # Strategy 3: Check source file headers for library name
    # Sample up to 3 files to avoid excessive I/O
    for fp in file_paths[:3]:
        abs_path = project_root_path / fp
        if abs_path.exists():
            name = _extract_library_name_from_source_header(abs_path)
            if name:
                return name

    return None


def _extract_library_name_from_source_header(path: Path) -> Optional[str]:
    """Extract library name from source file header comments.

    Looks for patterns like:
        * Bootstrap v3.3.5
        * Bootstrap: tooltip.js v3.3.5
        * Lightbox v2.11.4
        * jQuery v2.1.4
        * FullCalendar v6.1.19
        * Video.js - v7.20.3
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            header = ""
            for i, line in enumerate(f):
                if i >= 20:
                    break
                header += line
    except (OSError, PermissionError):
        return None

    # Look for "LibraryName ... v1.2.3" on the same line
    # Allows text between name and version (e.g., "Bootstrap: tooltip.js v3.3.5")
    # Only returns if the name matches a known library (prevents false positives)
    for line in header.split('\n'):
        m = re.search(
            r'[*/#!\s]+'                    # comment prefix
            r'([A-Za-z][A-Za-z0-9_.]+)'    # library name (starts with letter)
            r'.*?'                          # anything between name and version
            r'v(\d+\.\d+)',                 # version marker
            line
        )
        if m:
            candidate = m.group(1).strip().rstrip(':').rstrip('-')
            canonical = _KNOWN_LIBS.get(candidate.lower())
            if canonical:
                return canonical

    return None


def _extract_name_from_json(path: Path) -> Optional[str]:
    """Extract the 'name' field from a JSON package metadata file."""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        data = json.loads(content)
    except (OSError, PermissionError, json.JSONDecodeError, ValueError):
        return None

    name = data.get("name")
    if isinstance(name, str) and name:
        # Reject project-level metadata: package names never have spaces
        if ' ' in name:
            return None
        # Strip org scope (e.g., "@fullcalendar/core" -> "fullcalendar")
        if "/" in name:
            parts = name.split("/")
            # Use the org name if it's a scoped package (e.g., @fullcalendar/core -> fullcalendar)
            org = parts[0].lstrip("@")
            pkg = parts[-1]
            # Check if org name is a known library (common for monorepos)
            if org.lower() in _KNOWN_LIBS:
                return org
            return pkg
        return name

    return None


# =============================================================================
# Auto-detection of new third-party libraries from new files
# =============================================================================

def detect_new_third_party_files(
    new_file_paths: List[str],
    taxonomy: dict,
    project_root: str,
) -> List[dict]:
    """Check if newly added files look like known third-party libraries.

    Compares new file paths against existing third_party taxonomy rules.
    Files not covered by any rule are checked via filesystem detection
    (package.json, directory names, source headers). If a known library is
    identified, a new taxonomy rule is generated.

    Returns list of new taxonomy rule dicts to add to _taxonomy.json.
    """
    if not new_file_paths or not project_root:
        return []

    existing_rules = taxonomy.get("routing_rules", {}).get("third_party", [])

    # Filter to files not already covered by existing rules
    uncovered = []
    for fp in new_file_paths:
        norm = fp.replace("\\", "/")
        if not any(_matches_pattern_simple(norm, {}, r) for r in existing_rules):
            uncovered.append(norm)

    if not uncovered:
        return []

    # Group by parent directory
    dir_groups: Dict[str, List[str]] = defaultdict(list)
    for fp in uncovered:
        parts = fp.rsplit("/", 1)
        dir_key = parts[0] if len(parts) > 1 else ""
        dir_groups[dir_key].append(fp)

    # Detect library for each directory group using existing strategies
    new_rules: List[dict] = []
    seen_libs = set(r.get("library") for r in existing_rules if r.get("library"))

    for dir_path, files in dir_groups.items():
        mock_funcs = [{"file": fp} for fp in files]
        lib_name = _detect_library_from_files(mock_funcs, project_root)

        if not lib_name or lib_name in seen_libs:
            continue

        # Detect version
        version = detect_version_from_filesystem(mock_funcs, project_root) or "unknown"
        if version == "unknown":
            ver_match = _VERSION_RE.search(dir_path.lower())
            if ver_match:
                version = ver_match.group(1)

        rule = {
            "type": "path_contains",
            "pattern": dir_path,
            "reason": f"Auto-detected {lib_name} library",
            "library": lib_name,
            "version": version,
        }
        new_rules.append(rule)
        seen_libs.add(lib_name)

    return new_rules


# =============================================================================
# Grouping third-party functions by library
# =============================================================================

def group_by_library(
    third_party_funcs: List[dict],
    taxonomy: dict,
    project_root: str = "",
) -> Dict[str, dict]:
    """Group third-party functions by (library, version).

    Returns: {
        "fullcalendar/6.1.19": {"library": "fullcalendar", "version": "6.1.19",
                                 "functions": [...], "rules": [...]},
        "_unresolved": {"functions": [...], "rules": [...]}
    }

    Multiple taxonomy rules can contribute to the same library/version.
    Uses a two-pass approach:
      1. Check explicit library/version fields and pattern-based auto-detection
      2. For unresolved functions, detect library name + version from the actual
         files on disk (package.json, composer.json, bower.json, directory names)
    When version is "unknown", attempts to detect it from package metadata.
    """
    rules = taxonomy.get("routing_rules", {}).get("third_party", [])

    # Build a mapping: rule index -> (library, version)
    rule_lib_map: Dict[int, Tuple[Optional[str], Optional[str]]] = {}
    for i, rule in enumerate(rules):
        lib, ver = resolve_library_info(rule)
        rule_lib_map[i] = (lib, ver)

    # Group functions by matching rule -> library
    groups: Dict[str, dict] = {}
    unresolved_funcs: List[dict] = []
    unresolved_rules: List[dict] = []
    # Track unresolved functions grouped by which rule matched them
    # so we can detect the library from their shared directory
    unresolved_by_rule: Dict[int, List[dict]] = defaultdict(list)

    # Track which rules contributed to which groups
    rule_to_group: Dict[int, str] = {}

    for fn in third_party_funcs:
        fp = fn["file"].replace("\\", "/")
        matched_rule_idx = None

        for i, rule in enumerate(rules):
            if _matches_pattern_simple(fp, fn, rule):
                matched_rule_idx = i
                break

        if matched_rule_idx is None:
            unresolved_funcs.append(fn)
            continue

        lib, ver = rule_lib_map[matched_rule_idx]
        if not lib:
            # Rule matched but we couldn't identify the library from the pattern.
            # Track by rule index so the second pass can detect from files.
            unresolved_by_rule[matched_rule_idx].append(fn)
            if rules[matched_rule_idx] not in unresolved_rules:
                unresolved_rules.append(rules[matched_rule_idx])
            continue

        key = f"{lib}/{ver}"
        if key not in groups:
            groups[key] = {
                "library": lib,
                "version": ver,
                "functions": [],
                "rules": [],
            }

        groups[key]["functions"].append(fn)
        if matched_rule_idx not in rule_to_group:
            rule_to_group[matched_rule_idx] = key
            groups[key]["rules"].append(rules[matched_rule_idx])

    # --- Second pass: detect library name + version from files on disk ---
    if project_root and unresolved_by_rule:
        for rule_idx, funcs in unresolved_by_rule.items():
            lib_name = _detect_library_from_files(funcs, project_root)
            if lib_name:
                version = detect_version_from_filesystem(funcs, project_root) or "unknown"
                key = f"{lib_name}/{version}"

                if key not in groups:
                    groups[key] = {
                        "library": lib_name,
                        "version": version,
                        "functions": [],
                        "rules": [],
                    }

                groups[key]["functions"].extend(funcs)
                groups[key]["rules"].append(rules[rule_idx])
                print(f"[thirdparty] {lib_name}/{version}: detected from filesystem "
                      f"({len(funcs)} functions from rule '{rules[rule_idx].get('reason', rules[rule_idx].get('pattern', '?'))}')")
            else:
                # Truly unresolved -- couldn't detect from pattern or files
                unresolved_funcs.extend(funcs)

    if unresolved_funcs:
        groups["_unresolved"] = {
            "functions": unresolved_funcs,
            "rules": unresolved_rules,
        }
        # Warn about unresolved functions so the user knows to add annotations
        print(f"[thirdparty] WARNING: {len(unresolved_funcs)} third-party functions could not "
              f"be identified as a known library")
        print(f"[thirdparty] These functions are excluded from first-party maps but won't get "
              f"their own searchable third-party map.")
        if unresolved_rules:
            print(f"[thirdparty] Add 'library' and 'version' fields to these taxonomy rules "
                  f"to fix this:")
            for rule in unresolved_rules:
                pattern = rule.get("pattern", "?")
                reason = rule.get("reason", "")
                print(f"[thirdparty]   - \"{pattern}\" ({reason})")

    # Upgrade "unknown" versions by scanning package metadata on disk
    if project_root:
        upgraded = []
        for key in list(groups.keys()):
            if key == "_unresolved":
                continue
            group = groups[key]
            if group["version"] != "unknown":
                continue

            detected = detect_version_from_filesystem(group["functions"], project_root)
            if detected and detected != "unknown":
                old_key = key
                new_key = f"{group['library']}/{detected}"
                group["version"] = detected
                print(f"[thirdparty] {group['library']}: detected version {detected} "
                      f"from package metadata")

                # Re-key the group if the key changed
                if new_key != old_key:
                    if new_key in groups:
                        # Merge into existing group for this version
                        groups[new_key]["functions"].extend(group["functions"])
                        groups[new_key]["rules"].extend(group["rules"])
                        del groups[old_key]
                    else:
                        groups[new_key] = group
                        del groups[old_key]
                    upgraded.append((old_key, new_key))
                else:
                    upgraded.append((old_key, old_key))

    return groups


def _matches_pattern_simple(fp: str, fn: dict, rule: dict) -> bool:
    """Simplified pattern matching (mirrors categorize.py's _matches_pattern)."""
    rule_type = rule.get("type", "path_contains")
    pattern = rule.get("pattern", "")

    if rule_type == "path_contains":
        return pattern.lower() in fp.lower()
    elif rule_type == "path_prefix":
        return fp.startswith(pattern)
    elif rule_type == "path_regex":
        return bool(re.search(pattern, fp))
    elif rule_type == "file_exact":
        return fp == pattern

    return False


# =============================================================================
# Mapping a single library version
# =============================================================================

def map_library(
    lib_name: str,
    version: str,
    functions: List[dict],
    source_project: str,
    functionmap_root: Path,
    source_root: str = "",
    force: bool = False,
) -> Optional[dict]:
    """Map a third-party library version to the shared location.

    1. Check if third-party/{lib}/{version}/ already exists -> skip (dedup)
    2. If not: create directory, write _functions.json, _meta.json
    3. Auto-generate _taxonomy.json from function structure
    4. Run categorization (reuse categorize.py's logic)
    5. Generate version index .md and category .md files
    6. Return metadata dict for _index.json

    For libs already mapped: just add source_project to used_by list.
    """
    tp_root = functionmap_root / "third-party"
    lib_dir = tp_root / lib_name / version

    # Skip libraries that match a registered project (e.g., cmsb -> cmsb-3-82)
    registry_path = functionmap_root / "_registry.json"
    if registry_path.exists():
        try:
            registry = json.loads(_read_text(registry_path))
            # Check if lib_name matches any registered project name or is a prefix of one
            for proj_name in registry:
                proj_lower = proj_name.lower()
                lib_lower = lib_name.lower()
                if lib_lower == proj_lower or proj_lower.startswith(lib_lower + "-"):
                    print(f"[thirdparty] {lib_name}/{version}: SKIPPED -- "
                          f"matches registered project '{proj_name}' (see {proj_name}.md)")
                    return None
        except (json.JSONDecodeError, ValueError):
            pass

    # If already mapped, just update used_by
    if lib_dir.exists() and not force:
        meta_path = lib_dir / "_meta.json"
        if meta_path.exists():
            meta = json.loads(_read_text(meta_path))
            used_by = meta.get("used_by", [])
            if source_project not in used_by:
                used_by.append(source_project)
                meta["used_by"] = used_by
                _write_text(meta_path, json.dumps(meta, indent=2))
                print(f"[thirdparty] {lib_name}/{version}: already mapped, added {source_project} to used_by")
            else:
                print(f"[thirdparty] {lib_name}/{version}: already mapped (used by: {', '.join(used_by)})")
            return _build_result_metadata(meta)
        # Corrupt state -- remap
        print(f"[thirdparty] {lib_name}/{version}: directory exists but no _meta.json, remapping")

    if force and lib_dir.exists():
        import shutil
        shutil.rmtree(lib_dir)
        print(f"[thirdparty] {lib_name}/{version}: force remapping (deleted existing)")

    # Clean up stale "unknown" directory if we now have a real version
    if version != "unknown":
        unknown_dir = tp_root / lib_name / "unknown"
        if unknown_dir.exists():
            import shutil
            shutil.rmtree(unknown_dir)
            print(f"[thirdparty] {lib_name}: cleaned up stale 'unknown' directory (now versioned as {version})")

    if not functions:
        print(f"[thirdparty] {lib_name}/{version}: no functions to map, skipping")
        return None

    # Check for minified-only libraries
    if _is_minified_only(functions):
        print(f"[thirdparty] {lib_name}/{version}: minified-only, no meaningful source available")
        print(f"[thirdparty] Run: /functionmap-docs {lib_name} {version}")
        print(f"[thirdparty] (This will fetch API docs via context7 and build the function map)")
        # Still create the directory with needs_docs status
        lib_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            "library": lib_name,
            "version": version,
            "source_project": source_project,
            "source_root": source_root,
            "generated_at": _now_iso(),
            "file_count": len(set(fn["file"] for fn in functions)),
            "function_count": len(functions),
            "status": "needs_docs",
            "source_type": "minified",
            "used_by": [source_project],
        }
        _write_text(lib_dir / "_meta.json", json.dumps(meta, indent=2))
        return _build_result_metadata(meta)

    # Create directory structure
    lib_dir.mkdir(parents=True, exist_ok=True)
    print(f"[thirdparty] Mapping {lib_name}/{version} ({len(functions)} functions from {source_project})")

    # Compute file path prefix (common prefix of all function files)
    file_paths = sorted(set(fn["file"] for fn in functions))
    file_prefix = _common_path_prefix(file_paths)

    # Write _functions.json
    _write_text(lib_dir / "_functions.json", json.dumps(functions, indent=2))

    # Auto-generate taxonomy
    taxonomy = _generate_library_taxonomy(lib_name, version, functions, file_prefix)
    _write_text(lib_dir / "_taxonomy.json", json.dumps(taxonomy, indent=2))

    # Write _meta.json
    meta = {
        "library": lib_name,
        "version": version,
        "source_project": source_project,
        "source_root": source_root,
        "file_path_prefix": file_prefix,
        "generated_at": _now_iso(),
        "file_count": len(file_paths),
        "function_count": len(functions),
        "source_type": "source",
        "used_by": [source_project],
    }

    # Run categorization on the library's functions
    categories, cat_count = _categorize_library(functions, taxonomy)

    # Generate category .md files
    file_count = 0
    for top_cat, subcats in sorted(categories.items()):
        for sub_name, funcs in sorted(subcats.items()):
            md_content = _generate_lib_category_markdown(
                lib_name, version, top_cat, sub_name, funcs, taxonomy
            )
            filename = f"{top_cat}--{sub_name}.md"
            _write_text(lib_dir / filename, md_content)
            file_count += 1

    meta["category_count"] = file_count
    _write_text(lib_dir / "_meta.json", json.dumps(meta, indent=2))

    # Generate version index .md
    index_content = _generate_version_index(lib_name, version, categories, meta, taxonomy)
    index_filename = f"{lib_name}-{version}.md"
    _write_text(lib_dir / index_filename, index_content)

    print(f"[thirdparty] {lib_name}/{version}: {len(functions)} functions, "
          f"{len(categories)} categories, {file_count} files")

    return _build_result_metadata(meta)


def _build_result_metadata(meta: dict) -> dict:
    """Build a result metadata dict from _meta.json data."""
    return {
        "function_count": meta.get("function_count", 0),
        "file_count": meta.get("file_count", 0),
        "category_count": meta.get("category_count", 0),
        "mapped_at": meta.get("generated_at", ""),
        "source_project": meta.get("source_project", ""),
        "used_by": meta.get("used_by", []),
        "status": meta.get("status", "mapped"),
        "source_type": meta.get("source_type", "source"),
    }


def _is_minified_only(functions: List[dict]) -> bool:
    """Detect if extracted functions look like they came from minified code.

    Signs: all function names are 1-2 characters (a, b, Xb, etc.)
    """
    if not functions:
        return True

    short_name_count = 0
    for fn in functions:
        name = fn.get("short_name", "")
        if len(name) <= 2:
            short_name_count += 1

    # If >80% of functions have ultra-short names, it's minified
    return short_name_count > len(functions) * 0.8


def _common_path_prefix(paths: List[str]) -> str:
    """Find the common directory prefix of a list of file paths."""
    if not paths:
        return ""
    if len(paths) == 1:
        # Return directory of single file
        parts = paths[0].replace("\\", "/").rsplit("/", 1)
        return parts[0] + "/" if len(parts) > 1 else ""

    # Normalize
    normalized = [p.replace("\\", "/") for p in paths]
    # Split into parts
    split = [p.split("/") for p in normalized]
    # Find common prefix
    prefix_parts = []
    for parts in zip(*split):
        if len(set(parts)) == 1:
            prefix_parts.append(parts[0])
        else:
            break

    return "/".join(prefix_parts) + "/" if prefix_parts else ""


# =============================================================================
# Auto-generated taxonomy for third-party libraries
# =============================================================================

def _generate_library_taxonomy(
    lib_name: str,
    version: str,
    functions: List[dict],
    file_prefix: str,
) -> dict:
    """Auto-generate a taxonomy for a third-party library.

    Strategy:
    - Libraries with < 50 functions get a single "core" category
    - Libraries with >= 50 functions get directory-based splitting
    - Class names become subcategories within each directory group
    """
    taxonomy = {
        "project": f"{lib_name}-{version}",
        "description": f"Auto-generated taxonomy for {lib_name} {version}",
        "categories": {},
        "routing_rules": {},
    }

    if len(functions) < 50:
        # Simple: single core category
        taxonomy["categories"]["core"] = {
            "description": f"Core {lib_name} functions and classes.",
            "subcategories": {
                "core": f"All {lib_name} functions."
            }
        }
        taxonomy["routing_rules"]["directory_routes"] = [
            {"pattern": "", "category": "core", "subcategory": "core"}
        ]
        return taxonomy

    # Group by directory (relative to common prefix)
    dir_groups: Dict[str, List[dict]] = defaultdict(list)
    for fn in functions:
        fp = fn["file"].replace("\\", "/")
        # Strip common prefix
        if file_prefix and fp.startswith(file_prefix):
            rel = fp[len(file_prefix):]
        else:
            rel = fp
        # Get directory
        parts = rel.split("/")
        if len(parts) > 1:
            dir_key = parts[0]
        else:
            dir_key = "core"
        dir_groups[dir_key].append(fn)

    # Build categories from directory groups
    directory_routes = []
    for dir_key, funcs in sorted(dir_groups.items()):
        cat_name = _sanitize_category_name(dir_key)

        # Group by class within this directory
        class_groups: Dict[str, List[dict]] = defaultdict(list)
        for fn in funcs:
            cls = fn.get("class_name") or "functions"
            class_groups[cls].append(fn)

        subcategories = {}
        for cls_name, cls_funcs in sorted(class_groups.items()):
            sub_name = _sanitize_category_name(cls_name)
            subcategories[sub_name] = f"{cls_name} ({len(cls_funcs)} functions)"

        taxonomy["categories"][cat_name] = {
            "description": f"{lib_name} {dir_key} module.",
            "subcategories": subcategories,
        }

        # Add directory route
        route_pattern = f"{file_prefix}{dir_key}" if file_prefix else dir_key
        for cls_name in class_groups:
            sub_name = _sanitize_category_name(cls_name) or "core"
            route = {
                "pattern": route_pattern,
                "category": cat_name,
                "subcategory": sub_name,
            }
            if cls_name != "functions":
                route["class"] = cls_name
            directory_routes.append(route)

    taxonomy["routing_rules"]["directory_routes"] = directory_routes

    return taxonomy


def _sanitize_category_name(name: str) -> str:
    """Convert a name to a valid category key."""
    # Lowercase, replace non-alphanumeric with dashes
    result = re.sub(r'[^a-z0-9]+', '-', name.lower())
    result = result.strip('-')
    # Collapse multiple dashes
    result = re.sub(r'-{2,}', '-', result)
    return result or "core"


# =============================================================================
# Library categorization (reuses categorize.py concepts)
# =============================================================================

def _categorize_library(
    functions: List[dict],
    taxonomy: dict,
) -> Tuple[Dict[str, Dict[str, List[dict]]], int]:
    """Categorize library functions using the auto-generated taxonomy.

    Returns (categories_dict, total_category_file_count).
    """
    categories: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    dir_routes = taxonomy.get("routing_rules", {}).get("directory_routes", [])

    for fn in functions:
        fp = fn["file"].replace("\\", "/")
        cls = fn.get("class_name") or ""
        matched = False

        for route in dir_routes:
            pattern = route.get("pattern", "")
            route_class = route.get("class")

            if pattern and not fp.startswith(pattern):
                continue

            if route_class and cls != route_class:
                continue

            cat = route["category"]
            sub = route.get("subcategory", "core")
            categories[cat][sub].append(fn)
            matched = True
            break

        if not matched:
            categories["core"]["other"].append(fn)

    # Convert defaultdicts to regular dicts
    result = {k: dict(v) for k, v in categories.items()}
    total = sum(len(subcats) for subcats in result.values())
    return result, total


# =============================================================================
# Markdown generation for libraries
# =============================================================================

def _generate_lib_category_markdown(
    lib_name: str,
    version: str,
    top_cat: str,
    sub_name: str,
    funcs: List[dict],
    taxonomy: dict,
) -> str:
    """Generate markdown content for a library category file."""
    top_title = top_cat.replace("-", " ").replace("_", " ").title()
    sub_title = sub_name.replace("-", " ").replace("_", " ").title()

    # Get description from taxonomy
    cat_entry = taxonomy.get("categories", {}).get(top_cat, {})
    subcats = cat_entry.get("subcategories", {}) if isinstance(cat_entry, dict) else {}
    sub_desc = subcats.get(sub_name, "")
    if isinstance(sub_desc, dict):
        sub_desc = sub_desc.get("description", "")

    lines = [
        f"# {lib_name} {version} > {top_title} > {sub_title}",
        "",
        sub_desc if sub_desc else f"{lib_name} {top_cat} {sub_name} functions.",
        "",
        f"**Function count:** {len(funcs)}",
        "",
        "---",
        "",
    ]

    # Sort functions by name
    funcs.sort(key=lambda f: f.get("short_name", "").lower())

    for func in funcs:
        vis = f"{func.get('visibility', '')} " if func.get("visibility") else ""
        static = "static " if func.get("is_static") else ""
        async_m = "async " if func.get("is_async") else ""

        sig = f"{vis}{static}{async_m}{func['short_name']}({func.get('params', '')})"
        rtype = func.get("return_type", "")
        if rtype and rtype != "unknown":
            sig += f": {rtype}"

        lines.append(f"## {func['short_name']}")
        lines.append("")

        summary = func.get("summary", "")
        if summary:
            lines.append(summary)
            lines.append("")

        lines.append(f"**Signature:** `{sig}`")
        lines.append("")

        loc = f"{func['file']}:{func['line_start']}"
        if func.get("line_end") and func["line_end"] != func["line_start"]:
            loc += f"-{func['line_end']}"
        lines.append(f"**Location:** `{loc}`")
        lines.append("")

        if func.get("class_name"):
            lines.append(f"**Class:** `{func['class_name']}`")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _generate_version_index(
    lib_name: str,
    version: str,
    categories: Dict[str, Dict[str, List[dict]]],
    meta: dict,
    taxonomy: dict,
) -> str:
    """Generate the version index markdown file."""
    total_funcs = sum(
        len(funcs)
        for subcats in categories.values()
        for funcs in subcats.values()
    )
    total_subcats = sum(len(subcats) for subcats in categories.values())

    lines = [
        f"# {lib_name} {version} Function Map",
        "",
        f"**Library:** {lib_name}",
        f"**Version:** {version}",
        f"**Total functions:** {total_funcs}",
        f"**Categories:** {len(categories)} top-level, {total_subcats} subcategories",
        f"**Source project:** {meta.get('source_project', 'unknown')}",
        "",
        "---",
        "",
    ]

    for top_cat in sorted(categories.keys()):
        subcats = categories[top_cat]
        top_title = top_cat.replace("-", " ").replace("_", " ").title()
        cat_entry = taxonomy.get("categories", {}).get(top_cat, {})
        top_desc = ""
        if isinstance(cat_entry, dict):
            top_desc = cat_entry.get("description", "")
        top_count = sum(len(funcs) for funcs in subcats.values())

        lines.append(f"## {top_title}")
        lines.append("")
        if top_desc:
            lines.append(f"*{top_desc}*")
            lines.append("")
        lines.append(f"**{top_count} functions** across {len(subcats)} subcategories:")
        lines.append("")

        for sub_name in sorted(subcats.keys()):
            funcs = subcats[sub_name]
            sub_title = sub_name.replace("-", " ").replace("_", " ").title()
            filename = f"{top_cat}--{sub_name}.md"
            lines.append(f"- **[{sub_title}]({filename})** ({len(funcs)})")

        lines.append("")

    return "\n".join(lines)


# =============================================================================
# Index management
# =============================================================================

def update_index(
    functionmap_root: Path,
    lib_name: str,
    version: str,
    metadata: dict,
    project_name: str,
) -> None:
    """Update _index.json, _versions.json, and regenerate third-party.md."""
    tp_root = functionmap_root / "third-party"
    tp_root.mkdir(parents=True, exist_ok=True)

    # Update master _index.json
    index_path = tp_root / "_index.json"
    index = {"version": 1, "libraries": {}}
    if index_path.exists():
        try:
            index = json.loads(_read_text(index_path))
        except (json.JSONDecodeError, ValueError):
            pass

    libs = index.setdefault("libraries", {})
    lib_entry = libs.setdefault(lib_name, {"versions": {}})
    versions = lib_entry.setdefault("versions", {})

    used_by = list(dict.fromkeys(metadata.get("used_by", [project_name])))
    if project_name not in used_by:
        used_by.append(project_name)

    versions[version] = {
        "function_count": metadata.get("function_count", 0),
        "file_count": metadata.get("file_count", 0),
        "category_count": metadata.get("category_count", 0),
        "mapped_at": metadata.get("mapped_at", _now_iso()),
        "source_project": metadata.get("source_project", project_name),
        "used_by": used_by,
        "status": metadata.get("status", "mapped"),
        "source_type": metadata.get("source_type", "source"),
    }

    # Remove stale "unknown" entry if we now have a real version
    if version != "unknown" and "unknown" in versions:
        del versions["unknown"]

    _write_text(index_path, json.dumps(index, indent=2))

    # Update library _versions.json
    lib_dir = tp_root / lib_name
    lib_dir.mkdir(parents=True, exist_ok=True)
    versions_path = lib_dir / "_versions.json"
    versions_data = {"library": lib_name, "versions": {}}
    if versions_path.exists():
        try:
            versions_data = json.loads(_read_text(versions_path))
        except (json.JSONDecodeError, ValueError):
            pass

    versions_data["versions"][version] = {
        "function_count": metadata.get("function_count", 0),
        "mapped_at": metadata.get("mapped_at", _now_iso()),
        "source_project": metadata.get("source_project", project_name),
        "status": metadata.get("status", "mapped"),
    }

    # Remove stale "unknown" entry from versions file too
    if version != "unknown" and "unknown" in versions_data["versions"]:
        del versions_data["versions"]["unknown"]

    _write_text(versions_path, json.dumps(versions_data, indent=2))

    # Regenerate third-party.md master index
    master_md = generate_master_index(functionmap_root)
    _write_text(tp_root / "third-party.md", master_md)


def generate_master_index(functionmap_root: Path) -> str:
    """Generate the human-readable third-party.md master index."""
    tp_root = functionmap_root / "third-party"
    index_path = tp_root / "_index.json"

    if not index_path.exists():
        return "# Third-Party Library Maps\n\nNo libraries mapped yet.\n"

    try:
        index = json.loads(_read_text(index_path))
    except (json.JSONDecodeError, ValueError):
        return "# Third-Party Library Maps\n\nError reading index.\n"

    libs = index.get("libraries", {})
    if not libs:
        return "# Third-Party Library Maps\n\nNo libraries mapped yet.\n"

    lines = [
        "# Third-Party Library Maps",
        "",
        "Shared function maps for bundled third-party libraries across all projects.",
        "",
    ]

    total_funcs = 0
    total_libs = 0

    for lib_name in sorted(libs.keys()):
        lib_entry = libs[lib_name]
        versions = lib_entry.get("versions", {})
        if not versions:
            continue

        display_name = lib_name.replace("-", " ").title()
        lines.append(f"## {display_name}")
        lines.append("")

        for ver in sorted(versions.keys(), reverse=True):
            ver_info = versions[ver]
            func_count = ver_info.get("function_count", 0)
            used_by = ver_info.get("used_by", [])
            status = ver_info.get("status", "mapped")
            source_type = ver_info.get("source_type", "source")

            total_funcs += func_count
            total_libs += 1

            index_filename = f"{lib_name}-{ver}.md"
            link = f"{lib_name}/{ver}/{index_filename}"

            status_note = ""
            if status == "needs_docs":
                status_note = " *(needs documentation fetch)*"
            elif source_type == "documentation":
                status_note = " *(from docs)*"

            used_str = ", ".join(used_by) if used_by else "unknown"
            lines.append(f"- **[{ver}]({link})** ({func_count:,} functions) "
                         f"-- used by: {used_str}{status_note}")

        lines.append("")

    # Summary at top
    summary = f"**{total_libs} library versions** mapped, **{total_funcs:,} total functions**.\n"
    lines.insert(3, summary)

    return "\n".join(lines)


def get_project_libs(functionmap_root: Path, project_name: str) -> Dict[str, dict]:
    """Get all third-party libs used by a project (from _index.json used_by)."""
    tp_root = functionmap_root / "third-party"
    index_path = tp_root / "_index.json"

    if not index_path.exists():
        return {}

    try:
        index = json.loads(_read_text(index_path))
    except (json.JSONDecodeError, ValueError):
        return {}

    result = {}
    for lib_name, lib_entry in index.get("libraries", {}).items():
        for ver, ver_info in lib_entry.get("versions", {}).items():
            if project_name in ver_info.get("used_by", []):
                key = f"{lib_name}/{ver}"
                result[key] = {
                    "library": lib_name,
                    "version": ver,
                    "function_count": ver_info.get("function_count", 0),
                    "category_count": ver_info.get("category_count", 0),
                    "status": ver_info.get("status", "mapped"),
                    "source_type": ver_info.get("source_type", "source"),
                }

    return result


# =============================================================================
# Enhanced third-party-bundled.md generation
# =============================================================================

def enhance_third_party_summary(
    summary_lines: str,
    mapped_libs: Dict[str, dict],
    third_party_funcs: List[dict],
    taxonomy: dict,
) -> str:
    """Enhance the third-party-bundled.md summary with links to mapped libraries.

    Inserts "Mapped: [lib version](link)" after each group heading
    for libraries that were successfully mapped.
    """
    rules = taxonomy.get("routing_rules", {}).get("third_party", [])

    # Build a mapping: rule reason -> (lib_name, version)
    reason_to_lib: Dict[str, Tuple[str, str]] = {}
    for rule in rules:
        lib, ver = resolve_library_info(rule)
        if lib and ver:
            reason = rule.get("reason", rule.get("pattern", "Unknown"))
            reason_to_lib[reason] = (lib, ver)

    # Process lines and insert mapped links
    result_lines = []
    for line in summary_lines.split("\n"):
        result_lines.append(line)

        # Check if this is a group heading (## Reason (N functions))
        if line.startswith("## "):
            # Extract reason text
            heading_match = re.match(r'^## (.+?) \(\d+ functions?\)$', line)
            if heading_match:
                reason = heading_match.group(1)
                if reason in reason_to_lib:
                    lib, ver = reason_to_lib[reason]
                    key = f"{lib}/{ver}"
                    if key in mapped_libs:
                        index_filename = f"{lib}-{ver}.md"
                        link = f"third-party/{lib}/{ver}/{index_filename}"
                        result_lines.append("")
                        result_lines.append(f"**Mapped:** [{lib} {ver}]({link})")

    return "\n".join(result_lines)


# =============================================================================
# Project index third-party table
# =============================================================================

def generate_third_party_table(
    functionmap_root: Path,
    project_name: str,
) -> str:
    """Generate the Third-Party Libraries table for a project's index .md.

    Returns markdown text to append to the project index, or empty string
    if no third-party libs are used.
    """
    project_libs = get_project_libs(functionmap_root, project_name)
    if not project_libs:
        return ""

    lines = [
        "## Third-Party Libraries",
        "",
        "| Library | Version | Functions | Status | Map |",
        "|---------|---------|-----------|--------|-----|",
    ]

    for key in sorted(project_libs.keys()):
        info = project_libs[key]
        lib = info["library"]
        ver = info["version"]
        func_count = info["function_count"]
        status = info.get("status", "mapped")
        source_type = info.get("source_type", "source")

        display_name = lib.replace("-", " ").title()
        index_filename = f"{lib}-{ver}.md"
        link = f"third-party/{lib}/{ver}/{index_filename}"

        status_text = "Mapped"
        if status == "needs_docs":
            status_text = "Needs docs"
        elif source_type == "documentation":
            status_text = "From docs"

        lines.append(f"| {display_name} | {ver} | {func_count:,} | {status_text} "
                     f"| [{index_filename}]({link}) |")

    lines.append("")
    return "\n".join(lines)
