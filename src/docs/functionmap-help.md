# Function Map Commands -- Quick Reference

## Terminology

| Term | What it means |
|------|---------------|
| **Function map** | An index of every function/method in a project -- name, signature, file, line number -- organized into categories so Claude can look up what already exists before writing code. |
| **Extraction** | Scanning source files and pulling out function signatures. The expensive part (~30,000 tokens per project). |
| **Taxonomy** | The category system that organizes functions. Stored in `_taxonomy.json` -- a tree of categories, subcategories, and keyword routing rules that decide where each function goes. |
| **Categorization** | Sorting extracted functions into taxonomy categories. Fast (~1 second, done by `categorize.py`). |
| **Hashes** | SHA-256 fingerprints of each source file, stored in `_hashes.json`. Used to detect which files changed since the last map, so only those files need re-extraction. |
| **Incremental update** | Re-extracts functions from only the files that changed (based on hash comparison). Same result as a full remap but ~98% cheaper. |
| **Full remap** | Deletes the existing map and rebuilds everything from scratch -- extraction, taxonomy design, categorization, verification. |
| **Registry** | `_registry.json` -- the master list of all mapped projects with their root paths, function counts, and timestamps. |
| **Routing rules** | Keywords in `_taxonomy.json` that automatically sort functions into categories (e.g., functions in `htdocs/api/` go to `dashboard-api`). |
| **Sub-project** | A separate codebase that lives inside a parent project but gets its own independent map (own `_functions.json`, `_taxonomy.json`, categories). Declared in the parent's `_meta.json` under `sub_projects`. Example: my-webapp's cli.js decompilation (~16,990 functions) is a sub-project of my-webapp (584 functions). |
| **Third-party library map** | A shared function map for a bundled third-party library (e.g., jQuery, Bootstrap, FullCalendar), stored in `third-party/{lib}/{version}/`. Deduplicated across projects -- if two projects bundle jQuery 2.1.4, only one map exists and both reference it. Created automatically during categorization when taxonomy rules have `library`/`version` fields. |
| **`library`/`version` fields** | Optional annotations on `third_party` taxonomy rules that identify the library name and version. Enables mapping to the shared third-party location. Version auto-detected from `package.json`, `composer.json`, `bower.json`, and source headers when possible. |

---

## Which command do I use?

### `/functionmap <project> [path]` -- Full interactive remap

**When to use:**
- First time mapping a project (no existing map)
- You want to redesign the taxonomy (rename categories, split/merge groups, add routing rules)
- The taxonomy has drifted and too many functions are landing in `uncategorized`
- You want hands-on control over how functions are organized

**What it does:**
1. Scans all source files and extracts every function signature
2. Claude proposes a taxonomy -- you review and iterate on it together
3. Functions are categorized, verified, and indexed
4. Generates `_hashes.json` so future incremental updates work

**Cost:** ~30,000 tokens per project. Interactive -- runs in your current conversation.

**Flags:**
```
/functionmap my-webapp                          # Map current directory as "my-webapp"
/functionmap my-webapp ~/projects/my-webapp  # Map a specific path
/functionmap my-webapp --ignore-dir evidence    # Skip directories
/functionmap my-webapp --include-vendor         # Include vendor/node_modules
/functionmap my-webapp --subproject path/to/other/codebase  # Add a sub-project
/functionmap my-webapp --subproject-only --subproject path/to/sub  # Map ONLY the sub-project
```

---

### `/functionmap-update [projects] [flags]` -- Incremental batch update

**When to use:**
- Regular maintenance -- "have any functions changed since the last map?"
- After editing source files and wanting the map to reflect changes
- Updating multiple projects at once without babysitting each one

**What it does:**
1. Compares file hashes to find what changed (via `quickmap.py`)
2. Re-extracts functions from only the changed files
3. Re-categorizes using the existing taxonomy (no redesign)
4. Updates the registry and index

**Cost:** ~300-500 tokens per project (vs ~30,000 for full remap). Runs in seconds.

**Flags:**
```
/functionmap-update                    # Incremental update ALL projects
/functionmap-update my-webapp            # Just one project
/functionmap-update my-webapp data-layer      # Multiple specific projects
/functionmap-update --dry-run          # Show plan without executing
/functionmap-update --force            # Skip confirmation prompt
/functionmap-update --full             # Force full remap (all projects in scope)
/functionmap-update my-webapp --full     # Force full remap (just my-webapp)
/functionmap-update my-cms-2-5 --with-deps  # Include dependency chain
```

**`--full` runs a full remap autonomously** -- same as `/functionmap` but without interactive taxonomy review. An agent runs the whole pipeline in the background. Use this when you want a fresh remap but don't need to steer the taxonomy.

---

## Decision flowchart

```
Do you have an existing map for this project?
  NO  --> /functionmap <project> <path>
  YES --> Has the taxonomy drifted? Too many uncategorized?
            YES --> /functionmap <project> (interactive taxonomy redesign)
            NO  --> /functionmap-update <project> (incremental, seconds)
                      Still not right? --> /functionmap-update <project> --full
                                           (autonomous full remap, no review)
```

---

## Sub-projects

Some projects contain a separate codebase that's big enough to deserve its own map. Rather than lumping everything into one giant function list, you can declare **sub-projects** -- each gets its own extraction, taxonomy, categories, and hashes, but they live under the parent project's folder.

**Example:** My-Webapp has 584 of its own functions, but also contains the decompiled cli.js source with ~16,990 functions. Those are completely different codebases with different languages, patterns, and categories -- so cli.js is mapped as a sub-project.

**How to create one:**

Pass `--subproject` (or `--sub-project`) when running `/functionmap`:
```
/functionmap my-webapp ~/projects/my-webapp --subproject ~/projects/my-webapp/vendor-decompiled/v2.1.70/output
```

The sub-project name is derived from the directory name (e.g., `output` in this case). You can pass `--subproject` multiple times for multiple sub-projects.

Sub-projects are **never auto-detected** -- they only exist if you explicitly specify them with `--subproject`.

**What it creates:**

The sub-project config is stored in the parent's `_meta.json` under `sub_projects`, and each sub-project gets its own folder:
```
~/.claude/functionmap/my-webapp/
  _functions.json          # Parent's 584 functions
  _meta.json               # Parent config (includes sub_projects dict)
  _taxonomy.json           # Parent's categories
  _hashes.json             # Parent's file hashes
  output/                  # Sub-project folder
    _functions.json        # Sub-project's ~16,990 functions
    _taxonomy.json         # Sub-project's own categories
    _hashes.json           # Sub-project's own file hashes
```

**Updating sub-projects:**
- `/functionmap-update` handles sub-projects automatically -- quickmap.py reads `sub_projects` from `_meta.json` and runs incremental updates on each one after the parent. No extra flags needed.
- To re-run a full `/functionmap` with the same sub-projects, pass the same `--subproject` flags again.
- To add or update a single sub-project without touching the parent, use `--subproject-only`:
  ```
  /functionmap my-webapp --subproject-only --subproject ~/projects/my-webapp/vendor-decompiled/v2.1.71/output
  ```
  This extracts, taxonomizes, and categorizes only the sub-project. The parent's maps are untouched. The parent's `_meta.json` is updated to include the new sub-project (existing sub-projects are preserved).

---

## What lives where

```
~/.claude/functionmap/
  _registry.json              # Master project list
  my-webapp.md                  # Project index (category listing)
  my-webapp/
    _meta.json                # Project config (root path, ignore dirs, counts)
    _functions.json           # All extracted function signatures
    _taxonomy.json            # Category tree + routing rules
    _hashes.json              # File hashes for incremental updates
    preload-core--core.md     # Category file (functions grouped by category)
    dashboard-api--core.md    # Another category file
    ...
  third-party/                # Shared third-party library maps
    _index.json               # Master registry of all mapped libs
    third-party.md            # Human-readable master index
    fullcalendar/
      6.1.19/                 # One directory per version
        _functions.json
        _meta.json
        fullcalendar-6.1.19.md  # Version index
        {category}.md           # Category files
    bootstrap/
      3.3.5/...
    jquery/
      2.1.4/...

~/.claude/tools/functionmap/
    functionmap.py            # Extractor + CLI utilities
    categorize.py             # Sorts functions into taxonomy categories
    quickmap.py               # Incremental update engine (hash-based)
    thirdparty.py             # Third-party library mapping + deduplication
```

---

## Common scenarios

| I want to... | Command |
|--------------|---------|
| Map a project for the first time | `/functionmap myproject /path/to/code` |
| Check if anything changed across all projects | `/functionmap-update` |
| Update one project after editing files | `/functionmap-update myproject` |
| See what would be updated without doing it | `/functionmap-update --dry-run` |
| Redo the taxonomy from scratch | `/functionmap myproject` |
| Full remap without interactive review | `/functionmap-update myproject --full` |
| Full remap everything, no review | `/functionmap-update --full` |
| Map a project with a sub-project | `/functionmap myproject /path/to/code --subproject /path/to/subcode` |
| Add/update just one sub-project | `/functionmap myproject --subproject-only --subproject /path/to/sub` |
| Update MyCMS and all its library deps | `/functionmap-update my-cms-2-5 --with-deps` |
| See all mapped third-party libraries | Read `~/.claude/functionmap/third-party/third-party.md` |
| Look up a third-party library's API | Read `~/.claude/functionmap/third-party/{lib}/{version}/{lib}-{version}.md` |
| Force re-map third-party libs for a project | `/functionmap-update myproject --remap-third-party` (or pass `--remap-third-party` to quickmap.py) |
| Check which projects use a library | Read `third-party/_index.json` -- each version has a `used_by` list |
