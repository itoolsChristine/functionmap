import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


class TestExtraction(unittest.TestCase):
    """Smoke tests: run functionmap.py against test fixtures and verify output."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir     = os.path.dirname(os.path.abspath(__file__))
        cls.fixtures_dir = os.path.join(cls.test_dir, 'fixtures')
        cls.tool_path    = os.path.normpath(
            os.path.join(cls.test_dir, '..', 'src', 'tools', 'functionmap.py')
        )
        cls.out_root = tempfile.mkdtemp(prefix='functionmap_test_')

        # Run functionmap.py once for all tests
        # Redirect HOME so update_registry writes to temp dir instead of real ~/.claude
        env = os.environ.copy()
        env['HOME'] = cls.out_root
        env['USERPROFILE'] = cls.out_root
        os.makedirs(os.path.join(cls.out_root, '.claude', 'functionmap'), exist_ok=True)

        result = subprocess.run(
            [sys.executable, cls.tool_path, 'test-fixtures', cls.fixtures_dir,
             '--out-root', cls.out_root],
            capture_output=True, text=True, env=env
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"functionmap.py exited with code {result.returncode}\n"
                f"--- stdout ---\n{result.stdout}\n"
                f"--- stderr ---\n{result.stderr}"
            )
        cls.run_result = result
        cls.project_dir = os.path.join(cls.out_root, 'test-fixtures')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out_root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Structural tests
    # ------------------------------------------------------------------

    def test_extraction_produces_functions_json(self):
        path = os.path.join(self.project_dir, '_functions.json')
        self.assertTrue(os.path.isfile(path), '_functions.json not found')

        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        self.assertIsInstance(data, list)
        # 3 fixtures with ~6-8 functions each = roughly 18-22
        self.assertGreaterEqual(len(data), 14,
                                f'Expected at least 14 functions, got {len(data)}')
        self.assertLessEqual(len(data), 30,
                             f'Expected at most 30 functions, got {len(data)}')

    def test_extraction_produces_meta_json(self):
        path = os.path.join(self.project_dir, '_meta.json')
        self.assertTrue(os.path.isfile(path), '_meta.json not found')

        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('project', data)
        self.assertEqual(data['project'], 'test-fixtures')
        self.assertIn('root_path', data)

    def test_extraction_produces_hashes_json(self):
        path = os.path.join(self.project_dir, '_hashes.json')
        self.assertTrue(os.path.isfile(path), '_hashes.json not found')

        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        self.assertIsInstance(data, dict)
        # Should have entries for the 3 fixture files
        self.assertGreaterEqual(len(data), 3,
                                f'Expected at least 3 hash entries, got {len(data)}')

    # ------------------------------------------------------------------
    # Language-specific tests
    # ------------------------------------------------------------------

    def _get_function_names(self):
        path = os.path.join(self.project_dir, '_functions.json')
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return [fn.get('name', '') for fn in data]

    def test_php_functions_extracted(self):
        names = self._get_function_names()
        for expected in ['calculateTotal', 'formatCurrency', 'getName', 'fromArray']:
            self.assertIn(expected, names,
                          f'PHP function {expected!r} not found in extraction results')

    def test_js_functions_extracted(self):
        names = self._get_function_names()
        for expected in ['formatDate', 'fetchUserData', 'slugify', 'createEmitter']:
            self.assertIn(expected, names,
                          f'JS function {expected!r} not found in extraction results')

    def test_ts_functions_extracted(self):
        names = self._get_function_names()
        for expected in ['clamp', 'loadConfig', 'debounce', 'getDefaultLogger']:
            self.assertIn(expected, names,
                          f'TS function {expected!r} not found in extraction results')


if __name__ == '__main__':
    unittest.main()
