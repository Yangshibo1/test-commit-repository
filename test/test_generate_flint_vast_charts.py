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

    def test_every_row_has_evidence_and_event_backed_rows_keep_event_ids(self):
        for question, rows in self.tables.items():
            with self.subTest(question=question):
                self.assertTrue(
                    all(
                        isinstance(row.get("evidence_reference"), list)
                        and row["evidence_reference"]
                        for row in rows
                    )
                )
                self.assertTrue(
                    all(
                        isinstance(row.get("source_event_ids"), list)
                        for row in rows
                    )
                )

    def test_q3_summary_metrics_do_not_misattribute_post_events(self):
        q3_by_metric = {row["metric"]: row for row in self.tables["q3"]}
        for metric in ("total_posts", "direct_subordinates"):
            self.assertEqual(q3_by_metric[metric]["source_event_ids"], [])
            self.assertTrue(q3_by_metric[metric]["evidence_reference"][0].startswith("record:"))

    def test_event_backed_rows_preserve_event_ids(self):
        self.assertTrue(all(row["source_event_ids"] for row in self.tables["q1"]))
        self.assertTrue(all(row["source_event_ids"] for row in self.tables["q2"]))
        self.assertEqual(
            next(row for row in self.tables["q3"] if row["metric"] == "abnormal_posts")["source_event_ids"],
            [27290, 98591, 373902],
        )
        self.assertTrue(all(row["source_event_ids"] for row in self.tables["q4"]))
        self.assertTrue(all(row["source_event_ids"] for row in self.tables["q5"]))
        self.assertEqual(self.tables["q6"][0]["source_event_ids"], [27290, 98591, 373902])

    def test_missing_content_verification_is_not_reported_as_empty(self):
        module = load_module()
        original_load = module._load

        def load_without_swiftwren(path):
            data = original_load(path)
            if path.name == "node_20_content_and_creator_verification.json":
                posts = data["investigation"]["q1_post_content_analysis"]["posts"]
                data["investigation"]["q1_post_content_analysis"]["posts"] = [
                    post for post in posts if post["post_id"] != 373902
                ]
            return data

        module._load = load_without_swiftwren
        tables = module.build_chart_tables(CHALLENGE_DIR)
        swiftwren = next(row for row in tables["q5"] if row["post_id"] == 373902)
        self.assertEqual(swiftwren["verification_status"], "unavailable")
        self.assertIsNone(swiftwren["content_length"])
        self.assertIsNone(swiftwren["is_empty"])


if __name__ == "__main__":
    unittest.main()
