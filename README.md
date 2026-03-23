# functionmap

**Give Claude a map of your codebase so it finds existing functions before writing new ones.**

![Version](https://img.shields.io/badge/version-1.1.0-blue)
[![CI](https://github.com/itoolsChristine/functionmap/actions/workflows/ci.yml/badge.svg)](https://github.com/itoolsChristine/functionmap/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## The Problem

Claude's context window is finite, but codebases are vast. Without a map, Claude either floods its context with irrelevant code from broad searches, or misses existing functionality entirely and reinvents the wheel -- writing a new `formatCurrency()` when one already exists three files away.

The bigger the codebase, the worse this gets. Grepping for every task burns tokens and still misses things. Claude ends up guessing instead of knowing.

## The Solution

functionmap indexes every function in your codebase -- name, signature, file path, line number -- and organizes them into semantic categories designed by Claude itself. When Claude needs to understand or modify code, it consults this compact index first, loading only the relevant category instead of grepping the entire codebase.

The result: Claude finds existing functions before writing new ones, understands your codebase structure without reading every file, and uses your APIs correctly because it checked the map first.

## Quick Install

**Windows (CMD -- double-click):**

Download and double-click `install.cmd`, or from a command prompt:
```cmd
install.cmd
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/itoolsChristine/functionmap/main/install.ps1 | iex
```

**Windows (Git Bash):**
```bash
curl -fsSL https://raw.githubusercontent.com/itoolsChristine/functionmap/main/install.sh | bash
```

**macOS / Linux / Git Bash:**
```bash
curl -fsSL https://raw.githubusercontent.com/itoolsChristine/functionmap/main/install.sh | bash
```

**From a local clone (any platform):**
```bash
git clone https://github.com/itoolsChristine/functionmap.git
cd functionmap
install.cmd         # Windows CMD (or double-click)
.\install.ps1       # Windows PowerShell
./install.sh        # macOS/Linux/Git Bash
```

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and run at least once (so `~/.claude/` exists)
- Python 3.10+

## Quick Start

**Create your first map:**
```
/functionmap myproject /path/to/code
```

**Update an existing map after code changes:**
```
/functionmap-update
```

**Show help and available commands:**
```
/functionmap help
```

## How It Works

### Full remap (5 phases)

1. **Extract** -- Parse every PHP, JavaScript, and TypeScript file. Pull out function names, signatures, file paths, and line numbers.
2. **Taxonomy** -- Claude designs a semantic category structure tailored to your codebase (not generic buckets -- categories that reflect how your code is actually organized).
3. **Categorize** -- Each function is assigned to its best-fit category. Claude writes a markdown file per category with every function's details.
4. **Verify** -- Automated pass checks that line numbers still match reality. Drifted references are auto-corrected.
5. **Usability test** -- Looks up 5 random functions through the map to confirm the discovery procedure works end-to-end.

### Incremental update (3 steps)

1. **Hash compare** -- SHA-256 hashes identify which files changed since the last map.
2. **Re-extract** -- Only changed files are re-parsed (typically 2-5% of the codebase).
3. **Re-categorize** -- Updated functions are merged into existing categories.

Incremental updates are ~98% cheaper than a full remap.

## What It Creates

```
~/.claude/functionmap/
|-- myproject.md                    # Project index (category list + navigation)
|-- myproject/
|   |-- _meta.json                  # Hashes, timestamps, config
|   |-- _functions.json             # Raw extracted function data
|   |-- _taxonomy.json              # Category definitions
|   |-- libraries.md                # Dependency links to other mapped projects
|   |-- auth-and-sessions.md        # Category file (example)
|   |-- database-operations.md      # Category file (example)
|   |-- string-formatting.md        # Category file (example)
|   |-- ...                         # One .md per category
|   |-- third-party/                # Shared maps for bundled libraries
|       |-- {lib}/{version}/
|           |-- categories.md
|           |-- ...
```

Each category `.md` file contains a table of functions with their signatures, file paths, line numbers, and descriptions -- everything Claude needs to decide whether to use an existing function or write a new one.

## CLAUDE.md Integration

The installer adds two blocks to your `~/.claude/CLAUDE.md`, both delimited by sentinel comments so they can be updated independently:

1. **Instructions block** (`<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN/END -->`) -- Teaches Claude the 5-step discovery procedure: check the project index, follow dependencies, check sub-projects, check third-party libraries, then act. This is what makes Claude actually *use* the maps instead of ignoring them.

2. **Registry block** (`<!-- FUNCTIONMAP:BEGIN/END -->`) -- Lists all available maps. Auto-populated each time you run `/functionmap` on a project.

**Both blocks are required.** Without the instructions block, Claude generates maps but never consults them. Without the registry block, Claude doesn't know which projects have maps available.

## Updating

Re-run the install command. The installer is idempotent -- it updates existing files and sentinel blocks without duplicating anything.

## Uninstalling

**Windows (CMD -- double-click):**
```cmd
uninstall.cmd
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/itoolsChristine/functionmap/main/uninstall.ps1 | iex
```

**Windows (Git Bash):**
```bash
curl -fsSL https://raw.githubusercontent.com/itoolsChristine/functionmap/main/uninstall.sh | bash
```

**macOS / Linux / Git Bash:**
```bash
curl -fsSL https://raw.githubusercontent.com/itoolsChristine/functionmap/main/uninstall.sh | bash
```

**From a local clone:** Run `uninstall.cmd`, `.\uninstall.ps1`, or `./uninstall.sh`.

This removes installed commands, tools, docs, and CLAUDE.md sentinel blocks. Your generated maps in `~/.claude/functionmap/` are preserved.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Install [Python 3.10+](https://www.python.org/downloads/) and ensure it's in your PATH |
| `~/.claude/` doesn't exist | Install and run [Claude Code](https://docs.anthropic.com/en/docs/claude-code) at least once |
| Commands not showing up | Restart Claude Code after installation |
| Maps generated but Claude doesn't use them | Check that both CLAUDE.md sentinel blocks are present (instructions + registry) |

## Architecture

```
functionmap/
|-- README.md
|-- LICENSE
|-- CHANGELOG.md
|-- .gitignore
|-- install.sh                     # macOS/Linux/Git Bash installer
|-- install.ps1                    # Windows PowerShell installer
|-- install.cmd                    # Windows CMD installer (double-click)
|-- uninstall.sh                   # macOS/Linux/Git Bash uninstaller
|-- uninstall.ps1                  # Windows PowerShell uninstaller
|-- uninstall.cmd                  # Windows CMD uninstaller (double-click)
|-- sync.cmd                       # Dev sync: installed files -> repo src/
|-- sync.py                        # Dev sync engine (path normalization, version management)
|-- substitutions.example.json     # Template for personal path sanitization
|-- VERSION                        # Single source of truth for version number
|
|-- src/
|   |-- commands/                  # Skill definition files
|   |   |-- functionmap.md
|   |   |-- functionmap-update.md
|   |
|   |-- docs/                      # Help documentation
|   |   |-- functionmap-help.md
|   |
|   |-- tools/                     # Extraction and categorization engine
|   |   |-- functionmap.py
|   |   |-- categorize.py
|   |   |-- quickmap.py
|   |   |-- thirdparty.py
|   |   |-- describe.py
|   |   |-- build-callgraph.cjs    # Inter-function call graph (Node.js)
|   |
|   |-- claude-md/                 # CLAUDE.md integration content
|       |-- functionmap-instructions.md
|       |-- functionmap-registry.md
|
|-- tests/
|   |-- test_install_uninstall.sh  # End-to-end install/integrity/uninstall test
|   |-- test_install.ps1
|   |-- test_extraction.py
|   |-- test_sync.py
|   |-- fixtures/
|       |-- sample.php
|       |-- sample.js
|       |-- sample.ts
|
|-- .github/
    |-- workflows/
        |-- ci.yml
```

## Contributing

Contributions are welcome! Here's how:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run the test suite (`python tests/test_extraction.py`)
5. Commit your changes (`git commit -m "Add my feature"`)
6. Push to your branch (`git push origin feature/my-feature`)
7. Open a Pull Request

Please keep PRs focused on a single change. For major changes, open an issue first to discuss the approach.

## License

[MIT](LICENSE)
