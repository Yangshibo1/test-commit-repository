# Saidit Posts and TXT Chain Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a department-grouped point-and-line timeline that places all Saidit posts and the three traceable TXT posting chains in a single, equal-spaced chronological event sequence.

**Architecture:** A standalone Matplotlib generator will load the post dataset, the normalized TXT-chain dataset, and the authoritative organization chart. It will normalize actor identifiers, map only organization-chart employees to department rows, deduplicate shared post IDs, sort all merged records by `(when, id)`, assign sequence positions `1..N`, render typed department-colored points at those positions, and draw three semi-transparent chain polylines through visible actor events. Original timestamps are preserved as data but never control horizontal distance.

**Tech Stack:** Python 3, standard library (`json`, `pathlib`, `collections`), Matplotlib, `unittest`

---

## File structure

- Create: `test/draw_saidit_posts_and_txt_chains_timeline.py` — input loading, organization mapping, plotting-data construction, chart rendering, and CLI entry point.
- Create: `test/test_draw_saidit_posts_and_txt_chains_timeline.py` — unit tests for actor normalization, deduplication, filtering, and visible line segmentation.
- Create at runtime: `result/saidit_posts_and_txt_chains_timeline.png` — 300 DPI static point-and-line visualization.

### Task 1: Establish organization-row mapping and actor normalization

**Files:**
- Create: `test/draw_saidit_posts_and_txt_chains_timeline.py`
- Create: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`

- [ ] **Step 1: Write the failing tests for primary-actor normalization and organization-only rows**

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from draw_saidit_posts_and_txt_chains_timeline import (
    build_employee_rows,
    normalize_person_id,
    primary_actor,
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
```

- [ ] **Step 2: Run the new test file and confirm it fails because the module does not exist**

Run: `python test/test_draw_saidit_posts_and_txt_chains_timeline.py`

Expected: `ModuleNotFoundError: No module named 'draw_saidit_posts_and_txt_chains_timeline'`.

- [ ] **Step 3: Implement identifier normalization and department row construction**

Create `test/draw_saidit_posts_and_txt_chains_timeline.py` with:

```python
"""Render Saidit posts and TXT posting chains as a department timeline."""
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).parent.parent


def normalize_person_id(actor_id: str) -> Optional[str]:
    """Return a bare employee identifier, excluding system and unknown actors."""
    value = str(actor_id)
    if value.startswith("Agent/person:"):
        return value.removeprefix("Agent/person:")
    if value.startswith("person:"):
        return value.removeprefix("person:")
    return None


def primary_actor(event: Dict[str, Any]) -> Optional[str]:
    """Use the first recorded party as the event's active actor or delegator."""
    parties = event.get("parties") or []
    return normalize_person_id(parties[0]) if parties else None


def build_employee_rows(org_chart: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return alphabetized person rows grouped alphabetically by department."""
    nodes = {node["id"]: node for node in org_chart.get("nodes", [])}
    parent_by_child = {
        edge["target"]: edge["source"]
        for edge in org_chart.get("edges", [])
        if edge.get("source") and edge.get("target")
    }
    rows_by_department = defaultdict(list)

    for node in nodes.values():
        if node.get("type") != "person":
            continue
        person_id = normalize_person_id(node["id"])
        parent_id = parent_by_child.get(node["id"])
        parent = nodes.get(parent_id, {})
        if not person_id or parent.get("type") != "department":
            continue
        rows_by_department[parent.get("label", "Unassigned")].append({
            "person_id": person_id,
            "person_label": node.get("label", person_id.replace("_", " ").title()),
            "department": parent.get("label", "Unassigned"),
        })

    rows = []
    for department in sorted(rows_by_department):
        rows.extend(sorted(rows_by_department[department], key=lambda row: row["person_label"]))
    return rows
```

- [ ] **Step 4: Run the mapping tests and confirm they pass**

Run: `python test/test_draw_saidit_posts_and_txt_chains_timeline.py`

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit the organization mapping foundation**

```bash
git add test/draw_saidit_posts_and_txt_chains_timeline.py test/test_draw_saidit_posts_and_txt_chains_timeline.py
git commit -m "feat: map Saidit timeline actors to departments"
```

### Task 2: Build a deduplicated render-event collection and segmented chain paths

**Files:**
- Modify: `test/draw_saidit_posts_and_txt_chains_timeline.py`
- Modify: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`

- [ ] **Step 1: Write failing tests for deduplication, event visibility, and chain discontinuities**

Append these imports and test class to `test/test_draw_saidit_posts_and_txt_chains_timeline.py`:

```python
from draw_saidit_posts_and_txt_chains_timeline import (
    build_render_events,
    build_visible_chain_segments,
)


class RenderEventTests(unittest.TestCase):
    def test_keeps_one_copy_of_shared_post_and_excludes_unknown_actor_points(self):
        posts = [
            {"id": 10, "short_name": "saidit_post", "when": 10.0, "parties": ["person:aria_towline"]},
        ]
        chain_dataset = {
            "chains": {
                "SwiftWren.txt": {
                    "events": [
                        {"id": 10, "short_name": "saidit_post", "when": 10.0,
                         "parties": ["Agent/person:aria_towline"], "chain_file": "SwiftWren.txt"},
                        {"id": 11, "short_name": "queue_subordinate_task", "when": 11.0,
                         "parties": ["system:file_system"], "chain_file": "SwiftWren.txt"},
                    ]
                }
            }
        }
        row_lookup = {"aria_towline": {"y": 5, "department": "Operations"}}

        events = build_render_events(posts, chain_dataset, row_lookup)

        self.assertEqual([event["id"] for event in events], [10])
        self.assertEqual(events[0]["chain_file"], "SwiftWren.txt")
        self.assertEqual(events[0]["department"], "Operations")

    def test_breaks_a_chain_when_an_actor_has_no_organization_row(self):
        chain_events = [
            {"id": 1, "when": 1.0, "actor": "aria_towline", "y": 4},
            {"id": 2, "when": 2.0, "actor": None, "y": None},
            {"id": 3, "when": 3.0, "actor": "ava_tiller", "y": 1},
            {"id": 4, "when": 4.0, "actor": "aria_towline", "y": 4},
        ]

        segments = build_visible_chain_segments(chain_events)

        self.assertEqual(segments, [
            [{"id": 1, "when": 1.0, "actor": "aria_towline", "y": 4}],
            [
                {"id": 3, "when": 3.0, "actor": "ava_tiller", "y": 1},
                {"id": 4, "when": 4.0, "actor": "aria_towline", "y": 4},
            ],
        ])
```

- [ ] **Step 2: Run the test file and confirm it fails because the render functions cannot be imported**

Run: `python test/test_draw_saidit_posts_and_txt_chains_timeline.py`

Expected: `ImportError` stating that `build_render_events` cannot be imported.

- [ ] **Step 3: Implement event merge, source-aware deduplication, and visible path segmentation**

Add the following to `test/draw_saidit_posts_and_txt_chains_timeline.py`:

```python
CHAIN_ORDER = ("SwiftWren.txt", "HiddenOrca.txt", "MellowOtter.txt")


def merge_chain_metadata(post: Dict[str, Any], chain_event: Dict[str, Any]) -> Dict[str, Any]:
    """Keep post content fields while preserving chain-specific annotation fields."""
    merged = dict(post)
    for key in ("chain_file", "related_file", "lifecycle_stage", "is_post_event"):
        if key in chain_event:
            merged[key] = chain_event[key]
    return merged


def build_render_events(
    posts: List[Dict[str, Any]],
    chain_dataset: Dict[str, Any],
    row_lookup: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge both datasets by event ID and retain events with organization rows."""
    events_by_id = {event["id"]: dict(event) for event in posts}

    for chain in chain_dataset.get("chains", {}).values():
        for chain_event in chain.get("events", []):
            event_id = chain_event["id"]
            if event_id in events_by_id:
                events_by_id[event_id] = merge_chain_metadata(events_by_id[event_id], chain_event)
            else:
                events_by_id[event_id] = dict(chain_event)

    render_events = []
    for event in events_by_id.values():
        actor = primary_actor(event)
        row = row_lookup.get(actor)
        if row is None:
            continue
        render_event = dict(event)
        render_event["actor"] = actor
        render_event["department"] = row["department"]
        render_event["y"] = row["y"]
        render_events.append(render_event)

    return sorted(render_events, key=lambda event: (event.get("when", 0), event["id"]))


def build_visible_chain_segments(chain_events: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Split chronological paths at events without a visible organization row."""
    segments = []
    current_segment = []
    for event in chain_events:
        if event.get("y") is None:
            if current_segment:
                segments.append(current_segment)
                current_segment = []
            continue
        current_segment.append(event)
    if current_segment:
        segments.append(current_segment)
    return segments
```

- [ ] **Step 4: Correct `build_render_events` so chain paths retain invisible events before segmentation**

Replace `build_render_events` with this implementation, which returns all merged records while setting `y=None` for unmatched actors. This preserves the required line breaks rather than silently joining a path across unknown participants:

```python
def build_render_events(
    posts: List[Dict[str, Any]],
    chain_dataset: Dict[str, Any],
    row_lookup: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge source records, preserve gaps, and number chronological positions."""
    events_by_id = {event["id"]: dict(event) for event in posts}
    for chain in chain_dataset.get("chains", {}).values():
        for chain_event in chain.get("events", []):
            event_id = chain_event["id"]
            events_by_id[event_id] = (
                merge_chain_metadata(events_by_id[event_id], chain_event)
                if event_id in events_by_id else dict(chain_event)
            )

    render_events = []
    for event in events_by_id.values():
        actor = primary_actor(event)
        row = row_lookup.get(actor)
        render_events.append(dict(
            event,
            actor=actor,
            department=row["department"] if row else None,
            y=row["y"] if row else None,
        ))

    return [
        dict(event, sequence_position=index)
        for index, event in enumerate(
            sorted(render_events, key=lambda event: (event["when"], event["id"])), start=1
        )
    ]
```

- [ ] **Step 5: Run all mapping and render-event tests and confirm they pass**

Run: `python test/test_draw_saidit_posts_and_txt_chains_timeline.py`

Expected: `Ran 4 tests ... OK`.

- [ ] **Step 6: Commit the dataset-merge and segmentation behavior**

```bash
git add test/draw_saidit_posts_and_txt_chains_timeline.py test/test_draw_saidit_posts_and_txt_chains_timeline.py
git commit -m "feat: merge Saidit posts with TXT chain events"
```

### Task 3: Render the publication-quality timeline and output the PNG

**Files:**
- Modify: `test/draw_saidit_posts_and_txt_chains_timeline.py`
- Modify: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`
- Create at runtime: `result/saidit_posts_and_txt_chains_timeline.png`

- [ ] **Step 1: Write the failing integration test for data loading and generated output**

Append this test class to `test/test_draw_saidit_posts_and_txt_chains_timeline.py`:

```python
from tempfile import TemporaryDirectory

from draw_saidit_posts_and_txt_chains_timeline import (
    build_row_lookup,
    load_org_chart,
    load_posts,
    load_txt_chain_dataset,
    render_timeline,
)


class TimelineOutputTests(unittest.TestCase):
    def test_renders_the_real_combined_dataset_to_png(self):
        rows = build_employee_rows(load_org_chart())
        row_lookup = build_row_lookup(rows)
        events = build_render_events(load_posts(), load_txt_chain_dataset(), row_lookup)

        self.assertEqual(len({event["id"] for event in events}), 353)
        self.assertEqual(sum(event["short_name"] == "saidit_post" for event in events), 108)

        with TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "timeline.png"
            render_timeline(events, rows, output_path)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 10_000)
```

- [ ] **Step 2: Run the test and confirm it fails because loader or renderer functions are unavailable**

Run: `python test/test_draw_saidit_posts_and_txt_chains_timeline.py`

Expected: `ImportError` identifying one of `load_posts`, `load_txt_chain_dataset`, or `render_timeline`.

- [ ] **Step 3: Add dataset loaders and stable Y-axis placement**

Add this code to `test/draw_saidit_posts_and_txt_chains_timeline.py`:

```python
import json


def load_posts() -> List[Dict[str, Any]]:
    with (PROJECT_ROOT / "result" / "all_posts_dataset.json").open(encoding="utf-8") as data_file:
        return json.load(data_file)


def load_txt_chain_dataset() -> Dict[str, Any]:
    with (PROJECT_ROOT / "result" / "three_txt_posting_chains_dataset.json").open(encoding="utf-8") as data_file:
        return json.load(data_file)


def load_org_chart() -> Dict[str, Any]:
    with (PROJECT_ROOT / "VAST_Challenge_2026_MC2" / "org_chart.json").open(encoding="utf-8") as data_file:
        return json.load(data_file)


def build_row_lookup(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Assign department-separated numeric Y positions to employee rows."""
    lookup = {}
    y = 0
    previous_department = None
    for row in rows:
        if previous_department is not None and row["department"] != previous_department:
            y += 1
        positioned_row = dict(row)
        positioned_row["y"] = y
        lookup[row["person_id"]] = positioned_row
        y += 1
        previous_department = row["department"]
    return lookup
```

- [ ] **Step 4: Add Matplotlib rendering with shape, department, and chain encodings**

Add this rendering implementation to `test/draw_saidit_posts_and_txt_chains_timeline.py`:

```python
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


DEPARTMENT_COLORS = [
    "#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1",
    "#76B7B2", "#EDC948", "#FF9DA7", "#9C755F", "#BAB0AC",
]
EVENT_MARKERS = {
    "saidit_post": "o",
    "create_file": "s",
    "read_file": "D",
    "queue_subordinate_task": "^",
    "delete_file": "X",
}
CHAIN_COLORS = {
    "SwiftWren.txt": "#C33C54",
    "HiddenOrca.txt": "#246EB9",
    "MellowOtter.txt": "#5A9367",
}


SEQUENCE_TICK_INTERVAL = 25


def department_color_map(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    departments = sorted({row["department"] for row in rows})
    return {
        department: DEPARTMENT_COLORS[index % len(DEPARTMENT_COLORS)]
        for index, department in enumerate(departments)
    }


def render_timeline(
    events: List[Dict[str, Any]], rows: List[Dict[str, Any]], output_path: Path
) -> None:
    """Render all visible events and the three segmented TXT-chain paths."""
    row_lookup = build_row_lookup(rows)
    colors = department_color_map(rows)
    visible_events = [event for event in events if event.get("y") is not None]
    chain_events = defaultdict(list)
    for event in events:
        chain_file = event.get("chain_file")
        if chain_file in CHAIN_ORDER:
            chain_events[chain_file].append(event)

    figure_height = max(14, len(rows) * 0.32 + 5)
    fig, axis = plt.subplots(figsize=(25, figure_height))
    fig.patch.set_facecolor("#FAFAF8")
    axis.set_facecolor("#FFFFFF")

    for chain_file in CHAIN_ORDER:
        ordered = sorted(chain_events[chain_file], key=lambda event: event["sequence_position"])
        for segment in build_visible_chain_segments(ordered):
            if len(segment) < 2:
                continue
            axis.plot(
                [event["sequence_position"] for event in segment],
                [event["y"] for event in segment],
                color=CHAIN_COLORS[chain_file], alpha=0.42, linewidth=1.25,
                solid_capstyle="round", zorder=1,
            )

    for event_type, marker in EVENT_MARKERS.items():
        typed_events = [event for event in visible_events if event.get("short_name") == event_type]
        if not typed_events:
            continue
        axis.scatter(
            [event["sequence_position"] for event in typed_events],
            [event["y"] for event in typed_events],
            c=[colors[event["department"]] for event in typed_events],
            marker=marker, s=58 if event_type == "saidit_post" else 38,
            edgecolors="#FFFFFF", linewidths=0.55, alpha=0.92, zorder=3,
        )

    y_ticks = [row_lookup[row["person_id"]]["y"] for row in rows]
    axis.set_yticks(y_ticks, [row["person_label"] for row in rows], fontsize=7.5)
    axis.invert_yaxis()
    event_count = len(events)
    sequence_ticks = list(range(1, event_count + 1, SEQUENCE_TICK_INTERVAL))
    if event_count and sequence_ticks[-1] != event_count:
        sequence_ticks.append(event_count)
    axis.set_xticks(sequence_ticks)
    axis.set_xlim(0.5, event_count + 0.5)
    axis.grid(axis="x", color="#D9D9D6", linewidth=0.6, alpha=0.75)
    axis.grid(axis="y", visible=False)
    axis.set_xlabel("Event sequence (chronological order)", fontsize=11, weight="bold")
    axis.set_ylabel("Employees, grouped by department", fontsize=11, weight="bold")
    axis.set_title(
        "Saidit Posts and Traceable TXT Posting Chains\n"
        "Department-colored events, typed actions, and chronological chain paths",
        fontsize=16, weight="bold", pad=20,
    )

    department_starts = {}
    for row in rows:
        department_starts.setdefault(row["department"], row_lookup[row["person_id"]]["y"])
    for department, start_y in department_starts.items():
        axis.axhline(start_y - 0.5, color="#D0D0CC", linewidth=0.7, zorder=0)
        axis.text(
            1.005, start_y, department, transform=axis.get_yaxis_transform(),
            va="center", ha="left", fontsize=8, weight="bold", color=colors[department],
        )

    event_handles = [
        Line2D([0], [0], marker=marker, color="none", markerfacecolor="#666666",
               markeredgecolor="#FFFFFF", markersize=7, label=event_type)
        for event_type, marker in EVENT_MARKERS.items()
    ]
    chain_handles = [
        Line2D([0], [0], color=CHAIN_COLORS[chain_file], linewidth=2,
               label=chain_file)
        for chain_file in CHAIN_ORDER
    ]
    department_handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=color,
               markersize=7, label=department)
        for department, color in colors.items()
    ]
    legend_events = axis.legend(handles=event_handles, title="Event type", loc="upper left", bbox_to_anchor=(1.005, 1.0), fontsize=8)
    axis.add_artist(legend_events)
    legend_chains = axis.legend(handles=chain_handles, title="TXT chain", loc="upper left", bbox_to_anchor=(1.005, 0.76), fontsize=8)
    axis.add_artist(legend_chains)
    axis.legend(handles=department_handles, title="Department", loc="upper left", bbox_to_anchor=(1.005, 0.57), fontsize=8)

    fig.subplots_adjust(left=0.20, right=0.80, top=0.92, bottom=0.07)
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
```

- [ ] **Step 5: Add the CLI entry point**

Append this code:

```python
def main() -> None:
    rows = build_employee_rows(load_org_chart())
    row_lookup = build_row_lookup(rows)
    events = build_render_events(load_posts(), load_txt_chain_dataset(), row_lookup)
    output_path = PROJECT_ROOT / "result" / "saidit_posts_and_txt_chains_timeline.png"
    render_timeline(events, rows, output_path)
    print(f"Saved {len(events)} merged events to: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the full timeline test file and confirm it passes**

Run: `python test/test_draw_saidit_posts_and_txt_chains_timeline.py`

Expected: `Ran 5 tests ... OK`.

- [ ] **Step 7: Generate the final plot via the script interface**

Run: `PYTHONIOENCODING=utf-8 python test/draw_saidit_posts_and_txt_chains_timeline.py`

Expected: output states `Saved 353 merged events to:` followed by `result/saidit_posts_and_txt_chains_timeline.png`.

- [ ] **Step 8: Inspect the generated image and verify expected visual evidence**

Open: `result/saidit_posts_and_txt_chains_timeline.png`

Confirm visually:
- the X axis is `Event sequence (chronological order)` with equal spacing;
- every organization-chart employee has a Y-axis row grouped under department labels;
- direct Saidit posts appear as circular department-colored points;
- five event shapes appear in the event-type legend;
- three differently colored lines identify the three TXT chains;
- no `system:*` or `Unknown` category appears on the Y axis.

- [ ] **Step 9: Commit the renderer, tests, and generated artifact**

```bash
git add test/draw_saidit_posts_and_txt_chains_timeline.py test/test_draw_saidit_posts_and_txt_chains_timeline.py result/saidit_posts_and_txt_chains_timeline.png
git commit -m "feat: visualize Saidit posts and TXT chains timeline"
```
