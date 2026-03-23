# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-03-23

### Added
- **MCP server** (`functionmap-mcp/`): Fast function search and lookup via 4 MCP tools (`functionmap_search`, `functionmap_detail`, `functionmap_categories`, `functionmap_projects`). Queries `_functions.json` directly instead of parsing markdown -- collapses 2-3 Read calls into a single tool call with relevance-scored results. Lazy per-project loading with mtime-based freshness checks. Supports third-party libraries (`project="third-party/jquery/2.1.4"`), sub-projects (`project="squimsh/output"`), and exposes dependency chains per project.
- **MCP reference doc** (`functionmap-mcp.md`): Detailed usage guide with workflow examples, dual-search strategy, project discovery procedure, third-party/sub-project addressing, and accountability format.
- **Call graph engine** (`build-callgraph.cjs`): Builds inter-function call graphs with call edges, content anchors, and orphan detection. Improves taxonomy design by revealing natural function clusters and shared utilities.
- **Enrichment files** (`_enrichment.json`): Optional sidecar files providing display names, descriptions, and category hints for functions lacking source-level documentation. Supports three key formats: `file:name:line`, `name_only`, and `custom`.
- **Sub-project path auto-resolution**: When a sub-project's `root_path` no longer exists (common after version upgrades), `quickmap.py` resolves via `root_path_glob` patterns in `_meta.json`.
- **Fixture-based MCP tests** (`test_mcp_fixture.py`): 43 tests covering index loading, search scoring, and all 4 server tools against synthetic fixture data. Runs in CI without requiring real function map data.
- **Parity tests** (`test_parity.py`): 11 tests verifying that the MCP server and MD-file discovery paths return equivalent data -- same functions, same file paths, same line numbers, same categories. Ensures both paths work regardless of MCP installation choice.
- **Synthetic fixture data** (`tests/fixtures/functionmap/`): Self-contained test project with 10 functions across 2 categories, complete with registry, taxonomy, category markdown files, and project index.

### Changed
- **MCP installation is now optional**: Installers prompt whether to include the MCP server (default: yes for fresh installs and non-interactive mode). Use `--mcp` / `--no-mcp` flags (`-Mcp` / `-NoMcp` in PowerShell) to bypass the prompt. Re-running with `--no-mcp` on an existing MCP install cleanly deregisters and removes MCP files. The CLAUDE.md instructions already handle both modes at runtime.
- **Taxonomy review in `/functionmap-update`**: Replaced minimal uncategorized-function check with full taxonomy review and validation -- threshold checks, delta file routing verification, category-level impact analysis, and ripple effect detection with before/after count comparison.
- **Sync pipeline**: Added JS tools category for `build-callgraph.cjs` and MCP server files; `remove_swarm()` now silently skips when swarm content has already been removed from source.
- **Install/uninstall scripts**: Updated file lists and verification counts to include `build-callgraph.cjs` and MCP server. Installers now register/deregister the MCP server in `~/.claude.json`. MCP installation is optional via `--mcp` / `--no-mcp` flags.
- **Automatic version management**: `VERSION` file is now the single source of truth. `sync.py` auto-bumps patch version when file changes are detected, propagates to `__version__`, README badge, and CHANGELOG header. Supports `--minor` and `--major` flags for manual bumps.
- **README.md**: Added version badge; updated Python requirement to 3.10+; added `VERSION` and `build-callgraph.cjs` to architecture tree; added MCP flag documentation and troubleshooting row.
- **CI**: Opted into Node.js 24 for GitHub Actions (`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`); dropped Python 3.8 from test matrix (EOL, unavailable on macOS ARM runners). Added fixture-based MCP and parity test steps.
- **Install/uninstall tests**: Replaced minimal `test_install.sh` with comprehensive `test_install_uninstall.sh` covering three paths (with MCP, without MCP, cross-mode upgrade) with shared verification helpers.
- **CLAUDE.md instructions**: Added MCP-preferred discovery section -- Claude uses MCP tools when available, falls back to Read-based procedure when not.

### Fixed
- **CRLF corruption in `patch_py_version`**: Reading with `read_bytes().decode()` then writing with `newline="\r\n"` doubled carriage returns (`\r\n` -> `\r\r\n`). Now uses `read_text()` for proper newline normalization.

## [1.0.0] - 2026-03-10

### Added
- Initial release
- Function extraction engine supporting PHP, JavaScript, and TypeScript
- Incremental update system with hash-based change detection (98% cheaper than full remap)
- Claude-driven taxonomy design with semantic categorization
- Third-party library deduplication and shared mapping
- Sub-project support for large embedded codebases
- Cross-platform installers (bash + PowerShell)
- CLAUDE.md integration with sentinel-based instruction and registry injection
- Automated verification pass with line-drift auto-correction
- Usability self-test (5-function lookup validation)
