#!/usr/bin/env bash
set -euo pipefail

PASS=0
FAIL=0
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

pass() {
    PASS=$((PASS + 1))
    echo "  PASS: $1"
}

fail() {
    FAIL=$((FAIL + 1))
    echo "  FAIL: $1"
}

check_file() {
    if [ -f "$1" ]; then
        pass "$2"
    else
        fail "$2 -- file not found: $1"
    fi
}

check_sentinel() {
    if grep -q "$2" "$1" 2>/dev/null; then
        pass "$3"
    else
        fail "$3 -- sentinel not found in $1"
    fi
}

# -------------------------------------------------------------------
# Setup: create a fake HOME with .claude/ directory
# -------------------------------------------------------------------
FAKE_HOME="$(mktemp -d)"
export HOME="$FAKE_HOME"
mkdir -p "$FAKE_HOME/.claude"

echo ""
echo "=========================================="
echo "  Functionmap Install Tests"
echo "=========================================="
echo "  Fake HOME: $FAKE_HOME"
echo ""

# -------------------------------------------------------------------
# Run installer (local clone mode)
# -------------------------------------------------------------------
echo "--- First install ---"
if bash "$REPO_ROOT/install.sh"; then
    pass "install.sh exited successfully"
else
    fail "install.sh exited with error"
fi

# -------------------------------------------------------------------
# Verify files exist
# -------------------------------------------------------------------
echo ""
echo "--- File checks ---"
check_file "$FAKE_HOME/.claude/commands/functionmap.md"        "commands/functionmap.md"
check_file "$FAKE_HOME/.claude/commands/functionmap-update.md"  "commands/functionmap-update.md"
check_file "$FAKE_HOME/.claude/docs/functionmap-help.md"        "docs/functionmap-help.md"
check_file "$FAKE_HOME/.claude/tools/functionmap/functionmap.py" "tools/functionmap.py"
check_file "$FAKE_HOME/.claude/tools/functionmap/categorize.py"  "tools/categorize.py"
check_file "$FAKE_HOME/.claude/tools/functionmap/quickmap.py"    "tools/quickmap.py"
check_file "$FAKE_HOME/.claude/tools/functionmap/thirdparty.py"  "tools/thirdparty.py"
check_file "$FAKE_HOME/.claude/tools/functionmap/describe.py"    "tools/describe.py"

# -------------------------------------------------------------------
# Verify CLAUDE.md sentinels
# -------------------------------------------------------------------
echo ""
echo "--- Sentinel checks ---"
CLAUDE_MD="$FAKE_HOME/.claude/CLAUDE.md"
check_file "$CLAUDE_MD" "CLAUDE.md exists"
check_sentinel "$CLAUDE_MD" "FUNCTIONMAP:INSTRUCTIONS:BEGIN" "Instructions BEGIN sentinel"
check_sentinel "$CLAUDE_MD" "FUNCTIONMAP:INSTRUCTIONS:END"   "Instructions END sentinel"
check_sentinel "$CLAUDE_MD" "FUNCTIONMAP:BEGIN"               "Registry BEGIN sentinel"
check_sentinel "$CLAUDE_MD" "FUNCTIONMAP:END"                 "Registry END sentinel"

# -------------------------------------------------------------------
# Verify .version file
# -------------------------------------------------------------------
echo ""
echo "--- Version check ---"
check_file "$FAKE_HOME/.claude/tools/functionmap/.version" ".version file"

# -------------------------------------------------------------------
# Idempotency: run installer again
# -------------------------------------------------------------------
echo ""
echo "--- Idempotency (second install) ---"
if bash "$REPO_ROOT/install.sh"; then
    pass "install.sh idempotent re-run succeeded"
else
    fail "install.sh idempotent re-run failed"
fi

# -------------------------------------------------------------------
# Cleanup
# -------------------------------------------------------------------
rm -rf "$FAKE_HOME"

# -------------------------------------------------------------------
# Summary
# -------------------------------------------------------------------
echo ""
echo "=========================================="
TOTAL=$((PASS + FAIL))
echo "  Results: $PASS/$TOTAL passed"
if [ "$FAIL" -gt 0 ]; then
    echo "  $FAIL FAILED"
    echo "=========================================="
    exit 1
fi
echo "  All tests passed."
echo "=========================================="
exit 0
