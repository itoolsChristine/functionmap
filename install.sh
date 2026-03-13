#!/usr/bin/env bash
# install.sh -- Functionmap installer for macOS / Linux / Windows Git Bash
# Usage: curl -fsSL https://raw.githubusercontent.com/itoolsChristine/functionmap/main/install.sh | bash
set -euo pipefail

# ============================================================================
#  Constants
# ============================================================================

REPO_URL="https://raw.githubusercontent.com/itoolsChristine/functionmap/main"
CLAUDE_DIR="$HOME/.claude"
TOOLS_DIR="$CLAUDE_DIR/tools/functionmap"
COMMANDS_DIR="$CLAUDE_DIR/commands"
DOCS_DIR="$CLAUDE_DIR/docs"
MAPS_DIR="$CLAUDE_DIR/functionmap"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"

# Files to install  (source-relative-path : destination)
TOOL_FILES="functionmap.py categorize.py quickmap.py thirdparty.py describe.py"
COMMAND_FILES="functionmap.md functionmap-update.md"
DOC_FILES="functionmap-help.md"

# ============================================================================
#  Banner
# ============================================================================

banner() {
    echo ""
    echo "  ============================================================"
    echo "    FUNCTIONMAP INSTALLER"
    echo "    Index every function so Claude finds before it builds."
    echo "  ============================================================"
    echo ""
}

# ============================================================================
#  Helpers
# ============================================================================

info()    { echo "  [INFO]  $*"; }
ok()      { echo "  [OK]    $*"; }
warn()    { echo "  [WARN]  $*"; }
fail()    { echo "  [ERROR] $*" >&2; exit 1; }

# ============================================================================
#  Pre-flight checks
# ============================================================================

preflight() {
    # Find Python
    PYTHON=""
    if command -v python3 &>/dev/null; then
        PYTHON="python3"
    elif command -v python &>/dev/null; then
        PYTHON="python"
    fi

    if [ -z "$PYTHON" ]; then
        fail "Python not found. Install Python 3.8+ and ensure it is in your PATH."
    fi

    # Verify Python version >= 3.8
    PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
        fail "Python 3.8+ required (found $PY_VERSION). Please upgrade Python."
    fi
    ok "Python $PY_VERSION ($PYTHON)"

    # Check Claude Code directory
    if [ ! -d "$CLAUDE_DIR" ]; then
        fail "$CLAUDE_DIR does not exist. Install and run Claude Code at least once first."
    fi
    ok "Claude Code directory exists"

    # Check write permissions
    if [ ! -w "$CLAUDE_DIR" ]; then
        fail "No write permission to $CLAUDE_DIR"
    fi
    ok "Write permissions verified"
}

# ============================================================================
#  Determine source mode (local clone vs. curl from GitHub)
# ============================================================================

detect_source() {
    # If this script is running from a cloned repo, src/ will exist nearby
    SCRIPT_DIR=""
    SOURCE_MODE="remote"

    # When piped from curl, BASH_SOURCE is empty
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ "${BASH_SOURCE[0]}" != "bash" ]; then
        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        if [ -d "$SCRIPT_DIR/src/tools" ] && [ -d "$SCRIPT_DIR/src/commands" ]; then
            SOURCE_MODE="local"
        fi
    fi

    if [ "$SOURCE_MODE" = "local" ]; then
        info "Installing from local clone: $SCRIPT_DIR"
    else
        info "Installing from GitHub: $REPO_URL"
    fi
}

# ============================================================================
#  File retrieval (local copy or curl download)
# ============================================================================

get_file() {
    local src_rel="$1"   # e.g. src/tools/functionmap.py
    local dest="$2"      # e.g. ~/.claude/tools/functionmap/functionmap.py

    if [ "$SOURCE_MODE" = "local" ]; then
        if [ ! -f "$SCRIPT_DIR/$src_rel" ]; then
            fail "Local file not found: $SCRIPT_DIR/$src_rel"
        fi
        cp "$SCRIPT_DIR/$src_rel" "$dest"
    else
        local url="$REPO_URL/$src_rel"
        if ! curl -fsSL "$url" -o "$dest" 2>/dev/null; then
            fail "Failed to download: $url"
        fi
    fi
}

# ============================================================================
#  Confirm before proceeding
# ============================================================================

confirm_install() {
    IS_UPGRADE=false
    local existing_tools=false
    local existing_cmds=false
    local existing_docs=false
    local existing_claude_md=false
    local existing_maps=false

    for f in $TOOL_FILES; do [ -f "$TOOLS_DIR/$f" ] && existing_tools=true && break; done
    for f in $COMMAND_FILES; do [ -f "$COMMANDS_DIR/$f" ] && existing_cmds=true && break; done
    for f in $DOC_FILES; do [ -f "$DOCS_DIR/$f" ] && existing_docs=true && break; done
    [ -f "$CLAUDE_MD" ] && existing_claude_md=true
    [ -d "$MAPS_DIR" ] && [ "$(ls -A "$MAPS_DIR" 2>/dev/null)" ] && existing_maps=true

    if $existing_tools || $existing_cmds || $existing_docs; then
        IS_UPGRADE=true
    fi

    echo ""
    if $IS_UPGRADE; then
        echo "  Existing functionmap installation detected."
        echo "  This will UPGRADE your installation."
    else
        echo "  This will install functionmap."
    fi

    echo ""
    echo "  The following will be backed up before any changes:"
    if $existing_tools; then echo "    - Python tools ($TOOLS_DIR)"; fi
    if $existing_cmds;  then echo "    - Skill commands (functionmap.md, functionmap-update.md)"; fi
    if $existing_docs;  then echo "    - Help documentation (functionmap-help.md)"; fi
    if $existing_claude_md; then echo "    - CLAUDE.md (sentinel blocks will be updated, not replaced)"; fi
    if $existing_maps;  then echo "    - Generated function maps ($MAPS_DIR)"; fi
    if ! $existing_tools && ! $existing_cmds && ! $existing_docs && ! $existing_claude_md && ! $existing_maps; then
        echo "    (nothing to back up -- fresh install)"
    fi

    echo ""
    if $IS_UPGRADE; then
        echo "  Your existing function maps will NOT be erased."
    fi

    echo ""
    # Default to NO if non-interactive (piped from curl)
    if [ -t 0 ]; then
        read -rp "  Continue? [y/N] " answer
    else
        # Non-interactive: proceed automatically (curl | bash usage)
        answer="y"
        info "Non-interactive mode: proceeding automatically"
    fi

    case "$answer" in
        [yY]|[yY][eE][sS]) ;;
        *)
            echo ""
            info "Installation cancelled."
            exit 0
            ;;
    esac
}

# ============================================================================
#  Pre-install backup (snapshot everything that will be overwritten)
# ============================================================================

BACKUP_DIR=""

backup_existing() {
    local has_existing=false

    # Check if any files exist that we're about to overwrite
    for f in $TOOL_FILES; do [ -f "$TOOLS_DIR/$f" ] && has_existing=true && break; done
    for f in $COMMAND_FILES; do [ -f "$COMMANDS_DIR/$f" ] && has_existing=true && break; done
    for f in $DOC_FILES; do [ -f "$DOCS_DIR/$f" ] && has_existing=true && break; done
    [ -f "$CLAUDE_MD" ] && has_existing=true

    if ! $has_existing; then
        info "Fresh install (no existing files to back up)"
        return
    fi

    BACKUP_DIR="$CLAUDE_DIR/.functionmap-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR/tools" "$BACKUP_DIR/commands" "$BACKUP_DIR/docs"

    # Back up Python tools
    for f in $TOOL_FILES; do
        [ -f "$TOOLS_DIR/$f" ] && cp "$TOOLS_DIR/$f" "$BACKUP_DIR/tools/$f"
    done
    [ -f "$TOOLS_DIR/.version" ] && cp "$TOOLS_DIR/.version" "$BACKUP_DIR/tools/.version"

    # Back up skill commands
    for f in $COMMAND_FILES; do
        [ -f "$COMMANDS_DIR/$f" ] && cp "$COMMANDS_DIR/$f" "$BACKUP_DIR/commands/$f"
    done

    # Back up docs
    for f in $DOC_FILES; do
        [ -f "$DOCS_DIR/$f" ] && cp "$DOCS_DIR/$f" "$BACKUP_DIR/docs/$f"
    done

    # Back up CLAUDE.md
    [ -f "$CLAUDE_MD" ] && cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md"

    # Back up generated function maps
    if [ -d "$MAPS_DIR" ] && [ "$(ls -A "$MAPS_DIR" 2>/dev/null)" ]; then
        cp -r "$MAPS_DIR" "$BACKUP_DIR/functionmap"
        ok "Function maps backed up"
    fi

    ok "Pre-install backup created: $BACKUP_DIR"
}

on_failure() {
    echo ""
    echo "  [ERROR] Installation failed!"
    if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
        echo ""
        echo "  Your original files were backed up before any changes."
        echo "  To restore, run:"
        echo ""
        echo "    # Restore tools"
        echo "    cp \"$BACKUP_DIR/tools/\"* \"$TOOLS_DIR/\" 2>/dev/null"
        echo "    # Restore commands"
        echo "    cp \"$BACKUP_DIR/commands/\"* \"$COMMANDS_DIR/\" 2>/dev/null"
        echo "    # Restore docs"
        echo "    cp \"$BACKUP_DIR/docs/\"* \"$DOCS_DIR/\" 2>/dev/null"
        echo "    # Restore CLAUDE.md"
        echo "    cp \"$BACKUP_DIR/CLAUDE.md\" \"$CLAUDE_MD\" 2>/dev/null"
        echo "    # Restore function maps"
        echo "    cp -r \"$BACKUP_DIR/functionmap/\"* \"$MAPS_DIR/\" 2>/dev/null"
        echo ""
        echo "  Backup location: $BACKUP_DIR"
    fi
}

# ============================================================================
#  Create directories
# ============================================================================

create_dirs() {
    mkdir -p "$TOOLS_DIR" "$COMMANDS_DIR" "$DOCS_DIR" "$MAPS_DIR"
    ok "Directories created"
}

# ============================================================================
#  Install files
# ============================================================================

install_files() {
    # Python tools
    for f in $TOOL_FILES; do
        get_file "src/tools/$f" "$TOOLS_DIR/$f"
    done
    ok "Python tools installed (5 files)"

    # Skill commands
    for f in $COMMAND_FILES; do
        get_file "src/commands/$f" "$COMMANDS_DIR/$f"
    done
    ok "Skill commands installed (2 files)"

    # Help docs
    for f in $DOC_FILES; do
        get_file "src/docs/$f" "$DOCS_DIR/$f"
    done
    ok "Help documentation installed (1 file)"
}

# ============================================================================
#  Write .version file
# ============================================================================

write_version() {
    local version
    version=$(grep -m1 '__version__' "$TOOLS_DIR/functionmap.py" | sed 's/.*"\(.*\)".*/\1/' 2>/dev/null || echo "unknown")
    echo "$version" > "$TOOLS_DIR/.version"
    ok "Version file written: $version"
}

# ============================================================================
#  CLAUDE.md injection
# ============================================================================

inject_claude_md() {
    local instr_file
    local registry_file

    # Load instruction and registry content
    if [ "$SOURCE_MODE" = "local" ]; then
        instr_file="$SCRIPT_DIR/src/claude-md/functionmap-instructions.md"
        registry_file="$SCRIPT_DIR/src/claude-md/functionmap-registry.md"
        if [ ! -f "$instr_file" ] || [ ! -f "$registry_file" ]; then
            fail "CLAUDE.md source files not found in src/claude-md/"
        fi
        INSTR_CONTENT=$(cat "$instr_file")
        REGISTRY_CONTENT=$(cat "$registry_file")
    else
        INSTR_CONTENT=$(curl -fsSL "$REPO_URL/src/claude-md/functionmap-instructions.md" 2>/dev/null) || fail "Failed to download functionmap-instructions.md"
        REGISTRY_CONTENT=$(curl -fsSL "$REPO_URL/src/claude-md/functionmap-registry.md" 2>/dev/null) || fail "Failed to download functionmap-registry.md"
    fi

    # Sentinel markers
    local INSTR_BEGIN="<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->"
    local INSTR_END="<!-- FUNCTIONMAP:INSTRUCTIONS:END -->"
    local REG_BEGIN="<!-- FUNCTIONMAP:BEGIN -->"
    local REG_END="<!-- FUNCTIONMAP:END -->"

    # Case 1: No CLAUDE.md -- create it
    if [ ! -f "$CLAUDE_MD" ]; then
        {
            echo "# CLAUDE.md"
            echo ""
            echo "$INSTR_CONTENT"
            echo ""
            echo "$REGISTRY_CONTENT"
        } > "$CLAUDE_MD"
        ok "Created $CLAUDE_MD with both blocks"
        return
    fi

    # Create backup before any modification
    cp "$CLAUDE_MD" "$CLAUDE_MD.bak"
    info "Backup created: CLAUDE.md.bak"

    local content
    content=$(cat "$CLAUDE_MD")

    # Check for existing "Function Maps" heading without sentinels
    if echo "$content" | grep -q "Function Maps" && ! echo "$content" | grep -q "$INSTR_BEGIN"; then
        warn "Found existing \"Function Maps\" section in CLAUDE.md without sentinel markers."
        warn "The installer will append sentinel-wrapped blocks at the end of the file."
        warn "You may want to manually remove the old section to avoid duplication."
    fi

    local has_instr_sentinels=false
    local has_reg_sentinels=false
    echo "$content" | grep -q "$INSTR_BEGIN" && has_instr_sentinels=true
    echo "$content" | grep -q "$REG_BEGIN" && has_reg_sentinels=true

    # --- Instructions block ---
    if $has_instr_sentinels; then
        # Extract existing instructions block for comparison
        local existing_instr
        existing_instr=$(echo "$content" | awk '
            /<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->/{found=1}
            found{print}
            /<!-- FUNCTIONMAP:INSTRUCTIONS:END -->/{exit}
        ')
        if [ "$existing_instr" = "$INSTR_CONTENT" ]; then
            ok "Instructions block is up to date"
        else
            content=$(echo "$content" | awk -v new="$INSTR_CONTENT" '
                /<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->/{found=1; print new; next}
                /<!-- FUNCTIONMAP:INSTRUCTIONS:END -->/{found=0; next}
                !found{print}
            ')
            ok "Updated instructions block in CLAUDE.md"
        fi
    fi

    # --- Registry block ---
    if $has_reg_sentinels; then
        # Extract existing map entries (the "- **name**..." lines) and preserve them
        local existing_entries
        existing_entries=$(echo "$content" | awk '
            /<!-- FUNCTIONMAP:BEGIN -->/{found=1; next}
            /<!-- FUNCTIONMAP:END -->/{found=0; next}
            found && /^- \*\*/{print}
        ')
        # Rebuild registry: template format + preserved entries
        local rebuilt_registry
        rebuilt_registry="$REG_BEGIN"$'\n'"### Available maps (auto-generated -- do not edit):"
        if [ -n "$existing_entries" ]; then
            rebuilt_registry="$rebuilt_registry"$'\n'"$existing_entries"
        fi
        rebuilt_registry="$rebuilt_registry"$'\n\n'"$REG_END"
        # Replace existing registry block with rebuilt version
        content=$(echo "$content" | awk -v new="$rebuilt_registry" '
            /<!-- FUNCTIONMAP:BEGIN -->/{found=1; print new; next}
            /<!-- FUNCTIONMAP:END -->/{found=0; next}
            !found{print}
        ')
        if [ -n "$existing_entries" ]; then
            ok "Preserved existing map entries in registry block"
        else
            ok "Registry block is up to date"
        fi
    fi

    # --- Add missing blocks (instructions always before registry) ---
    if ! $has_instr_sentinels; then
        if $has_reg_sentinels; then
            # Registry exists -- insert instructions BEFORE it
            content=$(echo "$content" | awk -v new="$INSTR_CONTENT" '
                /<!-- FUNCTIONMAP:BEGIN -->/{print new; print ""; print ""}
                {print}
            ')
            ok "Inserted instructions block before registry in CLAUDE.md"
        else
            content="$content"$'\n\n'"$INSTR_CONTENT"
            ok "Appended instructions block to CLAUDE.md"
        fi
    fi

    if ! $has_reg_sentinels; then
        content="$content"$'\n\n'"$REGISTRY_CONTENT"
        ok "Appended registry block to CLAUDE.md"
    fi

    echo "$content" > "$CLAUDE_MD"
}

# ============================================================================
#  Post-install verification
# ============================================================================

verify() {
    local errors=0

    # Check Python can run functionmap.py --version
    if ! $PYTHON "$TOOLS_DIR/functionmap.py" --version &>/dev/null; then
        warn "functionmap.py --version failed"
        errors=$((errors + 1))
    fi

    # Verify all expected files exist
    local expected_files=(
        "$TOOLS_DIR/functionmap.py"
        "$TOOLS_DIR/categorize.py"
        "$TOOLS_DIR/quickmap.py"
        "$TOOLS_DIR/thirdparty.py"
        "$TOOLS_DIR/describe.py"
        "$COMMANDS_DIR/functionmap.md"
        "$COMMANDS_DIR/functionmap-update.md"
        "$DOCS_DIR/functionmap-help.md"
    )
    for f in "${expected_files[@]}"; do
        if [ ! -f "$f" ]; then
            warn "Missing: $f"
            errors=$((errors + 1))
        fi
    done

    # Verify CLAUDE.md has both sentinel pairs
    if [ -f "$CLAUDE_MD" ]; then
        if ! grep -q "FUNCTIONMAP:INSTRUCTIONS:BEGIN" "$CLAUDE_MD"; then
            warn "CLAUDE.md missing instructions sentinel"
            errors=$((errors + 1))
        fi
        if ! grep -q "FUNCTIONMAP:BEGIN" "$CLAUDE_MD"; then
            warn "CLAUDE.md missing registry sentinel"
            errors=$((errors + 1))
        fi
    else
        warn "CLAUDE.md not found after install"
        errors=$((errors + 1))
    fi

    if [ $errors -eq 0 ]; then
        ok "All 8 files verified"
        ok "CLAUDE.md sentinels verified"
    else
        warn "$errors verification issue(s) found"
    fi

    return $errors
}

# ============================================================================
#  Success message
# ============================================================================

success_message() {
    local version
    version=$(cat "$TOOLS_DIR/.version" 2>/dev/null || echo "unknown")

    echo ""
    echo "  ============================================================"
    echo "    FUNCTIONMAP v$version INSTALLED SUCCESSFULLY"
    echo "  ============================================================"
    echo ""
    echo "    Usage (in Claude Code):"
    echo "      /functionmap          Full index of a project"
    echo "      /functionmap-update   Incremental update (changed files only)"
    echo "      /functionmap help     Show detailed help"
    echo ""
    echo "    To update:  Re-run this installer"
    echo "    To remove:  curl -fsSL $REPO_URL/uninstall.sh | bash"
    echo ""
    echo "  ============================================================"
    echo ""
}

# ============================================================================
#  Main
# ============================================================================

main() {
    banner
    preflight
    detect_source
    confirm_install
    backup_existing
    trap on_failure ERR
    create_dirs
    install_files
    write_version
    inject_claude_md
    trap - ERR
    verify || true
    success_message
    if [ -n "$BACKUP_DIR" ]; then
        info "Pre-install backup: $BACKUP_DIR"
    fi
}

main
