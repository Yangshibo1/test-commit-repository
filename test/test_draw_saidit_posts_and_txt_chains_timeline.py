import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from draw_saidit_posts_and_txt_chains_timeline import (
    CHAIN_COLORS,
    CHAIN_ORDER,
    EVENT_MARKERS,
    build_employee_rows,
    build_render_events,
    build_row_lookup,
    build_sequence_ticks,
    build_visible_chain_segments,
    load_org_chart,
    load_posts,
    load_txt_chain_dataset,
    normalize_person_id,
    primary_actor,
    render_timeline,
)


class OrganizationMappingTests(unittest.TestCase):
    def test_normalizes_person_and_agent_person_identifiers(self):
        self.assertEqual(normalize_person_id("person:aria_towline"), "aria_towline")
        self.assertEqual(normalize_person_id("Agent/person:aria_towline"), "aria_towline")
        self.assertIsNone(normalize_person_id("system:saidit"))

    def test_uses_only_organization_people_as_rows_grouped_by_department(self):
        org_chart = {
            "nodes": [
                {"id": "department:operations", "type": "department", "label": "Operations"},
                {"id": "department:marketing", "type": "department", "label": "Marketing"},
                {"id": "person:aria_towline", "type": "person", "label": "Aria Towline"},
                {"id": "person:ava_tiller", "type": "person", "label": "Ava Tiller"},
                {"id": "system:saidit", "type": "system", "label": "Saidit"},
            ],
            "edges": [
                {"source": "department:operations", "target": "person:aria_towline"},
                {"source": "department:marketing", "target": "person:ava_tiller"},
            ],
        }
        rows = build_employee_rows(org_chart)
        self.assertEqual([row["person_id"] for row in rows], ["ava_tiller", "aria_towline"])
        self.assertEqual([row["department"] for row in rows], ["Marketing", "Operations"])
        self.assertEqual(primary_actor({"parties": ["Agent/person:aria_towline", "system:saidit"]}), "aria_towline")
    def test_resolves_people_through_team_ancestors_to_departments(self):
        org_chart = {
            "nodes": [
                {"id": "department:products", "type": "department", "label": "Products"},
                {"id": "team:analysis", "type": "team", "label": "Analysis"},
                {"id": "person:john_windward", "type": "person", "label": "John Windward"},
            ],
            "edges": [
                {"source": "department:products", "target": "team:analysis"},
                {"source": "team:analysis", "target": "person:john_windward"},
            ],
        }

        rows = build_employee_rows(org_chart)

        self.assertEqual(rows, [{
            "person_id": "john_windward",
            "person_label": "John Windward",
            "department": "Products",
        }])


class RenderEventTests(unittest.TestCase):
    def test_keeps_one_copy_of_shared_post_and_excludes_unknown_actor_points(self):
        posts = [{"id": 10, "short_name": "saidit_post", "when": 10.0, "parties": ["person:aria_towline"]}]
        chain_dataset = {"chains": {"SwiftWren.txt": {"events": [
            {"id": 10, "short_name": "saidit_post", "when": 10.0, "parties": ["Agent/person:aria_towline"], "chain_file": "SwiftWren.txt"},
            {"id": 11, "short_name": "queue_subordinate_task", "when": 11.0, "parties": ["system:file_system"], "chain_file": "SwiftWren.txt"},
        ]}}}
        events = build_render_events(posts, chain_dataset, {"aria_towline": {"y": 5, "department": "Operations"}})
        self.assertEqual([event["id"] for event in events], [10, 11])
        self.assertEqual(events[0]["chain_file"], "SwiftWren.txt")
        self.assertEqual(events[0]["department"], "Operations")
        self.assertIsNone(events[1]["y"])

    def test_breaks_a_chain_when_an_actor_has_no_organization_row(self):
        chain_events = [
            {"id": 1, "when": 1.0, "actor": "aria_towline", "y": 4},
            {"id": 2, "when": 2.0, "actor": None, "y": None},
            {"id": 3, "when": 3.0, "actor": "ava_tiller", "y": 1},
            {"id": 4, "when": 4.0, "actor": "aria_towline", "y": 4},
        ]
        self.assertEqual(build_visible_chain_segments(chain_events), [
            [{"id": 1, "when": 1.0, "actor": "aria_towline", "y": 4}],
            [{"id": 3, "when": 3.0, "actor": "ava_tiller", "y": 1}, {"id": 4, "when": 4.0, "actor": "aria_towline", "y": 4}],
        ])


class EventSequenceTests(unittest.TestCase):
    def test_builds_regular_ticks_and_replaces_nearby_final_tick(self):
        self.assertEqual(
            build_sequence_ticks(353, 25),
            [1, 26, 51, 76, 101, 126, 151, 176, 201, 226, 251, 276, 301, 326, 353],
        )
        self.assertEqual(
            build_sequence_ticks(375, 25),
            [1, 26, 51, 76, 101, 126, 151, 176, 201, 226, 251, 276, 301, 326, 375],
        )

    def test_builds_ticks_for_empty_and_single_event_sequences(self):
        self.assertEqual(build_sequence_ticks(0, 25), [])
        self.assertEqual(build_sequence_ticks(1, 25), [1])

    def test_assigns_equal_spaced_sequence_positions_in_time_and_id_order(self):
        posts = [
            {"id": 9, "short_name": "saidit_post", "when": 1000.0, "parties": ["person:aria_towline"]},
            {"id": 3, "short_name": "saidit_post", "when": 1.0, "parties": ["person:aria_towline"]},
            {"id": 5, "short_name": "saidit_post", "when": 1000.0, "parties": ["person:aria_towline"]},
        ]
        events = build_render_events(posts, {"chains": {}}, {"aria_towline": {"y": 5, "department": "Operations"}})

        self.assertEqual(
            [(event["id"], event["sequence_position"]) for event in events],
            [(3, 1), (5, 2), (9, 3)],
        )


class TimelineOutputTests(unittest.TestCase):
    def test_uses_event_sequence_positions_for_points_lines_and_axis(self):
        rows = [{"person_id": "aria_towline", "person_label": "Aria Towline", "department": "Operations"}]
        events = [
            {"id": 1, "when": 1.0, "sequence_position": 1, "short_name": "create_file", "department": "Operations", "y": 0, "chain_file": "SwiftWren.txt"},
            {"id": 2, "when": 999999.0, "sequence_position": 2, "short_name": "saidit_post", "department": "Operations", "y": 0, "chain_file": "SwiftWren.txt"},
        ]
        axis = MagicMock()
        figure = MagicMock()
        with patch("draw_saidit_posts_and_txt_chains_timeline.plt.subplots", return_value=(figure, axis)):
            with patch("draw_saidit_posts_and_txt_chains_timeline.plt.close"):
                render_timeline(events, rows, Path("timeline.png"))

        self.assertEqual(axis.set_xlabel.call_args.args[0], "Event sequence (chronological order)")
        self.assertIn(1, axis.set_xticks.call_args.args[0])
        self.assertIn(2, axis.set_xticks.call_args.args[0])
        self.assertEqual(axis.plot.call_args.args[0], [1, 2])
        self.assertEqual(axis.scatter.call_args_list[0].args[0], [2])
        self.assertEqual(axis.scatter.call_args_list[1].args[0], [1])

    def test_renders_real_combined_dataset_to_png(self):
        rows = build_employee_rows(load_org_chart())
        events = build_render_events(load_posts(), load_txt_chain_dataset(), build_row_lookup(rows))
        self.assertEqual(len(rows), 49)
        self.assertEqual(
            {row["department"] for row in rows},
            {
                "Executive Suite",
                "Products",
                "Human Resources",
                "Legal",
                "Information Technologies",
                "Customer Support",
            },
        )
        self.assertEqual(
            {name: len(chain["events"]) for name, chain in load_txt_chain_dataset()["chains"].items()},
            {"SwiftWren.txt": 191, "HiddenOrca.txt": 42, "MellowOtter.txt": 15},
        )
        self.assertEqual(len({event["id"] for event in events}), 353)
        self.assertEqual([event["sequence_position"] for event in events], list(range(1, 354)))
        self.assertEqual(sum(event["short_name"] == "saidit_post" for event in events), 108)
        self.assertEqual(
            EVENT_MARKERS,
            {
                "saidit_post": "o",
                "create_file": "s",
                "read_file": "D",
                "queue_subordinate_task": "^",
                "delete_file": "X",
            },
        )
        self.assertEqual(set(CHAIN_COLORS), set(CHAIN_ORDER))
        self.assertEqual(len(set(CHAIN_COLORS.values())), 3)
        self.assertTrue(all(event["department"] is not None for event in events))
        with TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "timeline.png"
            render_timeline(events, rows, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 10_000)


if __name__ == "__main__":
    unittest.main()
