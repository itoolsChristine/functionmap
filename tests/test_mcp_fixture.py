"""Fixture-based tests for the functionmap MCP server modules.

Tests index loading, search scoring, and server tool functions against
synthetic fixture data in tests/fixtures/functionmap/. Runs in CI without
requiring real function map data.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add MCP source to path
TESTS_DIR = Path(__file__).parent
MCP_DIR = TESTS_DIR.parent / "src" / "mcp"
sys.path.insert(0, str(MCP_DIR))

FIXTURE_DIR = TESTS_DIR / "fixtures" / "functionmap"


def setUpModule():
    """Point the MCP index module at our fixture directory."""
    # Clear any cached state from previous test runs
    import index
    index._registry = None
    index._registry_mtime = 0.0
    index._projects.clear()


class FixtureMixin:
    """Mixin that patches FUNCTIONMAP_DIR to point at fixture data."""

    def setUp(self):
        import index
        # Reset caches so each test class starts fresh
        index._registry = None
        index._registry_mtime = 0.0
        index._projects.clear()
        # Patch the directory constant
        self._patcher = patch.object(index, 'FUNCTIONMAP_DIR', FIXTURE_DIR)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()


# ===========================================================================
#  Index tests
# ===========================================================================

class TestIndexFixture(FixtureMixin, unittest.TestCase):
    """Tests for index.py against fixture data."""

    def test_registry_loads(self):
        from index import get_registry
        reg = get_registry()
        self.assertIsInstance(reg, dict)
        self.assertIn("testproject", reg)

    def test_registry_entry_has_required_fields(self):
        from index import get_registry
        reg = get_registry()
        info = reg["testproject"]
        self.assertIn("root_path", info)
        self.assertIn("function_count", info)
        self.assertEqual(info["function_count"], 10)

    def test_project_loads(self):
        from index import get_project
        proj = get_project("testproject")
        self.assertIsNotNone(proj)
        self.assertIn("functions", proj)
        self.assertIn("taxonomy", proj)
        self.assertIn("name_index", proj)
        self.assertIn("category_map", proj)

    def test_project_has_10_functions(self):
        from index import get_project
        proj = get_project("testproject")
        self.assertEqual(len(proj["functions"]), 10)

    def test_function_entries_have_required_fields(self):
        from index import get_project
        proj = get_project("testproject")
        required = ("short_name", "file", "line_start", "language")
        for fn in proj["functions"]:
            for field in required:
                self.assertIn(field, fn, f"Function {fn.get('short_name', '?')} missing {field}")

    def test_name_index_built(self):
        from index import get_project
        proj = get_project("testproject")
        idx = proj["name_index"]
        self.assertIsInstance(idx, dict)
        # All 10 functions should be indexed (8 unique short_names -- select, insert, update, delete, escape, formatCurrency, slugify, truncate, debounce, formatDate)
        self.assertIn("select", idx)
        self.assertIn("formatcurrency", idx)
        self.assertIn("debounce", idx)

    def test_category_map_built(self):
        from index import get_project
        proj = get_project("testproject")
        cat_map = proj["category_map"]
        self.assertIsInstance(cat_map, dict)
        self.assertGreater(len(cat_map), 0)
        # Should have our two categories
        cat_names = list(cat_map.keys())
        self.assertTrue(
            any("database" in c for c in cat_names),
            f"Expected a database category, got: {cat_names}"
        )
        self.assertTrue(
            any("string" in c for c in cat_names),
            f"Expected a string utilities category, got: {cat_names}"
        )

    def test_category_map_covers_all_functions(self):
        """Every function should appear in at least one category."""
        from index import get_project
        proj = get_project("testproject")
        all_indices = set()
        for indices in proj["category_map"].values():
            all_indices.update(indices)
        self.assertEqual(
            len(all_indices), 10,
            f"Expected 10 functions in categories, got {len(all_indices)}"
        )

    def test_nonexistent_project_returns_none(self):
        from index import get_project
        self.assertIsNone(get_project("nonexistent-project-xyz"))

    def test_freshness_cache(self):
        """Loading same project twice should return cached object."""
        from index import get_project
        proj1 = get_project("testproject")
        proj2 = get_project("testproject")
        self.assertIs(proj1, proj2)

    def test_list_projects(self):
        from index import list_projects
        projects = list_projects()
        self.assertIsInstance(projects, list)
        self.assertGreater(len(projects), 0)
        names = [p["name"] for p in projects]
        self.assertIn("testproject", names)

    def test_list_projects_entry_has_fields(self):
        from index import list_projects
        projects = list_projects()
        tp = next(p for p in projects if p["name"] == "testproject")
        self.assertEqual(tp["type"], "project")
        self.assertEqual(tp["function_count"], 10)
        self.assertIn("root_path", tp)
        self.assertIn("dependencies", tp)

    def test_get_dependencies(self):
        from index import get_dependencies
        deps = get_dependencies("testproject")
        # Our libraries.md has no cross-references, so empty list
        self.assertIsInstance(deps, list)

    def test_get_project_overview(self):
        from index import get_project_overview
        overview = get_project_overview("testproject")
        self.assertIn("testproject", overview.lower())
        self.assertIn("10", overview)

    def test_get_dependency_narrative(self):
        from index import get_dependency_narrative
        narrative = get_dependency_narrative("testproject")
        self.assertIn("Dependencies", narrative)

    def test_get_category_patterns(self):
        from index import get_category_patterns
        patterns = get_category_patterns("testproject", "database-operations--core")
        self.assertIn("Select with parameters", patterns)
        self.assertIn("DB::select", patterns)


# ===========================================================================
#  Search tests
# ===========================================================================

class TestSearchFixture(FixtureMixin, unittest.TestCase):
    """Tests for search.py against fixture data."""

    def _get_proj(self):
        from index import get_project
        return get_project("testproject")

    def test_search_by_name_exact(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="select", max_results=5,
        )
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["short_name"], "select")
        self.assertGreaterEqual(results[0]["relevance_score"], 200)

    def test_search_by_name_prefix(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="format", max_results=10,
        )
        self.assertGreater(len(results), 0)
        names = [r["short_name"] for r in results]
        self.assertIn("formatCurrency", names)
        self.assertIn("formatDate", names)

    def test_search_by_query_keyword(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="currency", max_results=5,
        )
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["short_name"], "formatCurrency")

    def test_search_by_query_in_summary(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="URL-safe slug", max_results=5,
        )
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["short_name"], "slugify")

    def test_search_respects_max_results(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="a", max_results=3,
        )
        self.assertLessEqual(len(results), 3)

    def test_search_by_language_filter(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="format", language="js", max_results=10,
        )
        for r in results:
            self.assertEqual(r["language"], "js")
        # Should find formatDate but not formatCurrency (php)
        names = [r["short_name"] for r in results]
        self.assertIn("formatDate", names)
        self.assertNotIn("formatCurrency", names)

    def test_search_by_class_filter(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            class_name="DB", max_results=20,
        )
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r.get("class_name"), "DB")

    def test_search_by_kind_filter(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            kind="method", max_results=20,
        )
        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r["kind"], "method")

    def test_search_results_sorted_by_score(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            query="format", max_results=10,
        )
        if len(results) > 1:
            scores = [r["relevance_score"] for r in results]
            self.assertEqual(scores, sorted(scores, reverse=True))

    def test_search_no_match_returns_empty(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="xyzNonexistentFunction123", max_results=5,
        )
        self.assertEqual(len(results), 0)

    def test_compact_result_has_required_fields(self):
        from search import search_functions
        proj = self._get_proj()
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            name="select", max_results=1,
        )
        self.assertGreater(len(results), 0)
        r = results[0]
        for field in ("name", "short_name", "file", "line_start", "params",
                       "return_type", "relevance_score"):
            self.assertIn(field, r, f"Result missing field: {field}")

    def test_search_by_category(self):
        from search import search_functions
        proj = self._get_proj()
        # Find a database category
        db_cat = None
        for cat_name in proj["category_map"]:
            if "database" in cat_name:
                db_cat = cat_name
                break
        self.assertIsNotNone(db_cat, "No database category found")
        results = search_functions(
            proj["functions"], proj["name_index"], proj["category_map"],
            category=db_cat, max_results=20,
        )
        self.assertEqual(len(results), 5)


# ===========================================================================
#  Server tool tests (call Python functions directly, no MCP transport)
# ===========================================================================

class TestServerToolsFixture(FixtureMixin, unittest.TestCase):
    """Tests for server.py tool functions against fixture data."""

    def test_functionmap_projects(self):
        from server import functionmap_projects
        result = json.loads(functionmap_projects())
        self.assertNotIn("error", result)
        self.assertIn("count", result)
        self.assertIn("projects", result)
        self.assertGreater(result["count"], 0)
        names = [p["name"] for p in result["projects"]]
        self.assertIn("testproject", names)

    def test_functionmap_search_by_name(self):
        from server import functionmap_search
        result = json.loads(functionmap_search(name="select", project="testproject"))
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)
        self.assertEqual(result["results"][0]["short_name"], "select")

    def test_functionmap_search_by_query(self):
        from server import functionmap_search
        result = json.loads(functionmap_search(query="escape", project="testproject"))
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)

    def test_functionmap_search_cross_project(self):
        """When project is omitted, should search all registry projects."""
        from server import functionmap_search
        result = json.loads(functionmap_search(name="select"))
        self.assertNotIn("error", result)
        self.assertGreater(result["count"], 0)
        # Results should have project field
        self.assertEqual(result["results"][0]["project"], "testproject")

    def test_functionmap_search_requires_input(self):
        from server import functionmap_search
        result = json.loads(functionmap_search())
        self.assertIn("error", result)

    def test_functionmap_detail(self):
        from server import functionmap_detail
        result = json.loads(functionmap_detail(project="testproject", name="select"))
        self.assertNotIn("error", result)
        self.assertEqual(result["file"], "src/Database/DB.php")
        self.assertEqual(result["line_start"], 45)
        self.assertEqual(result["params"], "$table, $where = [], $orderBy = ''")
        self.assertEqual(result["return_type"], "array")
        self.assertIn("project", result)

    def test_functionmap_detail_not_found(self):
        from server import functionmap_detail
        result = json.loads(functionmap_detail(project="testproject", name="xyzNonexistent123"))
        self.assertIn("error", result)

    def test_functionmap_detail_nonexistent_project(self):
        from server import functionmap_detail
        result = json.loads(functionmap_detail(project="nonexistent-xyz", name="foo"))
        self.assertIn("error", result)

    def test_functionmap_categories_list(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="testproject"))
        self.assertNotIn("error", result)
        self.assertIn("categories", result)
        self.assertEqual(result["category_count"], 2)
        cat_names = [c["name"] for c in result["categories"]]
        self.assertTrue(any("database" in n for n in cat_names))
        self.assertTrue(any("string" in n for n in cat_names))

    def test_functionmap_categories_includes_overview(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="testproject"))
        self.assertIn("overview", result)
        self.assertIn("testproject", result["overview"].lower())

    def test_functionmap_categories_specific(self):
        from server import functionmap_categories
        # Get list first to find exact category name
        cat_result = json.loads(functionmap_categories(project="testproject"))
        db_cat = next(c for c in cat_result["categories"] if "database" in c["name"])
        result = json.loads(functionmap_categories(project="testproject", category=db_cat["name"]))
        self.assertNotIn("error", result)
        self.assertIn("functions", result)
        self.assertEqual(result["function_count"], 5)

    def test_functionmap_categories_includes_patterns(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="testproject", category="database-operations--core"))
        self.assertNotIn("error", result)
        self.assertIn("patterns", result)
        self.assertIn("Select with parameters", result["patterns"])

    def test_functionmap_categories_partial_match(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="testproject", category="database"))
        self.assertNotIn("error", result)
        self.assertIn("functions", result)

    def test_functionmap_categories_not_found(self):
        from server import functionmap_categories
        result = json.loads(functionmap_categories(project="testproject", category="nonexistent-xyz"))
        self.assertIn("error", result)

    def test_all_results_are_valid_json(self):
        """Every tool should return parseable JSON, never raise."""
        from server import functionmap_projects, functionmap_search, functionmap_detail, functionmap_categories
        for fn, kwargs in [
            (functionmap_projects, {}),
            (functionmap_search, {"name": "select", "project": "testproject"}),
            (functionmap_detail, {"project": "testproject", "name": "select"}),
            (functionmap_categories, {"project": "testproject"}),
        ]:
            result_str = fn(**kwargs)
            try:
                json.loads(result_str)
            except json.JSONDecodeError:
                self.fail(f"{fn.__name__} returned invalid JSON: {result_str[:200]}")


if __name__ == '__main__':
    unittest.main()
