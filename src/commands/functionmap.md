---
description: Deep-scan a repo/dir and (re)build a fully-interlinked function map tree under ~/.claude/functionmap, then verify correctness with a second pass.
argument-hint: <projectName|path> [project|<path>] [--include-vendor] [--ignore-dir <name> ...] [--subproject <path> ...] [--subproject-only]
allowed-tools: Bash(*), Read, Grep, Glob, Write, Edit
---

# /functionmap — Project-wide Function Network Map (max coverage, minimal context)

**If the argument is `help`**: Read and output `$HOME/.claude/docs/functionmap-help.md` in full, then stop. Do not run the extraction pipeline.

You are running inside **Claude Code** as the `/functionmap` command.

## THE FUNDAMENTAL GOAL (Never lose sight of this)

This command exists to solve a critical problem: **Claude's context window is finite, but codebases are vast.**

Without function mapping:
- Claude either floods context with irrelevant functions (wasting tokens)
- Or misses existing functionality and reinvents wheels (wasting effort)

With function mapping:
- Claude consults a **categorized index** of functions, loading only what's needed for the current task
- Existing functionality is discovered before new code is written
- Cross-project dependencies are navigable (my-cms → data-layer → string-utils)
- Context stays lean; knowledge stays comprehensive

**Every decision in this command serves that goal: maximum discoverability, minimum context waste.**

---

## Non‑negotiables (do not "optimize" these away)

1. **Full remap on re-run**: Running `/functionmap` for an already-mapped project MUST delete the old map folder and regenerate everything from scratch. We never keep stale references. **However:** before deleting, snapshot the old `_functions.json` to `_functions.prev.json` so a diff report can show what changed (new/removed/modified functions). Delete `_functions.prev.json` only after the diff is reported.

2. **Maximal function coverage**: Map *every* named function and method you can detect:
   - Public, protected, private (all exposures)
   - Static, instance, async, generator
   - Class methods, standalone functions, closures assigned to constants
   - **Why?** Because "private" functions can still be useful references. A developer might see a private security function and realize they need to make it public, or understand a pattern to replicate elsewhere.

3. **Context discipline**: Do NOT dump function lists into chat. Output is markdown files on disk. In chat, print only:
   - Summary statistics (files scanned, functions found, categories created)
   - Paths to generated files
   - Verification results
   - Next steps if issues found

4. **Verification is mandatory**:
   - Automated verification pass (check that documented functions actually exist at documented locations)

5. **Interconnection over duplication**: If Project A uses Library B, and both are mapped:
   - Project A's function map should **reference** Library B's map for B's functions
   - Project A's map should **only document** functions unique to Project A
   - Exception: If Library B isn't mapped yet, temporarily document those functions in Project A, but mark them as "from unmapped dependency - remap after mapping [Library B]"

---

## Where outputs live (Windows)

All generated files:
```
$HOME/.claude/functionmap/
```

Global instruction file:
```
$HOME/.claude/CLAUDE.md
```

**Example output structure for project `my-cms`:**
```
$HOME/.claude/functionmap/
├── _registry.json                      # Global registry of all mapped projects
├── my-cms.md                            # Project index (category listing + usage guide)
└── my-cms\
    ├── _functions.json                 # Raw function data (for verification)
    ├── _metadata.json                  # Version, scan date, root path
    ├── security.md                     # Security-related functions
    ├── plugins.md                      # Plugin system functions
    ├── database.md                     # Database/query functions
    ├── auth.md                         # Authentication/authorization
    ├── validation.md                   # Input validation/sanitization
    ├── file-handling.md                # File operations/uploads
    ├── templating.md                   # Template/rendering functions
    ├── utilities.md                    # General utilities
    ├── libraries.md                    # Dependency links to other maps
    └── [other categories as detected]
```

**Example output structure for library `data-layer`:**
```
$HOME/.claude/functionmap/
├── data-layer.md                            # Library index
└── data-layer\
    ├── _functions.json
    ├── _metadata.json
    ├── query-building.md               # Query construction functions
    ├── connection.md                   # Connection management
    ├── results.md                      # Result handling
    ├── security.md                     # SQL injection prevention
    └── libraries.md                    # Empty or links to sub-dependencies
```

**Shared third-party library maps (auto-generated during categorization):**
```
$HOME/.claude/functionmap/
└── third-party\
    ├── _index.json                     # Master registry of all mapped libs
    ├── third-party.md                  # Human-readable master index
    ├── fullcalendar\
    │   ├── _versions.json
    │   └── 6.1.19\
    │       ├── _functions.json         # Functions for this version
    │       ├── _meta.json              # Metadata (source project, file count)
    │       ├── _taxonomy.json          # Auto-generated taxonomy
    │       ├── fullcalendar-6.1.19.md  # Version index (category listing)
    │       └── {category}.md           # Category files
    ├── bootstrap\
    │   └── 3.3.5\...
    └── jquery\
        └── 2.1.4\...
```

Third-party library maps are shared across projects. If project A already mapped jQuery 2.1.4, project B using the same version just references it (added to `used_by` list). Versions are auto-detected from `package.json`, `composer.json`, `bower.json`, source headers, and path patterns. Libraries without detectable versions use `"unknown"`.

---

## Argument interpretation

The installed generator script supports these invocation patterns:

**Auto-detect project name from current directory:**
```
/functionmap
```
→ Scans current directory, uses folder name as project name

**Explicit project name, scan current directory:**
```
/functionmap my-cms
/functionmap my-cms project
```
→ Scans current directory, names it `my-cms`

**Scan specific path, infer project name:**
```
/functionmap ~/projects/data-layer
```
→ Scans that directory, project name = `data-layer`

**Explicit project name + path:**
```
/functionmap my-cms ~/projects/client-site/htdocs/my-cms
```
→ Scans that directory, names it `my-cms`

**Version-specific naming (RECOMMENDED for libraries with multiple versions):**
```
/functionmap my-cms@3.80 project
/functionmap my-cms@3.82 ~/projects/my-cms
/functionmap data-layer@2.1.0 ~/projects/data-layer
```
→ Creates separate maps for each version

**Additional flags:**
- `--include-vendor` — Include vendor/ and node_modules/ (usually not recommended, bloats map)
- `--ignore-dir <name>` — Exclude specific directories (repeatable)
- `--ignore-dir tests --ignore-dir docs` — Exclude multiple directories
- `--subproject <path>` (or `--sub-project`) — A separate directory to map as a sub-project (repeatable). Gets its own extraction, taxonomy, categories, and hashes under the parent project's folder. Sub-project name is derived from the directory name. Example:
  ```
  /functionmap my-webapp ~/projects/my-webapp --subproject ~/projects/my-webapp/vendor-decompiled/v2.1.70/output
  ```
- `--subproject-only` — **Only process sub-project(s); skip the parent project entirely.** Requires `--subproject` and an already-mapped parent. Use this to add or update a single sub-project without re-extracting the parent. Example:
  ```
  /functionmap my-webapp --subproject-only --subproject ~/projects/my-webapp/vendor-decompiled/v2.1.71/output
  ```

**Sub-project rules:**
- Sub-projects are ONLY created when the user explicitly passes `--subproject`. Do NOT auto-detect or suggest sub-projects.
- If a project already has sub-projects from a previous run (recorded in `_meta.json`), preserve them on re-run -- pass the same `--subproject` flags to update them, or omit to drop them.
- Each sub-project gets its own Phase 2 taxonomy design (separate `_taxonomy.json`) since it's a different codebase with different patterns.
- `--subproject-only` merges into the parent's `_meta.json` without touching the parent's own maps. Existing sub-projects not named in the current run are preserved.

---

## Subproject-only mode

**When `--subproject-only` is passed**, the pipeline is shortened:

1. **Pre-flight**: Verify Python tools exist and parent project is already mapped (has `_meta.json`)
2. **Run extraction** for only the sub-project(s):
   ```bash
   python "$HOME/.claude/tools/functionmap/functionmap.py" {project} --subproject-only --subproject {path}
   ```
3. **Phase 2 (taxonomy)** and **Phase 3 (categorization)** run for the sub-project ONLY. Skip the parent entirely.
4. **Phase 4 (verification)** runs for the sub-project ONLY.
5. **Update CLAUDE.md** registry if needed (sub-project function count may appear in the parenthetical).
6. **Done.** Parent's own maps, taxonomy, and categories are untouched.

Skip to Phase 2 after running the extraction command above. All Phase 2/3/4 instructions apply but are scoped to the sub-project only.

---

## Enrichment files (optional)

Projects can optionally provide an `_enrichment.json` file alongside `_functions.json` in their functionmap directory. This file provides supplementary metadata that wasn't extractable from source code analysis -- human annotations, AI-generated descriptions, naming data from decompilation, etc.

Enrichment files are loaded automatically by `categorize.py` during Phase 3. No special flags are needed. If no `_enrichment.json` exists, categorization proceeds as normal.

**Schema:**
```json
{
  "version": 1,
  "source": "description of where the data came from",
  "key_format": "file:name:line | name_only | custom",
  "entries": {
    "function_key": {
      "displayName": "Human Readable Name",
      "description": "What this function does",
      "category_hint": "suggested-category",
      "library": "library-name or null",
      "confidence": "confident | tentative | unknown",
      "tags": ["ai-analyzed", "third-party"],
      "notes": "additional context"
    }
  }
}
```

**Key format modes:**
- `file:name:line` -- keys are `file::short_name::line_start` (most precise, for normal projects)
- `name_only` -- keys are `short_name` alone (for decompiled code where function names are unique)
- `custom` -- each entry has `match_field` and `match_value` for arbitrary matching

**What enrichment does:**
- `displayName` overrides the function heading in markdown (original name shown in parentheses)
- `description` supplements or overrides docblock descriptions
- `category_hint` routes otherwise-uncategorized functions to the hinted category (only if the category exists in taxonomy)
- `library`, `confidence`, `tags`, `notes` appear as metadata in the function entry

All entry fields are optional. Sub-projects can have their own `_enrichment.json` independent of the parent.

---

## Phase 1 — Function extraction (authoritative output)

### Step 1.1: Pre-flight checks

Before running the extractor:

1. **Verify tools exist:**
   ```bash
   test -f "$HOME/.claude/tools/functionmap/functionmap.py" || echo "ERROR: functionmap.py not found"
   test -f "$HOME/.claude/tools/functionmap/categorize.py" || echo "ERROR: categorize.py not found"
   ```
   If missing, STOP and inform user they need to install the functionmap tools first.

2. **Detect project version if possible:**
   - For PHP projects: Look for `composer.json` → `version` field
   - For MyCMS: Look for `lib/version.php` or similar
   - For Node projects: Look for `package.json` → `version` field
   - If version detected and user didn't specify `@version` in project name, **prompt user:**
     ```
     Detected version X.Y.Z for this project.

     Recommended: /functionmap {project}@X.Y.Z

     This allows different versions to coexist without conflicts.
     Continue with plain name, or use versioned name?
     ```

3. **Check for existing map:**
   If `$HOME/.claude/functionmap/{project}.md` exists:
   ```
   Found existing function map for {project}.

   This will be completely regenerated (old map deleted).
   All references in other projects will be updated.

   Continue? [This is the expected behavior - proceed unless user cancels]
   ```

### Step 1.2: Snapshot previous map (if exists)

Before deleting the old map, preserve the old function data for diffing:

```bash
python "$HOME/.claude/tools/functionmap/functionmap.py" --snapshot {project}
```

Now delete the old map directory (except the snapshot) and proceed with extraction.

### Step 1.3: Run the extractor

Execute the Python extractor (this extracts raw function data only -- no categorization):

```bash
python "$HOME/.claude/tools/functionmap/functionmap.py" [ARGUMENTS]
```

**Progress monitoring for large projects:** The Python extractor can take significant time on large codebases (9000+ functions). After launching it, if the project's previous function count was >500, monitor progress by checking the output file size periodically:

```bash
# For large projects, check extraction progress
while ! [ -f "$HOME/.claude/functionmap/{project}/_functions.json" ]; do sleep 2; done
python -c "import json; funcs=json.load(open('$HOME/.claude/functionmap/{project}/_functions.json')); print(f'Extracted: {len(funcs)} functions')"
```

Print intermediate progress to chat so the user knows the extraction is working, not hung.

The extractor will:
1. **Scan all files** in the target directory (recursively)
2. **Extract functions** using language-specific parsing:
   - PHP: `function name(`, `fn(`, methods in classes, closures
   - JavaScript/TypeScript: `function name`, `const name = function`, `async`, `export`, class methods
3. **Write raw function data** to `_functions.json` (no categories)
4. **Write metadata** to `_meta.json` (project name, root path, timestamps)

**What the extractor writes:**
- `{project}/_functions.json` — Raw function data (for taxonomy design + categorization)
- `{project}/_meta.json` — Version, timestamps, root path, scan config (ignore_dirs, include_vendor)
- `{project}/_hashes.json` — Per-file SHA-256 hashes (for incremental updates via `/functionmap-update`)

**Important:** The extractor does NOT categorize or generate markdown. That happens in Phase 2 (taxonomy design) and Phase 3 (categorization).

### Step 1.4: Function diff report

If `_functions.prev.json` exists, generate a diff report showing what changed:

```bash
python "$HOME/.claude/tools/functionmap/functionmap.py" --diff {project}
```

Print the diff summary to chat. This helps the user understand whether the remap was worthwhile and what changed in their codebase since the last map.

### Step 1.5: Build call graph and content anchors

After extraction, build the inter-function call graph and extract content anchors for change tracking:

```bash
node "$HOME/.claude/tools/functionmap/build-callgraph.cjs" {project}
```

This produces `{project}/_callgraph.json` containing:
- **Call edges**: which functions call which other functions (regex-based, ~80% accuracy)
- **Content anchors**: distinctive string literals per function (for tracking functions across refactors)
- **Orphan detection**: functions never called by anything (potential dead code)

The call graph improves taxonomy design (Phase 2) because:
- Functions that call each other should be in the same category
- Functions called by many others are likely utilities/helpers
- Orphaned functions may indicate dead code or entry points

**Using the call graph in taxonomy design (Phase 2):**
When analyzing the project for categories, consult `_callgraph.json` stats:
- Functions with many callers (`calledBy.length > 5`) are shared utilities
- Tight call clusters (group of functions that only call each other) form natural categories
- If keyword routing puts a function in "error-handling" but its callers are all in "auth", it probably belongs in "auth"

**Content anchors for `/functionmap-update`:**
When a function moves between files (refactor), `_callgraph.json` anchors help `quickmap.py` recognize it as a move rather than a deletion + addition. The anchor is a distinctive string literal that uniquely identifies the function regardless of its file location.

---

## Phase 2 — Taxonomy design (Claude-driven, project-specific)

This is the key innovation: **Claude analyzes the project structure and designs a taxonomy tailored to THIS project's domain, rather than using hard-coded categories.**

### Step 2.1: Analyze the project

Read the project structure to understand what categories make sense:

1. **Read _functions.json summary** -- don't load the full file into context. Instead, extract key statistics:
   ```bash
   python "$HOME/.claude/tools/functionmap/functionmap.py" --analyze {project}
   ```

2. **Read call graph stats** (if `_callgraph.json` exists):
   ```bash
   node -e "const cg=JSON.parse(require('fs').readFileSync(require('os').homedir()+'/.claude/functionmap/{project}/_callgraph.json','utf8'));console.log(JSON.stringify(cg.stats,null,2))"
   ```
   Use the call graph to identify:
   - **Natural clusters**: Groups of functions that call each other heavily
   - **Shared utilities**: Functions with many callers (calledBy > 5)
   - **Entry points**: Functions with callers but no calls (leaf functions with external callers)
   - **Orphans**: Functions with 0 calls and 0 calledBy (potential dead code or standalone utilities)

3. **Scan project directory tree** -- use Glob/Bash to see the overall structure:
   ```bash
   ls -la "{scan_root}"
   ```

4. **Look for project-specific patterns:**
   - Plugin/module system? (e.g., `plugins/`, `modules/`, `packages/`)
   - Third-party bundled code? (e.g., `vendor/`, `node_modules/`, specific library dirs)
   - Test directories? (usually excluded from function maps)
   - Configuration/data directories?

4. **Annotate third-party rules with `library`/`version` (MANDATORY for all third-party rules):**
   For each `third_party` routing rule, add `"library"` and `"version"` fields so the categorizer can map them to the shared third-party location. Without these fields, third-party functions are excluded but never mapped -- they become invisible to future sessions. Key considerations:
   - Multiple rules can point to the same library (e.g., 15 Bootstrap component rules all get `"library": "bootstrap", "version": "3.3.5"`)
   - Version auto-detection checks `package.json`, `composer.json`, `bower.json`, and source headers -- but explicit annotation is recommended for clarity
   - Libraries without detectable versions get `"unknown"` -- warn the user to add explicit version info
   - Check if the library is already mapped in `third-party/_index.json` before spending time on annotation (it may already exist from another project)

### Step 2.2: Design the taxonomy

Based on the analysis, design categories that match THIS project's domain. Create a `_taxonomy.json` file with:

**Categories (10-25 depending on project size):**
- Each category should represent a **semantic domain** (what functions DO, not where they LIVE)
- Category descriptions should help future Claude sessions find what they need
- Include subcategories for large domains (>50 functions)

**Routing rules (in priority order):**
- `third_party` — Patterns for bundled third-party code to exclude
- `deprecated` — Patterns for legacy/deprecated code
- `namespace_routes` — Map namespace prefixes to categories (most specific first)
- `directory_routes` — Map directory prefixes to categories
- `file_routes` — Map specific files to categories
- `keyword_routes` — Map function name keywords to categories (fallback)

**Usage examples (recommended for non-test categories):**
- Add 1-3 `usage_examples` per category showing the most common patterns
- Examples should show real-world usage, not just method signatures
- Include cross-library chaining where applicable (e.g., DB::select()->pluck()->implode())
- Each example needs: `title` (what it demonstrates), `code` (runnable snippet), `language` (php/js/ts), `notes` (brief explanation)
- For typed-variant categories, add a `variant_note` field explaining the override pattern, e.g.: "Methods here return the same variant type as the caller. Calling pluck() on ArrayUtilsHtml returns ArrayUtilsHtml, preserving HTML encoding."

**Sizing guidelines:**
- Small project (<200 functions): 5-10 categories
- Medium project (200-2000 functions): 10-15 categories
- Large project (2000+ functions): 15-25 categories
- Each category should have 10-200 functions (split if larger)

### Step 2.3: Write _taxonomy.json

Write the taxonomy to the project directory:

```
$HOME/.claude/functionmap/{project}/_taxonomy.json
```

**Schema:**

```json
{
  "version": 1,
  "project": "project-name",
  "project_version": "1.0.0",
  "root_path": "~/projects/path//to//project",
  "generated_at": "2026-03-03T10:00:00",

  "categories": {
    "category-slug": {
      "description": "Rich description for discovery. Explains what this category covers and when to use it.",
      "usage_examples": [
        {
          "title": "Common operation name",
          "code": "// Example code showing typical usage",
          "language": "php",
          "notes": "Brief explanation of the pattern."
        }
      ],
      "variant_note": "Optional note about return type behavior for variant/override categories.",
      "subcategories": {
        "sub-slug": {
          "description": "Subcategory description."
        }
      }
    },
    "uncategorized": {
      "description": "Functions that did not match any routing rule.",
      "subcategories": {}
    }
  },

  "routing_rules": {
    "third_party": [
      {"type": "path_contains", "pattern": "vendor/", "reason": "Composer dependencies"},
      {"type": "path_contains", "pattern": "fullcalendar-6.1.19", "reason": "Bundled FullCalendar library",
       "library": "fullcalendar", "version": "6.1.19"},
      {"type": "path_contains", "pattern": "jquery", "exclude_language": "php", "reason": "Bundled jQuery JS",
       "library": "jquery", "version": "2.1.4"}
    ],
    "deprecated": [
      {"type": "path_contains", "pattern": "old_alias", "category": "deprecated", "subcategory": "aliases"}
    ],
    "namespace_routes": [
      {"pattern": "App\\DB\\Query", "category": "database", "subcategory": "queries"},
      {"pattern": "App\\DB", "category": "database", "subcategory": "core"}
    ],
    "directory_routes": [
      {"pattern": "src/Database/", "category": "database"},
      {"pattern": "src/Auth/", "category": "authentication"}
    ],
    "file_routes": [
      {"file": "src/helpers.php", "category": "utilities", "subcategory": "helpers"}
    ],
    "keyword_routes": [
      {"keywords": ["select", "query", "where", "join"], "category": "database"},
      {"keywords": ["login", "auth", "password", "session"], "category": "authentication"}
    ]
  }
}
```

**Rule types supported:**
- `path_contains` — Case-insensitive substring match on file path
- `path_prefix` — File path starts with pattern
- `path_regex` — Regex match against file path
- `file_exact` — Exact file path match

**Rule modifiers:**
- `exclude_language` — Skip match if function is in this language (e.g., exclude PHP files from jQuery detection)
- `class` — (namespace_routes only) Additional class name filter
- `file_contains` — (namespace_routes only) Additional file path filter

**Third-party library fields (optional, on `third_party` rules):**
- `library` — Canonical library name (e.g., `"fullcalendar"`, `"bootstrap"`, `"jquery"`). When multiple rules match the same library (e.g., 15 separate Bootstrap component file rules), they all merge into one shared library map.
- `version` — Library version string (e.g., `"6.1.19"`, `"3.3.5"`). Use `"unknown"` if version cannot be determined. The pipeline also auto-detects versions from `package.json`, `composer.json`, `bower.json`, and source file headers when possible.

When `library`/`version` are present, the categorizer maps those functions to the shared third-party location (`~/.claude/functionmap/third-party/{library}/{version}/`) instead of just listing them in `third-party-bundled.md`. If the library+version is already mapped (by another project), functions are deduplicated -- only a reference is added.

**Important principles:**
- More specific rules go FIRST in each section (first match wins)
- Namespace routes should go from most specific to least specific
- Directory routes should go from deepest path to shallowest
- Every function should land in a meaningful category or "uncategorized"
- Always include an "uncategorized" category as safety net

### Step 2.4: Verify taxonomy coverage

After writing _taxonomy.json, do a quick sanity check:

```bash
python "$HOME/.claude/tools/functionmap/functionmap.py" --preview-taxonomy {project}
```

**Quality thresholds (hard requirements, not suggestions):**
- `uncategorized` MUST be <15% of functions
- No single category may have >40% of functions
- Categories with <5 functions should be merged into a related category

**Mandatory iteration loop (max 3 rounds):**

This is NOT optional. If coverage fails any threshold above:

1. **Round 1**: Design initial taxonomy, run coverage preview
2. **If thresholds fail**: Diagnose why (examine the uncategorized functions' namespaces, paths, and names), add targeted routing rules, re-run preview
3. **Round 2**: Re-check. If still failing, split dominant categories or merge tiny ones
4. **Round 3**: Final attempt. If still failing after 3 rounds, proceed but print a prominent warning:
   ```
   WARNING: Taxonomy coverage did not meet thresholds after 3 iterations.
   uncategorized: 22% (threshold: <15%)
   
   ```

Do NOT silently accept a poor taxonomy on the first try. The iteration is what makes the taxonomy actually useful.

---

## Phase 3 — Categorization & markdown generation

Run the categorizer, which reads `_taxonomy.json` and `_functions.json` to produce categorized markdown:

```bash
python "$HOME/.claude/tools/functionmap/categorize.py"
```

The categorizer will:
1. **Load taxonomy** from `_taxonomy.json`
2. **Load functions** from `_functions.json`
3. **Separate third-party** from first-party code
4. **Map third-party libraries** to the shared location (`third-party/{lib}/{version}/`) when `library`/`version` fields are present on taxonomy rules. Libraries already mapped by another project are deduplicated (only `used_by` is updated). Version detection from package metadata files is attempted automatically.
5. **Categorize each function** using taxonomy routing rules
6. **Consolidate** tiny subcategories (<3 functions) into "other"
7. **Split** oversized subcategories (>250 functions) by file clustering
8. **Generate category markdown files** with function documentation
9. **Generate project index** (`{project}.md`) with category listing + third-party library table
10. **Generate third-party summary** if applicable

**What the categorizer writes:**
- `{project}/{top-cat}--{sub-cat}.md` — One file per subcategory
- `{project}/third-party-bundled.md` — Excluded third-party code summary (with links to mapped libraries)
- `{project}.md` — Project index with all categories + "Third-Party Libraries" table
- `third-party/{lib}/{version}/` — Shared library maps (category files, `_functions.json`, `_meta.json`, index `.md`). Only created for libraries with `library`/`version` annotations on their taxonomy rules.
- `third-party/_index.json` — Master registry of all mapped third-party libraries
- `third-party/third-party.md` — Human-readable master index of all third-party library maps

### Step 3.1: Post-categorization tasks

After categorize.py finishes, you (Claude) should:

1. **Validate usage examples in taxonomy:**
   For each category in `_taxonomy.json` that has `usage_examples`, verify the examples reference functions that actually exist in the newly generated category markdown files. If an example references a function that was removed or renamed:
   - Update the example to use a current function, OR
   - Remove the stale example entirely
   Stale examples that reference non-existent functions are actively misleading -- worse than no examples.

2. **Enrich project index descriptions (use call graph if available):**
   After categorization, you know exactly what's in each category. Update each category's description in the project index (`{project}.md`) to include:
   - The most important/commonly-used function names (top 3-5 by likely usage)
   - Specific guidance on when to load this category ("Load this when working with file uploads, media thumbnails, or download handlers")
   - **If `_callgraph.json` exists**: Include key call relationships. For example: "Entry point: `handleUpload()` which calls `validateMime()`, `resizeImage()`, `storeFile()`". This shows the flow through the category, not just a flat list.
   The goal: a developer reading ONLY the project index should be able to identify the right category without opening individual category files. Generic descriptions like "Database functions" should become "Query building (DB::select, DB::insert, DB::update), connection management, result hydration. Load when writing or modifying database queries."

3. **Generate `libraries.md`** with dependency links:
   - Scan for `require`, `use`, `import`, `composer.json`, `package.json`
   - Link to other mapped projects in `~/.claude/functionmap/`
   - Note unmapped dependencies

4. **Update global registry** (`_registry.json`):

   ```bash
   python "$HOME/.claude/tools/functionmap/functionmap.py" --update-registry {project}
   ```

   The registry update uses file locking to handle parallel `/functionmap-update` agents safely.

5. **Update global CLAUDE.md** with reference to this map (see Updating global CLAUDE.md section below).

---

## Phase 4 — Automated verification pass (MUST RUN)

Now perform a mechanical sanity check against what was just generated.

### What this checks:

1. **File existence:** Do the files referenced in `_functions.json` actually exist at the recorded `root_path`?
2. **Line accuracy:** Does the function signature appear near the recorded line number (±4 lines)?
3. **Signature matching:** Does the function name match the pattern for its language?
   - PHP: `function {name}(`
   - JS: `function {name}(`, `{name} = function`, `{name} = async`, etc.

### How to run it:

```bash
python "$HOME/.claude/tools/functionmap/functionmap.py" --verify {project}
```

### Auto-fix: line drift correction

Many `SIG_NOT_FOUND_NEAR_LINE` mismatches are caused by **line drift** -- the function still exists in the same file but shifted up or down due to code changes. Before reporting these as failures, attempt auto-correction:

For each `SIG_NOT_FOUND_NEAR_LINE` mismatch:
1. Search the ENTIRE file for the function signature (not just the +/-4 line window)
2. If found elsewhere in the same file, update `_functions.json` with the corrected line number
3. Report as "auto-corrected drift" rather than "mismatch"
4. Only report as a true mismatch if the signature is not found anywhere in the file

After the auto-fix pass, re-run the verification script on the corrected `_functions.json` to confirm fixes are accurate.

Print the auto-fix summary:
```
[functionmap:verify] Auto-corrected 14 line-drift mismatches
[functionmap:verify] Remaining true mismatches: 3
```

### Interpreting results:

**Clean verification (0 remaining mismatches after auto-fix):**
- Parser did its job correctly
- All functions documented actually exist where claimed
- Line numbers may have drifted but were corrected


**Low mismatches (<5% of total after auto-fix):**
- Usually edge cases: functions defined across multiple lines, unusual formatting
- Note them but not a major concern


**High mismatches (>10% of total after auto-fix):**
- Parser likely missed common patterns in this codebase
- **Do NOT silently accept this**

- May need to update parser and re-run

**Common mismatch causes:**
- PHP arrow functions: `fn() =>`
- JS export patterns: `export default function`, `export const foo = () =>`
- Async patterns: `async function`, `async () =>`
- Generator functions: `function* name()`, `async function* name()`
- Methods with attributes: `#[Route]` `public function`
- Multiline signatures split across lines


## Phase 5 -- Usability self-test (MUST RUN)

After all generation and fixes are complete, verify the map is actually usable by simulating a real lookup.

### What this tests:

Can a future Claude session, starting from only the project index, find a specific function through the intended path?

### How to run it:

1. **Pick 5 functions at random** from `_functions.json` -- spread across different categories
2. **For each function, simulate the lookup path:**
   a. Read ONLY the project index (`{project}.md`)
   b. Based on the function's name/purpose, identify which category to load
   c. Open that category file
   d. Confirm the function appears in it with correct file path and signature
3. **Score each lookup:**
   - PASS: Found the function in the expected category on the first try
   - INDIRECT: Found it, but had to check 2+ categories (category description was misleading)
   - FAIL: Could not find it through the index at all (function exists in _functions.json but is not in any category file, or category description gives no clue)

### Interpreting results:

- **5/5 PASS**: Map is well-organized and discoverable
- **3-4 PASS, 1-2 INDIRECT**: Acceptable but note which category descriptions need improvement
- **Any FAIL**: Something is broken -- the function was categorized but the index doesn't lead to it. Fix the index descriptions immediately.
- **Multiple INDIRECT**: Category descriptions are too vague. Go back to Step 3.1 task 2 (Enrich project index descriptions) and improve them.

Print the self-test results:
```
Usability self-test:
  DB::select()           -> database/query-building.md     PASS
  validateEmail()        -> validation/input.md            PASS
  handleFileUpload()     -> file-handling/uploads.md       PASS
  renderBreadcrumbs()    -> templating/navigation.md       INDIRECT (tried ui.md first)
  Plugin::on()           -> plugins/hooks.md               PASS

Score: 4/5 PASS, 1/5 INDIRECT
```

---

## Versioning rules (avoiding cross-version footguns)

This system supports multiple versions as separate projects **if you name them explicitly.**

### Recommended version naming:

**For libraries you maintain:**
```
/functionmap data-layer@2.0.0 ~/projects/data-layer
/functionmap data-layer@2.1.0 ~/projects/data-layer-2.1
```

**For third-party dependencies:**
```
/functionmap my-cms@3.80 ~/projects/old-project/htdocs/my-cms
/functionmap my-cms@3.82 ~/projects/my-cms
```

This creates separate map trees:
- `~/.claude/functionmap/data-layer@2.0.0.md` + `data-layer@2.0.0/` folder
- `~/.claude/functionmap/data-layer@2.1.0.md` + `data-layer@2.1.0/` folder

### Version detection:

When you run `/functionmap project_name` without `@version`:

1. **Attempt auto-detection:**
   - PHP: Check `composer.json` → `version`, or `lib/version.php`, or define/const patterns
   - Node: Check `package.json` → `version`
   - MyCMS: Check for `$PRODUCT_VERSION` or similar

2. **If version detected, prompt user:**
   ```
   Detected version 3.82 for this project.

   Recommended naming: /functionmap my-cms@3.82

   This prevents version conflicts if you map multiple versions.

   Use versioned name? [Recommend: yes]
   ```

3. **If user declines or no version detected:**
   - Map with unversioned name
   - Note in `_metadata.json`: `"version_detected": "3.82"` or `"version_detected": "unknown"`

### Dependency version matching:

When Project A depends on Library B:

**Ideal case (exact match):**
- Project A uses `data-layer@2.1.0`
- Map exists for `data-layer@2.1.0`
- `libraries.md` links to `~/.claude/functionmap/data-layer@2.1.0.md`

**Close version (minor/patch difference):**
- Project A uses `data-layer@2.1.0`
- Only `data-layer@2.1.3` is mapped
- `libraries.md` links to `data-layer@2.1.3.md` with note:
  ```
  ⚠️ Using data-layer@2.1.3 map for data-layer@2.1.0 — minor version difference, should be compatible
  ```

**Major version mismatch:**
- Project A uses `data-layer@2.1.0`
- Only `data-layer@3.0.0` is mapped
- `libraries.md` links with strong caveat:
  ```
  ⚠️ Using data-layer@3.0.0 map for data-layer@2.1.0 — MAJOR version difference, verify all signatures before use
  ```

**No version mapped:**
- Project A uses `data-layer` (any version)
- No data-layer map exists at all
- `libraries.md` notes:
  ```
  data-layer — NOT YET MAPPED
  Run /functionmap data-layer to create function map for this dependency.
  ```

### Cross-project updates when mapping a new version:

When you run `/functionmap data-layer@2.1.0` and `data-layer@2.0.0` was already mapped:

1. **Both versions coexist** (they're separate projects)
2. **Consuming projects get re-linked to the best match:**
   - If Project A declared dependency on `data-layer@2.1.0`, it now links to `data-layer@2.1.0.md`
   - If Project A declared dependency on `data-layer@2.0.0`, it stays linked to `data-layer@2.0.0.md`
   - If Project A declared dependency on just `data-layer` (no version), it links to the **newest mapped version** with a note

### Version in CLAUDE.md global reference:

The global CLAUDE.md section should be version-aware:

```markdown
## Function Maps

When working on projects, consult function maps to discover existing functionality before reinventing wheels.

Available maps:
- my-cms@3.80: ~/.claude/functionmap/my-cms@3.80.md
- my-cms@3.82: ~/.claude/functionmap/my-cms@3.82.md
- data-layer@2.0.0: ~/.claude/functionmap/data-layer@2.0.0.md
- data-layer@2.1.0: ~/.claude/functionmap/data-layer@2.1.0.md
- my-webapp: ~/.claude/functionmap/my-webapp.md

When working on a project that uses one of these libraries:
1. Check the project's `~/.claude/functionmap/{project}/libraries.md` for dependency links
2. Follow links to dependency maps to find existing functions
3. Only implement new functionality if no existing function serves the need
4. Prefer exact version matches, but use close versions with caution if needed
```

---

## Updating global CLAUDE.md

After successful mapping, the generator should update `$HOME/.claude/CLAUDE.md` with a reference to the new map.

**If no "Function Maps" section exists, create it:**

```markdown
## Function Maps

When working on projects, consult function maps to discover existing functionality before reinventing wheels.

Available maps:
- {project}: ~/.claude/functionmap/{project}.md

When working on a project that uses mapped libraries:
1. Check the project's `~/.claude/functionmap/{project}/libraries.md` for dependency links
2. Follow links to dependency maps to find existing functions
3. Only implement new functionality if no existing function serves the need
```

**If "Function Maps" section exists, update the available maps list:**

```markdown
Available maps:
- {existing_project_1}: ~/.claude/functionmap/{existing_project_1}.md
- {existing_project_2}: ~/.claude/functionmap/{existing_project_2}.md
- {new_project}: ~/.claude/functionmap/{new_project}.md  ← newly added
```

**Keep the list sorted alphabetically for easy scanning.**

**The generator should do this automatically, but verify it happened.**

---

## When to use function maps (guidance for Claude)

This section is for **your future self** (Claude in other sessions) when consulting these maps.

**✅ DO consult function maps when:**
- Implementing new features (check for existing similar functionality first)
- Fixing bugs (understand what functions touch the affected area)
- Refactoring (see what depends on what)
- Adding validation/security (use existing hardened functions)
- Working with dependencies (see what's available instead of digging through source)
- Writing JS/PHP that calls bundled third-party libraries (check `third-party/{lib}/{version}/` for API surface)

**✅ DO load specific categories when:**
- You know what domain you're working in (security → load security.md)
- You want to see all functions in an area (validation → load validation.md)
- You're exploring what's available (skim category names in project index)

**❌ DON'T load function maps when:**
- You're just reading/understanding existing code (read the actual source)
- You need implementation details (maps show signatures, not logic)
- You're debugging runtime behavior (maps don't show control flow)

**🎯 Efficient usage pattern:**
1. User asks to implement feature X
2. Check project index: which category might have related functions?
3. Load that category file ONLY
4. Scan for relevant functions
5. If found: use it (read source to understand implementation)
6. If not found: check dependencies in libraries.md
7. Still not found: implement new function, note what category it should go in for next map update

**This keeps context lean while still avoiding wheel-reinvention.**

---

## Handling edge cases and errors

- **Generator fails**: Check the error message (permissions, Python not found, module imports). The Python script is authoritative -- don't implement it yourself.
- **>50% verification mismatches**: Generator failed badly. Check if wrong directory was scanned, root_path is wrong, or files moved. Delete bad map and re-run.
- **Massive pattern gaps** (e.g., "500 arrow functions, only 50 mapped"): Determine if the gap matters (assigned-to-const = yes, inline closures = no). If it matters, inform user the generator needs pattern updates.
- **No dependencies**: Fine. `libraries.md` will be nearly empty.
- **Missing dependency detection**: Manually edit `libraries.md` to add the link.
- **Nonsensical categories**: Keyword matching failed. Add domain-specific routing rules to `_taxonomy.json` and re-run categorizer.

---

## Final output (what to print in chat)

After all phases complete, print a concise summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FUNCTION MAP COMPLETE: {project_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 Scanned: {scan_root_path}
📊 Files: {file_count} | Functions: {function_count}

📂 Categories created:
   - security.md ({count} functions)
   - database.md ({count} functions)
   - plugins.md ({count} functions)
   - validation.md ({count} functions)
   - [... list all categories with counts ...]

🔗 Dependencies: {dependency_count}
   - {dep1} → {link_status}
   - {dep2} → {link_status}
   - [...]

📄 Project index: ~/.claude/functionmap/{project}.md

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  VERIFICATION RESULTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Automated check: {status}
   - {checked} functions verified
   - {mismatches} mismatches ({percentage}%)

{if mismatches > 0:}
   Sample mismatches:
   - {file}:{line} :: {function} ({reason})
   - [... up to 5 examples ...]

✅ What's working:
   - {positive_finding_1}
   - {positive_finding_2}


🛠️ RECOMMENDED NEXT ACTIONS:
   1. {action_1}
   2. {action_2}
   3. {action_3}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  GLOBAL UPDATES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Updated: ~/.claude/CLAUDE.md
   Added function map reference for {project}

✅ Updated cross-project links:
   - {other_project_1}/libraries.md now links to {project}
   - {other_project_2}/libraries.md now links to {project}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

To use this map:
1. Open ~/.claude/functionmap/{project}.md to see category listing
2. Load specific categories as needed for your work
3. Follow dependency links in {project}/libraries.md

To update this map:
- Re-run /functionmap {project} to regenerate completely
```

**DO NOT paste category file contents into chat. The output is on disk, not in chat.**

If verification found issues, **be specific about what's wrong and how to fix it.** Don't just say "looks mostly good" — that helps no one.

---

## Philosophy: Specificity with wiggle room

This command is detailed and specific because Claude thrives on clear instructions. But it also includes wiggle room for intelligent decisions:

**Where to be strict:**
- Always run all phases (extract, taxonomy, categorize, verify, usability)
- Always do full remap (delete old, create fresh)
- Always update cross-project references
- Never flood chat with function lists

**Where to be flexible:**
- Categorization judgment calls (is `validatePassword` security or validation? both are defensible)
- Dependency version matching (use 2.1.3 for 2.1.0 is reasonable, use 3.0 for 2.0 is sketchy)
- What counts as a "mappable function" (exported arrow functions yes, inline closures no)
- How to handle edge cases (if generator fails 5 times, maybe the project is too weird)

**When in doubt:**
- Bias toward inclusion (map more functions, not fewer)
- Bias toward user notification (if something seems off, ask)
- Bias toward precision in reporting (specific examples, not vague "some issues")

**Remember the goal:** Maximum discoverability, minimum context waste. Every decision should serve that goal.

---

## Final checklist before claiming success

Before you print the final summary and exit, verify:

- [ ] Generator ran successfully (no Python errors)
- [ ] Project index exists at `~/.claude/functionmap/{project}.md`
- [ ] At least one category .md file exists in `~/.claude/functionmap/{project}/`
- [ ] `_functions.json` exists and is non-empty
- [ ] `_metadata.json` exists with root_path, generated_at, version_detected
- [ ] `libraries.md` exists (even if empty) in project folder
- [ ] `_registry.json` was updated with this project
- [ ] Automated verification ran (printed results)
- [ ] Global CLAUDE.md was updated with function map reference
- [ ] Cross-project `libraries.md` files were updated (if applicable)
- [ ] Final summary printed with specific findings and next actions

**If any checklist item failed, DO NOT claim success. Report what went wrong and stop.**

---

## Quick reference: Phase flow

1. **Extract** (`functionmap.py`) -> `_functions.json`, `_meta.json`, `_hashes.json`
2. **Taxonomy** (Claude designs `_taxonomy.json`, previews coverage, iterates)
3. **Categorize** (`categorize.py`) -> category `.md` files, project index, registry update
4. **Verify** (`functionmap.py --verify`) -> automated signature check, auto-fix line drift
5. **Usability** (5-function lookup test) -> confirm map is discoverable

---

**END OF COMMAND INSTRUCTIONS**
