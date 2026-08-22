# VAST MC2 Flint ECharts Visualizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate six Flint-validated ECharts option JSON visualizations from the VAST Challenge 2026 MC2 event and organization datasets, then expose them through the existing AgentVAST Inspector artifacts.

**Architecture:** A focused Python module will normalize only the event rows needed to answer the six challenge questions, derive six small chart tables, and hold six Flint `ChartAssemblyInput` specifications. A chart-generation script will validate and compile those specifications through `flint-chart-mcp` to ECharts options, then merge each option into the established `artifacts_llm/*.analysis.json` shape as `visualization_type: "echarts"` and `echarts_chart`.

**Tech Stack:** Python standard library, unittest, VAST MC2 JSON data, Flint Chart MCP (`validate_chart`, `compile_chart`), ECharts, existing React Inspector artifact renderer.

---

## File Structure

- Create: `VAST_Challenge_2026_MC2/src/vast_flint_charts.py`
  - Reads VAST event and organization inputs.
  - Normalizes party IDs, timestamps, and nested event details.
  - Builds compact rows and Flint specs for Q1–Q6.
  - Contains no direct MCP calls so its derivations are deterministic and unit-testable.
- Create: `VAST_Challenge_2026_MC2/src/generate_flint_echarts.py`
  - Invokes the six Flint MCP validations/compilations through the approved client workflow.
  - Persists prepared chart tables, Flint input specs, validation records, and compiled ECharts options under `VAST_Challenge_2026_MC2/flint_visualizations/`.
  - Merges compiled options into the six target analysis artifacts.
- Create: `test/test_vast_flint_charts.py`
  - Covers normalization, derived-table invariants, source-evidence boundaries, and artifact merge payloads.
- Modify: `VAST_Challenge_2026_MC2/artifacts_llm/node_04_source_trace.analysis.json`
  - Q1 Sankey option.
- Modify: `VAST_Challenge_2026_MC2/artifacts_llm/node_09_instruction_outcome_comparison.analysis.json`
  - Q2 connected-scatter/timeline option.
- Modify: `VAST_Challenge_2026_MC2/artifacts_llm/node_12_john_all_posts_analysis.analysis.json`
  - Q3 Graph option.
- Modify: `VAST_Challenge_2026_MC2/artifacts_llm/node_20_content_and_creator_verification.analysis.json`
  - Q4 provenance Graph option.
- Modify: `VAST_Challenge_2026_MC2/artifacts_llm/node_24_system_change_recommendations.analysis.json`
  - Q5 grouped-bar historical comparison option.
- Modify: `VAST_Challenge_2026_MC2/artifacts_llm/node_25_final_investigation_summary.analysis.json`
  - Q6 intervention funnel option.
- Create: `VAST_Challenge_2026_MC2/flint_visualizations/`
  - Generated, reviewable JSON artifacts only: six `*.data.json`, six `*.flint.json`, six `*.validation.json`, and six `*.echarts.json` files.

### Task 1: Establish deterministic event extraction

**Files:**
- Create: `test/test_vast_flint_charts.py`
- Create: `VAST_Challenge_2026_MC2/src/vast_flint_charts.py`

- [ ] **Step 1: Write failing tests for party and timestamp normalization**

```python
from VAST_Challenge_2026_MC2.src.vast_flint_charts import (
    normalize_party,
    normalize_event,
)


def test_normalize_party_removes_system_prefixes_and_formats_names():
    assert normalize_party("Agent/person:john_windward") == "John Windward"
    assert normalize_party("person:emma_harbor") == "Emma Harbor"
    assert normalize_party("system:saidit") == "saidit"


def test_normalize_event_flattens_known_detail_fields():
    event = {
        "id": 373902,
        "short_name": "saidit_post",
        "parties": ["Agent/person:john_windward", "system:saidit"],
        "when": 0,
        "details": {"forum": "general", "content_source": "SwiftWren.txt", "content": ""},
    }
    row = normalize_event(event)
    assert row["event_id"] == 373902
    assert row["action"] == "saidit_post"
    assert row["actor"] == "John Windward"
    assert row["forum"] == "general"
    assert row["content_source"] == "SwiftWren.txt"
    assert row["content_length"] == 0
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
```

Expected: FAIL with `ModuleNotFoundError` or missing `vast_flint_charts` symbols.

- [ ] **Step 3: Implement the normalization boundary**

```python
# VAST_Challenge_2026_MC2/src/vast_flint_charts.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def normalize_party(value: str) -> str:
    raw = str(value).replace("Agent/", "")
    if raw.startswith("person:"):
        return " ".join(part.capitalize() for part in raw.split(":", 1)[1].split("_"))
    if raw.startswith("system:"):
        return raw.split(":", 1)[1]
    return raw


def normalize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    details = dict(event.get("details") or {})
    parties = [normalize_party(party) for party in event.get("parties", [])]
    content = details.get("content") or ""
    when = event.get("when")
    timestamp = datetime.fromtimestamp(when, tz=timezone.utc).isoformat() if isinstance(when, (int, float)) else ""
    return {
        "event_id": event.get("id"),
        "timestamp": timestamp,
        "unix_time": when,
        "action": event.get("short_name", "unknown"),
        "actor": parties[0] if parties else "Unknown",
        "participants": parties,
        "filename": details.get("filename") or details.get("path") or "",
        "content_source": details.get("content_source") or "",
        "forum": details.get("forum") or "",
        "content_length": len(str(content)),
        "details": details,
    }
```

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
```

Expected: PASS for both normalization tests.

- [ ] **Step 5: Commit the extraction boundary**

```bash
git add test/test_vast_flint_charts.py VAST_Challenge_2026_MC2/src/vast_flint_charts.py
git commit -m "feat: normalize VAST events for Flint charts"
```

### Task 2: Derive source-evidenced chart tables for Q1–Q4

**Files:**
- Modify: `test/test_vast_flint_charts.py`
- Modify: `VAST_Challenge_2026_MC2/src/vast_flint_charts.py`

- [ ] **Step 1: Write failing tests for Q1–Q4 tables**

```python
from pathlib import Path
from VAST_Challenge_2026_MC2.src.vast_flint_charts import build_question_tables


def test_question_tables_retain_target_route_and_provenance():
    tables = build_question_tables(Path("VAST_Challenge_2026_MC2"))

    assert any(row["content_source"] == "SwiftWren.txt" for row in tables["q1_event_chain"])
    assert any(row["action"] == "saidit_post" for row in tables["q2_timeline"])
    assert any(row["node_type"] == "person" and row["label"] == "John Windward" for row in tables["q3_system_nodes"])
    assert {row["source_file"] for row in tables["q4_content_provenance"]} >= {
        "HiddenOrca.txt", "MellowOtter.txt", "SwiftWren.txt"
    }


def test_content_provenance_does_not_claim_unavailable_text_semantics():
    tables = build_question_tables(Path("VAST_Challenge_2026_MC2"))
    assert all("semantic_interpretation" not in row for row in tables["q4_content_provenance"])
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
python -m unittest test.test_vast_flint_charts.VastFlintChartTests.test_question_tables_retain_target_route_and_provenance test.test_vast_flint_charts.VastFlintChartTests.test_content_provenance_does_not_claim_unavailable_text_semantics -v
```

Expected: FAIL because `build_question_tables` does not exist.

- [ ] **Step 3: Implement Q1–Q4 compact derivations**

```python
TARGET_SOURCES = ("HiddenOrca.txt", "MellowOtter.txt", "SwiftWren.txt")
TARGET_ACTIONS = {"create_file", "read_file", "queue_subordinate_task", "saidit_post_check", "saidit_post", "delete_file"}


def build_question_tables(challenge_dir: Path) -> dict[str, list[dict[str, Any]]]:
    events = _load_events(challenge_dir / "MC2 data.json")
    rows = [normalize_event(event) for event in events]
    relevant = [
        row for row in rows
        if row["action"] in TARGET_ACTIONS
        and any(source in _event_text(row) for source in TARGET_SOURCES)
    ]
    q1 = [row for row in relevant if row["content_source"] == "SwiftWren.txt" or "SwiftWren" in _event_text(row)]
    q2 = sorted(q1, key=lambda row: (row["unix_time"] is None, row["unix_time"]))
    q3_nodes, q3_edges = _build_system_graph(q2)
    q4 = _build_content_provenance(rows)
    return {
        "q1_event_chain": q1,
        "q2_timeline": q2,
        "q3_system_nodes": q3_nodes,
        "q3_system_edges": q3_edges,
        "q4_content_provenance": q4,
        **_build_historical_and_intervention_tables(rows),
    }
```

Implement `_load_events`, `_event_text`, `_build_system_graph`, and `_build_content_provenance` so every row is traceable to source event IDs and only observed fields are used.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
```

Expected: PASS; source table includes all three content-source files and no semantic claim field.

- [ ] **Step 5: Commit Q1–Q4 derivations**

```bash
git add test/test_vast_flint_charts.py VAST_Challenge_2026_MC2/src/vast_flint_charts.py
git commit -m "feat: derive VAST provenance chart tables"
```

### Task 3: Derive validated historical and intervention evidence for Q5–Q6

**Files:**
- Modify: `test/test_vast_flint_charts.py`
- Modify: `VAST_Challenge_2026_MC2/src/vast_flint_charts.py`

- [ ] **Step 1: Write failing tests for historical comparison and intervention evidence**

```python
def test_historical_and_intervention_tables_cover_all_three_observed_cases():
    tables = build_question_tables(Path("VAST_Challenge_2026_MC2"))
    historical = tables["q5_historical_comparison"]
    intervention = tables["q6_intervention_evidence"]

    assert {row["source_file"] for row in historical} == {
        "HiddenOrca.txt", "MellowOtter.txt", "SwiftWren.txt"
    }
    assert all(row["poster"] == "John Windward" for row in historical)
    assert {row["source_file"] for row in intervention} == {row["source_file"] for row in historical}
    assert all(row["intervention_point"] == "saidit_post validation gate" for row in intervention)


def test_historical_counts_are_nonnegative_and_recomputed_from_events():
    tables = build_question_tables(Path("VAST_Challenge_2026_MC2"))
    assert all(row["related_event_count"] >= 1 for row in tables["q5_historical_comparison"])
    assert all(row["cascade_event_count"] >= 0 for row in tables["q5_historical_comparison"])
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
python -m unittest test.test_vast_flint_charts.VastFlintChartTests.test_historical_and_intervention_tables_cover_all_three_observed_cases test.test_vast_flint_charts.VastFlintChartTests.test_historical_counts_are_nonnegative_and_recomputed_from_events -v
```

Expected: FAIL because Q5/Q6 tables are missing or incomplete.

- [ ] **Step 3: Implement per-source lifecycle aggregation**

```python
def _build_historical_and_intervention_tables(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    historical: list[dict[str, Any]] = []
    intervention: list[dict[str, Any]] = []
    for source in TARGET_SOURCES:
        source_rows = [row for row in rows if source in _event_text(row)]
        posts = [row for row in source_rows if row["action"] == "saidit_post"]
        if not posts:
            continue
        post = min(posts, key=lambda row: row["unix_time"] or float("inf"))
        deletes = [row for row in source_rows if row["action"] == "delete_file"]
        task_rows = [row for row in source_rows if row["action"] == "queue_subordinate_task"]
        historical.append({
            "source_file": source,
            "poster": post["actor"],
            "post_timestamp": post["timestamp"],
            "related_event_count": len(source_rows),
            "cascade_event_count": len(task_rows),
            "delete_event_count": len(deletes),
            "content_length": post["content_length"],
            "is_target_case": source == "SwiftWren.txt",
        })
        intervention.append({
            "source_file": source,
            "post_event_id": post["event_id"],
            "poster": post["actor"],
            "content_source_present": bool(post["content_source"]),
            "content_length": post["content_length"],
            "intervention_point": "saidit_post validation gate",
            "would_block_empty_source_post": bool(post["content_source"]) and post["content_length"] == 0,
        })
    return {
        "q5_historical_comparison": historical,
        "q6_intervention_evidence": intervention,
    }
```

- [ ] **Step 4: Run the test module and verify it passes**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
```

Expected: PASS; every historical count is recomputed from raw rows and all intervention cases converge at the publication gate.

- [ ] **Step 5: Commit Q5–Q6 derivations**

```bash
git add test/test_vast_flint_charts.py VAST_Challenge_2026_MC2/src/vast_flint_charts.py
git commit -m "feat: add VAST recurrence and intervention evidence"
```

### Task 4: Define the six Flint ChartAssemblyInput specifications

**Files:**
- Modify: `test/test_vast_flint_charts.py`
- Modify: `VAST_Challenge_2026_MC2/src/vast_flint_charts.py`

- [ ] **Step 1: Write failing tests for the complete spec set**

```python
from VAST_Challenge_2026_MC2.src.vast_flint_charts import build_flint_specs


def test_build_flint_specs_has_one_exact_chart_per_question():
    tables = build_question_tables(Path("VAST_Challenge_2026_MC2"))
    specs = build_flint_specs(tables)

    assert set(specs) == {"q1", "q2", "q3", "q4", "q5", "q6"}
    assert specs["q1"]["chart_spec"]["chartType"] == "Sankey"
    assert specs["q2"]["chart_spec"]["chartType"] == "Connected Scatter Plot"
    assert specs["q3"]["chart_spec"]["chartType"] == "Graph"
    assert specs["q4"]["chart_spec"]["chartType"] == "Graph"
    assert specs["q5"]["chart_spec"]["chartType"] == "Grouped Bar Chart"
    assert specs["q6"]["chart_spec"]["chartType"] == "Funnel"


def test_each_flint_spec_declares_semantic_types_for_encoded_fields():
    for spec in build_flint_specs(build_question_tables(Path("VAST_Challenge_2026_MC2"))).values():
        encoded = spec["chart_spec"]["encodings"]
        semantic_types = spec["semantic_types"]
        for channel in encoded.values():
            values = channel if isinstance(channel, list) else [channel]
            for encoding in values:
                field = encoding["field"] if isinstance(encoding, dict) else encoding
                assert field in semantic_types
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
python -m unittest test.test_vast_flint_charts.VastFlintChartTests.test_build_flint_specs_has_one_exact_chart_per_question test.test_vast_flint_charts.VastFlintChartTests.test_each_flint_spec_declares_semantic_types_for_encoded_fields -v
```

Expected: FAIL because `build_flint_specs` does not exist.

- [ ] **Step 3: Implement the six semantic specifications**

```python
def build_flint_specs(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    return {
        "q1": {
            "data": {"values": tables["q1_event_chain"]},
            "semantic_types": {"source": "Name", "target": "Name", "weight": "Count", "stage": "Category"},
            "chart_spec": {
                "chartType": "Sankey",
                "encodings": {"source": {"field": "source"}, "target": {"field": "target"}, "size": {"field": "weight"}, "color": {"field": "stage"}},
                "baseSize": {"width": 1040, "height": 560},
            },
        },
        "q2": {
            "data": {"values": tables["q2_timeline"]},
            "semantic_types": {"timestamp": "DateTime", "sequence": "Rank", "action": "Category", "actor": "Name"},
            "chart_spec": {
                "chartType": "Connected Scatter Plot",
                "encodings": {"x": {"field": "timestamp"}, "y": {"field": "sequence"}, "order": {"field": "sequence"}, "color": {"field": "action"}, "detail": {"field": "actor"}},
                "baseSize": {"width": 1040, "height": 520},
            },
        },
        "q3": {
            "data": {"values": tables["q3_system_edges"]},
            "semantic_types": {"source": "Name", "target": "Name", "relation": "Category", "weight": "Count"},
            "chart_spec": {
                "chartType": "Graph",
                "encodings": {"source": {"field": "source"}, "target": {"field": "target"}, "color": {"field": "relation"}, "size": {"field": "weight"}},
                "baseSize": {"width": 1120, "height": 680},
            },
        },
        "q4": {
            "data": {"values": tables["q4_content_provenance"]},
            "semantic_types": {"source": "Name", "target": "Name", "relation": "Category", "weight": "Count"},
            "chart_spec": {
                "chartType": "Graph",
                "encodings": {"source": {"field": "source"}, "target": {"field": "target"}, "color": {"field": "relation"}, "size": {"field": "weight"}},
                "baseSize": {"width": 960, "height": 560},
            },
        },
        "q5": {
            "data": {"values": _long_form_historical_metrics(tables["q5_historical_comparison"])},
            "semantic_types": {"source_file": "Category", "value": "Count", "metric": "Category"},
            "chart_spec": {
                "chartType": "Grouped Bar Chart",
                "encodings": {"x": {"field": "source_file"}, "y": {"field": "value"}, "group": {"field": "metric"}},
                "baseSize": {"width": 960, "height": 520},
            },
        },
        "q6": {
            "data": {"values": _funnel_rows(tables["q6_intervention_evidence"])},
            "semantic_types": {"stage": "Category", "case_count": "Count"},
            "chart_spec": {
                "chartType": "Funnel",
                "encodings": {"stage": {"field": "stage"}, "value": {"field": "case_count"}},
                "baseSize": {"width": 820, "height": 500},
            },
        },
    }
```

Before implementation, use `list_chart_types` to confirm the exact channel names accepted by `Sankey`, `Graph`, and `Funnel`; revise the mappings to match the returned Flint catalog rather than inventing unsupported channel names.

- [ ] **Step 4: Run the spec unit tests and then call Flint validation for all six specs**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
```

Expected: PASS.

Then call `mcp__flint-chart__validate_chart` once per specification. Expected: each result returns a valid chart; if a graph-only chart type has backend-specific schema requirements, adjust only the spec channels or prepared rows and repeat validation.

- [ ] **Step 5: Commit the Flint spec definitions**

```bash
git add test/test_vast_flint_charts.py VAST_Challenge_2026_MC2/src/vast_flint_charts.py
git commit -m "feat: define Flint specs for six VAST questions"
```

### Task 5: Persist generated data/specs and compile all six ECharts options

**Files:**
- Create: `VAST_Challenge_2026_MC2/src/generate_flint_echarts.py`
- Create: `VAST_Challenge_2026_MC2/flint_visualizations/q1_event_chain.data.json`
- Create: `VAST_Challenge_2026_MC2/flint_visualizations/q1_event_chain.flint.json`
- Create: `VAST_Challenge_2026_MC2/flint_visualizations/q1_event_chain.validation.json`
- Create: `VAST_Challenge_2026_MC2/flint_visualizations/q1_event_chain.echarts.json`
- Create: equivalent four files for Q2–Q6

- [ ] **Step 1: Write a failing persistence test**

```python
from tempfile import TemporaryDirectory
from VAST_Challenge_2026_MC2.src.generate_flint_echarts import write_chart_inputs


def test_write_chart_inputs_creates_data_and_flint_specs_for_six_questions():
    with TemporaryDirectory() as tmp:
        written = write_chart_inputs(Path("VAST_Challenge_2026_MC2"), Path(tmp))
    assert set(written) == {"q1", "q2", "q3", "q4", "q5", "q6"}
    assert all(paths["data"].exists() and paths["spec"].exists() for paths in written.values())
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python -m unittest test.test_vast_flint_charts.VastFlintChartTests.test_write_chart_inputs_creates_data_and_flint_specs_for_six_questions -v
```

Expected: FAIL with `ModuleNotFoundError` for `generate_flint_echarts`.

- [ ] **Step 3: Implement chart input persistence**

```python
# VAST_Challenge_2026_MC2/src/generate_flint_echarts.py
import json
from pathlib import Path
from typing import Any

from VAST_Challenge_2026_MC2.src.vast_flint_charts import build_flint_specs, build_question_tables

CHART_FILES = {
    "q1": "q1_event_chain",
    "q2": "q2_detailed_timeline",
    "q3": "q3_system_overview",
    "q4": "q4_content_provenance",
    "q5": "q5_historic_recurrence",
    "q6": "q6_intervention_point",
}


def write_chart_inputs(challenge_dir: Path, output_dir: Path) -> dict[str, dict[str, Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tables = build_question_tables(challenge_dir)
    specs = build_flint_specs(tables)
    written: dict[str, dict[str, Path]] = {}
    for question, stem in CHART_FILES.items():
        spec = specs[question]
        data_path = output_dir / f"{stem}.data.json"
        spec_path = output_dir / f"{stem}.flint.json"
        data_path.write_text(json.dumps(spec["data"]["values"], ensure_ascii=False, indent=2), encoding="utf-8")
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        written[question] = {"data": data_path, "spec": spec_path}
    return written
```

- [ ] **Step 4: Run the persistence test and generate inputs**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
python -m VAST_Challenge_2026_MC2.src.generate_flint_echarts
```

Expected: all unit tests PASS; output lists data/spec paths for Q1–Q6.

- [ ] **Step 5: Validate and compile through Flint MCP**

For every generated `*.flint.json`:

1. Call `mcp__flint-chart__validate_chart` with the full saved input.
2. Save the exact validation response as `*.validation.json`.
3. Call `mcp__flint-chart__compile_chart` with `backend: "echarts"`.
4. Save the returned ECharts option object as `*.echarts.json`.

Expected: six valid Flint specs and six JSON ECharts options. Do not hand-edit the compiled ECharts option objects.

- [ ] **Step 6: Commit generated Flint inputs and compiled results**

```bash
git add VAST_Challenge_2026_MC2/src/generate_flint_echarts.py VAST_Challenge_2026_MC2/flint_visualizations test/test_vast_flint_charts.py
git commit -m "feat: compile VAST Flint charts to ECharts"
```

### Task 6: Merge options into Inspector artifacts and verify the frontend contract

**Files:**
- Modify: `test/test_vast_flint_charts.py`
- Modify: `VAST_Challenge_2026_MC2/src/generate_flint_echarts.py`
- Modify: six specified `VAST_Challenge_2026_MC2/artifacts_llm/*.analysis.json` files

- [ ] **Step 1: Write a failing artifact-merge test**

```python
from VAST_Challenge_2026_MC2.src.generate_flint_echarts import merge_compiled_options


def test_merge_compiled_options_sets_inspector_echarts_contract():
    with TemporaryDirectory() as tmp:
        artifact_dir = Path(tmp) / "artifacts"
        artifact_dir.mkdir()
        for filename in {
            "node_04_source_trace.analysis.json",
            "node_09_instruction_outcome_comparison.analysis.json",
            "node_12_john_all_posts_analysis.analysis.json",
            "node_20_content_and_creator_verification.analysis.json",
            "node_24_system_change_recommendations.analysis.json",
            "node_25_final_investigation_summary.analysis.json",
        }:
            (artifact_dir / filename).write_text("{}", encoding="utf-8")
        merge_compiled_options(artifact_dir, {key: {"series": []} for key in CHART_FILES})
        q1 = json.loads((artifact_dir / "node_04_source_trace.analysis.json").read_text(encoding="utf-8"))
    assert q1["visualization_type"] == "echarts"
    assert q1["echarts_chart"] == {"series": []}
    assert q1["visualization_title"].startswith("Q1")
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python -m unittest test.test_vast_flint_charts.VastFlintChartTests.test_merge_compiled_options_sets_inspector_echarts_contract -v
```

Expected: FAIL because `merge_compiled_options` does not exist.

- [ ] **Step 3: Implement lossless merge behavior**

```python
ARTIFACT_TARGETS = {
    "q1": ("node_04_source_trace.analysis.json", "Q1 · How was the anomalous SaidIT post made?"),
    "q2": ("node_09_instruction_outcome_comparison.analysis.json", "Q2 · Exact event chain"),
    "q3": ("node_12_john_all_posts_analysis.analysis.json", "Q3 · System overview"),
    "q4": ("node_20_content_and_creator_verification.analysis.json", "Q4 · Content origin evidence"),
    "q5": ("node_24_system_change_recommendations.analysis.json", "Q5 · Historic recurrence"),
    "q6": ("node_25_final_investigation_summary.analysis.json", "Q6 · Publication-gate intervention"),
}


def merge_compiled_options(artifact_dir: Path, options: dict[str, dict[str, Any]]) -> None:
    for question, (filename, title) in ARTIFACT_TARGETS.items():
        path = artifact_dir / filename
        artifact = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        artifact.update({
            "visualization_title": title,
            "visualization_summary": "Flint-compiled ECharts visualization generated from VAST MC2 source evidence.",
            "visualization_type": "echarts",
            "echarts_chart": options[question],
        })
        path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
```

The merge must preserve all pre-existing analysis fields, including `algorithm_purpose`, `algorithm_logic`, `data_flow`, `key_findings`, and any current HTML `visualization` content. The new ECharts option becomes the Inspector’s preferred render path.

- [ ] **Step 4: Run tests and merge the six real compiled options**

Run:

```bash
python -m unittest test.test_vast_flint_charts -v
python -m VAST_Challenge_2026_MC2.src.generate_flint_echarts --merge-artifacts
npm --prefix frontend run build
```

Expected: Python tests PASS and Vite build completes successfully. A Vite chunk-size warning is acceptable; TypeScript errors are not.

- [ ] **Step 5: Inspect generated artifact contract**

Run:

```bash
python -c "import json; from pathlib import Path; paths=Path('VAST_Challenge_2026_MC2/artifacts_llm').glob('*.analysis.json'); matches=[p for p in paths if json.loads(p.read_text(encoding='utf-8')).get('visualization_type') == 'echarts']; print('\n'.join(str(p) for p in matches))"
```

Expected: exactly the six Q1–Q6 target artifact paths are printed, each containing an object at `echarts_chart`.

- [ ] **Step 6: Commit artifact integration**

```bash
git add VAST_Challenge_2026_MC2/src/generate_flint_echarts.py VAST_Challenge_2026_MC2/artifacts_llm VAST_Challenge_2026_MC2/flint_visualizations test/test_vast_flint_charts.py
git commit -m "feat: expose Flint ECharts charts in VAST artifacts"
```

### Task 7: End-to-end verification and evidence review

**Files:**
- Verify only; no expected source modifications.

- [ ] **Step 1: Run the full relevant Python test suite**

Run:

```bash
python -m unittest test.test_vast_core_visualizations test.test_vast_full_chain_189 test.test_vast_flint_charts -v
```

Expected: PASS. Existing HTML visualizations remain covered while the new ECharts generation is tested separately.

- [ ] **Step 2: Review all six Flint validation records**

Run:

```bash
python -c "import json; from pathlib import Path; files=sorted(Path('VAST_Challenge_2026_MC2/flint_visualizations').glob('*.validation.json')); assert len(files) == 6, files; [print(p.name, json.loads(p.read_text(encoding='utf-8'))) for p in files]"
```

Expected: six successful validation records with no unsupported-chart-type or missing-channel error.

- [ ] **Step 3: Build the frontend**

Run:

```bash
npm --prefix frontend run build
```

Expected: `✓ built` output; only the known bundle-size warning may remain.

- [ ] **Step 4: Smoke-test the UI manually**

Run the frontend using the project’s documented start command, load the VAST session/artifacts, and select each of the six target nodes in Inspector. Verify the `visualization` tab appears and ECharts renders all six charts without a blank panel, JSON parse error, or console runtime error.

- [ ] **Step 5: Commit only if verification required a correction**

```bash
git status --short
git add <corrected-files>
git commit -m "fix: correct Flint visualization verification issue"
```

Do not commit if no verification correction was made.

## Plan Self-Review

- **Coverage:** Tasks 1–3 derive source-grounded data for all six VAST questions; Task 4 creates the six approved Flint chart types; Task 5 validates and compiles them to ECharts; Task 6 attaches the output to the exact Inspector artifact contract; Task 7 verifies source, compilation, frontend build, and UI rendering.
- **Evidence boundary:** Q4 explicitly limits itself to file/post provenance and empty-body evidence; it does not infer semantic meaning from absent post content.
- **Consistency:** `q1` through `q6` identifiers are used consistently in generated filenames, compiled options, and artifact merge mappings.
- **Scope:** Existing HTML report visualizations remain intact; this plan adds parallel ECharts chart data rather than removing or redesigning established frontend behavior.
