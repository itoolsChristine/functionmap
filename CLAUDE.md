# CLAUDE.md -- functionmap

## What This Project Is

A redistributable Claude Code skill suite that indexes every function in a codebase so Claude finds existing functionality before writing new code. Ships as cross-platform installers (bash + PowerShell) that place tools, commands, docs, and CLAUDE.md integration into `~/.claude/`.

**GitHub**: `itoolsChristine/functionmap`
**License**: MIT
**Current version**: Read from `VERSION` file (single source of truth)

## Architecture

There are two copies of the functionmap tools:

1. **Live (installed)**: `~/.claude/tools/functionmap/`, `~/.claude/commands/`, `~/.claude/docs/` -- these are the actively-used files. Development happens here.
2. **Repo (distribution)**: `src/` -- distribution-ready copies with transforms applied (path normalization, /swarm removal). Never edit `src/` directly.

**The live files are the source of truth.** `sync.py` copies them into `src/` with transforms. The install scripts copy from `src/` to the user's `~/.claude/`.

### Key directories

| Directory | Purpose | Tracked |
|-----------|---------|---------|
| `src/tools/` | Python + JS extraction/categorization engine | Yes |
| `src/commands/` | Skill definition files (`/functionmap`, `/functionmap-update`) | Yes |
| `src/docs/` | Help documentation | Yes |
| `src/mcp/` | MCP server for fast function search (4 files) | Yes |
| `src/claude-md/` | CLAUDE.md integration content (instructions + registry templates) | Yes |
| `temp/` | Sandboxed test directory (created/destroyed by test_install_uninstall.sh) | No (gitignored) |

### Installed file manifest (9 core + 5 optional MCP)

**Core files (always installed):**

| File | Destination |
|------|-------------|
| `functionmap.py` | `~/.claude/tools/functionmap/` |
| `categorize.py` | `~/.claude/tools/functionmap/` |
| `quickmap.py` | `~/.claude/tools/functionmap/` |
| `thirdparty.py` | `~/.claude/tools/functionmap/` |
| `describe.py` | `~/.claude/tools/functionmap/` |
| `build-callgraph.cjs` | `~/.claude/tools/functionmap/` |
| `functionmap.md` | `~/.claude/commands/` |
| `functionmap-update.md` | `~/.claude/commands/` |
| `functionmap-help.md` | `~/.claude/docs/` |

**MCP files (optional, included by default):**

| File | Destination |
|------|-------------|
| `functionmap-mcp.md` | `~/.claude/docs/` |
| `server.py` | `~/.claude/functionmap-mcp/` |
| `index.py` | `~/.claude/functionmap-mcp/` |
| `search.py` | `~/.claude/functionmap-mcp/` |
| `requirements.txt` | `~/.claude/functionmap-mcp/` |

The installer prompts for MCP inclusion. Use `--mcp` / `--no-mcp` flags to bypass the prompt. Re-run with `--no-mcp` to remove MCP from an existing install (deregisters and cleans up).

## Development Workflow

### Making changes

1. Edit the **live** files in `~/.claude/` (tools, commands, docs)
2. Run `sync.cmd` (or `python sync.py`) to pull changes into `src/`
3. sync.py automatically:
   - Copies Python/JS tools verbatim
   - Applies path normalization to .md files (`C:\Users\...` -> `$HOME/...`)
   - Strips /swarm references from `functionmap.md` (distribution doesn't include /swarm)
   - Applies project-specific substitutions from `substitutions.local.json`
   - Auto-bumps patch version if files changed
   - Propagates version to `__version__`, README badge, CHANGELOG header
4. Review changes with `git diff`
5. Update `CHANGELOG.md`
6. Commit and tag

### Version management

- `VERSION` file is the single source of truth
- **Patch (Z)**: Auto-bumped by `sync.py` when file changes are detected
- **Minor (Y)**: `python sync.py --minor` (for feature releases)
- **Major (X)**: `python sync.py --major` (for breaking changes)
- Version propagates to: `VERSION`, `src/tools/functionmap.py` (`__version__`), live `functionmap.py`, `README.md` badge, `CHANGELOG.md` header

### Substitutions

`substitutions.local.json` (gitignored) maps personal/client paths and project names to generic equivalents for the distribution. Auto-generates backslash variants for path entries. See `substitutions.example.json` for the format.

## Testing

### Unit tests (run by CI)

```bash
python -m unittest tests.test_extraction -v    # Extraction against fixtures
python -m unittest tests.test_sync -v           # Path normalization + swarm removal
python -m unittest tests.test_mcp_fixture -v   # MCP server against synthetic fixtures
python -m unittest tests.test_parity -v        # MCP vs MD-file discovery parity
```

### Install/uninstall test (manual, not in CI)

```bash
bash tests/test_install_uninstall.sh
```

Creates a sandboxed `temp/` directory with a fake HOME and tests three paths: install with MCP (`--mcp`), install without MCP (`--no-mcp`), and cross-mode upgrade (MCP -> no-MCP -> MCP). Each path verifies file counts, CLAUDE.md sentinels, `.claude.json` registration, idempotency, and cleanup.

### CI matrix

Python 3.10 + 3.12 across ubuntu, macos, windows (6 jobs). Uses `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`. Runs extraction, sync, MCP fixture, and parity tests. The `test_mcp` suite (real data) skips in CI since no maps exist.

## CLAUDE.md Integration (installed by installer)

The installer injects two sentinel-delimited blocks into the user's `~/.claude/CLAUDE.md`:

1. **Instructions block** (`FUNCTIONMAP:INSTRUCTIONS:BEGIN/END`) -- Teaches Claude the 5-step discovery procedure. Static content from `src/claude-md/functionmap-instructions.md`. This file is manually maintained (NOT synced from live) because the live version has InteractiveTools-specific language.

2. **Registry block** (`FUNCTIONMAP:BEGIN/END`) -- Lists available maps. Starts empty; populated at runtime by `/functionmap` and `/functionmap-update`.

## Things to Watch Out For

- **Never edit `src/` directly** -- changes will be overwritten by the next sync. Edit live files, then sync.
- **`src/claude-md/functionmap-instructions.md` is the exception** -- it's manually maintained for generic (non-InteractiveTools) language. NOT copied from the live CLAUDE.md.
- **CRLF handling**: The live files on Windows have CRLF endings. sync.py writes LF to `src/`. `patch_py_version()` must use `read_text()` (not `read_bytes().decode()`) to avoid doubling carriage returns.
- **`substitutions.local.json` is gitignored** -- it contains personal paths. Each developer creates their own from `substitutions.example.json`.
