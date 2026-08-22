import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from VAST_Challenge_2026_MC2.src.draw_full_chain_189 import build_full_chain_html


class VastFullChain189Tests(unittest.TestCase):
    def test_builds_interactive_html_with_real_records_and_expand_control(self):
        repo = Path(__file__).resolve().parents[1]
        base = repo / "VAST_Challenge_2026_MC2"

        html = build_full_chain_html(base / "src", base / "org_chart.json")

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("const RECORDS =", html)
        self.assertIn("showMiddle", html)
        self.assertIn("first 5", html.lower())
        self.assertIn("last 5", html.lower())
        self.assertIn("department", html.lower())
        self.assertIn("key-task", html)
        self.assertIn("John Windward", html)
        self.assertIn("Chloe Ballast", html)
        self.assertIn("saidit_post", html)
        match = re.search(r"Loaded\s+(\d+)\s+real", html)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1)), 189)


if __name__ == "__main__":
    unittest.main()
