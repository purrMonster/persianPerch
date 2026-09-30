"""kitten's tests: stdlib unittest only, run on Python 3.13 and 3.14 (test S8).

python -m unittest discover -s tests/kitten
"""

import ast
import sys
import unittest
from pathlib import Path

from kitten.kitten import KittenConfig

KITTEN_DIR = Path(__file__).resolve().parents[2] / "kitten"


class ConfigTest(unittest.TestCase):
    def test_reads_settings(self):
        cfg = KittenConfig.fromEnv(
            {
                "KITTEN_PERCH_URL": "https://perch.example.home.arpa/api/kitten",
                "KITTEN_TOKEN": "fake-token-not-real",
                "KITTEN_POUNCE_PATHS": r"C:\purrbrews\restic\snapshots; /srv/dumps ;",
                "KITTEN_NODE": "roastery",
            }
        )
        self.assertEqual(cfg.pouncePaths, (r"C:\purrbrews\restic\snapshots", "/srv/dumps"))
        self.assertEqual(cfg.node, "roastery")
        self.assertEqual(cfg.problems(), [])

    def test_token_never_in_repr(self):
        cfg = KittenConfig.fromEnv({"KITTEN_TOKEN": "fake-token-not-real"})
        self.assertNotIn("fake-token-not-real", repr(cfg))
        self.assertNotIn("fake-token-not-real", str(cfg))

    def test_problems_when_unset(self):
        problems = KittenConfig.fromEnv({"KITTEN_PERCH_URL": "http://perch"}).problems()
        self.assertEqual(len(problems), 2)


class StdlibOnlyTest(unittest.TestCase):
    """kitten ships as a zipapp: it may import nothing outside the standard library."""

    def test_imports_are_stdlib(self):
        allowed = set(sys.stdlib_module_names) | {"kitten", "__future__"}
        for source in KITTEN_DIR.glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    self.assertIn(name.split(".")[0], allowed, f"{source.name} imports {name}")


if __name__ == "__main__":
    unittest.main()
