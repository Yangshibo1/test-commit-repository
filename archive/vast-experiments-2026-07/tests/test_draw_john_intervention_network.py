import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "VAST_Challenge_2026_MC2" / "src"))

from draw_john_intervention_network import (
    CHAIN_ORDER,
    GATE_ID,
    _derive_event_edge,
    build_edge_routes,
    build_intervention_graph,
    build_person_positions,
    render_intervention_network,
)


def event(event_id, when, short_name, parties):
    return {
        "id": event_id,
        "when": when,
        "short_name": short_name,
        "parties": parties,
    }


def edge(event_id, chain_file, source, target, sequence):
    return {
        "event_id": event_id,
        "chain_file": chain_file,
        "when": float(event_id),
        "short_name": "queue_subordinate_task",
        "source": source,
        "target": target,
        "is_post": target == GATE_ID,
        "sequence": sequence,
    }


class InterventionGraphTests(unittest.TestCase):
    def test_derives_two_person_edge_and_preserves_self_transfer(self):
        derived = _derive_event_edge(
            "SwiftWren.txt",
            event(
                10,
                100.0,
                "custom_transfer",
                [
                    "system:file_system",
                    "Agent/person:emma_harbor",
                    "person:chloe_ballast",
                ],
            ),
        )
        self.assertEqual(derived["source"], "emma_harbor")
        self.assertEqual(derived["target"], "chloe_ballast")
        self.assertFalse(derived["is_post"])

        self_transfer = _derive_event_edge(
            "SwiftWren.txt",
            event(
                11,
                101.0,
                "queue_subordinate_task",
                ["person:olivia_keel", "Agent/person:olivia_keel"],
            ),
        )
        self.assertEqual((self_transfer["source"], self_transfer["target"]),
                         ("olivia_keel", "olivia_keel"))

    def test_projects_john_post_and_omits_unsupported_events(self):
        post = _derive_event_edge(
            "SwiftWren.txt",
            event(12, 102.0, "saidit_post", ["Agent/person:john_windward"]),
        )
        self.assertEqual(
            (post["source"], post["target"], post["is_post"]),
            ("john_windward", GATE_ID, True),
        )
        for short_name in ("create_file", "read_file", "delete_file"):
            self.assertIsNone(
                _derive_event_edge(
                    "SwiftWren.txt",
                    event(13, 103.0, short_name, ["Agent/person:emma_harbor"]),
                )
            )
        self.assertIsNone(
            _derive_event_edge(
                "SwiftWren.txt",
                event(14, 104.0, "queue_subordinate_task", ["person:a", "person:b", "person:c"]),
            )
        )

    def test_orders_viable_edges_per_chain_and_preserves_duplicates(self):
        dataset = {
            "chains": {
                "SwiftWren.txt": {
                    "events": [
                        event(5, 50, "saidit_post", ["person:john_windward"]),
                        event(4, 40, "read_file", ["person:alpha"]),
                        event(3, 30, "queue_subordinate_task", ["person:beta", "person:beta"]),
                        event(2, 20, "queue_subordinate_task", ["person:alpha", "person:beta"]),
                        event(1, 10, "queue_subordinate_task", ["person:alpha", "person:beta"]),
                    ]
                },
                "HiddenOrca.txt": {
                    "events": [
                        event(7, 80, "saidit_post", ["person:john_windward"]),
                        event(6, 60, "queue_subordinate_task", ["person:beta", "person:john_windward"]),
                    ]
                },
                "MellowOtter.txt": {
                    "events": [
                        event(9, 90, "saidit_post", ["person:john_windward"]),
                        event(8, 70, "queue_subordinate_task", ["person:beta", "person:john_windward"]),
                    ]
                },
            }
        }

        graph = build_intervention_graph(dataset)

        self.assertEqual(
            [item["event_id"] for item in graph["edges_by_chain"]["SwiftWren.txt"]],
            [1, 2, 3, 5],
        )
        self.assertEqual(
            [item["sequence"] for item in graph["edges_by_chain"]["SwiftWren.txt"]],
            [1, 2, 3, 4],
        )
        self.assertEqual(
            [item["sequence"] for item in graph["edges_by_chain"]["HiddenOrca.txt"]],
            [1, 2],
        )
        self.assertEqual(
            len([
                item for item in graph["edges"]
                if item["source"] == "alpha" and item["target"] == "beta"
            ]),
            2,
        )
        self.assertNotIn(GATE_ID, graph["people"])
        self.assertEqual(len([item for item in graph["edges"] if item["is_post"]]), 3)
        self.assertEqual(graph["omitted_events"][0]["event_id"], 4)
        self.assertEqual(graph["chain_people"]["SwiftWren.txt"], ["alpha", "beta", "john_windward"])

    def test_real_dataset_graph_contract(self):
        with (PROJECT_ROOT / "result" / "three_txt_posting_chains_dataset.json").open(encoding="utf-8") as source:
            graph = build_intervention_graph(json.load(source))

        self.assertEqual(len(graph["people"]), 19)
        self.assertEqual(len(graph["edges"]), 238)
        self.assertEqual(len(graph["omitted_events"]), 10)
        self.assertEqual(
            {name: len(graph["edges_by_chain"][name]) for name in CHAIN_ORDER},
            {"SwiftWren.txt": 187, "HiddenOrca.txt": 40, "MellowOtter.txt": 11},
        )
        posts = [item for item in graph["edges"] if item["is_post"]]
        self.assertEqual(len(posts), 3)
        self.assertEqual({item["source"] for item in posts}, {"john_windward"})
        self.assertEqual({item["target"] for item in posts}, {GATE_ID})
        self.assertEqual({item["chain_file"] for item in posts}, set(CHAIN_ORDER))
        self.assertEqual(
            {name: graph["edges_by_chain"][name][-1]["sequence"] for name in CHAIN_ORDER},
            {"SwiftWren.txt": 187, "HiddenOrca.txt": 40, "MellowOtter.txt": 11},
        )
        positions = build_person_positions(graph)
        self.assertEqual(set(positions), graph["people"])
        self.assertNotIn(GATE_ID, positions)

    def test_positions_keep_each_person_unique_and_attach_supplementary_people(self):
        graph = {
            "people": {"alpha", "beta", "john_windward", "upper_new", "lower_new"},
            "chain_people": {
                "SwiftWren.txt": ["alpha", "beta", "john_windward"],
                "HiddenOrca.txt": ["beta", "upper_new"],
                "MellowOtter.txt": ["lower_new", "beta"],
            },
            "edges_by_chain": {
                "SwiftWren.txt": [
                    edge(1, "SwiftWren.txt", "alpha", "beta", 1),
                    edge(2, "SwiftWren.txt", "beta", "john_windward", 2),
                ],
                "HiddenOrca.txt": [edge(3, "HiddenOrca.txt", "beta", "upper_new", 1)],
                "MellowOtter.txt": [edge(4, "MellowOtter.txt", "lower_new", "beta", 1)],
            },
        }

        positions = build_person_positions(graph)

        self.assertEqual(positions["alpha"][1], 0)
        self.assertEqual(positions["beta"][1], 0)
        self.assertEqual(positions["john_windward"][1], 0)
        self.assertLess(positions["alpha"][0], positions["beta"][0])
        self.assertLess(positions["beta"][0], positions["john_windward"][0])
        self.assertGreater(positions["upper_new"][1], 0)
        self.assertLess(positions["lower_new"][1], 0)
        self.assertGreater(positions["upper_new"][0], positions["beta"][0])
        self.assertLess(positions["lower_new"][0], positions["beta"][0])
        self.assertEqual(set(positions), graph["people"])

    def test_routes_separate_duplicate_edges_posts_and_loops(self):
        positions = {"alpha": (0.0, 0.0), "beta": (4.0, 0.0), "john_windward": (8.0, 0.0)}
        gate_position = (11.0, 0.0)
        edges = [
            edge(1, "SwiftWren.txt", "alpha", "beta", 1),
            edge(2, "SwiftWren.txt", "alpha", "beta", 2),
            edge(3, "HiddenOrca.txt", "alpha", "beta", 1),
            edge(4, "MellowOtter.txt", "alpha", "alpha", 1),
            edge(5, "MellowOtter.txt", "alpha", "alpha", 2),
            edge(6, "SwiftWren.txt", "john_windward", GATE_ID, 3),
            edge(7, "HiddenOrca.txt", "john_windward", GATE_ID, 2),
            edge(8, "MellowOtter.txt", "john_windward", GATE_ID, 3),
        ]

        routes = build_edge_routes(edges, positions, gate_position)
        duplicate_routes = routes[:3]
        self.assertEqual(len({item["curvature"] for item in duplicate_routes}), 3)
        self.assertEqual(len({item["label_position"] for item in duplicate_routes}), 3)
        self.assertGreater(duplicate_routes[2]["label_position"][1], 0)

        loops = [item for item in routes if item["is_self_loop"]]
        self.assertEqual(len(loops), 2)
        self.assertNotEqual(loops[0]["start"], loops[0]["end"])
        self.assertNotEqual(loops[0]["label_position"], positions["alpha"])
        self.assertNotEqual(loops[0]["label_position"], loops[1]["label_position"])

        post_routes = [item for item in routes if item["edge"]["target"] == GATE_ID]
        self.assertEqual(len(post_routes), 3)
        self.assertEqual(len({item["curvature"] for item in post_routes}), 3)
        self.assertEqual(len({item["label_position"] for item in post_routes}), 3)
        post_label_distances = [
            math.dist(first["label_position"], second["label_position"])
            for index, first in enumerate(post_routes)
            for second in post_routes[index + 1:]
        ]
        self.assertGreaterEqual(min(post_label_distances), 0.2)

    def test_renderer_writes_closed_png_without_mutating_dataset(self):
        dataset = {
            "chains": {
                "SwiftWren.txt": {
                    "events": [
                        event(1, 1, "queue_subordinate_task", ["person:alpha", "person:john_windward"]),
                        event(2, 2, "saidit_post", ["person:john_windward"]),
                    ]
                },
                "HiddenOrca.txt": {
                    "events": [
                        event(3, 3, "queue_subordinate_task", ["person:alpha", "person:john_windward"]),
                        event(4, 4, "saidit_post", ["person:john_windward"]),
                    ]
                },
                "MellowOtter.txt": {
                    "events": [
                        event(5, 5, "queue_subordinate_task", ["person:alpha", "person:john_windward"]),
                        event(6, 6, "saidit_post", ["person:john_windward"]),
                    ]
                },
            }
        }
        original = copy.deepcopy(dataset)
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "network.png"
            render_intervention_network(dataset, output_path)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 0)
            self.assertEqual(output_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(dataset, original)
        self.assertEqual(plt.get_fignums(), [])


if __name__ == "__main__":
    unittest.main()
