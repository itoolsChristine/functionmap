---
description: "Incrementally update function maps using file hashing. Much cheaper than full /functionmap for already-mapped projects. Falls back to full remap when needed."
argument-hint: "[project1 project2 ...] [--with-deps] [--dry-run] [--force] [--full]"
allowed-tools: Read, Grep, Glob, Bash(*), Write, Edit, Task(*), TeamCreate, TaskCreate, TaskUpdate, TaskList, TaskGet, SendMessage, Skill(functionmap)
---

# /functionmap-update -- Incremental Function Map Updater

**If the argument is `help`**: Read and output `$HOME/.claude/docs/functionmap-help.md` in full, then stop. Do not run the update pipeline.

You are running inside **Claude Code** as the `/functionmap-update` command.

## Purpose

Update function maps using **hash-based incremental detection** (`quickmap.py`). Only re-extracts functions from files that actually changed since the last map. Significantly cheaper than a full `/functionmap` remap for projects that are already mapped.

Falls back to full `/functionmap` when:
- Project has no `_hashes.json` (never been incrementally mapped)
- User passes `--full` flag
- Taxonomy review fails coverage thresholds after 3 iteration rounds (the taxonomy is fundamentally misaligned with the project's current shape)

## Arguments

| Flag | Purpose |
|------|---------|
| (no args) | Update all projects that have `_hashes.json`; skip projects without |
| `project1 project2` | Update only those specific projects |
| `--with-deps` | Include dependency chain for named projects |
| `--dry-run` | Show plan without executing |
| `--force` | Skip confirmation prompt |
| `--full` | Force full `/functionmap` for ALL projects in scope |
| `--remap-third-party` | Force re-mapping of all third-party libraries (even already mapped ones) |

**`--full` semantics**: Applies to whatever projects the command targets:
- `/functionmap-update --full` = full remap ALL registered projects
- `/functionmap-update data-layer my-webapp --full` = full remap data-layer and my-webapp only
- `/functionmap-update data-layer my-webapp` = incremental for both (if hashes exist)

**Examples:**
```
/functionmap-update                              # Incremental update all
/functionmap-update data-layer                        # Incremental update data-layer
/functionmap-update data-layer string-utils            # Incremental update both
/functionmap-update my-cms-2-5 --with-deps       # my-cms + data-layer + array-utils + string-utils
/functionmap-update --dry-run                    # Show plan, don't execute
/functionmap-update --force                      # Update all, skip confirmation
/functionmap-update --full                       # Full remap all projects
/functionmap-update data-layer --full                 # Full remap data-layer only
```

---

## Workflow

### Step 1: Pre-flight checks

1. **Verify Python tools exist:**
   ```bash
   test -f "$HOME/.claude/tools/functionmap/functionmap.py" && echo "OK: functionmap.py" || echo "MISSING: functionmap.py"
   test -f "$HOME/.claude/tools/functionmap/categorize.py" && echo "OK: categorize.py" || echo "MISSING: categorize.py"
   test -f "$HOME/.claude/tools/functionmap/quickmap.py" && echo "OK: quickmap.py" || echo "MISSING: quickmap.py"
   ```
   If any missing, STOP and tell user to install the functionmap tools.

2. **Read the registry:**
   Read `$HOME/.claude/functionmap/_registry.json` for project list with root paths, function counts, and generation timestamps.

3. **Validate root paths exist on disk:**
   For each project, verify `root_path` exists. Missing paths get a warning and are excluded.

### Step 2: Determine which projects to update

- **Named projects**: Filter registry to only those. Warn and skip unknown names.
- **No arguments**: Use all projects from registry (minus missing paths).
- **`--with-deps`**: Expand named projects to include transitive dependencies:
  1. Parse each project's `libraries.md` for references to other mapped projects
  2. Recursively resolve (if data-layer depends on array-utils, array-utils depends on string-utils, all get added)
  3. Fall back to known chain: `string-utils -> array-utils -> data-layer -> my-cms-2-5`

### Step 3: Compute dependency ordering

Tier computation (same as before -- libraries must be mapped before consumers):

```
string-utils  (no deps)         -- Tier 0
array-utils   (depends on string-utils)  -- Tier 1
data-layer        (depends on array-utils)   -- Tier 2
my-cms-2-5    (depends on data-layer)        -- Tier 3
my-webapp, client-site, etc. (no deps in chain) -- Tier 0
```

- Same tier = parallel. Tier N+1 waits for Tier N.
- When updating a subset, only selected projects participate but relative ordering is preserved.

### Step 4: Check _hashes.json and determine mode

For each project, decide the update mode:

| Has _hashes.json | --full flag | Mode |
|-------------------|-------------|------|
| Yes | No | **INCREMENTAL** (quickmap.py) |
| Yes | Yes | **FULL REMAP** (/functionmap agent) |
| No | No | **SKIP** with warning |
| No | Yes | **FULL REMAP** (/functionmap agent) |

Check for `_hashes.json`:
```bash
test -f "$HOME/.claude/functionmap/{project}/_hashes.json" && echo "HAS_HASHES" || echo "NO_HASHES"
```

### Step 5: Show plan

**Always show, even with --force:**

```
Function Map Update Plan
========================

Pre-flight: Python tools OK, all root paths verified

Tier 0 (parallel):
  string-utils   146 functions  3d stale  INCREMENTAL  @ ~/projects/string-utils
  my-webapp       584 functions  0d stale  INCREMENTAL  @ ~/projects/my-webapp

Tier 1 (after Tier 0):
  array-utils    428 functions  3d stale  INCREMENTAL  @ ~/projects/array-utils

Tier 2 (after Tier 1):
  data-layer         774 functions  3d stale  INCREMENTAL  @ ~/projects/data-layer

Tier 3 (after Tier 2):
  my-cms-2-5   9,062 functions  3d stale  INCREMENTAL  @ ~/projects/my-cms

Total: 5 projects (5 incremental, 0 full remap, 0 skipped)
```

- **`--dry-run`**: Print plan and STOP.
- **`--force`**: Print plan and proceed.
- Otherwise: Print plan and ask for confirmation.

### Step 6: Execute tier by tier

Process one tier at a time. Within each tier, run all projects in parallel.

**For each project in the tier:**

#### INCREMENTAL mode (quickmap.py):

Run via Bash -- no agent needed:

```bash
python "$HOME/.claude/tools/functionmap/quickmap.py" --project {project}
```

Read stdout for the delta summary. This takes ~1-3 seconds per project.

**Sub-projects**: quickmap.py automatically checks `_meta.json` for `sub_projects` and processes them if present. No special handling needed.

**Third-party libraries**: quickmap.py automatically detects unmapped third-party libraries (those with `library`/`version` annotations in `_taxonomy.json` but not yet in the shared `third-party/` location) and maps them. Already-mapped libraries are skipped (just referenced). Use `--remap-third-party` to force re-mapping even for already-mapped libraries.

To pass the remap flag:
```bash
python "$HOME/.claude/tools/functionmap/quickmap.py" --project {project} --remap-third-party
```

#### FULL REMAP mode (/functionmap agent):

Spawn a background Task agent (same as old behavior):

```
You are updating the function map for project "{project}".

Run the /functionmap command with these arguments:
  /functionmap {project} {root_path}

This is a full remap -- the old map will be deleted and regenerated from scratch.
Run the complete pipeline: extraction, taxonomy design, categorization, and verification.

When complete, report:
- Total functions found
- Number of categories created
- Any issues or warnings encountered
- Whether verification passed
```

Agent configuration:
- `subagent_type`: `general-purpose`
- `mode`: `bypassPermissions`
- `name`: `functionmap-{project}`
- `run_in_background`: `true`
- Do NOT use haiku or sonnet -- agents inherit the parent model

**Parallel within tiers, sequential between tiers.** Wait for all projects in a tier to complete before starting the next tier.

**Error resilience:** If a project fails:
- Report failure immediately
- Mark as failed
- Continue to next tier (downstream projects can still update with potentially stale upstream data)

### Step 6.5: Rebuild call graph (if functions changed)

For each project where functions were added/removed/modified, rebuild the call graph:

```bash
node "$HOME/.claude/tools/functionmap/build-callgraph.cjs" {project} --quiet
```

This updates `_callgraph.json` with current call edges and content anchors. Runs in ~1-2 seconds per project. Skip if no functions changed (quickmap reported 0 delta).

### Step 7: Taxonomy review and validation

**This step is mandatory whenever quickmap.py reports any delta (changed, new, or deleted files/functions).** Even small changes can invalidate existing taxonomy -- a new module might need a new category, deleted files might leave empty categories, refactored code might belong elsewhere. The incremental updater must be just as thorough as `/functionmap` in evaluating taxonomy fitness; it just starts from the existing taxonomy instead of a blank slate.

**Skip this step ONLY when quickmap.py reports 0 changes across all files and functions.**

#### Step 7.1: Assess the impact of changes

Analyze what changed and what it means for the taxonomy. Do ALL of the following:

1. **Read the quickmap.py delta** -- which files changed, which are new, which were deleted, how many functions were added/removed.

2. **Read the current `_taxonomy.json`** -- understand existing categories and routing rules.

3. **Run coverage preview:**
   ```bash
   python "$HOME/.claude/tools/functionmap/functionmap.py" --preview-taxonomy {project}
   ```

4. **Check coverage thresholds** (same as `/functionmap` Phase 2.4):
   - `uncategorized` MUST be <15% of functions
   - No single category may have >40% of functions
   - Categories with <5 functions should generally be merged -- but use judgment: some categories are legitimately small (e.g., a project's main entry points). Don't merge a category just to satisfy a number if the category is semantically distinct and useful for discovery.

5. **Check delta files for routing coverage** -- for EACH new or changed file from the quickmap delta, verify it has an explicit routing rule (namespace, directory, or file route) in `_taxonomy.json`. If a file only matches via keyword fallback routes, or matches no route at all, it needs a proper rule. This is the most important check because:
   - **Keyword routes are a fallback, not a categorization strategy.** They match on function name fragments and frequently misroute functions into wrong categories. A function named `composeTaxEmail` will match a "compose" keyword and land in an email category when it actually belongs in a tax/pay category.
   - **Namespace and directory routes are precise.** They route by where the code lives, which almost always matches its semantic domain. Every file in the project should ideally be covered by one of these before keyword routes even get a chance to fire.
   - **Silent misrouting is worse than uncategorized.** An uncategorized function is visibly wrong; a misrouted function is invisibly wrong. Someone looking for `composeTaxEmail` in the tax category won't find it, and they won't know to look in email.

   **How to check:** For each file in the delta, trace the routing rules in priority order (third_party -> deprecated -> namespace_routes -> directory_routes -> file_routes -> keyword_routes). If the first matching rule is a keyword route, that file needs a more specific rule added.

6. **Check for category-level impact** -- even with all files routed, step back and evaluate the bigger picture:
   - Did new files introduce a new logical domain that deserves its own category? (e.g., a whole new module with 10+ functions shouldn't be lumped into a catch-all)
   - Did deleted files leave any categories empty or severely depleted? Remove empty categories from the taxonomy.
   - Did a category's count change dramatically? If a category doubled in size, check whether it now covers two distinct domains that should be split.
   - Did modifications change a function's purpose enough that it belongs in a different category? (rarer, but possible with major refactors)
   - Do category descriptions still accurately reflect their contents after the changes?

#### Step 7.2: Fix taxonomy issues (iterative, max 3 rounds)

If ANY issue was found in 7.1 (threshold failure, missing routes, keyword-only routing, semantic misfit, stale descriptions), update `_taxonomy.json`:

1. **Snapshot category counts BEFORE making changes.** Record every category and its function count from the coverage preview. You need this baseline to detect ripple effects after re-categorization.

2. **Add specific routes first** -- namespace_routes and directory_routes for new/unrouted files. These are high-priority because they prevent keyword misrouting.

3. **Add or restructure categories** if the changes warrant it -- new categories for new domains, merge depleted categories, split overgrown ones.

4. **Update category descriptions** to reflect the project's current shape. A description that no longer matches its contents makes the whole map less discoverable.

5. **Remove stale routes** for deleted files/directories/namespaces.

6. **Re-run categorization:**
   ```bash
   python "$HOME/.claude/tools/functionmap/categorize.py" --project {project}
   ```

7. **Detect ripple effects -- compare before/after category counts.**

   Taxonomy changes don't just affect the delta files. When you add a new namespace or directory route, it can claim functions that were previously routed by a lower-priority rule (typically keyword routes). Those functions aren't in new or changed files -- they were already in the project -- but they silently move between categories.

   **Why this matters:** A new route that's too broad can vacuum up functions from other categories where they correctly belonged. A removed route can scatter functions into keyword-matched categories where they don't belong. The coverage preview shows aggregate numbers but won't tell you that 15 functions quietly migrated from category A to category B.

   **How to check:**
   - Re-run the coverage preview after categorization.
   - Compare every category's count against the baseline from sub-step 1.
   - For any category whose count changed AND that category was NOT directly affected by the delta files, investigate:
     - Which functions moved in or out? (Compare the old and new category markdown files, or check the categorizer output.)
     - Did they move because a new specific route correctly claimed them from a keyword fallback? (This is a FIX -- good.)
     - Did they move because a new route is too broad and is grabbing functions it shouldn't? (This is a REGRESSION -- fix the route pattern to be more specific.)
     - Did they move because a removed route left them to fall through to a keyword match? (This needs a replacement route.)

   **Expected vs. unexpected movement:**
   - **Expected:** Functions in delta files moving to new/updated categories. Functions moving FROM keyword-matched categories TO specific-route categories (this is always an improvement).
   - **Unexpected:** Functions in non-delta files moving between two specific-route categories. A category losing functions that aren't in any delta file and don't match any new route. A category gaining functions from files that have nothing to do with the changes.

   **Example of a ripple effect (from real experience):**
   Adding a `modules/PayCalcModule/assets/` directory route correctly claimed 102 new functions. But it also caused 4 functions from the same directory to move OUT of `dashboard-ui`, where keyword routes ("compose", "dialog") had previously misrouted them. The count change in `dashboard-ui` (81 -> 77) was a FIX, not a regression -- but without comparing before/after, you wouldn't know whether those 4 functions disappeared into the wrong place or were reclaimed into the right one.

8. **Re-run coverage preview and re-check all of 7.1 (thresholds, delta routing, category-level impact).** If issues remain, repeat from sub-step 2 (up to 3 rounds total).

**After 3 rounds**, if thresholds still fail or misrouting persists, proceed but print a prominent warning and suggest full `/functionmap`:
```
WARNING: Taxonomy review did not resolve all issues after 3 iterations.
uncategorized: {N}% (threshold: <15%)
Consider running: /functionmap {project} {root_path}
```

#### Step 7.3: Report taxonomy changes

Always report what was done, or that nothing was needed. The report must give confidence that the map is accurate and that no silent damage was done. Include ALL of the following sections:

```
Taxonomy review (round 1):
  Thresholds:
    Uncategorized: 0% ✓ (threshold: <15%)
    Largest category: email-ui at 16% ✓ (threshold: <40%)
    Smallest category: dashboard-main at 5 functions (entry points, kept as-is)

  Delta file routing:
    modules/PayCalcModule/PayCalcModule.php: NEW namespace route -> pay-calculator/php-handlers
    modules/PayCalcModule/assets/pay-calculator.js: NEW directory route -> pay-calculator/js-ui
    modules/PayCalcModule/lib/HarvestClient.php: covered by namespace route -> pay-calculator/php-handlers
    modules/EmailModule/assets/email.js: existing directory route -> email-ui ✓
    [... other changed files ...]

  Taxonomy changes:
    Categories: ADDED pay-calculator (124 functions, 2 subcategories)
    Routes: +1 namespace (PayCalcModule), +1 directory (PayCalcModule/assets/)

  Ripple effects (before -> after):
    pay-calculator: 0 -> 124 (+124) -- NEW category, all from delta files
    dashboard-ui: 81 -> 77 (-4) -- 4 functions reclaimed by pay-calculator from keyword misroute (FIX)
    email-ui: 171 -> 171 (no change)
    [... all other categories unchanged ...]
```

**When taxonomy changes were made**, the ripple effects section is mandatory. Show every category that changed count, explain WHY (delta files arriving, misrouted functions reclaimed, route overlap fixed), and flag whether each movement is a FIX or needs investigation.

**When no taxonomy changes were needed:**
```
Taxonomy review:
  All thresholds pass. All delta files have specific routing rules.
  No misrouting detected, no category changes needed.
  Category counts: [N] categories unchanged from pre-update baseline.
```

### Step 8: Update project index (if counts changed)

For each project where the function count changed, update the project index file:

Read `_meta.json` for the new count. If it differs from the registry's `function_count`, the categorizer already regenerated the index. Verify the index file exists and has the updated count.

### Step 9: Cross-reference verification

After ALL tiers complete:

1. **Re-read the updated registry** (`_registry.json`)
2. **For each updated project**, check `libraries.md` for references to other mapped projects
3. **Print cross-reference status:**
   ```
   Cross-reference check:
     my-cms-2-5 -> data-layer: OK (updated this run)
     data-layer -> array-utils: OK (updated this run)
     array-utils -> string-utils: OK (updated this run)
   ```
4. If a referenced project was NOT updated and is >30 days stale, warn:
   ```
   NOTE: {project} references {dep} which is 45 days stale -- consider updating
   ```

### Step 10: CLAUDE.md authoritative sync

Multiple projects may update `_registry.json` during the run. After all complete:

1. Re-read the updated `_registry.json`
2. Re-read `$HOME/.claude/CLAUDE.md`
3. Rebuild the `<!-- FUNCTIONMAP:BEGIN -->` ... `<!-- FUNCTIONMAP:END -->` section from the full registry
4. Write via Edit tool

**Format per entry** (match existing convention):
```
- **{project}** -> `$HOME/.claude/functionmap/{project}.md`
```
Include parenthetical notes from registry's `sub_projects` field if present.

Also add/update the third-party entry if `third-party/third-party.md` exists:
```
- **third-party** -> `$HOME/.claude/functionmap/third-party/third-party.md` (shared third-party library maps: {N} libraries, {M} functions)
```
Read `third-party/_index.json` to get accurate library/function counts.

### Step 11: Final summary

```
Function Map Update Complete
============================

Results:
  Tier 0:
    string-utils    146 ->    148 (+2)     INCREMENTAL  0.3s
    my-webapp        584 ->    587 (+3)     INCREMENTAL  1.2s
  Tier 1:
    array-utils     428 ->    428 (+0)     INCREMENTAL  0.8s  (no changes)
  Tier 2:
    data-layer          774 ->    780 (+6)     INCREMENTAL  0.9s

Cross-references: 4/4 OK
Total: 4 projects updated (4 incremental, 0 full remap)
```

**If there were failures:**
```
3/4 updated successfully. 1 FAILED:
  FAILED: my-webapp -- quickmap.py error (see output above)
```

**Interactive retry:** When projects failed, prompt user:
- Retry failed projects now (re-run quickmap or re-spawn agents)
- Skip (end the run)

If `--force` was used, skip interactive retry and print manual re-run command.

---

## When to use `/functionmap-update` vs `/functionmap`

- **`/functionmap-update`** is for already-mapped projects. It re-extracts only changed files, then validates and fixes the taxonomy. Much cheaper than a full remap when only a few files changed, and progressively more expensive as changes grow -- but still cheaper than a full remap unless the taxonomy needs a complete redesign.
- **`/functionmap`** is for first-time mapping or when the incremental updater can't get the taxonomy to pass thresholds after 3 rounds. It deletes the old map and regenerates everything from scratch. Expensive but thorough.
- **The output quality should be identical.** Both commands produce the same taxonomy, the same category files, the same coverage. The only difference is how much work is skipped on the extraction side.

---

## Important Notes

- quickmap.py handles sub-projects automatically via `_meta.json` -- no special handling needed
- **Sub-project path auto-resolution**: When a sub-project's `root_path` no longer exists (common after version upgrades), quickmap.py checks for a `root_path_glob` field in the sub-project config. If present, it resolves the glob pattern against the parent project's root path, picks the latest match (by sort order), and updates both the parent and sub-project `_meta.json` files. To set this up, add `root_path_glob` to the sub-project entry in `_meta.json`:
  ```json
  "sub_projects": {
      "output": {
          "root_path": "path/to/v2.1.79/output",
          "root_path_glob": "decompiled/v*/output"
      }
  }
  ```
- **Enrichment files**: If a project or sub-project has an `_enrichment.json` file, categorize.py automatically loads it during categorization. This provides display names, descriptions, and category hints for functions that lack source-level documentation. See `/functionmap help` for the schema.
- The registry file is updated by quickmap.py after each project completes (with file locking)
- For projects without `_hashes.json`, run `/functionmap` once to generate it, then future `/functionmap-update` calls will use incremental mode
- Do NOT use haiku or sonnet for agents -- they inherit the parent model per CLAUDE.md prime directives
- Track wall-clock time per project for the summary

---

**END OF COMMAND INSTRUCTIONS**
