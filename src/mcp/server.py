"""MCP server for functionmap -- fast function search and lookup.

Provides 4 tools via FastMCP with stdio transport:
  - functionmap_search: Search functions by name, keyword, or filters
  - functionmap_detail: Full function details + call graph
  - functionmap_categories: Browse taxonomy and category contents
  - functionmap_projects: List all mapped projects
"""
from __future__ import annotations

import json
import traceback
from typing import Optional

from mcp.server.fastmcp import FastMCP

from index import (get_project, get_callgraph, get_registry, list_projects,
                    get_dependencies, get_category_patterns, get_project_overview,
                    get_dependency_narrative)
from search import search_functions

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp_server = FastMCP("functionmap")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_response(message: str, detail: str = "") -> str:
    return json.dumps({"error": message, "detail": detail})


def _json_response(data: dict) -> str:
    return json.dumps(data, default=str)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp_server.tool()
def functionmap_search(
    query: Optional[str] = None,
    project: Optional[str] = None,
    name: Optional[str] = None,
    category: Optional[str] = None,
    class_name: Optional[str] = None,
    file: Optional[str] = None,
    language: Optional[str] = None,
    kind: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """Search functions across mapped projects by name, keyword, or filters.

    Use `name` for precise function name matching (highest relevance).
    Use `query` for broader keyword search across names, summaries, and docs.
    Combine with filters (project, language, kind, class_name, file, category)
    to narrow results. Returns compact results sorted by relevance.

    When project is omitted, searches all main projects from the registry.
    Third-party libraries and sub-projects require explicit project targeting:
      project="third-party/jquery/2.1.4"  or  project="squimsh/output"
    """
    try:
        if not query and not name and not project and not category:
            return _error_response(
                "At least one of query, name, project, or category is required"
            )

        # Determine which projects to search
        registry = get_registry()
        if project:
            project_names = [project]
        else:
            project_names = list(registry.keys())

        all_results = []
        for proj_name in project_names:
            proj = get_project(proj_name)
            if proj is None:
                continue

            results = search_functions(
                proj["functions"],
                proj["name_index"],
                proj["category_map"],
                query=query,
                name=name,
                category=category,
                class_name=class_name,
                file=file,
                language=language,
                kind=kind,
                max_results=max_results,
            )

            for r in results:
                r["project"] = proj_name
                r.pop("_index", None)
            all_results.extend(results)

        # Re-sort across projects and limit
        all_results.sort(key=lambda r: (-r["relevance_score"], r.get("short_name", "")))
        all_results = all_results[:max_results]

        return _json_response({
            "count": len(all_results),
            "results": all_results,
        })

    except Exception:
        return _error_response("Search failed", traceback.format_exc())


@mcp_server.tool()
def functionmap_detail(
    project: str,
    name: str,
    file: Optional[str] = None,
    line: Optional[int] = None,
) -> str:
    """Get full details for a specific function including signature, docs, and call graph.

    Use after functionmap_search to get complete information about a function.
    Provide file and/or line to disambiguate when multiple functions share a name.
    """
    try:
        proj = get_project(project)
        if proj is None:
            return _error_response(f"Project '{project}' not found or has no function data")

        # Find matching functions
        name_lower = name.lower()
        candidates = []
        for i, fn in enumerate(proj["functions"]):
            sn = fn.get("short_name", "").lower()
            full = fn.get("name", "").lower()
            if sn == name_lower or full == name_lower:
                candidates.append((i, fn))

        if not candidates:
            # Try substring match
            for i, fn in enumerate(proj["functions"]):
                sn = fn.get("short_name", "").lower()
                if name_lower in sn:
                    candidates.append((i, fn))

        if not candidates:
            return _error_response(f"Function '{name}' not found in project '{project}'")

        # Disambiguate
        if file:
            filtered = [(i, fn) for i, fn in candidates if file.lower() in fn.get("file", "").lower()]
            if filtered:
                candidates = filtered

        if line is not None:
            filtered = [(i, fn) for i, fn in candidates if fn.get("line_start") == line]
            if filtered:
                candidates = filtered

        # Take the first match
        _, fn = candidates[0]
        result = dict(fn)
        result["project"] = project

        # Add category
        for cat_name, cat_indices in proj["category_map"].items():
            idx = candidates[0][0]
            if idx in cat_indices:
                result["category"] = cat_name
                break

        # Add call graph data if available
        callgraph = get_callgraph(project)
        if callgraph and "functions" in callgraph:
            fn_key = f"{fn.get('file', '')}::{fn.get('short_name', '')}::{fn.get('line_start', '')}"
            cg_entry = callgraph["functions"].get(fn_key)
            if cg_entry:
                result["calls"] = cg_entry.get("calls", [])
                result["calledBy"] = cg_entry.get("calledBy", [])

        # Note if there were multiple matches
        if len(candidates) > 1:
            result["_ambiguous"] = True
            result["_match_count"] = len(candidates)
            result["_other_locations"] = [
                {"file": fn2.get("file", ""), "line_start": fn2.get("line_start", 0)}
                for _, fn2 in candidates[1:4]
            ]

        return _json_response(result)

    except Exception:
        return _error_response("Detail lookup failed", traceback.format_exc())


@mcp_server.tool()
def functionmap_categories(
    project: str,
    category: Optional[str] = None,
) -> str:
    """Browse categories for a project, or list functions in a specific category.

    Without category: returns all category names with descriptions and function counts.
    With category: returns functions in that category with their signatures.
    """
    try:
        proj = get_project(project)
        if proj is None:
            return _error_response(f"Project '{project}' not found or has no function data")

        taxonomy = proj.get("taxonomy", {})
        categories_def = taxonomy.get("categories", {})
        category_map = proj["category_map"]

        if category:
            # Find matching category (support partial match)
            matched_cat = None
            for cat_name in category_map:
                if cat_name == category or category.lower() in cat_name.lower():
                    matched_cat = cat_name
                    if cat_name == category:
                        break  # Exact match preferred

            if matched_cat is None:
                available = sorted(category_map.keys())
                return _error_response(
                    f"Category '{category}' not found in project '{project}'",
                    f"Available categories: {', '.join(available)}"
                )

            indices = category_map[matched_cat]
            functions = proj["functions"]
            func_list = []
            for idx in indices:
                fn = functions[idx]
                func_list.append({
                    "name":        fn.get("name", ""),
                    "short_name":  fn.get("short_name", ""),
                    "kind":        fn.get("kind", ""),
                    "params":      fn.get("params", ""),
                    "return_type": fn.get("return_type", ""),
                    "file":        fn.get("file", ""),
                    "line_start":  fn.get("line_start", 0),
                    "summary":     fn.get("summary", ""),
                })

            result = {
                "project":        project,
                "category":       matched_cat,
                "function_count": len(func_list),
                "functions":      func_list,
            }

            # Include Common Patterns (code examples) from the category markdown
            patterns = get_category_patterns(project, matched_cat)
            if patterns:
                result["patterns"] = patterns

            return _json_response(result)

        else:
            # List all categories
            cat_list = []
            for cat_name in sorted(category_map.keys()):
                description = ""
                # Try to get description from taxonomy
                # Category names in files use dashes; taxonomy keys may differ
                for tax_key, tax_val in categories_def.items():
                    if tax_key in cat_name or cat_name.startswith(tax_key):
                        description = tax_val.get("description", "")
                        break

                cat_list.append({
                    "name":           cat_name,
                    "description":    description,
                    "function_count": len(category_map[cat_name]),
                })

            result = {
                "project":        project,
                "category_count": len(cat_list),
                "categories":     cat_list,
            }

            # Include project overview and dependency narrative
            overview = get_project_overview(project)
            if overview:
                result["overview"] = overview

            narrative = get_dependency_narrative(project)
            if narrative:
                result["dependencies_narrative"] = narrative

            return _json_response(result)

    except Exception:
        return _error_response("Category lookup failed", traceback.format_exc())


@mcp_server.tool()
def functionmap_projects() -> str:
    """List all mapped projects, sub-projects, and third-party libraries.

    Returns project names, root paths, function counts, generation timestamps,
    types (project/sub-project/third-party), and dependency lists.

    Use this to discover what's available, determine which project to search
    (match your working directory against root_paths), and find dependency chains
    (e.g., cmsb-3-82 depends on zendb, smartarray, smartstring).

    Third-party entries include library name, version, and which projects use them.
    """
    try:
        projects = list_projects()
        return _json_response({
            "count":    len(projects),
            "projects": projects,
        })
    except Exception:
        return _error_response("Project listing failed", traceback.format_exc())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp_server.run(transport="stdio")
