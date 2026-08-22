import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from extract_three_txt_posting_chains_dataset import (
    CHAIN_POST_IDS,
    build_dataset,
    find_direct_file_events,
    load_mc2_events,
)


class DirectFileEventSelectionTests(unittest.TestCase):
    def test_selects_all_supported_direct_reference_fields(self):
        events = [
            {"id": 1, "details": {"target": "SwiftWren.txt"}},
            {"id": 2, "details": {"args": {"path": "SwiftWren_further_instructions.md"}}},
            {"id": 3, "details": {"task": "Read SwiftWren_further_instructions.md"}},
            {"id": 4, "details": {"content_source": "SwiftWren.txt"}},
            {"id": 5, "details": {"target": "unrelated.txt"}},
        ]

        selected = find_direct_file_events(
            events,
            "SwiftWren.txt",
            "SwiftWren_further_instructions.md",
        )

        self.assertEqual([event["id"] for event in selected], [1, 2, 3, 4])


class DatasetAssemblyTests(unittest.TestCase):
    def test_builds_annotated_chains_and_merged_chronology(self):
        events = [
            {
                "id": 20,
                "short_name": "saidit_post",
                "when": 20.0,
                "details": {"content_source": "SwiftWren.txt"},
            },
            {
                "id": 10,
                "short_name": "create_file",
                "when": 10.0,
                "details": {"target": "SwiftWren.txt"},
            },
        ]

        dataset = build_dataset(events, {"SwiftWren.txt": 20})
        chain = dataset["chains"]["SwiftWren.txt"]

        self.assertEqual([event["id"] for event in chain["events"]], [10, 20])
        self.assertEqual(chain["events"][0]["related_file"], "SwiftWren.txt")
        self.assertEqual(chain["events"][0]["lifecycle_stage"], "create")
        self.assertFalse(chain["events"][0]["is_post_event"])
        self.assertEqual(chain["events"][1]["lifecycle_stage"], "post")
        self.assertTrue(chain["events"][1]["is_post_event"])
        self.assertEqual(dataset["metadata"]["total_events"], 2)
        self.assertEqual(
            [event["id"] for event in dataset["all_events_chronological"]],
            [10, 20],
        )


class SourceCoverageTests(unittest.TestCase):
    def test_real_source_has_complete_expected_chain_coverage(self):
        dataset = build_dataset(load_mc2_events())
        expected_counts = {
            "SwiftWren.txt": 191,
            "HiddenOrca.txt": 42,
            "MellowOtter.txt": 15,
        }

        self.assertEqual(dataset["metadata"]["total_events"], 248)
        self.assertEqual(len(dataset["all_events_chronological"]), 248)
        self.assertEqual(
            len({event["id"] for event in dataset["all_events_chronological"]}),
            248,
        )
        for chain_file, expected_count in expected_counts.items():
            chain = dataset["chains"][chain_file]
            self.assertEqual(len(chain["events"]), expected_count)
            post_events = [event for event in chain["events"] if event["is_post_event"]]
            self.assertEqual(
                [event["id"] for event in post_events],
                [CHAIN_POST_IDS[chain_file]],
            )


if __name__ == "__main__":
    unittest.main()
