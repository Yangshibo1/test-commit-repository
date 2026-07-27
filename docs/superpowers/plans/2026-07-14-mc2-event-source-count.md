# MC2 Event Source Count Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Python script and compact JSON result that count all MC2 events by the literal first member of each event's `parties` array.

**Architecture:** The script reads `MC2 data.json` and `org_chart.json`, uses a single `collections.Counter` pass over the event list keyed by literal `parties[0]`, and never normalizes aliases. It emits every organization node, including nodes with zero events, and separately reports literal source identities that have no exact organization-node-ID match.

**Tech Stack:** Python 3 standard library (`argparse`, `collections`, `json`, `pathlib`, `typing`, `unittest`).

---

## File Structure

- Create: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/count_event_sources.py`
  - Command-line utility that loads the two source JSON files, resolves literal first-party sources, validates accounting totals, and writes the aggregate JSON report.
- Create: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/test_count_event_sources.py`
  - Standard-library unit tests using tiny temporary JSON fixtures; verifies literal identity separation, zero-count organization nodes, unmapped nodes, unresolved events, ordering, and count reconciliation.
- Create: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/event_source_counts.json`
  - Generated aggregate result from the full supplied VAST MC2 data. Not hand-edited.

### Task 1: Add Tests for Source Counting

**Files:**
- Create: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/test_count_event_sources.py`
- Create: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/count_event_sources.py`

- [ ] **Step 1: Write a failing unit test for literal source counts and organization-node enrichment**

```python
import unittest

from count_event_sources import build_report


class BuildReportTests(unittest.TestCase):
    def test_counts_literal_first_party_without_normalizing_agents(self):
        events = [
            {"id": 1, "parties": ["person:john_windward", "system:email_server"]},
            {"id": 2, "parties": ["Agent/person:john_windward", "system:email_server"]},
            {"id": 3, "parties": ["person:john_windward"]},
        ]
        org_nodes = [
            {"id": "person:john_windward", "label": "John Windward", "type": "person"},
            {"id": "person:isaac_mast", "label": "Isaac Mast", "type": "person"},
        ]

        report = build_report(events, org_nodes, "MC2 data.json", "org_chart.json")

        self.assertEqual(report["total_events"], 3)
        self.assertEqual(report["resolved_source_events"], 3)
        self.assertEqual(report["unresolved_source_events"], 0)
        self.assertEqual(
            report["organization_nodes"],
            [
                {
                    "source_id": "person:john_windward",
                    "label": "John Windward",
                    "type": "person",
                    "event_count": 2,
                    "event_percentage": 66.666667,
                },
                {
                    "source_id": "person:isaac_mast",
                    "label": "Isaac Mast",
                    "type": "person",
                    "event_count": 0,
                    "event_percentage": 0.0,
                },
            ],
        )
        self.assertEqual(
            report["external_or_unmapped_nodes"],
            [
                {
                    "source_id": "Agent/person:john_windward",
                    "event_count": 1,
                    "event_percentage": 33.333333,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails because the module does not yet exist**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python -m unittest test.vast_challenge_2026_mc2.test_count_event_sources -v
```

Expected: `ModuleNotFoundError: No module named 'count_event_sources'`.

- [ ] **Step 3: Add the minimal report builder implementation**

Create `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/count_event_sources.py` with:

```python
"""Count MC2 events by their literal first-party source."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _percentage(count: int, total: int) -> float:
    return round((count / total) * 100, 6) if total else 0.0


def _sort_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(nodes, key=lambda node: (-node["event_count"], node["source_id"]))


def build_report(
    events: list[dict[str, Any]],
    org_nodes: list[dict[str, Any]],
    events_path: str,
    org_chart_path: str,
) -> dict[str, Any]:
    source_counts: Counter[str] = Counter()
    unresolved_source_events = 0

    for event in events:
        parties = event.get("parties") if isinstance(event, dict) else None
        if not isinstance(parties, list) or not parties or not isinstance(parties[0], str):
            unresolved_source_events += 1
            continue
        source_counts[parties[0]] += 1

    total_events = len(events)
    org_nodes_by_id = {
        node["id"]: node
        for node in org_nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    organization_nodes = _sort_nodes(
        [
            {
                "source_id": source_id,
                "label": node.get("label"),
                "type": node.get("type"),
                "event_count": source_counts.get(source_id, 0),
                "event_percentage": _percentage(source_counts.get(source_id, 0), total_events),
            }
            for source_id, node in org_nodes_by_id.items()
        ]
    )
    external_or_unmapped_nodes = _sort_nodes(
        [
            {
                "source_id": source_id,
                "event_count": count,
                "event_percentage": _percentage(count, total_events),
            }
            for source_id, count in source_counts.items()
            if source_id not in org_nodes_by_id
        ]
    )

    return {
        "events_path": events_path,
        "org_chart_path": org_chart_path,
        "total_events": total_events,
        "resolved_source_events": sum(source_counts.values()),
        "unresolved_source_events": unresolved_source_events,
        "organization_nodes": organization_nodes,
        "external_or_unmapped_nodes": external_or_unmapped_nodes,
    }
```

- [ ] **Step 4: Run the unit test and verify it passes**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python -m unittest test.vast_challenge_2026_mc2.test_count_event_sources -v
```

Expected: `Ran 1 test ... OK`.

- [ ] **Step 5: Commit the tested report-builder unit**

```bash
git add VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/count_event_sources.py VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/test_count_event_sources.py
git commit -m "feat: add MC2 event source counter" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2: Cover Unresolved Events and JSON I/O

**Files:**
- Modify: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/test_count_event_sources.py`
- Modify: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/count_event_sources.py`

- [ ] **Step 1: Add a failing test for malformed/empty parties and output writing**

Append this test method to `BuildReportTests`:

```python
    def test_counts_missing_or_invalid_parties_as_unresolved_and_writes_json(self):
        import json
        import tempfile
        from pathlib import Path

        from count_event_sources import load_json_array, write_report

        events = [
            {"id": 1, "parties": []},
            {"id": 2},
            {"id": 3, "parties": [42]},
            {"id": 4, "parties": ["system:file_system"]},
        ]
        org_nodes = [{"id": "person:john_windward", "label": "John Windward", "type": "person"}]
        report = build_report(events, org_nodes, "MC2 data.json", "org_chart.json")

        self.assertEqual(report["resolved_source_events"], 1)
        self.assertEqual(report["unresolved_source_events"], 3)
        self.assertEqual(report["external_or_unmapped_nodes"][0]["source_id"], "system:file_system")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_report(path, report)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)

            events_path = Path(directory) / "events.json"
            events_path.write_text(json.dumps(events), encoding="utf-8")
            self.assertEqual(load_json_array(events_path, "events"), events)
```

- [ ] **Step 2: Run the test suite and verify it fails because the I/O functions do not exist**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python -m unittest test.vast_challenge_2026_mc2.test_count_event_sources -v
```

Expected: failure importing `load_json_array` or `write_report`.

- [ ] **Step 3: Implement strict JSON array loading, report writing, and the command-line entry point**

Append the following imports and functions to `count_event_sources.py`:

```python
import argparse
import json
from pathlib import Path


def load_json_array(path: Path, field: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Unable to load JSON from {path}: {error}") from error

    if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
        raise ValueError(f"Expected {path} to contain a top-level '{field}' array.")
    return payload[field]


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    project_directory = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--events",
        type=Path,
        default=project_directory / "MC2 data.json",
        help="Path to MC2 data JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--org-chart",
        type=Path,
        default=project_directory / "org_chart.json",
        help="Path to organization-chart JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("event_source_counts.json"),
        help="Path for the aggregate JSON report (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    events = load_json_array(arguments.events, "events")
    org_nodes = load_json_array(arguments.org_chart, "nodes")
    report = build_report(events, org_nodes, str(arguments.events), str(arguments.org_chart))
    if report["resolved_source_events"] + report["unresolved_source_events"] != report["total_events"]:
        raise RuntimeError("Source-event accounting does not match the total event count.")
    write_report(arguments.output, report)
    print(
        f"Wrote {arguments.output}: {report['total_events']} events, "
        f"{report['resolved_source_events']} resolved sources, "
        f"{report['unresolved_source_events']} unresolved sources."
    )


if __name__ == "__main__":
    main()
```

Move the `import argparse`, `import json`, and `from pathlib import Path` lines to the main import block rather than leaving duplicate imports. Keep `Any` imported from `typing`.

- [ ] **Step 4: Run the test suite and verify all tests pass**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python -m unittest test.vast_challenge_2026_mc2.test_count_event_sources -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 5: Commit the I/O and error-handling behavior**

```bash
git add VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/count_event_sources.py VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/test_count_event_sources.py
git commit -m "feat: write MC2 source count reports" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 3: Generate and Verify the Full Dataset Result

**Files:**
- Create: `VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/event_source_counts.json`

- [ ] **Step 1: Run the counter against the supplied MC2 dataset**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python test/vast_challenge_2026_mc2/count_event_sources.py
```

Expected: a `Wrote ...event_source_counts.json` message showing `185147` total events and zero or more unresolved events.

- [ ] **Step 2: Verify output JSON accounting and organization-node coverage**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python -c "import json; p='test/vast_challenge_2026_mc2/event_source_counts.json'; r=json.load(open(p, encoding='utf-8')); assert r['resolved_source_events'] + r['unresolved_source_events'] == r['total_events']; assert len(r['organization_nodes']) == 75; print({'total_events': r['total_events'], 'organization_nodes': len(r['organization_nodes']), 'unmapped_nodes': len(r['external_or_unmapped_nodes'])})"
```

Expected: a dictionary with `total_events: 185147`, `organization_nodes: 75`, and the number of unmapped literal source nodes.

- [ ] **Step 3: Run the complete test suite once more**

Run:

```bash
cd VAST_Challenge_2026_MC2 && python -m unittest test.vast_challenge_2026_mc2.test_count_event_sources -v
```

Expected: `Ran 2 tests ... OK`.

- [ ] **Step 4: Commit the generated aggregate result**

```bash
git add VAST_Challenge_2026_MC2/test/vast_challenge_2026_mc2/event_source_counts.json
git commit -m "data: add MC2 event source counts" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
