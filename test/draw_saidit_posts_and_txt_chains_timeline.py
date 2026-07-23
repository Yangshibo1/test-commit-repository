"""Render Saidit posts and TXT posting chains as a department timeline."""
import copy
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


PROJECT_ROOT = Path(__file__).parent.parent
CHAIN_ORDER = ("SwiftWren.txt", "HiddenOrca.txt", "MellowOtter.txt")
SEQUENCE_TICK_INTERVAL = 25
DEPARTMENT_LABEL_X = 1.005
LEGEND_COLUMN_X = 1.16
LEGEND_VERTICAL_PADDING = 0.025
FIGURE_WIDTH = 34
FIGURE_HEIGHT = 14.5
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


def normalize_person_id(actor_id: str) -> Optional[str]:
    """Return a bare employee ID, excluding system and other non-person actors."""
    value = str(actor_id)
    if value.startswith("Agent/person:"):
        return value.removeprefix("Agent/person:")
    if value.startswith("person:"):
        return value.removeprefix("person:")
    return None


def primary_actor(event: Dict[str, Any]) -> Optional[str]:
    """Return the first party: the active operator or task delegator."""
    parties = event.get("parties") or []
    return normalize_person_id(parties[0]) if parties else None


def build_employee_rows(org_chart: Dict[str, Any]) -> List[Dict[str, Any]]:
    """List organization-chart employees grouped alphabetically by department."""
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
        visited = set()
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = nodes.get(parent_id, {})
            if parent.get("type") == "department":
                break
            parent_id = parent_by_child.get(parent_id)
        else:
            parent = {}
        if not person_id or parent.get("type") != "department":
            continue
        department = parent.get("label", "Unassigned")
        rows_by_department[department].append({
            "person_id": person_id,
            "person_label": node.get("label", person_id.replace("_", " ").title()),
            "department": department,
        })

    return [
        row
        for department in sorted(rows_by_department)
        for row in sorted(rows_by_department[department], key=lambda item: item["person_label"])
    ]


def build_row_lookup(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Assign rows a department-separated numeric Y coordinate."""
    lookup = {}
    y = 0
    previous_department = None
    for row in rows:
        if previous_department is not None and row["department"] != previous_department:
            y += 1
        positioned = dict(row, y=y)
        lookup[row["person_id"]] = positioned
        y += 1
        previous_department = row["department"]
    return lookup


def merge_chain_metadata(post: Dict[str, Any], chain_event: Dict[str, Any]) -> Dict[str, Any]:
    """Keep post fields and add chain annotations from the duplicate source event."""
    merged = dict(post)
    for key in ("chain_file", "related_file", "lifecycle_stage", "is_post_event"):
        if key in chain_event:
            merged[key] = chain_event[key]
    return merged


def build_render_events(
    posts: List[Dict[str, Any]], chain_dataset: Dict[str, Any], row_lookup: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Deduplicate posts and chains while retaining invisible events as line breaks."""
    events_by_id = {event["id"]: copy.deepcopy(event) for event in posts}
    for chain in chain_dataset.get("chains", {}).values():
        for chain_event in chain.get("events", []):
            event_id = chain_event["id"]
            events_by_id[event_id] = (
                merge_chain_metadata(events_by_id[event_id], chain_event)
                if event_id in events_by_id else copy.deepcopy(chain_event)
            )

    output = []
    for event in events_by_id.values():
        enriched = dict(event)
        actor = primary_actor(event)
        row = row_lookup.get(actor)
        enriched.update({
            "actor": actor,
            "department": row["department"] if row else None,
            "y": row["y"] if row else None,
        })
        output.append(enriched)
    return [
        dict(event, sequence_position=index)
        for index, event in enumerate(
            sorted(output, key=lambda event: (event["when"], event["id"])), start=1
        )
    ]


def build_visible_chain_segments(chain_events: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Break a chain path at events whose actors do not have organization rows."""
    segments, current = [], []
    for event in chain_events:
        if event.get("y") is None:
            if current:
                segments.append(current)
                current = []
            continue
        current.append(event)
    if current:
        segments.append(current)
    return segments


def load_posts() -> List[Dict[str, Any]]:
    with (PROJECT_ROOT / "result" / "all_posts_dataset.json").open(encoding="utf-8") as source:
        return json.load(source)


def load_txt_chain_dataset() -> Dict[str, Any]:
    with (PROJECT_ROOT / "result" / "three_txt_posting_chains_dataset.json").open(encoding="utf-8") as source:
        return json.load(source)


def load_org_chart() -> Dict[str, Any]:
    with (PROJECT_ROOT / "VAST_Challenge_2026_MC2" / "org_chart.json").open(encoding="utf-8") as source:
        return json.load(source)


def department_color_map(rows: List[Dict[str, Any]]) -> Dict[str, str]:
    departments = sorted({row["department"] for row in rows})
    return {department: DEPARTMENT_COLORS[index % len(DEPARTMENT_COLORS)] for index, department in enumerate(departments)}


def build_sequence_ticks(event_count: int, interval: int = SEQUENCE_TICK_INTERVAL) -> List[int]:
    """Return regular sequence ticks plus a readable terminal event position."""
    if event_count <= 0:
        return []
    ticks = list(range(1, event_count + 1, interval))
    if ticks[-1] != event_count:
        if event_count - ticks[-1] < interval:
            ticks.pop()
        ticks.append(event_count)
    return ticks


def stack_legends(axis: Any, legends: List[Any]) -> None:
    """Place legends in one right-side column using their rendered heights."""
    next_top = 1.0
    for legend in legends:
        legend.set_bbox_to_anchor(
            (LEGEND_COLUMN_X, next_top), transform=axis.transAxes
        )
        axis.figure.canvas.draw()
        renderer = axis.figure.canvas.get_renderer()
        bounds = axis.transAxes.inverted().transform_bbox(
            legend.get_window_extent(renderer)
        )
        next_top = bounds.y0 - LEGEND_VERTICAL_PADDING


def render_timeline(events: List[Dict[str, Any]], rows: List[Dict[str, Any]], output_path: Path) -> None:
    """Render department-colored event marks and three chronological TXT-chain paths."""
    row_lookup = build_row_lookup(rows)
    department_colors = department_color_map(rows)
    visible_events = [event for event in events if event.get("y") is not None]
    chain_events = defaultdict(list)
    for event in events:
        if event.get("chain_file") in CHAIN_ORDER:
            chain_events[event["chain_file"]].append(event)

    fig, axis = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
    fig.patch.set_facecolor("#FAFAF8")
    axis.set_facecolor("#FFFFFF")

    for chain_file in CHAIN_ORDER:
        ordered = sorted(chain_events[chain_file], key=lambda item: (item.get("when", 0), item["id"]))
        for segment in build_visible_chain_segments(ordered):
            if len(segment) > 1:
                axis.plot(
                    [event["sequence_position"] for event in segment],
                    [event["y"] for event in segment], color=CHAIN_COLORS[chain_file],
                    alpha=0.42, linewidth=1.0, solid_capstyle="round", zorder=1,
                )

    for event_type, marker in EVENT_MARKERS.items():
        typed_events = [event for event in visible_events if event.get("short_name") == event_type]
        if typed_events:
            axis.scatter(
                [event["sequence_position"] for event in typed_events],
                [event["y"] for event in typed_events],
                c=[department_colors[event["department"]] for event in typed_events],
                marker=marker, s=46 if event_type == "saidit_post" else 30,
                edgecolors="#FFFFFF", linewidths=0.55, alpha=0.92, zorder=3,
            )

    axis.set_yticks([row_lookup[row["person_id"]]["y"] for row in rows])
    axis.set_yticklabels([row["person_label"] for row in rows], fontsize=7.5)
    axis.invert_yaxis()
    event_count = len(events)
    axis.set_xticks(build_sequence_ticks(event_count))
    axis.set_xlim(0.5, event_count + 0.5)
    axis.grid(axis="x", color="#D9D9D6", linewidth=0.6, alpha=0.75)
    axis.grid(axis="y", visible=False)
    axis.set_xlabel("Event sequence (chronological order)", fontsize=11, weight="bold")
    axis.set_ylabel("Employees, grouped by department", fontsize=11, weight="bold")
    axis.set_title("Saidit Posts and Traceable TXT Posting Chains\nDepartment-colored events, typed actions, and chronological chain paths", fontsize=16, weight="bold", pad=20)

    seen_departments = set()
    for row in rows:
        department = row["department"]
        if department not in seen_departments:
            y = row_lookup[row["person_id"]]["y"]
            axis.axhline(y - 0.5, color="#D0D0CC", linewidth=0.7, zorder=0)
            axis.text(DEPARTMENT_LABEL_X, y, department, transform=axis.get_yaxis_transform(), va="center", ha="left", fontsize=8, weight="bold", color=department_colors[department])
            seen_departments.add(department)

    event_handles = [Line2D([0], [0], marker=marker, color="none", markerfacecolor="#666666", markeredgecolor="#FFFFFF", markersize=7, label=name) for name, marker in EVENT_MARKERS.items()]
    chain_handles = [Line2D([0], [0], color=CHAIN_COLORS[name], linewidth=2, label=name) for name in CHAIN_ORDER]
    department_handles = [Line2D([0], [0], marker="o", color="none", markerfacecolor=color, markersize=7, label=name) for name, color in department_colors.items()]
    first_legend = axis.legend(handles=event_handles, title="Event type", loc="upper left", fontsize=8)
    axis.add_artist(first_legend)
    second_legend = axis.legend(handles=chain_handles, title="TXT chain", loc="upper left", fontsize=8)
    axis.add_artist(second_legend)
    third_legend = axis.legend(handles=department_handles, title="Department", loc="upper left", fontsize=8)
    stack_legends(axis, [first_legend, second_legend, third_legend])
    fig.subplots_adjust(left=0.15, right=0.68, top=0.92, bottom=0.08)
    fig.savefig(output_path, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    rows = build_employee_rows(load_org_chart())
    events = build_render_events(load_posts(), load_txt_chain_dataset(), build_row_lookup(rows))
    output = PROJECT_ROOT / "result" / "saidit_posts_and_txt_chains_timeline.png"
    render_timeline(events, rows, output)
    print(f"Saved {len(events)} merged events to: {output}")


if __name__ == "__main__":
    main()
