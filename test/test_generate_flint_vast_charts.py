import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHALLENGE_DIR = REPO_ROOT / "VAST_Challenge_2026_MC2"
MODULE_PATH = CHALLENGE_DIR / "src" / "generate_flint_vast_charts.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_flint_vast_charts", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildChartTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = load_module().build_chart_tables(CHALLENGE_DIR)

    def test_returns_six_question_tables(self):
        self.assertEqual(set(self.tables), {"q1", "q2", "q3", "q4", "q5", "q6"})
        self.assertTrue(all(isinstance(rows, list) and rows for rows in self.tables.values()))

    def test_q1_traces_swiftwren(self):
        self.assertTrue(any(row.get("content_source") == "SwiftWren.txt" for row in self.tables["q1"]))

    def test_q2_contains_saidit_post_event(self):
        self.assertTrue(any(row.get("event_type") == "saidit_post" for row in self.tables["q2"]))

    def test_q4_contains_only_observed_content_facts(self):
        self.assertTrue(any(row.get("content_source") == "SwiftWren.txt" for row in self.tables["q4"]))
        self.assertTrue(all("semantic_interpretation" not in row for row in self.tables["q4"]))

    def test_q5_contains_all_known_content_source_files(self):
        self.assertEqual(
            {row.get("content_source") for row in self.tables["q5"]},
            {"HiddenOrca.txt", "MellowOtter.txt", "SwiftWren.txt"},
        )

    def test_every_row_has_source_event_ids(self):
        for question, rows in self.tables.items():
            with self.subTest(question=question):
                self.assertTrue(all(isinstance(row.get("source_event_ids"), list) and row["source_event_ids"] for row in rows))


if __name__ == "__main__":
    unittest.main()
