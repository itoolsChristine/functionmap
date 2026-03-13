import os
import sys
import unittest
from pathlib import Path

# Add repo root to path so we can import sync module
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))

from sync import normalize_paths, remove_swarm  # noqa: E402

# Build test paths from the actual home directory (no hardcoded usernames)
_HOME     = str(Path.home())
_HOME_FWD = _HOME.replace("\\", "/")
_HOME_BK  = _HOME.replace("/", "\\")


class TestNormalizePaths(unittest.TestCase):
    """Unit tests for sync.normalize_paths()."""

    def test_normalize_userprofile_backslash(self):
        inp      = r'python "%USERPROFILE%\.claude\tools\functionmap\functionmap.py"'
        expected = 'python "$HOME/.claude/tools/functionmap/functionmap.py"'
        self.assertEqual(normalize_paths(inp), expected)

    def test_normalize_userprofile_forward(self):
        inp      = '$USERPROFILE/.claude/tools/functionmap/quickmap.py'
        expected = '$HOME/.claude/tools/functionmap/quickmap.py'
        self.assertEqual(normalize_paths(inp), expected)

    def test_normalize_absolute_backslash(self):
        inp      = _HOME_BK + r'\.claude\functionmap\project.md'
        expected = '$HOME/.claude/functionmap/project.md'
        self.assertEqual(normalize_paths(inp), expected)

    def test_normalize_absolute_forward(self):
        inp      = _HOME_FWD + '/.claude/docs/help.md'
        expected = '$HOME/.claude/docs/help.md'
        self.assertEqual(normalize_paths(inp), expected)

    def test_normalize_idempotent(self):
        inp    = _HOME_BK + r'\.claude\tools\functionmap\functionmap.py'
        first  = normalize_paths(inp)
        second = normalize_paths(first)
        self.assertEqual(first, second)


class TestRemoveSwarm(unittest.TestCase):
    """Unit tests for sync.remove_swarm()."""

    def test_remove_swarm_strips_phase5(self):
        inp = (
            "Some preamble.\n"
            "\n"
            "## Phase 5\n"
            "This is the swarm phase.\n"
            "It does deep checks.\n"
            "\n"
            "## Phase 6\n"
            "This is the usability test.\n"
        )
        result, warnings = remove_swarm(inp)
        self.assertNotIn('swarm', result.lower())
        self.assertIn('## Phase 5', result)
        self.assertIn('usability test', result)

    def test_remove_swarm_strips_yaml_description(self):
        inp = 'description: Deep-scan + /swarm deep checks.'
        result, warnings = remove_swarm(inp)
        self.assertNotIn('/swarm deep checks', result)

    def test_remove_swarm_preserves_skill_functionmap(self):
        inp = (
            "allowed-tools:\n"
            "  - Skill(functionmap)\n"
            "  - Read\n"
        )
        result, warnings = remove_swarm(inp)
        self.assertIn('Skill(functionmap)', result)

    def test_remove_swarm_warns_on_missing_marker(self):
        inp = "This content has no Phase 5 marker at all.\n"
        result, warnings = remove_swarm(inp)
        self.assertGreater(len(warnings), 0,
                           'Expected warnings when Phase 5 marker is missing')

    def test_remove_swarm_idempotent(self):
        inp = (
            "Preamble.\n"
            "\n"
            "## Phase 5\n"
            "Swarm content.\n"
            "\n"
            "## Phase 6\n"
            "Usability test.\n"
        )
        first, _  = remove_swarm(inp)
        second, _ = remove_swarm(first)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
