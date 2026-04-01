"""Parity tests: verify MCP and MD-file discovery paths return equivalent data.

Given the same fixture data, both paths should surface the same functions
with the same metadata. This ensures that whether Claude reads .md files
directly or queries the MCP server, it finds the same functions.
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add MCP source to path
TESTS_DIR = Path(__file__).parent
MCP_DIR = TESTS_DIR.parent / "src" / "mcp"
sys.path.insert(0, str(MCP_DIR))

FIXTURE_DIR = TESTS_DIR / "fixtures" / "functionmap"
PROJECT_NAME = "testproject"
PROJECT_DIR = FIXTURE_DIR / PROJECT_NAME


class ParityMixin:
    """Mixin that patches FUNCTIONMAP_DIR and loads fixture data."""

    def setUp(self):
        import index
        index._registry = None
        index._registry_mtime = 0.0
        index._projects.clear()
        self._patcher = patch.object(index, 'FUNCTIONMAP_DIR', FIXTURE_DIR)
        self._patcher.start()

        # Load the JSON source of truth
        with open(PROJECT_DIR / "_functions.json", "r", encoding="utf-8") as f:
            self.functions_json = json.load(f)

        # Parse all category markdown files
        self.md_functions = self._parse_all_category_mds()

    def tearDown(self):
        self._patcher.stop()

    def _parse_all_category_mds(self):
        """Parse category .md files and extract function entries.

        Returns dict: short_name -> {file, line_start, line_end, category_file}
        """
        functions = {}
        for md_file in sorted(PROJECT_DIR.glob("*.md")):
            if md_file.name.startswith("_") or md_file.name == "libraries.md":
                continue

            content = md_file.read_text(encoding="utf-8")
            category_name = md_file.stem

            # Extract ## heading blocks -- each is a function
            # Pattern: ## functionName\n...**Location:** `path:start-end`
            for match in re.finditer(
                r'^## (\w+)\n(.*?)(?=^## |\Z)',
                content,
                re.MULTILINE | re.DOTALL,
            ):
                name = match.group(1)
                body = match.group(2)

                # Skip non-function headings
                if name in ("Common", "Function", "Usage"):
                    continue

                # Extract location
                loc_match = re.search(
                    r'\*\*Location:\*\*\s*`([^:]+):(\d+)-(\d+)`',
                    body,
                )
                if loc_match:
                    functions[name] = {
                        "file": loc_match.group(1),
                        "line_start": int(loc_match.group(2)),
                        "line_end": int(loc_match.group(3)),
                        "category_file": category_name,
                    }

        return functions


# ===========================================================================
#  Parity: every function in JSON appears in MD files
# ===========================================================================

class TestJsonToMdParity(ParityMixin, unittest.TestCase):
    """Verify every function in _functions.json is discoverable in the MD files."""

    def test_all_json_functions_appear_in_md(self):
        """Every function from _functions.json should be in at least one category .md."""
        missing = []
        for fn in self.functions_json:
            short_name = fn["short_name"]
            if short_name not in self.md_functions:
                missing.append(short_name)
        self.assertEqual(
            missing, [],
            f"Functions in _functions.json but NOT in any category .md: {missing}"
        )

    def test_all_md_functions_appear_in_json(self):
        """Every function in category .md files should exist in _functions.json."""
        json_names = {fn["short_name"] for fn in self.functions_json}
        extra = []
        for name in self.md_functions:
            if name not in json_names:
                extra.append(name)
        self.assertEqual(
            extra, [],
            f"Functions in category .md but NOT in _functions.json: {extra}"
        )

    def test_file_paths_match(self):
        """File paths in .md should match _functions.json."""
        for fn in self.functions_json:
            name = fn["short_name"]
            if name in self.md_functions:
                md_file = self.md_functions[name]["file"]
                json_file = fn["file"]
                self.assertEqual(
                    md_file, json_file,
                    f"File mismatch for {name}: MD has '{md_file}', JSON has '{json_file}'"
                )

    def test_line_numbers_match(self):
        """Line numbers in .md should match _functions.json."""
        for fn in self.functions_json:
            name = fn["short_name"]
            if name in self.md_functions:
                md_start = self.md_functions[name]["line_start"]
                md_end = self.md_functions[name]["line_end"]
                self.assertEqual(
                    md_start, fn["line_start"],
                    f"line_start mismatch for {name}: MD has {md_start}, JSON has {fn['line_start']}"
                )
                self.assertEqual(
                    md_end, fn["line_end"],
                    f"line_end mismatch for {name}: MD has {md_end}, JSON has {fn['line_end']}"
                )

    def test_function_count_matches(self):
        """Total function count should match between JSON and MD."""
        self.assertEqual(
            len(self.functions_json),
            len(self.md_functions),
            f"Count mismatch: {len(self.functions_json)} in JSON, {len(self.md_functions)} in MD"
        )


# ===========================================================================
#  Parity: MCP search results match what's in the MD files
# ===========================================================================

class TestMcpToMdParity(ParityMixin, unittest.TestCase):
    """Verify MCP tool results are consistent with the MD file contents."""

    def test_mcp_search_matches_md_for_each_function(self):
        """For every function, MCP search should return data consistent with the MD."""
        from server import functionmap_detail

        for fn in self.functions_json:
            name = fn["short_name"]
            result = json.loads(functionmap_detail(project=PROJECT_NAME, name=name))
            self.assertNotIn("error", result, f"MCP detail failed for {name}: {result}")

            # Check file path matches
            self.assertEqual(
                result["file"], fn["file"],
                f"MCP file mismatch for {name}"
            )
            # Check line number matches
            self.assertEqual(
                result["line_start"], fn["line_start"],
                f"MCP line_start mismatch for {name}"
            )

            # Also verify against MD data
            if name in self.md_functions:
                self.assertEqual(
                    result["file"], self.md_functions[name]["file"],
                    f"MCP vs MD file mismatch for {name}"
                )
                self.assertEqual(
                    result["line_start"], self.md_functions[name]["line_start"],
                    f"MCP vs MD line_start mismatch for {name}"
                )

    def test_mcp_category_listing_matches_md_files(self):
        """MCP categories should match the set of category .md files."""
        from server import functionmap_categories

        result = json.loads(functionmap_categories(project=PROJECT_NAME))
        self.assertNotIn("error", result)

        mcp_cat_names = {c["name"] for c in result["categories"]}

        # Gather category names from .md files
        md_cat_names = set()
        for md_file in PROJECT_DIR.glob("*.md"):
            if md_file.name.startswith("_") or md_file.name == "libraries.md":
                continue
            md_cat_names.add(md_file.stem)

        self.assertEqual(
            mcp_cat_names, md_cat_names,
            f"Category mismatch: MCP has {mcp_cat_names}, MD files have {md_cat_names}"
        )

    def test_mcp_category_function_count_matches_md(self):
        """For each category, MCP function count should match functions in the MD file."""
        from server import functionmap_categories

        result = json.loads(functionmap_categories(project=PROJECT_NAME))
        self.assertNotIn("error", result)

        for cat in result["categories"]:
            cat_name = cat["name"]
            # Get functions from MCP
            cat_detail = json.loads(
                functionmap_categories(project=PROJECT_NAME, category=cat_name)
            )
            mcp_count = cat_detail["function_count"]
            mcp_names = {f["short_name"] for f in cat_detail["functions"]}

            # Count functions in corresponding MD file
            md_names = {
                name for name, info in self.md_functions.items()
                if info["category_file"] == cat_name
            }

            self.assertEqual(
                mcp_names, md_names,
                f"Category '{cat_name}' function mismatch: "
                f"MCP has {mcp_names}, MD has {md_names}"
            )

    def test_mcp_search_finds_same_functions_as_md(self):
        """A broad MCP search should return all functions that exist in MD files."""
        from search import search_functions
        from index import get_project

        proj = get_project(PROJECT_NAME)

        # Search with no name/query filter -- just category-based listing
        # Get all functions by searching each category
        mcp_all_names = set()
        for cat_name, indices in proj["category_map"].items():
            results = search_functions(
                proj["functions"], proj["name_index"], proj["category_map"],
                category=cat_name, max_results=100,
            )
            for r in results:
                mcp_all_names.add(r["short_name"])

        md_all_names = set(self.md_functions.keys())

        self.assertEqual(
            mcp_all_names, md_all_names,
            f"Full inventory mismatch: MCP has {mcp_all_names}, MD has {md_all_names}"
        )


# ===========================================================================
#  Parity: project index MD matches registry + categories
# ===========================================================================

class TestProjectIndexParity(ParityMixin, unittest.TestCase):
    """Verify the project index .md file is consistent with the data files."""

    def test_project_index_lists_all_categories(self):
        """The project index .md should reference every category .md file."""
        index_path = FIXTURE_DIR / f"{PROJECT_NAME}.md"
        content = index_path.read_text(encoding="utf-8")

        # Extract category .md file references
        md_refs = set(re.findall(r'\(testproject/([^)]+\.md)\)', content))

        # Get actual category files
        actual_files = set()
        for md_file in PROJECT_DIR.glob("*.md"):
            if md_file.name.startswith("_") or md_file.name == "libraries.md":
                continue
            actual_files.add(md_file.name)

        self.assertEqual(
            md_refs, actual_files,
            f"Project index references {md_refs} but actual files are {actual_files}"
        )

    def test_project_index_function_count(self):
        """The total function count in the project index should match _functions.json."""
        index_path = FIXTURE_DIR / f"{PROJECT_NAME}.md"
        content = index_path.read_text(encoding="utf-8")

        count_match = re.search(r'\*\*Total functions:\*\*\s*(\d+)', content)
        self.assertIsNotNone(count_match, "Project index missing total function count")
        index_count = int(count_match.group(1))
        self.assertEqual(
            index_count, len(self.functions_json),
            f"Project index says {index_count} functions, _functions.json has {len(self.functions_json)}"
        )


if __name__ == '__main__':
    unittest.main()
