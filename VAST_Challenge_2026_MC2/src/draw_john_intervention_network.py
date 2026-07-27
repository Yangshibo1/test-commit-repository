"""Render the three observed TXT personnel chains and one proposed validation gate."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, RegularPolygon


PROJECT_ROOT = Path(__file__).parent.parent.parent
DATASET_PATH = PROJECT_ROOT / "result" / "three_txt_posting_chains_dataset.json"
OUTPUT_PATH = (
    PROJECT_ROOT
    / "VAST_Challenge_2026_MC2"
    / "report_question_visualizations"
    / "q6_john_posting_intervention_network.png"
)
GATE_ID = "__validation_gate__"
CHAIN_ORDER = ("SwiftWren.txt", "HiddenOrca.txt", "MellowOtter.txt")
CHAIN_BANDS = {
    "HiddenOrca.txt": 1,
    "SwiftWren.txt": 0,
    "MellowOtter.txt": -1,
}
CHAIN_COLORS = {
    "SwiftWren.txt": "#C33C54",
    "HiddenOrca.txt": "#246EB9",
    "MellowOtter.txt": "#000000",
}
PERSON_COLUMN_SPACING = 2.4
SUPPLEMENTARY_OFFSET = 0.55
CHAIN_BAND_Y = 2.35
CHAIN_CURVATURE = {
    "HiddenOrca.txt": 0.19,
    "SwiftWren.txt": 0.0,
    "MellowOtter.txt": -0.19,
}


def _person_id(value: str) -> str | None:
    value = str(value)
    for prefix in ("Agent/person:", "person:"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return None


def _person_ids(parties: Any) -> list[str]:
    """Return normalized personnel identifiers in their original party order."""
    return [
        person_id
        for party in parties or []
        if (person_id := _person_id(str(party))) is not None
    ]


def _display_name(person_id: str) -> str:
    return " ".join(part.capitalize() for part in person_id.split("_"))


def _derive_event_edge(
    chain_file: str,
    event: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return one supported personnel arrow, or None for unresolved events."""
    people = _person_ids(event.get("parties"))
    if len(people) == 2:
        return {
            "event_id": event.get("id"),
            "chain_file": chain_file,
            "when": event.get("when"),
            "short_name": event.get("short_name", ""),
            "source": people[0],
            "target": people[1],
            "is_post": False,
        }
    if (
        len(people) == 1
        and people[0] == "john_windward"
        and event.get("short_name") == "saidit_post"
    ):
        return {
            "event_id": event.get("id"),
            "chain_file": chain_file,
            "when": event.get("when"),
            "short_name": "saidit_post",
            "source": "john_windward",
            "target": GATE_ID,
            "is_post": True,
        }
    return None


def _event_sort_key(event: Mapping[str, Any]) -> tuple[bool, float, int]:
    when = event.get("when")
    return (when is None, float(when or 0), int(event.get("id") or 0))


def build_intervention_graph(dataset: Mapping[str, Any]) -> dict[str, Any]:
    """Build all directionally viable events with independent chain sequences."""
    people: set[str] = set()
    edges: list[dict[str, Any]] = []
    edges_by_chain: dict[str, list[dict[str, Any]]] = {name: [] for name in CHAIN_ORDER}
    chain_people: dict[str, list[str]] = {name: [] for name in CHAIN_ORDER}
    omitted_events: list[dict[str, Any]] = []

    for chain_file in CHAIN_ORDER:
        events = dataset.get("chains", {}).get(chain_file, {}).get("events", [])
        for event in sorted(events, key=_event_sort_key):
            edge = _derive_event_edge(chain_file, event)
            if edge is None:
                omitted_events.append({
                    "event_id": event.get("id"),
                    "chain_file": chain_file,
                    "short_name": event.get("short_name", ""),
                    "person_count": len(_person_ids(event.get("parties"))),
                })
                continue
            edge["sequence"] = len(edges_by_chain[chain_file]) + 1
            edges.append(edge)
            edges_by_chain[chain_file].append(edge)
            for person in (edge["source"], edge["target"]):
                if person == GATE_ID:
                    continue
                people.add(person)
                if person not in chain_people[chain_file]:
                    chain_people[chain_file].append(person)

    return {
        "people": people,
        "edges": edges,
        "edges_by_chain": edges_by_chain,
        "chain_people": chain_people,
        "omitted_events": omitted_events,
    }


def build_person_positions(graph: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    """Place SwiftWren on the center line and attach unique supplementary people."""
    positions: dict[str, tuple[float, float]] = {}
    for index, person in enumerate(graph["chain_people"]["SwiftWren.txt"]):
        positions[person] = (index * PERSON_COLUMN_SPACING, 0.0)

    for chain_file in ("HiddenOrca.txt", "MellowOtter.txt"):
        band_y = CHAIN_BANDS[chain_file] * CHAIN_BAND_Y
        pending = list(graph["edges_by_chain"].get(chain_file, []))
        made_progress = True
        while pending and made_progress:
            made_progress = False
            remaining: list[Mapping[str, Any]] = []
            for edge in pending:
                source, target = edge["source"], edge["target"]
                if source == GATE_ID or target == GATE_ID:
                    continue
                source_known, target_known = source in positions, target in positions
                if source_known == target_known:
                    remaining.append(edge)
                    continue
                if source_known:
                    positions[target] = (positions[source][0] + SUPPLEMENTARY_OFFSET, band_y)
                else:
                    positions[source] = (positions[target][0] - SUPPLEMENTARY_OFFSET, band_y)
                made_progress = True
            pending = remaining

        # Any disconnected component has no first attachment. Keep it deterministic.
        fallback_x = max((x for x, _ in positions.values()), default=0.0) + PERSON_COLUMN_SPACING
        for person in graph["chain_people"].get(chain_file, []):
            if person not in positions:
                positions[person] = (fallback_x, band_y)
                fallback_x += PERSON_COLUMN_SPACING

    return positions


def _symmetric_offsets(count: int) -> list[float]:
    return [index - (count - 1) / 2 for index in range(count)]


def _curve_midpoint(
    start: tuple[float, float],
    end: tuple[float, float],
    curvature: float,
) -> tuple[float, float]:
    """Return a quadratic Bezier midpoint with a normal-direction control point."""
    start_x, start_y = start
    end_x, end_y = end
    dx, dy = end_x - start_x, end_y - start_y
    distance = max((dx * dx + dy * dy) ** 0.5, 0.001)
    normal_x, normal_y = -dy / distance, dx / distance
    control_x = (start_x + end_x) / 2 + normal_x * curvature * distance
    control_y = (start_y + end_y) / 2 + normal_y * curvature * distance
    return (
        0.25 * start_x + 0.5 * control_x + 0.25 * end_x,
        0.25 * start_y + 0.5 * control_y + 0.25 * end_y,
    )


def build_edge_routes(
    edges: list[Mapping[str, Any]],
    person_positions: Mapping[str, tuple[float, float]],
    gate_position: tuple[float, float],
) -> list[dict[str, Any]]:
    """Compute distinct arrow routes and labels for every retained event."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for edge in edges:
        groups[(str(edge["source"]), str(edge["target"]))].append(edge)

    routes: list[dict[str, Any]] = []
    for (source, target), pair_edges in groups.items():
        for occurrence, (edge, offset) in enumerate(zip(pair_edges, _symmetric_offsets(len(pair_edges)))):
            start = person_positions[source]
            end = gate_position if target == GATE_ID else person_positions[target]
            base_curve = CHAIN_CURVATURE[edge["chain_file"]]
            if source == target:
                direction = 1 if CHAIN_BANDS[edge["chain_file"]] >= 0 else -1
                radius = 0.8 + occurrence * 0.28
                start = (start[0] - 0.32, start[1])
                end = (end[0] + 0.32, end[1])
                routes.append({
                    "edge": edge,
                    "start": start,
                    "end": end,
                    "curvature": direction * radius,
                    "label_position": (person_positions[source][0], person_positions[source][1] + direction * (1.0 + occurrence * 0.32)),
                    "is_self_loop": True,
                })
                continue

            curvature = base_curve + offset * 0.09
            if target == GATE_ID:
                curvature = {"SwiftWren.txt": 0.0, "HiddenOrca.txt": 0.34, "MellowOtter.txt": -0.34}[edge["chain_file"]]
            routes.append({
                "edge": edge,
                "start": start,
                "end": end,
                "curvature": curvature,
                "label_position": _curve_midpoint(start, end, curvature),
                "is_self_loop": False,
            })
    return routes


def _draw_person_node(
    axis: Any,
    x: float,
    y: float,
    person: str,
    *,
    emphasized: bool,
) -> None:
    width, height = (2.02, 0.66) if emphasized else (1.78, 0.56)
    facecolor = "#FFF3CD" if emphasized else "#EDF4FA"
    edgecolor = "#C98200" if emphasized else "#4E79A7"
    node = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.03,rounding_size=0.08",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.8 if emphasized else 1.35,
        zorder=4,
    )
    axis.add_patch(node)
    axis.text(x, y, _display_name(person), ha="center", va="center", fontsize=7.4 if emphasized else 6.7,
              weight="bold" if emphasized else "normal", zorder=5)


def render_intervention_network(dataset: Mapping[str, Any], output_path: Path) -> None:
    """Render the approved static Q6 personnel-chain intervention figure."""
    graph = build_intervention_graph(dataset)
    person_positions = build_person_positions(graph)
    if "john_windward" not in person_positions:
        raise ValueError("The observed intervention graph requires John Windward")

    john_x, john_y = person_positions["john_windward"]
    gate_position = (john_x + 2.7, john_y)
    routes = build_edge_routes(graph["edges"], person_positions, gate_position)

    figure, axis = plt.subplots(figsize=(34, 17))
    figure.patch.set_facecolor("#FAFAF8")
    axis.set_facecolor("#FFFFFF")
    axis.axis("off")

    for route in routes:
        edge = route["edge"]
        arrow = FancyArrowPatch(
            route["start"],
            route["end"],
            arrowstyle="-|>",
            mutation_scale=7.4,
            connectionstyle=f"arc3,rad={route['curvature']}",
            linewidth=0.72,
            color=CHAIN_COLORS[edge["chain_file"]],
            alpha=0.56,
            zorder=2,
        )
        axis.add_patch(arrow)
        label_x, label_y = route["label_position"]
        axis.text(
            label_x,
            label_y,
            str(edge["sequence"]),
            ha="center",
            va="center",
            fontsize=4.7,
            color="#202124",
            zorder=3,
            bbox={"boxstyle": "round,pad=0.11", "facecolor": "#FFFFFF", "edgecolor": "none", "alpha": 0.83},
        )

    for person, (x, y) in person_positions.items():
        _draw_person_node(axis, x, y, person, emphasized=person == "john_windward")

    gate = RegularPolygon(
        gate_position,
        numVertices=4,
        radius=0.8,
        orientation=0.785,
        facecolor="#FCE8E6",
        edgecolor="#B3261E",
        linewidth=1.8,
        zorder=4,
    )
    axis.add_patch(gate)
    axis.text(*gate_position, "saidit_post\nvalidation gate", ha="center", va="center", fontsize=6.5,
              weight="bold", color="#7A271A", zorder=5)

    min_x = min(x for x, _ in person_positions.values())
    max_x = max(x for x, _ in person_positions.values())
    min_y = min(y for _, y in person_positions.values())
    max_y = max(y for _, y in person_positions.values())
    axis.set_xlim(min_x - 1.8, max(max_x, gate_position[0]) + 4.3)
    axis.set_ylim(min_y - 3.0, max_y + 3.4)

    title_y = max_y + 2.8
    axis.text(
        min_x - 1.5,
        title_y,
        "Three Observed TXT Posting Chains Converge at John Windward’s Publication Workflow",
        fontsize=18,
        weight="bold",
        color="#202124",
    )
    axis.text(
        min_x - 1.5,
        title_y - 0.48,
        "Each person appears once. Every directionally viable personnel event is a separately numbered arrow.",
        fontsize=9.5,
        color="#5F6368",
    )
    axis.text(
        gate_position[0] + 1.12,
        gate_position[1] - 1.02,
        "content_source exists +\ncontent empty → block + audit",
        fontsize=7.5,
        va="top",
        color="#4A4A4A",
    )
    axis.text(
        min_x - 1.5,
        min_y - 2.4,
        "The gate covers all three observed TXT-derived anomalous posting chains.\n"
        "This observed pattern does not establish that every future anomaly will reach John Windward’s publication workflow.",
        fontsize=8.6,
        color="#3C4043",
    )

    legend_handles = [
        Line2D([0], [0], color=CHAIN_COLORS[name], linewidth=2, label=name)
        for name in CHAIN_ORDER
    ]
    legend_handles.extend([
        Line2D([], [], color="#FFFFFF", linewidth=0, label="number = event order within its chain"),
        Line2D([0], [0], color="#B3261E", marker="D", linestyle="None", markersize=7,
               label="proposed pre-publication validation gate"),
    ])
    axis.legend(handles=legend_handles, loc="lower left", bbox_to_anchor=(0.01, 0.04), ncol=3,
                fontsize=7.3, frameon=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=220, bbox_inches="tight", facecolor=figure.get_facecolor())
    plt.close(figure)


def main() -> None:
    with DATASET_PATH.open(encoding="utf-8") as source:
        dataset = json.load(source)
    render_intervention_network(dataset, OUTPUT_PATH)
    print(f"Saved intervention network to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
