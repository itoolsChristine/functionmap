<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->
## Function Maps -- MANDATORY CHECK

**THIS IS A BLOCKING REQUIREMENT when working on ANY project that has a function map.**

**You MUST check function maps BEFORE writing new code, debugging issues, exploring architecture, or modifying existing code. No exceptions. No shortcuts. No "I'll check later." Check FIRST, act SECOND.**

**If you skip this check, you will miss existing functionality, waste tokens grepping through source files when the map already tells you where things live, misuse library APIs, or misunderstand object behavior.**

### Detection -- when does this apply?
- **You are working on ANY project listed in the available maps below**
- The project's path, `composer.json`, or code references another mapped project
- Code calls a bundled third-party library (check the project index for a "Third-Party Libraries" table)

### When this check is mandatory (every single time):
- **Before exploring how a feature works** -- the map tells you where code lives without grepping. Check the map index first, load the relevant category, THEN read source.
- Before creating ANY new function or method -- even "simple" ones
- Before writing utilities, helpers, formatters, validators, transformers, or converters
- Before implementing anything that manipulates strings, arrays, dates, files, uploads, HTML, URLs, or SQL
- Before adding error handling, logging, caching, or security functions
- Before writing database queries, schema operations, or record manipulation
- **Before debugging** -- understand return types, object behavior, and extraction methods from the maps
- **Before modifying existing code** -- check how APIs are meant to be called and what they return
- **When verifying or reviewing code** -- cross-reference library usage against the maps
- **Before writing code that calls a bundled third-party library** -- check its map for API surface and calling patterns
- Whenever something "feels like it should already exist" -- it probably does

### MCP-accelerated discovery (preferred when available)

When `functionmap_*` MCP tools are available (check your tool list), use them INSTEAD of the Read-based procedure below. They are faster and waste less context.

- **Find a function by name:** `functionmap_search(name="select", project="myproject")`
- **Keyword search:** `functionmap_search(query="upload", project="myproject")`
- **Browse categories:** `functionmap_categories(project="myproject")`
- **Functions in a category:** `functionmap_categories(project="myproject", category="database")`
- **Full details + call graph:** `functionmap_detail(project="myproject", name="select")`
- **List all projects:** `functionmap_projects()`

The 5-step procedure below still applies conceptually (check project, dependencies, sub-projects, third-party, then act) -- the MCP tools just make each step faster:
- Step 1 (project index): `functionmap_categories(project=...)` then `functionmap_search(...)`
- Step 2 (dependencies): Check `functionmap_detail` for cross-project references, or `functionmap_projects()` to see what's available
- Step 3 (sub-projects): `functionmap_projects()` shows sub-projects
- Step 4 (third-party): `functionmap_categories(project=...)` surfaces third-party libs

**Fall back to Read-based discovery** when MCP tools are not available.

**Determining which project to search:** Call `functionmap_projects()` -- it returns all projects with root_paths and dependency lists. Match your current working directory against root_paths to find the right project. Check the project's `dependencies` field to know what library projects to also search.

**Dual-search (mandatory):** Always search BOTH by name AND by keyword before concluding a function doesn't exist. If not found in the main project, check its dependencies too.

**Third-party libraries:** `functionmap_search(name="ajax", project="third-party/jquery/2.1.4")`. Discover available libraries via `functionmap_projects()` (entries with `type: "third-party"` include `used_by` showing which projects bundle them).

**Sub-projects:** `functionmap_search(query="compaction", project="myproject/subproject")`. Listed in `functionmap_projects()` with `type: "sub-project"`.

**When to fall back to Read:** The MCP returns code examples when browsing a specific category (`patterns` field in `functionmap_categories` response), and dependency narrative + project overview when browsing a project (`dependencies_narrative` and `overview` fields in `functionmap_categories` response). Fall back to Read only when you need the full category markdown layout or want to verify something directly in source.

### STOP-AND-CHECK rule (this is the part Claude keeps skipping):
**When you are about to call Grep, Read, or any search tool to find/understand code in a mapped project: STOP.** Do not make that call yet. Instead, use the MCP tools above if available, or follow the discovery procedure below. The map is the table of contents. Source files are the chapters. You don't grep a book to find the chapter on authentication -- you check the table of contents first.

### Discovery procedure (do ALL of these, every time -- no skipping):

**Step 1 -- Project index:** Read `~/.claude/functionmap/{project}.md`. Find the category covering your domain. Read that category `.md` file -- it has function names, signatures, file paths, and line numbers.

**Step 2 -- Dependencies:** Read `~/.claude/functionmap/{project}/libraries.md`. It lists other mapped projects this one depends on. Follow each dependency link and check those maps too. Dependencies chain: if A depends on B and B depends on C, check A, B, and C. (If the file doesn't exist, the project has no mapped dependencies -- note this in your accountability report.)

**Step 3 -- Sub-projects:** Read `~/.claude/functionmap/{project}/_meta.json` and look for a `sub_projects` field. It lists sub-project map directories inside the project's map folder, each with its own category index (typically `categories.md`). These cover large embedded codebases. (If the field is absent, note "no sub-projects" in your accountability report.)

**Step 4 -- Third-party libraries:** Scroll to the bottom of the project index (`{project}.md`) and look for a "Third-Party Libraries" table. It lists bundled libraries with links to their shared maps at `~/.claude/functionmap/third-party/{lib}/{version}/`. Open the relevant library map when the code touches that library. (If there is no table, note "no third-party libs" in your accountability report.)

**Step 5 -- Now act.** Only implement new code after confirming NOTHING existing serves the need across all of the above. If something close exists but doesn't quite fit, prefer extending/wrapping it over reimplementing.

### After checking (mandatory accountability):
**Report ALL five steps**, not just the ones that found results. Example:
> Checked `myproject.md` -> auth category, found `validateToken()`. Dependencies: `libraries.md` references utils, checked relevant categories. Sub-projects: none. Third-party: none.

- **Surface near-misses**: If you find something that does 70-90% of what's needed, tell the user before deciding to extend vs. reimplement.
- **Use existing functions**: If you find an exact match, USE IT. Don't write a "simpler version" or a "slightly different" one.

### This applies to spawned agents too:
Teammates, subagents, and swarm members implementing code on mapped projects MUST follow this same check. The team lead should include function map checking in agent prompts for any implementation work.

### Stale maps:
Function maps may not include functions added since the last `/functionmap` run. If you suspect something should exist but the map doesn't show it, do a quick `Grep` of the source before implementing. Maps are a fast index, not a replacement for the actual codebase.
<!-- FUNCTIONMAP:INSTRUCTIONS:END -->
