"""Tests for the functionmap MCP server modules.

Tests index loading, search scoring, and server tool functions
against the real function map data in ~/.claude/functionmap/.
Skips gracefully if no function map data exists.
"""
import json
import os
import sys
import unittest
from pathlib import Path

# Add MCP source to path
MCP_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'src', 'mcp'))
sys.path.insert(0, MCP_DIR)

FUNCTIONMAP_DIR = Path.home() / ".claude" / "functionmap"
HAS_MAP_DATA = FUNCTIONMAP_DIR.exists() and (FUNCTIONMAP_DIR / "_registry.json").exists()


def skip_without_data(reason="No function map data in ~/.claude/functionmap/"):
    return unittest.skipUnless(HAS_MAP_DATA, reason)


# ===========================================================================
#  Index tests
# ===========================================================================

class TestIndex(unittest.TestCase):
    """Tests for index.py -- registry and project loading."""

    @skip_without_data()
    def test_registry_loads(self):
        from index import get_registry
        reg = get_registry()
        self.assertIsInstance(reg, dict)
        self.assertGreater(len(reg), 0, "Registry should have at least one project")

    @skip_without_data()
    def test_registry_entries_have_required_fields(self):
        from index import get_registry
        reg = get_registry()
        for name, info in reg.items():
            self.assertIn("root_path", info, f"Project {name} missing root_path")
            self.assertIn("function_count", info, f"Project {name} missing function_count")

    @skip_without_data()
    def test_project_loads(self):
        from index import get_registry, get_project
        reg = get_registry()
        project_name = next(iter(reg))
        proj = get_project(project_name)
        self.assertIsNotNone(proj, f"Failed to load project {project_name}")
        self.assertIn("functions", proj)
        self.assertIn("taxonomy", proj)
        self.assertIn("name_index", proj)
        self.assertIn("category_map", proj)

    @skip_without_data()
    def test_project_functions_are_list(self):
        from index import get_registry, get_project
        reg = get_registry()
        project_name = next(iter(reg))
        proj = get_project(project_name)
        self.assertIsInstance(proj["functions"], list)
        self.assertGreater(len(proj["functions"]), 0)

    @skip_without_data()
    def test_function_entries_have_required_fields(self):
        from index import get_registry, get_project
        reg = get_registry()
        project_name = next(iter(reg))
        proj = get_project(project_name)
        fn = proj["functions"][0]
        for field in ("short_name", "file", "line_start", "language"):
            self.assertIn(field, fn, f"Function missing field: {field}")

    @skip_without_data()
    def test_name_index_built(self):
        from index import get_registry, get_project
        reg = get_registry()
        project_name = next(iter(reg))
        proj = get_project(project_name)
        self.assertIsInstance(proj["name_index"], dict)
        self.assertGreater(len(proj["name_index"]), 0)

    @skip_without_data()
    def test_category_map_built(self):
        from index import get_registry, get_project
        reg = get_registry()
        project_name = next(iter(reg))
        proj = get_project(project_name)
        self.assertIsInstance(proj["category_map"], dict)
        # Most projects should have at least 1 category
        self.assertGreater(len(proj["category_map"]), 0,
                           f"Project {project_name} has no categories")

    @skip_without_data()
    def test_nonexistent_project_returns_none(self):
        from index import get_project
        self.assertIsNone(get_project("nonexistent-project-xyz"))

    @skip_without_data()
    def test_list_projects(self):
        from index import list_projects
        projects = list_projects()
        self.assertIsInstance(projects, list)
        self.assertGreater(len(projects), 0)
        self.assertIn("name", projects[0])
        self.assertIn("function_count", projects[0])

    @skip_without_data()
    def test_freshness_check(self):
        """Loading same project twice should return cached data."""
        from index import get_project, get_registry
        reg = get_registry()
        project_name = next(iter(reg))
        proj1 = get_project(project_name)
        proj2 = get_project(project_name)
        self.assertIs(proj1, proj2, "Same project loaded twice should be same object (cached)")

    @skip_without_data()
    def test_third_party_loads(self):
        from index import get_project
        proj = get_project("third-party/jquery/2.1.4")
        if proj is None:
            self.skipTest("third-party/jquery/2.1.4 not available")
        self.assertIsInstance(proj["functions"], list)
        self.assertGreater(len(proj["functions"]), 0)

    @skip_without_data()
    def test_list_projects_includes_types(self):
        from index import list_projects
        projects = list_projects()
        types = set(p.get("type") for p in projects)
        self.assertIn("project", types)
        # Third-party may or may not be present depending on data
        if any(p.get("type") == "third-party" for p in projects):
            tp = next(p for p in projects if p["type"] == "third-party")
            self.assertIn("library", tp)
            self.assertIn("version", tp)

    @skip_without_data()
    def test_list_projects_includes_dependencies(self):
        from index import list_projects
        projects = list_projects()
        # At least one project should have dependencies
        has_deps = any(p.get("dependencies") for p in projects if p.get("type") == "project")
        self.assertTrue(has_deps, "Expected at least one project with dependencies")

    @skip_without_data()
    def test_get_dependencies(self):
        from index import get_dependencies
        deps = get_dependencies("cmsb-3-82")
        if not deps:
            self.skipTest("cmsb-3-82 has no libraries.md or no deps")
        self.assertIn("zendb", deps)


# ===========================================================================
#  Search tests
# ===========================================================================

class TestSearch(unittest.TestCase):
    """Tests for search.py -- scoring and filtering."""

    @skip_without_data()
    def test_search_by_name_exact(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="select",
            max_results=5,
        )
        self.assertGreater(len(results), 0, "Expected results for name='select'")
        # Top result should be exact match with high score
        self.assertGreaterEqual(results[0]["relevance_score"], 200)

    @skip_without_data()
    def test_search_by_query(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="escape",
            max_results=5,
        )
        self.assertGreater(len(results), 0, "Expected results for query='escape'")

    @skip_without_data()
    def test_search_respects_max_results(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="test",
            max_results=3,
        )
        self.assertLessEqual(len(results), 3)

    @skip_without_data()
    def test_search_by_category(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        cats = list(proj["category_map"].keys())
        if not cats:
            self.skipTest("No categories in zendb")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            category=cats[0],
            max_results=50,
        )
        self.assertGreater(len(results), 0, f"Expected results for category={cats[0]}")

    @skip_without_data()
    def test_search_by_language_filter(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="select",
            language="php",
            max_results=10,
        )
        for r in results:
            self.assertEqual(r["language"], "php", "Language filter not applied")

    @skip_without_data()
    def test_search_results_sorted_by_score(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="query",
            max_results=10,
        )
        if len(results) > 1:
            scores = [r["relevance_score"] for r in results]
            self.assertEqual(scores, sorted(scores, reverse=True),
                             "Results should be sorted by score descending")

    @skip_without_data()
    def test_search_no_match_returns_empty(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="xyzNonexistentFunction123",
            max_results=5,
        )
        self.assertEqual(len(results), 0)

    @skip_without_data()
    def test_compact_result_has_required_fields(self):
        from index import get_project
        from search import search_functions
        proj = get_project("zendb")
        if proj is None:
            self.skipTest("zendb project not available")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="select",
            max_results=1,
        )
        self.assertGreater(len(results), 0)
        r = results[0]
        for field in ("name", "short_name", "file", "line_start", "params",
                       "return_type", "relevance_score"):
            self.assertIn(field, r, f"Result missing field: {field}")


# ===========================================================================
#  Server tool tests (calls Python functions directly, no MCP transport)
# ===========================================================================

class TestServerTools(unittest.TestCase):
    """Tests for server.py tool functions."""

    @skip_without_data()
    def test_functionmap_projects(self):
        from server import functionmap_projects
        result = json.loads(functionmap_projects())
        self.assertNotIn("error", result)
        self.assertIn("count", result)
        self.assertIn("projects", result)
        self.assertGreater(result["count"], 0)

    @skip_without_data()
    def test_functionmap_search_by_name(self):
        from server import functionmap_search
        result = json.loads(functionmap_search(name="select", project="zendb"))
        self.assertNotIn("error", result)
        self.assertIn("count", result)
        self.assertGreater(result["count"], 0)
        self.assertEqual(result["results"][0]["short_name"], "select")

    @skip_without_data()
    def test_functionmap_search_requires_input(self):
        from server import functionmap_search
        result = json.loads(functionmap_search())
        self.assertIn("error", result)

    @skip_without_data()
    def test_functionmap_detail(self):
        from server import functionmap_detail
        result = json.loads(functionmap_detail(project="zendb", name="select"))
        self.assertNotIn("error", result)
        self.assertIn("file", result)
        self.assertIn("line_start", result)
        self.assertIn("params", result)

    @skip_without_data()
    def test_functionmap_detail_not_found(self):
        from server import functionmap_detail
        result = json.loads(functionmap_detail(project="zendb", name="xyzNonexistent123"))
        self.assertIn("error", result)

    @skip_without_data()
    def test_functionmap_categories_list(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="zendb"))
        self.assertNotIn("error", result)
        self.assertIn("categories", result)
        self.assertGreater(result["category_count"], 0)

    @skip_without_data()
    def test_functionmap_categories_specific(self):
        from server import functionmap_categories
        # First get category list
        cat_result = json.loads(functionmap_categories(project="zendb"))
        if cat_result.get("category_count", 0) == 0:
            self.skipTest("No categories in zendb")
        cat_name = cat_result["categories"][0]["name"]
        result = json.loads(functionmap_categories(project="zendb", category=cat_name))
        self.assertNotIn("error", result)
        self.assertIn("functions", result)
        self.assertGreater(result["function_count"], 0)

    @skip_without_data()
    def test_functionmap_categories_not_found(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="zendb", category="nonexistent-xyz"))
        self.assertIn("error", result)

    @skip_without_data()
    def test_functionmap_detail_nonexistent_project(self):
        from server import functionmap_detail
        result = json.loads(functionmap_detail(project="nonexistent-xyz", name="foo"))
        self.assertIn("error", result)

    @skip_without_data()
    def test_functionmap_search_third_party(self):
        from server import functionmap_search
        result = json.loads(functionmap_search(name="ajax", project="third-party/jquery/2.1.4"))
        if "error" in result:
            self.skipTest("third-party/jquery/2.1.4 not available")
        self.assertGreater(result["count"], 0)

    @skip_without_data()
    def test_functionmap_projects_has_types(self):
        from server import functionmap_projects
        result = json.loads(functionmap_projects())
        types = set(p.get("type") for p in result["projects"])
        self.assertIn("project", types)

    @skip_without_data()
    def test_functionmap_projects_has_dependencies(self):
        from server import functionmap_projects
        result = json.loads(functionmap_projects())
        projects_with_deps = [p for p in result["projects"] if p.get("dependencies")]
        self.assertGreater(len(projects_with_deps), 0, "Expected projects with dependencies")

    @skip_without_data()
    def test_functionmap_categories_includes_patterns(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="zendb", category="query-crud--core"))
        if "error" in result:
            self.skipTest("zendb query-crud--core not available")
        self.assertIn("patterns", result, "Category response should include Common Patterns")
        self.assertIn("Select with parameters", result["patterns"])

    @skip_without_data()
    def test_all_results_are_valid_json(self):
        """Every tool should return parseable JSON, never raise."""
        from server import functionmap_projects, functionmap_search, functionmap_detail, functionmap_categories
        for fn, kwargs in [
            (functionmap_projects, {}),
            (functionmap_search, {"name": "select", "project": "zendb"}),
            (functionmap_detail, {"project": "zendb", "name": "select"}),
            (functionmap_categories, {"project": "zendb"}),
        ]:
            result_str = fn(**kwargs)
            try:
                json.loads(result_str)
            except json.JSONDecodeError:
                self.fail(f"{fn.__name__} returned invalid JSON: {result_str[:200]}")


if __name__ == '__main__':
    unittest.main()
