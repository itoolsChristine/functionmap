"""
sync.py -- Sync functionmap files from ~/.claude/ into the repo's src/ directory.

Copies Python tools verbatim and applies transforms to .md skill/doc files:
- Path normalization (Windows-specific paths -> $HOME/.claude/)
- /swarm removal (functionmap.md only)

Also handles version management:
- Reads VERSION file as single source of truth
- Auto-bumps patch (Z) when synced files have actual changes
- Propagates version to __version__, README badge, CHANGELOG header

Usage:
    python sync.py              # Full sync (auto-bumps patch if changes detected)
    python sync.py --dry-run    # Show what would change without writing
    python sync.py --minor      # Bump minor version (Y), reset patch
    python sync.py --major      # Bump major version (X), reset minor + patch
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLAUDE_HOME         = Path.home() / ".claude"
REPO_ROOT           = Path(__file__).resolve().parent
SRC_DIR             = REPO_ROOT / "src"
SUBSTITUTIONS_FILE  = REPO_ROOT / "substitutions.local.json"

# Source -> destination mappings (relative to CLAUDE_HOME and SRC_DIR)
PYTHON_TOOLS = [
    ("tools/functionmap/functionmap.py", "tools/functionmap.py"),
    ("tools/functionmap/categorize.py",  "tools/categorize.py"),
    ("tools/functionmap/quickmap.py",    "tools/quickmap.py"),
    ("tools/functionmap/thirdparty.py",  "tools/thirdparty.py"),
    ("tools/functionmap/describe.py",    "tools/describe.py"),
]

JS_TOOLS = [
    ("tools/functionmap/build-callgraph.cjs", "tools/build-callgraph.cjs"),
]

SKILL_FILES = [
    ("commands/functionmap.md",        "commands/functionmap.md"),
    ("commands/functionmap-update.md", "commands/functionmap-update.md"),
]

HELP_DOCS = [
    ("docs/functionmap-help.md",  "docs/functionmap-help.md"),
    ("docs/functionmap-mcp.md",   "docs/functionmap-mcp.md"),
]

MCP_FILES = [
    ("functionmap-mcp/server.py",        "mcp/server.py"),
    ("functionmap-mcp/index.py",         "mcp/index.py"),
    ("functionmap-mcp/search.py",        "mcp/search.py"),
    ("functionmap-mcp/requirements.txt", "mcp/requirements.txt"),
]

# ANSI color codes
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

def normalize_paths(content: str) -> str:
    """Replace platform-specific path references with cross-platform $HOME equivalents.

    Auto-detects the current user's home directory and generates replacement
    patterns for both backslash and forward-slash variants. Also handles
    generic %USERPROFILE% and $USERPROFILE references.
    """
    result = content

    # Build home-directory patterns dynamically (no hardcoded usernames)
    home = str(Path.home())
    home_fwd = home.replace("\\", "/")
    home_bk  = home.replace("/", "\\")

    literal_replacements = [
        (home_bk  + "\\.claude\\",  "$HOME/.claude/"),
        (home_fwd + "/.claude/",    "$HOME/.claude/"),
        (home_bk  + "\\.claude",    "$HOME/.claude"),
        (home_fwd + "/.claude",     "$HOME/.claude"),
        ("%USERPROFILE%\\.claude\\", "$HOME/.claude/"),
        ("%USERPROFILE%/.claude/",   "$HOME/.claude/"),
        ("$USERPROFILE/.claude/",    "$HOME/.claude/"),
    ]
    for old, new in literal_replacements:
        result = result.replace(old, new)

    # Normalize backslash paths in .claude/ contexts that remain after literal replacement.
    # Match patterns like $HOME/.claude\tools\functionmap\ and convert backslashes to forward slashes.
    # This catches paths that were partially normalized but still have internal backslashes.
    def _fix_claude_backslashes(m: re.Match) -> str:
        return m.group(0).replace("\\", "/")

    result = re.sub(r'\$HOME/\.claude[\\\/][^\s"\'`\n]*', _fix_claude_backslashes, result)

    return result


# ---------------------------------------------------------------------------
# Version management (VERSION file is the single source of truth)
# ---------------------------------------------------------------------------

VERSION_FILE = REPO_ROOT / "VERSION"


def read_version() -> str:
    """Read the current version from the VERSION file."""
    if not VERSION_FILE.exists():
        return "0.0.0"
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def write_version(version: str) -> None:
    """Write a version string to the VERSION file."""
    VERSION_FILE.write_text(version + "\n", encoding="utf-8", newline="\n")


def bump_version(version: str, part: str) -> str:
    """Bump a semver version string by part ('major', 'minor', or 'patch').

        bump_version("1.2.3", "patch") -> "1.2.4"
        bump_version("1.2.3", "minor") -> "1.3.0"
        bump_version("1.2.3", "major") -> "2.0.0"
    """
    parts = version.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"{major}.{minor}.{patch}"


def patch_py_version(file_path: Path, version: str, dry_run: bool = False) -> bool:
    """Replace __version__ = "..." in a Python file. Returns True if changed.

    Preserves the file's original line endings (CRLF or LF).
    Reads via read_text() so \r\n is normalized to \n, then writes back
    with the detected newline style.
    """
    raw = file_path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw[:2000] else "\n"

    # read_text normalizes \r\n to \n -- safe for regex + write_text(newline=...)
    content = file_path.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'(__version__\s*=\s*")[^"]*(")',
        rf'\g<1>{version}\2',
        content,
        count=1,
    )
    if count == 0 or new_content == content:
        return False
    if not dry_run:
        file_path.write_text(new_content, encoding="utf-8", newline=newline)
    return True


def patch_readme_badge(version: str, dry_run: bool = False) -> bool:
    """Update the version badge in README.md. Returns True if changed."""
    readme = REPO_ROOT / "README.md"
    if not readme.exists():
        return False
    content = readme.read_text(encoding="utf-8")
    new_content = re.sub(
        r'!\[Version\]\(https://img\.shields\.io/badge/version-[^)]*\)',
        f'![Version](https://img.shields.io/badge/version-{version}-blue)',
        content,
    )
    if new_content == content:
        return False
    if not dry_run:
        readme.write_text(new_content, encoding="utf-8", newline="\n")
    return True


def patch_changelog_header(version: str, dry_run: bool = False) -> bool:
    """Update the latest ## [X.Y.Z] header in CHANGELOG.md. Returns True if changed."""
    changelog = REPO_ROOT / "CHANGELOG.md"
    if not changelog.exists():
        return False
    content = changelog.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'^(## \[)\d+\.\d+\.\d+(\])',
        rf'\g<1>{version}\2',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0 or new_content == content:
        return False
    if not dry_run:
        changelog.write_text(new_content, encoding="utf-8", newline="\n")
    return True


# ---------------------------------------------------------------------------
# Project-specific substitutions
# ---------------------------------------------------------------------------

def load_substitutions() -> dict[str, str]:
    """Load project-specific substitutions from substitutions.local.json.

    Returns empty dict if file doesn't exist.
    For path entries (containing / with a drive letter or absolute prefix),
    auto-generates single-backslash and double-backslash variants.
    """
    if not SUBSTITUTIONS_FILE.exists():
        return {}

    raw = json.loads(SUBSTITUTIONS_FILE.read_text(encoding="utf-8"))

    expanded: dict[str, str] = {}
    for key, value in raw.items():
        expanded[key] = value

        # Auto-generate backslash variants for path entries
        is_path = "/" in key and (len(key) > 2 and key[1] == ":" or key.startswith("/"))
        if is_path:
            # Single backslash: D:/_Source/ -> D:\_Source\
            single = key.replace("/", "\\")
            expanded[single] = value

            # Double backslash: D:/_Source/ -> D:\\_Source\\ (JSON-in-markdown contexts)
            double = key.replace("/", "\\\\")
            expanded[double] = value

    return expanded


def apply_substitutions(content: str, substitutions: dict[str, str]) -> str:
    """Apply substitutions to content, longest keys first to prevent partial matches."""
    if not substitutions:
        return content

    sorted_subs = sorted(substitutions.items(), key=lambda x: len(x[0]), reverse=True)

    for old, new in sorted_subs:
        content = content.replace(old, new)

    # Normalize remaining backslashes in ~/paths (substitution may leave mixed slashes)
    def _fix_backslashes(m: re.Match) -> str:
        return m.group(0).replace("\\", "/")

    content = re.sub(r'~/[^\s"\'`\n]*\\[^\s"\'`\n]*', _fix_backslashes, content)

    return content


# ---------------------------------------------------------------------------
# /swarm removal (functionmap.md only)
# ---------------------------------------------------------------------------

def remove_swarm(content: str) -> tuple[str, list[str]]:
    """Remove /swarm-related content from functionmap.md distribution copy.

    Returns:
        (transformed_content, list_of_warnings)

    If no swarm markers are found at all, swarm has already been removed from
    the source -- return silently with no warnings. Only warn if some markers
    are present but others are missing (partial/broken state).
    """
    # Quick check: if no swarm indicators exist, it's already clean
    has_any_swarm = bool(re.search(r'/swarm|swarm deep|Deep check \(swarm\)', content, re.IGNORECASE))
    if not has_any_swarm:
        return content, []

    result = content
    warnings = []

    # -----------------------------------------------------------------------
    # 1. YAML front-matter: remove "+ /swarm deep checks" from description
    # -----------------------------------------------------------------------
    marker = "+ /swarm deep checks"
    if marker in result:
        result = result.replace(marker, "")
        # Clean up any double spaces left behind
        result = re.sub(r'(description:.*?),?\s*\.\s*$', r'\1.', result, flags=re.MULTILINE)
    else:
        warnings.append(f"YAML front-matter: marker not found: '{marker}'")

    # -----------------------------------------------------------------------
    # 2. Non-negotiable #4: remove /swarm bullet points, keep automated verification
    # -----------------------------------------------------------------------
    marker_nn4 = "/swarm deep-check"
    if marker_nn4 in result:
        # Remove bullet lines referencing /swarm
        result = re.sub(
            r'^[ \t]*-\s+/swarm deep-check.*$\n?',
            '',
            result,
            flags=re.MULTILINE
        )
        # Remove "Both MUST run" line that references both checks
        result = re.sub(
            r'^[ \t]*-\s+Both MUST run\..*$\n?',
            '',
            result,
            flags=re.MULTILINE
        )
    else:
        warnings.append(f"Non-negotiable #4: marker not found: '{marker_nn4}'")

    # -----------------------------------------------------------------------
    # 3. Phase 5 block: remove everything from "## Phase 5" up to "## Phase 6"
    # -----------------------------------------------------------------------
    marker_p5 = "## Phase 5"
    marker_p6 = "## Phase 6"
    if marker_p5 in result and marker_p6 in result:
        # Find the swarm phase (Phase 5 -- /swarm deep verification)
        p5_match = re.search(r'^## Phase 5\b', result, flags=re.MULTILINE)
        p6_match = re.search(r'^## Phase 6\b', result, flags=re.MULTILINE)
        if p5_match and p6_match and p5_match.start() < p6_match.start():
            # Also remove the preceding "---" separator if present
            remove_start = p5_match.start()
            before_p5 = result[:remove_start].rstrip()
            if before_p5.endswith("---"):
                remove_start = before_p5.rfind("---")
            result = result[:remove_start] + "\n\n" + result[p6_match.start():]
    else:
        if marker_p5 not in result:
            warnings.append(f"Phase 5 block: marker not found: '{marker_p5}'")
        if marker_p6 not in result:
            warnings.append(f"Phase 5 block: marker not found: '{marker_p6}'")

    # -----------------------------------------------------------------------
    # 4. Phase 6 renumber: "## Phase 6" -> "## Phase 5"
    # -----------------------------------------------------------------------
    if "## Phase 6" in result:
        result = result.replace("## Phase 6", "## Phase 5")
        result = result.replace("Phase 6", "Phase 5")
    else:
        # Only warn if we didn't already remove it (which we shouldn't have)
        if "## Phase 5 --" not in result or "Usability" not in result:
            warnings.append("Phase 6 renumber: '## Phase 6' not found after Phase 5 removal")

    # -----------------------------------------------------------------------
    # 5. Quick reference: remove swarm line and renumber
    # -----------------------------------------------------------------------
    # The phase flow list has numbered items. Remove the swarm line.
    swarm_flow_marker = "**Swarm**"
    if swarm_flow_marker in result:
        result = re.sub(
            r'^[ \t]*\d+\.\s+\*\*Swarm\*\*.*$\n?',
            '',
            result,
            flags=re.MULTILINE
        )
        # Renumber the remaining list items in the quick reference section
        # Find the "## Quick reference" section and renumber within it
        qr_match = re.search(r'(## Quick reference.*?\n)((?:[ \t]*\d+\..*\n?)+)', result, flags=re.DOTALL)
        if qr_match:
            prefix = qr_match.group(1)
            list_block = qr_match.group(2)
            lines = list_block.split('\n')
            renumbered = []
            num = 1
            for line in lines:
                numbered = re.match(r'^([ \t]*)\d+\.(.*)$', line)
                if numbered:
                    renumbered.append(f"{numbered.group(1)}{num}.{numbered.group(2)}")
                    num += 1
                else:
                    renumbered.append(line)
            result = result[:qr_match.start(2)] + '\n'.join(renumbered) + result[qr_match.end(2):]
    else:
        warnings.append(f"Quick reference: marker not found: '{swarm_flow_marker}'")

    # -----------------------------------------------------------------------
    # 6. Final checklist: remove swarm-related items
    # -----------------------------------------------------------------------
    checklist_swarm_markers = [
        "Swarm deep-check ran",
        "swarm deep-check ran",
        "5 agents reported back",
    ]
    found_checklist_marker = False
    for cm in checklist_swarm_markers:
        if cm in result:
            found_checklist_marker = True
            # Remove the entire checklist line containing the marker
            result = re.sub(
                rf'^[ \t]*-\s*\[[ x]\]\s*.*{re.escape(cm)}.*$\n?',
                '',
                result,
                flags=re.MULTILINE
            )
    if not found_checklist_marker:
        warnings.append("Final checklist: no swarm-related checklist items found")

    # -----------------------------------------------------------------------
    # 7. Verification results template: remove swarm/deep-check section
    # -----------------------------------------------------------------------
    # Remove the deep check output block from the final summary template
    deep_check_marker = "Deep check (swarm)"
    if deep_check_marker in result:
        # Remove from the deep check line through the swarm-related blocks
        # Pattern: the line with the marker, then subsequent lines until next section marker
        result = re.sub(
            r'^\S*\s*Deep check \(swarm\):.*$\n?',
            '',
            result,
            flags=re.MULTILINE
        )
        result = re.sub(
            r'^\n?\{swarm_summary\}\s*$\n?',
            '',
            result,
            flags=re.MULTILINE
        )
        # Remove "Likely missing patterns" block (swarm output)
        result = re.sub(
            r'^.*Likely missing patterns:.*$\n(?:^[ \t]*-\s+\{pattern.*$\n?)*',
            '',
            result,
            flags=re.MULTILINE
        )
        # Remove "Duplication issues" block (swarm output)
        result = re.sub(
            r'^.*Duplication issues:.*$\n(?:^[ \t]*-\s+\{duplication.*$\n?)*',
            '',
            result,
            flags=re.MULTILINE
        )
    else:
        warnings.append(f"Verification template: marker not found: '{deep_check_marker}'")

    # -----------------------------------------------------------------------
    # 8. Phase 4 prose: remove forward references to swarm
    # -----------------------------------------------------------------------
    swarm_forward_refs = [
        (r'[ \t]*-\s*Proceed to swarm.*$', "Proceed to swarm"),
        (r'[ \t]*-\s*Swarm will investigate.*$', "Swarm will investigate"),
        (r'[ \t]*-\s*Swarm MUST identify.*$', "Swarm MUST identify"),
        (r'Proceeding anyway -- swarm verification will investigate\.', "swarm verification will investigate"),
        (r'swarm will investigate', "swarm will investigate"),
        (r'Proceed to swarm deep-check \(still required\)', "Proceed to swarm deep-check"),
        (r'\s*-\s*Swarm will investigate\s*$', "Swarm will investigate (line)"),
    ]
    for pattern, desc in swarm_forward_refs:
        if re.search(pattern, result, flags=re.MULTILINE | re.IGNORECASE):
            result = re.sub(pattern, '', result, flags=re.MULTILINE | re.IGNORECASE)

    # Also clean up "- Proceed to swarm" style lines that appear in verification interpretation
    result = re.sub(r'^[ \t]*- Proceed to swarm.*$\n?', '', result, flags=re.MULTILINE)
    result = re.sub(r'^[ \t]*- Swarm .*$\n?', '', result, flags=re.MULTILINE)

    # Clean up prose references to "or swarm" in general text
    result = result.replace("or swarm found issues", "found issues")
    result = result.replace("verification or swarm", "verification")

    # -----------------------------------------------------------------------
    # 9. Philosophy section: fix phase count references
    # -----------------------------------------------------------------------
    # "all 3 phases (generate, verify, swarm)" -> "all phases (extract, taxonomy, categorize, verify, usability)"
    result = re.sub(
        r'all 3 phases \(generate, verify, swarm\)',
        'all phases (extract, taxonomy, categorize, verify, usability)',
        result
    )
    # "Always run all 3 phases" -> "Always run all phases"
    result = re.sub(r'run all 3 phases', 'run all phases', result)

    # -----------------------------------------------------------------------
    # Clean up: remove triple+ blank lines left by removals
    # -----------------------------------------------------------------------
    result = re.sub(r'\n{4,}', '\n\n\n', result)

    return result, warnings


# ---------------------------------------------------------------------------
# File sync
# ---------------------------------------------------------------------------

def sync_file(src: Path, dst: Path, transforms: list[str] | None = None,
              dry_run: bool = False,
              substitutions: dict[str, str] | None = None) -> dict:
    """Copy a file from src to dst, optionally applying transforms.

    Args:
        src: Source file path
        dst: Destination file path
        transforms: List of transform names to apply. Options:
            - "normalize_paths"
            - "remove_swarm"
        dry_run: If True, do not write files
        substitutions: Project-specific string replacements (loaded from substitutions.local.json)

    Returns:
        dict with keys: src, dst, src_lines, dst_lines, warnings, skipped, changed
    """
    transforms = transforms or []
    stats = {
        "src":       src,
        "dst":       dst,
        "src_lines": 0,
        "dst_lines": 0,
        "warnings":  [],
        "skipped":   False,
        "changed":   False,
    }

    if not src.exists():
        stats["warnings"].append(f"Source not found: {src}")
        stats["skipped"] = True
        return stats

    content = src.read_text(encoding="utf-8")
    stats["src_lines"] = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

    if "normalize_paths" in transforms:
        content = normalize_paths(content)

    if "remove_swarm" in transforms:
        content, swarm_warnings = remove_swarm(content)
        stats["warnings"].extend(swarm_warnings)

    if substitutions:
        content = apply_substitutions(content, substitutions)

    stats["dst_lines"] = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

    # Detect whether the file actually changed
    if dst.exists():
        existing = dst.read_text(encoding="utf-8")
        stats["changed"] = (content != existing)
    else:
        stats["changed"] = True  # New file = always a change

    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8", newline="\n")

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    dry_run  = "--dry-run" in sys.argv
    do_minor = "--minor" in sys.argv
    do_major = "--major" in sys.argv

    print()
    print(f"  {BOLD}FUNCTIONMAP SYNC{RESET}")
    if dry_run:
        print(f"  {YELLOW}(dry run -- no files will be written){RESET}")
    print()

    # -----------------------------------------------------------------------
    # Load substitutions
    # -----------------------------------------------------------------------
    substitutions = load_substitutions()
    if substitutions:
        # Count original entries (before backslash expansion)
        raw_count = 0
        if SUBSTITUTIONS_FILE.exists():
            raw_count = len(json.loads(SUBSTITUTIONS_FILE.read_text(encoding="utf-8")))
        print(f"  {GREEN}Substitutions loaded: {raw_count} entries ({len(substitutions)} with variants){RESET}")
    else:
        print(f"  {YELLOW}No substitutions.local.json found (personal paths will not be sanitized){RESET}")
    print()

    # -----------------------------------------------------------------------
    # Verify all source files exist
    # -----------------------------------------------------------------------
    all_sources = PYTHON_TOOLS + JS_TOOLS + SKILL_FILES + HELP_DOCS + MCP_FILES
    missing = []
    for src_rel, _ in all_sources:
        src_path = CLAUDE_HOME / src_rel
        if not src_path.exists():
            missing.append(str(src_path))

    if missing:
        print(f"  {RED}ERROR: Source files not found:{RESET}")
        for m in missing:
            print(f"    - {m}")
        print()
        print(f"  Ensure the functionmap tools are installed in {CLAUDE_HOME}")
        return 1

    # -----------------------------------------------------------------------
    # Sync Python tools (verbatim copy)
    # -----------------------------------------------------------------------
    print(f"  {CYAN}Python tools:{RESET}")
    tool_stats = []
    for src_rel, dst_rel in PYTHON_TOOLS:
        src_path = CLAUDE_HOME / src_rel
        dst_path = SRC_DIR / dst_rel
        stats = sync_file(src_path, dst_path, dry_run=dry_run)
        tool_stats.append((dst_rel, stats))
        status = "would copy" if dry_run else "copied"
        name = Path(dst_rel).name
        print(f"    {GREEN}{name:<22}{RESET} [{status} - {stats['src_lines']:,} lines]")

    # -----------------------------------------------------------------------
    # Sync JS tools (verbatim copy)
    # -----------------------------------------------------------------------
    print()
    print(f"  {CYAN}JS tools:{RESET}")
    js_stats = []
    for src_rel, dst_rel in JS_TOOLS:
        src_path = CLAUDE_HOME / src_rel
        dst_path = SRC_DIR / dst_rel
        stats = sync_file(src_path, dst_path, dry_run=dry_run)
        js_stats.append((dst_rel, stats))
        status = "would copy" if dry_run else "copied"
        name = Path(dst_rel).name
        print(f"    {GREEN}{name:<22}{RESET} [{status} - {stats['src_lines']:,} lines]")

    # -----------------------------------------------------------------------
    # Sync skill files (with transforms)
    # -----------------------------------------------------------------------
    print()
    print(f"  {CYAN}Skill files:{RESET}")
    skill_stats = []
    for src_rel, dst_rel in SKILL_FILES:
        src_path = CLAUDE_HOME / src_rel
        dst_path = SRC_DIR / dst_rel

        transforms = ["normalize_paths"]
        if "functionmap.md" == Path(dst_rel).name:
            transforms.append("remove_swarm")

        stats = sync_file(src_path, dst_path, transforms=transforms, dry_run=dry_run, substitutions=substitutions)
        skill_stats.append((dst_rel, stats))

        name = Path(dst_rel).name
        status = "would sync" if dry_run else "synced"

        if "remove_swarm" in transforms:
            detail = f"paths + /swarm stripped"
        else:
            detail = "paths only"

        line_info = f"{stats['dst_lines']:,} lines"
        if stats['src_lines'] != stats['dst_lines']:
            line_info = f"{stats['dst_lines']:,} lines (was {stats['src_lines']:,})"

        print(f"    {GREEN}{name:<22}{RESET} [{status} - {line_info} -- {detail}]")

        for w in stats["warnings"]:
            print(f"      {YELLOW}WARNING: {w}{RESET}")

    # -----------------------------------------------------------------------
    # Sync help docs (path normalization only)
    # -----------------------------------------------------------------------
    print()
    print(f"  {CYAN}Help docs:{RESET}")
    doc_stats = []
    for src_rel, dst_rel in HELP_DOCS:
        src_path = CLAUDE_HOME / src_rel
        dst_path = SRC_DIR / dst_rel
        stats = sync_file(src_path, dst_path, transforms=["normalize_paths"], dry_run=dry_run, substitutions=substitutions)
        doc_stats.append((dst_rel, stats))

        name = Path(dst_rel).name
        status = "would sync" if dry_run else "synced"
        print(f"    {GREEN}{name:<22}{RESET} [{status} - {stats['dst_lines']:,} lines]")

    # -----------------------------------------------------------------------
    # Sync MCP server (verbatim copy)
    # -----------------------------------------------------------------------
    print()
    print(f"  {CYAN}MCP server:{RESET}")
    mcp_stats = []
    for src_rel, dst_rel in MCP_FILES:
        src_path = CLAUDE_HOME / src_rel
        dst_path = SRC_DIR / dst_rel
        stats = sync_file(src_path, dst_path, dry_run=dry_run)
        mcp_stats.append((dst_rel, stats))
        status = "would copy" if dry_run else "copied"
        name = Path(dst_rel).name
        print(f"    {GREEN}{name:<22}{RESET} [{status} - {stats['src_lines']:,} lines]")

    # -----------------------------------------------------------------------
    # Version management
    # -----------------------------------------------------------------------
    all_warnings = []
    print()
    print(f"  {CYAN}Version:{RESET}")

    old_version = read_version()

    # Determine if any synced files actually changed
    has_changes = any(
        stats["changed"]
        for _, stats in tool_stats + js_stats + skill_stats + doc_stats + mcp_stats
        if not stats["skipped"]
    )

    # Decide what to bump
    if do_major:
        new_version = bump_version(old_version, "major")
        bump_reason = "major bump (--major)"
    elif do_minor:
        new_version = bump_version(old_version, "minor")
        bump_reason = "minor bump (--minor)"
    elif has_changes:
        new_version = bump_version(old_version, "patch")
        bump_reason = "patch bump (changes detected)"
    else:
        new_version = old_version
        bump_reason = None

    if bump_reason:
        verb = "would bump" if dry_run else "bumped"
        print(f"    {GREEN}v{old_version} -> v{new_version}{RESET} [{verb}: {bump_reason}]")
        if not dry_run:
            write_version(new_version)
    else:
        print(f"    {GREEN}v{old_version}{RESET} [no changes, no bump]")

    # Propagate version to all targets
    src_py  = SRC_DIR / "tools" / "functionmap.py"
    live_py = CLAUDE_HOME / "tools" / "functionmap" / "functionmap.py"

    propagated = []
    if patch_py_version(src_py, new_version, dry_run=dry_run):
        propagated.append("src/__version__")
    if patch_py_version(live_py, new_version, dry_run=dry_run):
        propagated.append("live/__version__")
    if patch_readme_badge(new_version, dry_run=dry_run):
        propagated.append("README.md badge")
    if patch_changelog_header(new_version, dry_run=dry_run):
        propagated.append("CHANGELOG.md header")

    if propagated:
        verb = "would update" if dry_run else "updated"
        print(f"    {GREEN}Propagated:{RESET} {verb} {', '.join(propagated)}")

    # -----------------------------------------------------------------------
    # Collect all warnings
    # -----------------------------------------------------------------------
    for _, stats in tool_stats + js_stats + skill_stats + doc_stats + mcp_stats:
        all_warnings.extend(stats["warnings"])

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print(f"  {'=' * 60}")
    if dry_run:
        print(f"  {BOLD}  DRY RUN COMPLETE -- no files written{RESET}")
    else:
        print(f"  {BOLD}  SYNC COMPLETE{RESET}")
    print(f"  {'=' * 60}")

    total_files = len(tool_stats) + len(js_stats) + len(skill_stats) + len(doc_stats) + len(mcp_stats)
    print(f"  {total_files} files processed")

    if all_warnings:
        print()
        print(f"  {YELLOW}Warnings ({len(all_warnings)}):{RESET}")
        for w in all_warnings:
            print(f"    - {w}")

    if not dry_run:
        print()
        print(f"  {CYAN}Next steps:{RESET}")
        print(f"    1. Review changes:  git diff")
        print(f"    2. Commit & tag:    git add -A && git commit && git tag v{new_version}")

    print()
    return 1 if all_warnings else 0


if __name__ == "__main__":
    sys.exit(main())
