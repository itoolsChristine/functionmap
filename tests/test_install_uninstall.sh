#!/usr/bin/env bash
# test_install_uninstall.sh -- End-to-end test of install and uninstall scripts
#
# Creates a fake HOME in ./temp, runs install.sh (local mode), verifies
# every file and config entry, then runs uninstall.sh and verifies cleanup.
# Tests three paths: with MCP, without MCP, and cross-mode upgrade.
#
# Usage:  ./tests/test_install_uninstall.sh
# Run from the project root (D:\_Source\_interactive-tools\functionmap)

set -euo pipefail

# ============================================================================
#  Setup
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMP_DIR="$PROJECT_ROOT/temp"

# Colors
GREEN="\033[92m"
RED="\033[91m"
YELLOW="\033[93m"
BOLD="\033[1m"
RESET="\033[0m"

pass() { echo -e "  ${GREEN}[PASS]${RESET} $*"; }
fail() { echo -e "  ${RED}[FAIL]${RESET} $*"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "  ${YELLOW}[INFO]${RESET} $*"; }

FAILURES=0
CHECKS=0

check() {
    CHECKS=$((CHECKS + 1))
    if eval "$1"; then
        pass "$2"
    else
        fail "$2"
    fi
}

# Find Python
PYTHON=""
command -v python3 &>/dev/null && PYTHON="python3" || PYTHON="python"

# Convert paths for Python (cygpath available in Git Bash)
win_path() {
    if command -v cygpath &>/dev/null; then
        cygpath -w "$1"
    else
        echo "$1"
    fi
}

# ============================================================================
#  Shared helpers
# ============================================================================

create_clean_slate() {
    if [ -d "$TEMP_DIR" ]; then
        rm -rf "$TEMP_DIR"
    fi

    mkdir -p "$TEMP_DIR/.claude"

    # Create a fake CLAUDE.md with some existing content
    cat > "$TEMP_DIR/.claude/CLAUDE.md" << 'EOF'
# CLAUDE.md

## Existing Section

This is pre-existing content that should be preserved.

## Another Section

More content here.
EOF

    # Create a fake .claude.json with an existing MCP server
    cat > "$TEMP_DIR/.claude.json" << 'EOF'
{
  "mcpServers": {
    "other-server": {
      "type": "stdio",
      "command": "node",
      "args": ["other-server.js"],
      "env": {}
    }
  },
  "someOtherSetting": true
}
EOF

    export HOME="$TEMP_DIR"
    info "Clean slate created in temp/"
}

verify_core_files() {
    local label="${1:-}"

    # Python tools
    for f in functionmap.py categorize.py quickmap.py thirdparty.py describe.py; do
        check "[ -f '$TEMP_DIR/.claude/tools/functionmap/$f' ]" "${label}Tool installed: $f"
    done

    # JS tools
    check "[ -f '$TEMP_DIR/.claude/tools/functionmap/build-callgraph.cjs' ]" "${label}Tool installed: build-callgraph.cjs"

    # Commands
    check "[ -f '$TEMP_DIR/.claude/commands/functionmap.md' ]" "${label}Command installed: functionmap.md"
    check "[ -f '$TEMP_DIR/.claude/commands/functionmap-update.md' ]" "${label}Command installed: functionmap-update.md"

    # Core doc (always installed)
    check "[ -f '$TEMP_DIR/.claude/docs/functionmap-help.md' ]" "${label}Docs installed: functionmap-help.md"

    # .version file
    check "[ -f '$TEMP_DIR/.claude/tools/functionmap/.version' ]" "${label}.version file created"

    # Function map directory created
    check "[ -d '$TEMP_DIR/.claude/functionmap' ]" "${label}Function map directory created"

    # functionmap.py --version works
    check "$PYTHON '$TEMP_DIR/.claude/tools/functionmap/functionmap.py' --version &>/dev/null" "${label}functionmap.py --version runs"
}

verify_mcp_present() {
    local label="${1:-}"
    local CLAUDE_JSON_WIN
    CLAUDE_JSON_WIN=$(win_path "$TEMP_DIR/.claude.json")

    # MCP doc
    check "[ -f '$TEMP_DIR/.claude/docs/functionmap-mcp.md' ]" "${label}MCP doc installed: functionmap-mcp.md"

    # MCP server files
    for f in server.py index.py search.py requirements.txt; do
        check "[ -f '$TEMP_DIR/.claude/functionmap-mcp/$f' ]" "${label}MCP installed: $f"
    done

    # .claude.json -- functionmap MCP registered
    check "$PYTHON -c \"
import json
d = json.load(open(r'$CLAUDE_JSON_WIN'))
assert 'functionmap' in d.get('mcpServers', {}), 'functionmap not in mcpServers'
entry = d['mcpServers']['functionmap']
assert entry.get('type') == 'stdio', 'missing type'
assert 'args' in entry, 'missing args'
\" 2>&1" "${label}.claude.json has functionmap MCP entry"
}

verify_mcp_absent() {
    local label="${1:-}"
    local CLAUDE_JSON_WIN
    CLAUDE_JSON_WIN=$(win_path "$TEMP_DIR/.claude.json")

    # MCP doc should not exist
    check "[ ! -f '$TEMP_DIR/.claude/docs/functionmap-mcp.md' ]" "${label}MCP doc NOT present: functionmap-mcp.md"

    # MCP server directory should not exist
    check "[ ! -d '$TEMP_DIR/.claude/functionmap-mcp' ]" "${label}MCP server directory NOT present"

    # .claude.json -- functionmap MCP NOT registered
    check "$PYTHON -c \"
import json
d = json.load(open(r'$CLAUDE_JSON_WIN'))
assert 'functionmap' not in d.get('mcpServers', {}), 'functionmap unexpectedly in mcpServers'
\" 2>&1" "${label}.claude.json does NOT have functionmap MCP entry"
}

verify_claude_md() {
    local label="${1:-}"

    # Sentinels present
    check "grep -q 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md has instructions BEGIN sentinel"
    check "grep -q 'FUNCTIONMAP:INSTRUCTIONS:END' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md has instructions END sentinel"
    check "grep -q 'FUNCTIONMAP:BEGIN' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md has registry BEGIN sentinel"
    check "grep -q 'FUNCTIONMAP:END' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md has registry END sentinel"
    check "grep -q 'Function Maps -- MANDATORY CHECK' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md has function maps heading"

    # Pre-existing content preserved
    check "grep -q 'Existing Section' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md preserved: Existing Section"
    check "grep -q 'Another Section' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md preserved: Another Section"
    check "grep -q 'pre-existing content' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md preserved: pre-existing content"
}

verify_other_settings_preserved() {
    local label="${1:-}"
    local CLAUDE_JSON_WIN
    CLAUDE_JSON_WIN=$(win_path "$TEMP_DIR/.claude.json")

    # .claude.json -- existing server preserved
    check "$PYTHON -c \"
import json
d = json.load(open(r'$CLAUDE_JSON_WIN'))
assert 'other-server' in d.get('mcpServers', {}), 'other-server was lost'
\" 2>&1" "${label}.claude.json preserved: other-server entry"

    # .claude.json -- other settings preserved
    check "$PYTHON -c \"
import json
d = json.load(open(r'$CLAUDE_JSON_WIN'))
assert d.get('someOtherSetting') == True, 'someOtherSetting was lost'
\" 2>&1" "${label}.claude.json preserved: someOtherSetting"
}

verify_uninstall_cleanup() {
    local label="${1:-}"

    # Tools directory removed
    check "[ ! -d '$TEMP_DIR/.claude/tools/functionmap' ]" "${label}Tools directory removed"

    # Commands removed
    check "[ ! -f '$TEMP_DIR/.claude/commands/functionmap.md' ]" "${label}Command removed: functionmap.md"
    check "[ ! -f '$TEMP_DIR/.claude/commands/functionmap-update.md' ]" "${label}Command removed: functionmap-update.md"

    # Docs removed
    check "[ ! -f '$TEMP_DIR/.claude/docs/functionmap-help.md' ]" "${label}Docs removed: functionmap-help.md"
    check "[ ! -f '$TEMP_DIR/.claude/docs/functionmap-mcp.md' ]" "${label}Docs removed: functionmap-mcp.md"

    # MCP server removed
    check "[ ! -d '$TEMP_DIR/.claude/functionmap-mcp' ]" "${label}MCP server directory removed"

    # .claude.json -- functionmap deregistered
    local CLAUDE_JSON_WIN
    CLAUDE_JSON_WIN=$(win_path "$TEMP_DIR/.claude.json")
    check "$PYTHON -c \"
import json
d = json.load(open(r'$CLAUDE_JSON_WIN'))
assert 'functionmap' not in d.get('mcpServers', {}), 'functionmap still in mcpServers'
\" 2>&1" "${label}.claude.json: functionmap entry removed"

    # .claude.json -- existing server preserved after uninstall
    check "$PYTHON -c \"
import json
d = json.load(open(r'$CLAUDE_JSON_WIN'))
assert 'other-server' in d.get('mcpServers', {}), 'other-server was lost during uninstall'
\" 2>&1" "${label}.claude.json still has: other-server"

    # .claude.json -- file still exists
    check "[ -f '$TEMP_DIR/.claude.json' ]" "${label}.claude.json file still exists (not deleted)"

    # CLAUDE.md -- sentinels removed
    check "! grep -q 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md: instructions BEGIN sentinel removed"
    check "! grep -q 'FUNCTIONMAP:INSTRUCTIONS:END' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md: instructions END sentinel removed"
    check "! grep -q 'Function Maps -- MANDATORY CHECK' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md: function maps section removed"

    # CLAUDE.md -- pre-existing content still preserved after uninstall
    check "grep -q 'Existing Section' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md still has: Existing Section"
    check "grep -q 'Another Section' '$TEMP_DIR/.claude/CLAUDE.md'" "${label}CLAUDE.md still has: Another Section"
}

echo ""
echo "  ============================================================"
echo "    FUNCTIONMAP INSTALL/UNINSTALL TEST"
echo "    Testing in sandboxed temp/ directory"
echo "  ============================================================"
echo ""

# ############################################################################
#  PATH 1: Install with MCP (--mcp flag)
# ############################################################################

echo ""
echo -e "  ${BOLD}====== PATH 1: Install WITH MCP ======${RESET}"
echo ""

create_clean_slate

# ============================================================================
#  Run install with --mcp
# ============================================================================

echo ""
echo "  --- Running install.sh --mcp ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --mcp 2>&1 | sed 's/^/    /'
INSTALL_EXIT=$?

echo ""
check '[ $INSTALL_EXIT -eq 0 ]' "install.sh --mcp exited with code 0"

# ============================================================================
#  Post-install integrity checks
# ============================================================================

echo ""
echo "  --- Post-install integrity checks (with MCP) ---"
echo ""

verify_core_files
verify_mcp_present
verify_claude_md
verify_other_settings_preserved

echo ""
echo "  --- Post-install summary: $CHECKS checks, $FAILURES failures ---"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}PATH 1 INSTALL VERIFICATION FAILED${RESET} -- skipping remaining tests"
    echo ""
    rm -rf "$TEMP_DIR"
    exit 1
fi

# ============================================================================
#  Idempotency: run installer again with --mcp
# ============================================================================

echo ""
echo "  --- Idempotency (second install with --mcp) ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --mcp 2>&1 | sed 's/^/    /'
REINSTALL_EXIT=$?

echo ""

check '[ $REINSTALL_EXIT -eq 0 ]' "Idempotent re-install exited with code 0"

# Verify sentinels aren't duplicated
INSTR_COUNT=$(grep -c 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' "$TEMP_DIR/.claude/CLAUDE.md" || true)
check "[ $INSTR_COUNT -eq 1 ]" "Instructions sentinel not duplicated (count: $INSTR_COUNT)"

REG_ONLY_COUNT=$(grep -c '^<!-- FUNCTIONMAP:BEGIN -->' "$TEMP_DIR/.claude/CLAUDE.md" || true)
check "[ $REG_ONLY_COUNT -eq 1 ]" "Registry sentinel not duplicated (count: $REG_ONLY_COUNT)"

echo ""
echo "  --- Post-idempotency summary: $CHECKS checks, $FAILURES failures ---"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}PATH 1 IDEMPOTENCY CHECKS FAILED${RESET} -- skipping remaining tests"
    echo ""
    rm -rf "$TEMP_DIR"
    exit 1
fi

# ============================================================================
#  Create fake function map data (simulate user data)
# ============================================================================

mkdir -p "$TEMP_DIR/.claude/functionmap/myproject"
cat > "$TEMP_DIR/.claude/functionmap/myproject/_meta.json" << 'EOF'
{"project": "myproject", "function_count": 42}
EOF
echo "# myproject" > "$TEMP_DIR/.claude/functionmap/myproject.md"
info "Created fake function map data (simulates user data)"

# ============================================================================
#  Run uninstall
# ============================================================================

echo ""
echo "  --- Running uninstall.sh ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/uninstall.sh" 2>&1 | sed 's/^/    /'
UNINSTALL_EXIT=$?

echo ""
check '[ $UNINSTALL_EXIT -eq 0 ]' "uninstall.sh exited with code 0"

echo ""
echo "  --- Post-uninstall integrity checks ---"
echo ""

verify_uninstall_cleanup

# Function maps preserved (default: don't delete in non-interactive mode)
check "[ -d '$TEMP_DIR/.claude/functionmap' ]" "Function map directory preserved (not deleted)"
check "[ -f '$TEMP_DIR/.claude/functionmap/myproject/_meta.json' ]" "User map data preserved: myproject/_meta.json"
check "[ -f '$TEMP_DIR/.claude/functionmap/myproject.md' ]" "User map data preserved: myproject.md"

# Backup created
BACKUP_COUNT=$(ls -d "$TEMP_DIR/.claude/.functionmap-backup-"* 2>/dev/null | wc -l)
check "[ $BACKUP_COUNT -gt 0 ]" "Uninstall backup directory created ($BACKUP_COUNT found)"

echo ""
echo -e "  ${BOLD}====== PATH 1 COMPLETE: $CHECKS checks, $FAILURES failures ======${RESET}"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}PATH 1 FAILED${RESET} -- skipping remaining paths"
    echo ""
    rm -rf "$TEMP_DIR"
    exit 1
fi

# ############################################################################
#  PATH 2: Install WITHOUT MCP (--no-mcp flag)
# ############################################################################

echo ""
echo -e "  ${BOLD}====== PATH 2: Install WITHOUT MCP ======${RESET}"
echo ""

create_clean_slate

# ============================================================================
#  Run install with --no-mcp
# ============================================================================

echo ""
echo "  --- Running install.sh --no-mcp ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --no-mcp 2>&1 | sed 's/^/    /'
INSTALL_EXIT=$?

echo ""
check '[ $INSTALL_EXIT -eq 0 ]' "install.sh --no-mcp exited with code 0"

# ============================================================================
#  Post-install integrity checks (no MCP)
# ============================================================================

echo ""
echo "  --- Post-install integrity checks (without MCP) ---"
echo ""

verify_core_files
verify_mcp_absent
verify_claude_md
verify_other_settings_preserved

echo ""
echo "  --- Path 2 post-install summary: $CHECKS checks, $FAILURES failures ---"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}PATH 2 INSTALL VERIFICATION FAILED${RESET} -- skipping remaining tests"
    echo ""
    rm -rf "$TEMP_DIR"
    exit 1
fi

# ============================================================================
#  Idempotency: run installer again with --no-mcp
# ============================================================================

echo ""
echo "  --- Idempotency (second install with --no-mcp) ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --no-mcp 2>&1 | sed 's/^/    /'
REINSTALL_EXIT=$?

echo ""

check '[ $REINSTALL_EXIT -eq 0 ]' "Idempotent re-install (no-mcp) exited with code 0"
verify_mcp_absent "Idempotency: "

echo ""
echo "  --- Path 2 idempotency summary: $CHECKS checks, $FAILURES failures ---"
echo ""

# ============================================================================
#  Uninstall from no-MCP state
# ============================================================================

echo ""
echo "  --- Running uninstall.sh (from no-MCP state) ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/uninstall.sh" 2>&1 | sed 's/^/    /'
UNINSTALL_EXIT=$?

echo ""
check '[ $UNINSTALL_EXIT -eq 0 ]' "uninstall.sh (no-MCP) exited with code 0"

echo ""
echo "  --- Post-uninstall integrity checks (from no-MCP) ---"
echo ""

verify_uninstall_cleanup "no-MCP uninstall: "

echo ""
echo -e "  ${BOLD}====== PATH 2 COMPLETE: $CHECKS checks, $FAILURES failures ======${RESET}"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}PATH 2 FAILED${RESET} -- skipping remaining paths"
    echo ""
    rm -rf "$TEMP_DIR"
    exit 1
fi

# ############################################################################
#  PATH 3: Cross-mode upgrade (MCP -> no-MCP -> MCP)
# ############################################################################

echo ""
echo -e "  ${BOLD}====== PATH 3: Cross-mode upgrade ======${RESET}"
echo ""

create_clean_slate

# Step 1: Install with MCP
echo ""
echo "  --- Step 1: Install with --mcp ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --mcp 2>&1 | sed 's/^/    /'
INSTALL_EXIT=$?

echo ""
check '[ $INSTALL_EXIT -eq 0 ]' "Cross-mode step 1: install --mcp exited with code 0"
verify_mcp_present "Step 1: "

echo ""

# Step 2: Re-install without MCP (downgrade)
echo ""
echo "  --- Step 2: Re-install with --no-mcp (downgrade) ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --no-mcp 2>&1 | sed 's/^/    /'
INSTALL_EXIT=$?

echo ""
check '[ $INSTALL_EXIT -eq 0 ]' "Cross-mode step 2: install --no-mcp exited with code 0"
verify_core_files "Step 2: "
verify_mcp_absent "Step 2: "

echo ""

# Step 3: Re-install with MCP (upgrade back)
echo ""
echo "  --- Step 3: Re-install with --mcp (restore MCP) ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" --mcp 2>&1 | sed 's/^/    /'
INSTALL_EXIT=$?

echo ""
check '[ $INSTALL_EXIT -eq 0 ]' "Cross-mode step 3: install --mcp exited with code 0"
verify_core_files "Step 3: "
verify_mcp_present "Step 3: "
verify_claude_md "Step 3: "

echo ""
echo -e "  ${BOLD}====== PATH 3 COMPLETE: $CHECKS checks, $FAILURES failures ======${RESET}"
echo ""

# ============================================================================
#  Cleanup
# ============================================================================

echo ""
echo "  --- Cleaning up temp/ ---"
echo ""

rm -rf "$TEMP_DIR"
check "[ ! -d '$TEMP_DIR' ]" "temp/ directory removed"

# ============================================================================
#  Results
# ============================================================================

echo ""
echo "  ============================================================"
if [ $FAILURES -eq 0 ]; then
    echo -e "    ${GREEN}${BOLD}ALL $CHECKS CHECKS PASSED${RESET}"
else
    echo -e "    ${RED}${BOLD}$FAILURES of $CHECKS CHECKS FAILED${RESET}"
fi
echo "  ============================================================"
echo ""

exit $FAILURES
