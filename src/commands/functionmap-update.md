---
description: "Incrementally update function maps using file hashing (98% cheaper than full remap). Falls back to full /functionmap when needed."
argument-hint: "[project1 project2 ...] [--with-deps] [--dry-run] [--force] [--full]"
allowed-tools: Read, Grep, Glob, Bash(*), Write, Edit, Task(*), TeamCreate, TaskCreate, TaskUpdate, TaskList, TaskGet, SendMessage, Skill(functionmap)
---

# /functionmap-update -- Incremental Function Map Updater

**If the argument is `help`**: Read and output `$HOME/.claude/docs/functionmap-help.md` in full, then stop. Do not run the update pipeline.

You are running inside **Claude Code** as the `/functionmap-update` command.

## Purpose

Update function maps using **hash-based incremental detection** (`quickmap.py`). Only re-extracts functions from files that actually changed since the last map. For a typical update with 0-2 changed files, this costs ~500 tokens instead of ~30,000.

Falls back to full `/functionmap` when:
- Project has no `_hashes.json` (never been incrementally mapped)
- User passes `--full` flag
- Incremental update reports issues requiring full remap

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
Estimated cost: ~2,500 tokens (vs ~150,000 for full remap)
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

### Step 7: Handle uncategorized functions

After incremental updates, check quickmap.py output for uncategorized count:

- **0 uncategorized**: Perfect, no action needed.
- **<5 uncategorized**: Claude adds keyword routes to `_taxonomy.json`, re-runs `categorize.py`:
  ```bash
  python "$HOME/.claude/tools/functionmap/categorize.py" --project {project}
  ```
- **>=5 uncategorized**: Suggest full `/functionmap` for that project:
  ```
  {project}: 12 uncategorized functions after incremental update.
  Consider running: /functionmap {project} {root_path}
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
Estimated token savings: ~118,000 tokens vs full remap
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

## Token Budget Comparison

| Scenario | Full Remap | Incremental |
|----------|-----------|-------------|
| Nothing changed | ~30,000/project | ~300/project |
| 2 files changed | ~30,000/project | ~500/project |
| Needs full remap | ~30,000/project | ~30,000/project (fallback) |

**5 projects, nothing changed**: ~150,000 tokens (full) vs ~1,500 tokens (incremental) = **99% savings**

---

## Important Notes

- quickmap.py handles sub-projects automatically via `_meta.json` -- no special handling needed
- The registry file is updated by quickmap.py after each project completes (with file locking)
- For projects without `_hashes.json`, run `/functionmap` once to generate it, then future `/functionmap-update` calls will use incremental mode
- Do NOT use haiku or sonnet for agents -- they inherit the parent model per CLAUDE.md prime directives
- Track wall-clock time per project for the summary

---

**END OF COMMAND INSTRUCTIONS**
