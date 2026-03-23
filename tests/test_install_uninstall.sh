#!/usr/bin/env bash
# test_install_uninstall.sh -- End-to-end test of install and uninstall scripts
#
# Creates a fake HOME in ./temp, runs install.sh (local mode), verifies
# every file and config entry, then runs uninstall.sh and verifies cleanup.
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

echo ""
echo "  ============================================================"
echo "    FUNCTIONMAP INSTALL/UNINSTALL TEST"
echo "    Testing in sandboxed temp/ directory"
echo "  ============================================================"
echo ""

# ============================================================================
#  Clean slate
# ============================================================================

if [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
    info "Removed existing temp/"
fi

mkdir -p "$TEMP_DIR/.claude"
info "Created temp/.claude/"

# Create a fake CLAUDE.md with some existing content
cat > "$TEMP_DIR/.claude/CLAUDE.md" << 'EOF'
# CLAUDE.md

## Existing Section

This is pre-existing content that should be preserved.

## Another Section

More content here.
EOF
info "Created fake CLAUDE.md with pre-existing content"

# ============================================================================
#  Run install (with HOME overridden to temp/)
# ============================================================================

echo ""
echo "  --- Running install.sh ---"
echo ""

export HOME="$TEMP_DIR"
echo "y" | bash "$PROJECT_ROOT/install.sh" 2>&1 | sed 's/^/    /'
INSTALL_EXIT=$?

echo ""

check '[ $INSTALL_EXIT -eq 0 ]' "install.sh exited with code 0"

# ============================================================================
#  Integrity checks -- verify everything installed correctly
# ============================================================================

echo ""
echo "  --- Post-install integrity checks ---"
echo ""

# Python tools
for f in functionmap.py categorize.py quickmap.py thirdparty.py describe.py; do
    check "[ -f '$TEMP_DIR/.claude/tools/functionmap/$f' ]" "Tool installed: $f"
done

# JS tools
check "[ -f '$TEMP_DIR/.claude/tools/functionmap/build-callgraph.cjs' ]" "Tool installed: build-callgraph.cjs"

# Commands
check "[ -f '$TEMP_DIR/.claude/commands/functionmap.md' ]" "Command installed: functionmap.md"
check "[ -f '$TEMP_DIR/.claude/commands/functionmap-update.md' ]" "Command installed: functionmap-update.md"

# Docs
check "[ -f '$TEMP_DIR/.claude/docs/functionmap-help.md' ]" "Docs installed: functionmap-help.md"

# .version file
check "[ -f '$TEMP_DIR/.claude/tools/functionmap/.version' ]" ".version file created"

# Function map directory created
check "[ -d '$TEMP_DIR/.claude/functionmap' ]" "Function map directory created"

# CLAUDE.md -- sentinels present
check "grep -q 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md has instructions BEGIN sentinel"
check "grep -q 'FUNCTIONMAP:INSTRUCTIONS:END' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md has instructions END sentinel"
check "grep -q 'FUNCTIONMAP:BEGIN' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md has registry BEGIN sentinel"
check "grep -q 'FUNCTIONMAP:END' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md has registry END sentinel"
check "grep -q 'Function Maps -- MANDATORY CHECK' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md has function maps heading"

# CLAUDE.md -- pre-existing content preserved
check "grep -q 'Existing Section' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md preserved: Existing Section"
check "grep -q 'Another Section' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md preserved: Another Section"
check "grep -q 'pre-existing content' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md preserved: pre-existing content"

# functionmap.py --version works
PYTHON=""
command -v python3 &>/dev/null && PYTHON="python3" || PYTHON="python"
check "$PYTHON '$TEMP_DIR/.claude/tools/functionmap/functionmap.py' --version &>/dev/null" "functionmap.py --version runs"

echo ""
echo "  --- Post-install summary: $CHECKS checks, $FAILURES failures ---"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}INSTALL VERIFICATION FAILED${RESET} -- skipping remaining tests"
    echo ""
    exit 1
fi

# ============================================================================
#  Idempotency: run installer again
# ============================================================================

echo ""
echo "  --- Idempotency (second install) ---"
echo ""

echo "y" | bash "$PROJECT_ROOT/install.sh" 2>&1 | sed 's/^/    /'
REINSTALL_EXIT=$?

echo ""

check '[ $REINSTALL_EXIT -eq 0 ]' "Idempotent re-install exited with code 0"

# Verify sentinels aren't duplicated
INSTR_COUNT=$(grep -c 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' "$TEMP_DIR/.claude/CLAUDE.md" || true)
check "[ $INSTR_COUNT -eq 1 ]" "Instructions sentinel not duplicated (count: $INSTR_COUNT)"

REG_COUNT=$(grep -c 'FUNCTIONMAP:BEGIN' "$TEMP_DIR/.claude/CLAUDE.md" || true)
# FUNCTIONMAP:BEGIN also appears inside FUNCTIONMAP:INSTRUCTIONS:BEGIN line, so filter
REG_ONLY_COUNT=$(grep -c '^<!-- FUNCTIONMAP:BEGIN -->' "$TEMP_DIR/.claude/CLAUDE.md" || true)
check "[ $REG_ONLY_COUNT -eq 1 ]" "Registry sentinel not duplicated (count: $REG_ONLY_COUNT)"

echo ""
echo "  --- Post-idempotency summary: $CHECKS checks, $FAILURES failures ---"
echo ""

if [ $FAILURES -gt 0 ]; then
    echo -e "  ${RED}${BOLD}IDEMPOTENCY CHECKS FAILED${RESET} -- skipping uninstall test"
    echo ""
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
#  Run uninstall (with HOME still overridden)
# ============================================================================

echo ""
echo "  --- Running uninstall.sh ---"
echo ""

# Non-interactive: auto-yes for uninstall, auto-no for map data removal
echo "y" | bash "$PROJECT_ROOT/uninstall.sh" 2>&1 | sed 's/^/    /'
UNINSTALL_EXIT=$?

echo ""

check '[ $UNINSTALL_EXIT -eq 0 ]' "uninstall.sh exited with code 0"

# ============================================================================
#  Post-uninstall integrity checks
# ============================================================================

echo ""
echo "  --- Post-uninstall integrity checks ---"
echo ""

# Tools directory removed
check "[ ! -d '$TEMP_DIR/.claude/tools/functionmap' ]" "Tools directory removed"

# Commands removed
check "[ ! -f '$TEMP_DIR/.claude/commands/functionmap.md' ]" "Command removed: functionmap.md"
check "[ ! -f '$TEMP_DIR/.claude/commands/functionmap-update.md' ]" "Command removed: functionmap-update.md"

# Docs removed
check "[ ! -f '$TEMP_DIR/.claude/docs/functionmap-help.md' ]" "Docs removed: functionmap-help.md"

# CLAUDE.md -- sentinels removed
check "! grep -q 'FUNCTIONMAP:INSTRUCTIONS:BEGIN' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md: instructions BEGIN sentinel removed"
check "! grep -q 'FUNCTIONMAP:INSTRUCTIONS:END' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md: instructions END sentinel removed"
check "! grep -q 'Function Maps -- MANDATORY CHECK' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md: function maps section removed"

# CLAUDE.md -- pre-existing content still preserved after uninstall
check "grep -q 'Existing Section' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md still has: Existing Section"
check "grep -q 'Another Section' '$TEMP_DIR/.claude/CLAUDE.md'" "CLAUDE.md still has: Another Section"

# Function maps preserved (default: don't delete in non-interactive mode)
check "[ -d '$TEMP_DIR/.claude/functionmap' ]" "Function map directory preserved (not deleted)"
check "[ -f '$TEMP_DIR/.claude/functionmap/myproject/_meta.json' ]" "User map data preserved: myproject/_meta.json"
check "[ -f '$TEMP_DIR/.claude/functionmap/myproject.md' ]" "User map data preserved: myproject.md"

# Backup created
BACKUP_COUNT=$(ls -d "$TEMP_DIR/.claude/.functionmap-backup-"* 2>/dev/null | wc -l)
check "[ $BACKUP_COUNT -gt 0 ]" "Uninstall backup directory created ($BACKUP_COUNT found)"

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
