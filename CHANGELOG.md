# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-03-23

### Added
- **Call graph engine** (`build-callgraph.cjs`): Builds inter-function call graphs with call edges, content anchors, and orphan detection. Improves taxonomy design by revealing natural function clusters and shared utilities.
- **Enrichment files** (`_enrichment.json`): Optional sidecar files providing display names, descriptions, and category hints for functions lacking source-level documentation. Supports three key formats: `file:name:line`, `name_only`, and `custom`.
- **Sub-project path auto-resolution**: When a sub-project's `root_path` no longer exists (common after version upgrades), `quickmap.py` resolves via `root_path_glob` patterns in `_meta.json`.

### Changed
- **Taxonomy review in `/functionmap-update`**: Replaced minimal uncategorized-function check with full taxonomy review and validation -- threshold checks, delta file routing verification, category-level impact analysis, and ripple effect detection with before/after count comparison.
- **Sync pipeline**: Added JS tools category for `build-callgraph.cjs`; `remove_swarm()` now silently skips when swarm content has already been removed from source.
- **Install/uninstall scripts**: Updated file lists and verification counts (8 -> 9 files) to include `build-callgraph.cjs`.
- **Automatic version management**: `VERSION` file is now the single source of truth. `sync.py` auto-bumps patch version when file changes are detected, propagates to `__version__`, README badge, and CHANGELOG header. Supports `--minor` and `--major` flags for manual bumps.
- **README.md**: Added version badge; updated Python requirement to 3.10+; added `VERSION` and `build-callgraph.cjs` to architecture tree.
- **CI**: Opted into Node.js 24 for GitHub Actions (`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`); dropped Python 3.8 from test matrix (EOL, unavailable on macOS ARM runners).
- **Install/uninstall test**: Replaced minimal `test_install.sh` with comprehensive `test_install_uninstall.sh` (39 checks covering install, integrity, idempotency, uninstall, and cleanup in a sandboxed temp directory).

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
