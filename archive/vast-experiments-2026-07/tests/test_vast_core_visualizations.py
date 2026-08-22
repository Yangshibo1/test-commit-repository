import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from VAST_Challenge_2026_MC2.src.vast_core_visualizations import build_core_visualization_artifacts


class VastCoreVisualizationTests(unittest.TestCase):
    def test_builds_core_visualization_artifacts_with_html_payloads(self):
        repo = Path(__file__).resolve().parents[1]
        src_dir = repo / "VAST_Challenge_2026_MC2" / "src"

        artifacts = build_core_visualization_artifacts(src_dir)

        expected = {
            "node_04_source_trace",
            "node_09_instruction_outcome_comparison",
            "node_12_john_all_posts_analysis",
            "node_20_content_and_creator_verification",
            "node_24_system_change_recommendations",
            "node_25_final_investigation_summary",
        }
        self.assertTrue(expected.issubset(set(artifacts)))

        for key in expected:
            artifact = artifacts[key]
            self.assertEqual(artifact["visualization_type"], "html")
            self.assertIn("visualization_title", artifact)
            self.assertIn("visualization_summary", artifact)
            self.assertIn("visualization", artifact)
            self.assertIn("vast-viz", artifact["visualization"])

        route_html = artifacts["node_04_source_trace"]["visualization"]
        self.assertIn("SwiftWren.txt", route_html)
        self.assertIn("John Windward", route_html)
        self.assertIn("saidit_post", route_html)

        recurrence_html = artifacts["node_09_instruction_outcome_comparison"]["visualization"]
        self.assertIn("HiddenOrca", recurrence_html)
        self.assertIn("MellowOtter", recurrence_html)
        self.assertIn("SwiftWren", recurrence_html)

        intervention_html = artifacts["node_24_system_change_recommendations"]["visualization"]
        self.assertIn("Validation Gate", intervention_html)
        self.assertIn("saidit_post", intervention_html)

    def test_writes_standalone_html_files_for_browser_preview(self):
        from tempfile import TemporaryDirectory
        from VAST_Challenge_2026_MC2.src.vast_core_visualizations import write_standalone_html_visualizations

        repo = Path(__file__).resolve().parents[1]
        src_dir = repo / "VAST_Challenge_2026_MC2" / "src"

        with TemporaryDirectory() as tmp:
            written = write_standalone_html_visualizations(src_dir, Path(tmp))

            self.assertIn("node_04_source_trace", written)
            html = written["node_04_source_trace"].read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("Exact Anomaly Chain", html)
            self.assertIn("SwiftWren.txt", html)
    def test_writes_six_report_question_visualizations(self):
        from tempfile import TemporaryDirectory
        from VAST_Challenge_2026_MC2.src.vast_core_visualizations import write_report_question_visualizations

        repo = Path(__file__).resolve().parents[1]
        src_dir = repo / "VAST_Challenge_2026_MC2" / "src"

        with TemporaryDirectory() as tmp:
            written = write_report_question_visualizations(src_dir, Path(tmp))

            expected = {
                "q1_how_posts_made",
                "q2_detailed_event_chain",
                "q3_system_overview",
                "q4_post_meaning_origin",
                "q5_historic_recurrence",
                "q6_intervention_point",
            }
            self.assertEqual(set(written), expected | {"index"})
            for key in expected:
                html = written[key].read_text(encoding="utf-8")
                self.assertIn("<!DOCTYPE html>", html)
                self.assertIn("vast-viz", html)
                self.assertIn("<svg", html)
                self.assertTrue(any(mark in html for mark in ("<path", "<circle", "<rect", "<line")))

            self.assertIn("How was the anomalous SaidIT post made", written["q1_how_posts_made"].read_text(encoding="utf-8"))
            self.assertIn("Exact chain of events", written["q2_detailed_event_chain"].read_text(encoding="utf-8"))
            self.assertIn("System overview", written["q3_system_overview"].read_text(encoding="utf-8"))
            self.assertIn("What do the posts mean", written["q4_post_meaning_origin"].read_text(encoding="utf-8"))
            self.assertIn("Historic recurrence", written["q5_historic_recurrence"].read_text(encoding="utf-8"))
            self.assertIn("Intervention point", written["q6_intervention_point"].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
