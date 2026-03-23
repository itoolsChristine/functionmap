#!/usr/bin/env bash
# uninstall.sh -- Functionmap uninstaller for macOS / Linux / Windows Git Bash
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
TOOLS_DIR="$CLAUDE_DIR/tools/functionmap"
COMMANDS_DIR="$CLAUDE_DIR/commands"
DOCS_DIR="$CLAUDE_DIR/docs"
MAPS_DIR="$CLAUDE_DIR/functionmap"
MCP_DIR="$CLAUDE_DIR/functionmap-mcp"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
CLAUDE_JSON="$HOME/.claude.json"

# ============================================================================
#  Banner
# ============================================================================

echo ""
echo "  ============================================================"
echo "    FUNCTIONMAP UNINSTALLER"
echo "  ============================================================"
echo ""

info()  { echo "  [INFO]  $*"; }
ok()    { echo "  [OK]    $*"; }
warn()  { echo "  [WARN]  $*"; }

# ============================================================================
#  Confirm before proceeding
# ============================================================================

has_tools=false
has_cmds=false
has_docs=false
has_mcp=false
has_claude_md=false
has_maps=false

[ -d "$TOOLS_DIR" ] && has_tools=true
[ -f "$COMMANDS_DIR/functionmap.md" ] || [ -f "$COMMANDS_DIR/functionmap-update.md" ] && has_cmds=true
[ -f "$DOCS_DIR/functionmap-help.md" ] || [ -f "$DOCS_DIR/functionmap-mcp.md" ] && has_docs=true
[ -d "$MCP_DIR" ] && has_mcp=true
[ -f "$CLAUDE_MD" ] && has_claude_md=true
[ -d "$MAPS_DIR" ] && [ "$(ls -A "$MAPS_DIR" 2>/dev/null)" ] && has_maps=true

if ! $has_tools && ! $has_cmds && ! $has_docs && ! $has_mcp; then
    info "Functionmap does not appear to be installed. Nothing to uninstall."
    exit 0
fi

echo "  This will uninstall functionmap."
echo ""
echo "  The following will be backed up before removal:"
if $has_tools;     then echo "    - Python tools ($TOOLS_DIR)"; fi
if $has_cmds;      then echo "    - Skill commands (functionmap.md, functionmap-update.md)"; fi
if $has_docs;      then echo "    - Help documentation (functionmap-help.md)"; fi
if $has_mcp;       then echo "    - MCP server ($MCP_DIR)"; fi
if $has_claude_md; then echo "    - CLAUDE.md (functionmap sentinel blocks will be removed)"; fi
if $has_maps;      then echo "    - Generated function maps ($MAPS_DIR)"; fi
echo ""
echo "  Your generated function maps will NOT be deleted unless you choose to."
echo ""

# Default to NO if non-interactive (piped from curl)
if [ -t 0 ]; then
    read -rp "  Continue? [y/N] " answer
else
    answer="y"
    info "Non-interactive mode: proceeding automatically"
fi

case "$answer" in
    [yY]|[yY][eE][sS]) ;;
    *)
        echo ""
        info "Uninstall cancelled."
        exit 0
        ;;
esac

# ============================================================================
#  Pre-uninstall backup (snapshot everything before deletion)
# ============================================================================

BACKUP_DIR=""
has_existing=false

[ -d "$TOOLS_DIR" ] && has_existing=true
[ -f "$COMMANDS_DIR/functionmap.md" ] && has_existing=true
[ -f "$COMMANDS_DIR/functionmap-update.md" ] && has_existing=true
[ -f "$DOCS_DIR/functionmap-help.md" ] && has_existing=true
[ -f "$DOCS_DIR/functionmap-mcp.md" ] && has_existing=true
[ -d "$MCP_DIR" ] && has_existing=true

if $has_existing; then
    BACKUP_DIR="$CLAUDE_DIR/.functionmap-backup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR/tools" "$BACKUP_DIR/commands" "$BACKUP_DIR/docs"

    # Back up tools directory
    if [ -d "$TOOLS_DIR" ]; then
        cp -r "$TOOLS_DIR"/* "$BACKUP_DIR/tools/" 2>/dev/null || true
    fi

    # Back up commands
    for f in functionmap.md functionmap-update.md; do
        [ -f "$COMMANDS_DIR/$f" ] && cp "$COMMANDS_DIR/$f" "$BACKUP_DIR/commands/$f"
    done

    # Back up docs
    for f in functionmap-help.md functionmap-mcp.md; do
        [ -f "$DOCS_DIR/$f" ] && cp "$DOCS_DIR/$f" "$BACKUP_DIR/docs/"
    done

    # Back up MCP server
    if [ -d "$MCP_DIR" ]; then
        mkdir -p "$BACKUP_DIR/mcp"
        cp "$MCP_DIR"/* "$BACKUP_DIR/mcp/" 2>/dev/null || true
    fi

    # Back up CLAUDE.md
    [ -f "$CLAUDE_MD" ] && cp "$CLAUDE_MD" "$BACKUP_DIR/CLAUDE.md"

    # Back up generated function maps
    if [ -d "$MAPS_DIR" ] && [ "$(ls -A "$MAPS_DIR" 2>/dev/null)" ]; then
        cp -r "$MAPS_DIR" "$BACKUP_DIR/functionmap"
        ok "Function maps backed up"
    fi

    ok "Pre-uninstall backup created: $BACKUP_DIR"
else
    info "No existing files found to back up"
fi

# ============================================================================
#  Remove installed files
# ============================================================================

# Tools directory (entire folder)
if [ -d "$TOOLS_DIR" ]; then
    rm -rf "$TOOLS_DIR"
    ok "Removed $TOOLS_DIR"
else
    info "Tools directory not found (already removed?)"
fi

# Skill commands
for f in functionmap.md functionmap-update.md; do
    target="$COMMANDS_DIR/$f"
    if [ -f "$target" ]; then
        rm -f "$target"
        ok "Removed $target"
    fi
done

# Help docs
for f in functionmap-help.md functionmap-mcp.md; do
    target="$DOCS_DIR/$f"
    if [ -f "$target" ]; then
        rm -f "$target"
        ok "Removed $target"
    fi
done

# MCP server
if [ -d "$MCP_DIR" ]; then
    rm -rf "$MCP_DIR"
    ok "Removed $MCP_DIR"
else
    info "MCP server directory not found (already removed?)"
fi

# Deregister from .claude.json
if [ -f "$CLAUDE_JSON" ]; then
    PYTHON=""
    command -v python3 &>/dev/null && PYTHON="python3" || PYTHON="python"
    if [ -n "$PYTHON" ]; then
        $PYTHON - "$CLAUDE_JSON" << 'PYEOF' 2>/dev/null && ok "MCP server deregistered from .claude.json"
import json, sys
path = sys.argv[1]
try:
    with open(path, 'r') as f:
        data = json.load(f)
    if 'functionmap' in data.get('mcpServers', {}):
        del data['mcpServers']['functionmap']
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
except (FileNotFoundError, json.JSONDecodeError):
    pass
PYEOF
    fi
fi

# ============================================================================
#  Remove sentinel blocks from CLAUDE.md
# ============================================================================

if [ -f "$CLAUDE_MD" ]; then
    # Create backup
    cp "$CLAUDE_MD" "$CLAUDE_MD.bak"
    info "Backup created: CLAUDE.md.bak"

    content=$(cat "$CLAUDE_MD")
    modified=false

    # Remove INSTRUCTIONS block (inclusive of sentinels)
    if echo "$content" | grep -q "FUNCTIONMAP:INSTRUCTIONS:BEGIN"; then
        content=$(echo "$content" | awk '
            /<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->/{skip=1; next}
            /<!-- FUNCTIONMAP:INSTRUCTIONS:END -->/{skip=0; next}
            !skip{print}
        ')
        modified=true
        ok "Removed instructions block from CLAUDE.md"
    fi

    # Remove REGISTRY block (inclusive of sentinels)
    if echo "$content" | grep -q "FUNCTIONMAP:BEGIN"; then
        content=$(echo "$content" | awk '
            /<!-- FUNCTIONMAP:BEGIN -->/{skip=1; next}
            /<!-- FUNCTIONMAP:END -->/{skip=0; next}
            !skip{print}
        ')
        modified=true
        ok "Removed registry block from CLAUDE.md"
    fi

    # Clean up trailing blank lines left behind
    if $modified; then
        echo "$content" | sed -e :a -e '/^\n*$/{$d;N;ba;}' > "$CLAUDE_MD"
    fi
else
    info "No CLAUDE.md found (nothing to clean)"
fi

# ============================================================================
#  Prompt for function map data removal
# ============================================================================

if [ -d "$MAPS_DIR" ]; then
    echo ""
    # Default to NO if non-interactive (piped)
    if [ -t 0 ]; then
        read -rp "  Remove generated function maps ($MAPS_DIR)? [y/N] " answer
    else
        answer="n"
        info "Non-interactive mode: keeping generated function maps"
    fi

    case "$answer" in
        [yY]|[yY][eE][sS])
            rm -rf "$MAPS_DIR"
            ok "Removed $MAPS_DIR"
            ;;
        *)
            info "Kept $MAPS_DIR (your generated maps are preserved)"
            ;;
    esac
fi

# ============================================================================
#  Done
# ============================================================================

echo ""
echo "  ============================================================"
echo "    FUNCTIONMAP UNINSTALLED"
echo "  ============================================================"
echo ""
echo "    Restart Claude Code to complete the removal."
if [ -n "$BACKUP_DIR" ]; then
    echo ""
    echo "    Backup of removed files: $BACKUP_DIR"
    echo "    (Safe to delete once you've confirmed the uninstall is correct)"
fi
echo ""
