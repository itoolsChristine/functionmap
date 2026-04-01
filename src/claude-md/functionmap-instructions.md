<!-- FUNCTIONMAP:INSTRUCTIONS:BEGIN -->
## Function Maps -- Code Discovery Index

Function maps are a pre-built index of every function in mapped projects. Check
them before writing new code -- they prevent reimplementing existing functionality
and show you the correct API patterns for InteractiveTools libraries. The
session-start hook automatically detects if the current project has a map.

### How to search

Use the functionmap MCP tools (search for them via ToolSearch if not loaded):

- `functionmap_search(name="select", project="data-layer")` -- find by function name
- `functionmap_search(query="upload handling", project="my-cms-2-5")` -- keyword search
- `functionmap_categories(project="data-layer")` -- browse project structure
- `functionmap_detail(project="data-layer", name="select")` -- full docs + call graph
- `functionmap_projects()` -- list all mapped projects with dependency chains

**Dual-search:** Search both by name AND by keyword before concluding a function
doesn't exist. If not found in the main project, check its dependencies too
(listed in the `dependencies` field from `functionmap_projects()`).

**Stale maps:** Maps may not include functions added since the last `/functionmap`
run. If you suspect something should exist but the map doesn't show it, grep the
source before implementing.

<examples>
<example>
User: "Add a function to format phone numbers"
Claude's approach:
1. functionmap_search(query="phone format", project="my-cms-2-5") -- check if it exists
2. functionmap_search(query="phone format", project="data-layer") -- check dependencies
3. Nothing found -- safe to implement a new function
</example>
<example>
User: "How does the upload system work?"
Claude's approach:
1. functionmap_search(query="upload", project="my-cms-2-5") -- find upload functions
2. functionmap_categories(project="my-cms-2-5", category="file-handling--uploads") -- browse the category
3. Explain using the map results instead of grepping through source files
</example>
<example>
User: "Fix the record save hook"
Claude's approach:
1. functionmap_search(name="record_postsave", project="my-cms-2-5") -- find the hook
2. functionmap_detail(project="my-cms-2-5", name="record_postsave") -- get full signature + call graph
3. Read the actual source at the file:line from the detail result
</example>
</examples>

### Reference

Full search strategies, dependency chain walkthrough, third-party library lookup,
and sub-project discovery: @docs/functionmap-mcp.md
<!-- FUNCTIONMAP:INSTRUCTIONS:END -->
