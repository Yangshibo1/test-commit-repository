# Three TXT Posting Chains Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate one normalized JSON dataset containing all complete observable event chains for the three Saidit posts published from TXT files.

**Architecture:** A standalone extractor in `test/` reads the original MC2 events, selects events with direct references to each TXT file or its paired instruction file, and annotates each retained event without changing its source fields. It creates chronological per-chain event lists and a merged chronological event list, while a focused unittest validates exact source coverage and metadata.

**Tech Stack:** Python standard library (`json`, `pathlib`, `copy`, `unittest`)

---

## File structure

- Create: `test/extract_three_txt_posting_chains_dataset.py` — extraction, event annotation, dataset serialization, and CLI entry point.
- Create: `test/test_extract_three_txt_posting_chains_dataset.py` — source-to-dataset coverage validation using `unittest`.
- Create at runtime: `result/three_txt_posting_chains_dataset.json` — generated normalized dataset.

### Task 1: Create direct-reference extraction primitives

**Files:**
- Create: `test/extract_three_txt_posting_chains_dataset.py`
- Test: `test/test_extract_three_txt_posting_chains_dataset.py`

- [ ] **Step 1: Write the failing test for direct event selection**

```python
import unittest
from pathlib import Path

from extract_three_txt_posting_chains_dataset import find_direct_file_events


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test and confirm it fails because the module is missing**

Run: `python -m unittest test.test_extract_three_txt_posting_chains_dataset.DirectFileEventSelectionTests.test_selects_all_supported_direct_reference_fields -v`

Expected: `ModuleNotFoundError: No module named 'extract_three_txt_posting_chains_dataset'`.

- [ ] **Step 3: Implement direct-reference selection**

```python
"""Build one normalized dataset for the three TXT-based Saidit posting chains."""
from pathlib import Path
from typing import Any, Dict, Iterable, List


PROJECT_ROOT = Path(__file__).parent.parent


def event_reference_text(event: Dict[str, Any]) -> str:
    """Return all source fields that can directly reference a tracked file."""
    details = event.get("details") or {}
    args = details.get("args") or {}
    return "\n".join(
        str(value)
        for value in (
            details.get("target", ""),
            args.get("path", ""),
            details.get("task", ""),
            details.get("content_source", ""),
        )
    )


def find_direct_file_events(
    events: Iterable[Dict[str, Any]],
    primary_file: str,
    instruction_file: str,
) -> List[Dict[str, Any]]:
    """Select source events that directly reference either chain file."""
    selected = []
    for event in events:
        reference_text = event_reference_text(event)
        if primary_file in reference_text or instruction_file in reference_text:
            selected.append(event)
    return selected
```

- [ ] **Step 4: Run the direct-selection test and confirm it passes**

Run: `python -m unittest test.test_extract_three_txt_posting_chains_dataset.DirectFileEventSelectionTests.test_selects_all_supported_direct_reference_fields -v`

Expected: `OK`.

- [ ] **Step 5: Commit the extraction primitive and its test**

```bash
git add test/extract_three_txt_posting_chains_dataset.py test/test_extract_three_txt_posting_chains_dataset.py
git commit -m "feat: select direct TXT chain events"
```

### Task 2: Normalize events and assemble the dataset

**Files:**
- Modify: `test/extract_three_txt_posting_chains_dataset.py`
- Modify: `test/test_extract_three_txt_posting_chains_dataset.py`

- [ ] **Step 1: Write failing tests for annotations, sorting, and total coverage**

```python
from extract_three_txt_posting_chains_dataset import build_dataset


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
```

- [ ] **Step 2: Run the assembly test and confirm it fails because `build_dataset` is undefined**

Run: `python -m unittest test.test_extract_three_txt_posting_chains_dataset.DatasetAssemblyTests.test_builds_annotated_chains_and_merged_chronology -v`

Expected: `ImportError` identifying that `build_dataset` cannot be imported.

- [ ] **Step 3: Implement event annotation and dataset construction**

```python
import copy


CHAIN_POST_IDS = {
    "SwiftWren.txt": 373902,
    "HiddenOrca.txt": 27290,
    "MellowOtter.txt": 98591,
}


def instruction_filename(primary_file: str) -> str:
    return f"{primary_file.removesuffix('.txt')}_further_instructions.md"


def lifecycle_stage(event: Dict[str, Any]) -> str:
    return {
        "create_file": "create",
        "read_file": "read",
        "queue_subordinate_task": "delegate",
        "saidit_post": "post",
        "delete_file": "delete",
    }.get(event.get("short_name"), "other")


def related_filename(event: Dict[str, Any], primary_file: str, instruction_file: str) -> str:
    reference_text = event_reference_text(event)
    if instruction_file in reference_text:
        return instruction_file
    return primary_file


def annotate_event(
    event: Dict[str, Any],
    primary_file: str,
    post_id: int,
) -> Dict[str, Any]:
    """Copy one source event and attach dataset-specific chain fields."""
    annotated = copy.deepcopy(event)
    instruction_file = instruction_filename(primary_file)
    annotated["chain_file"] = primary_file
    annotated["related_file"] = related_filename(event, primary_file, instruction_file)
    annotated["lifecycle_stage"] = lifecycle_stage(event)
    annotated["is_post_event"] = event.get("id") == post_id
    return annotated


def build_dataset(events: List[Dict[str, Any]], post_ids: Dict[str, int] = CHAIN_POST_IDS) -> Dict[str, Any]:
    """Build all annotated per-file chains and a merged chronological view."""
    chains = {}
    merged_events = []

    for primary_file, post_id in post_ids.items():
        instruction_file = instruction_filename(primary_file)
        chain_events = [
            annotate_event(event, primary_file, post_id)
            for event in find_direct_file_events(events, primary_file, instruction_file)
        ]
        chain_events.sort(key=lambda event: (event.get("when", 0), event.get("id", 0)))
        chains[primary_file] = {
            "post_id": post_id,
            "instruction_file": instruction_file,
            "events": chain_events,
        }
        merged_events.extend(chain_events)

    merged_events.sort(key=lambda event: (event.get("when", 0), event.get("id", 0)))
    return {
        "metadata": {
            "description": "Complete observable lifecycle chains for all TXT-based Saidit posts",
            "source": "VAST_Challenge_2026_MC2/MC2 data.json",
            "chain_count": len(chains),
            "total_events": len(merged_events),
        },
        "chains": chains,
        "all_events_chronological": merged_events,
    }
```

- [ ] **Step 4: Run both unit tests and confirm they pass**

Run: `python -m unittest test.test_extract_three_txt_posting_chains_dataset -v`

Expected: both tests pass with `OK`.

- [ ] **Step 5: Commit the dataset assembly behavior**

```bash
git add test/extract_three_txt_posting_chains_dataset.py test/test_extract_three_txt_posting_chains_dataset.py
git commit -m "feat: build normalized TXT posting chains dataset"
```

### Task 3: Add the CLI writer and validate the real MC2 extraction

**Files:**
- Modify: `test/extract_three_txt_posting_chains_dataset.py`
- Modify: `test/test_extract_three_txt_posting_chains_dataset.py`
- Create at runtime: `result/three_txt_posting_chains_dataset.json`

- [ ] **Step 1: Write the failing source-coverage integration test**

```python
from extract_three_txt_posting_chains_dataset import (
    CHAIN_POST_IDS,
    PROJECT_ROOT,
    build_dataset,
    load_mc2_events,
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
            self.assertEqual([event["id"] for event in post_events], [CHAIN_POST_IDS[chain_file]])
            self.assertEqual(
                sum(event["lifecycle_stage"] == "delete" for event in chain["events"]),
                2,
            )
```

- [ ] **Step 2: Run the source-coverage test and confirm it fails because `load_mc2_events` is undefined**

Run: `python -m unittest test.test_extract_three_txt_posting_chains_dataset.SourceCoverageTests.test_real_source_has_complete_expected_chain_coverage -v`

Expected: `ImportError` identifying that `load_mc2_events` cannot be imported.

- [ ] **Step 3: Implement source loading, output writing, and the script entry point**

```python
import json


def load_mc2_events() -> List[Dict[str, Any]]:
    """Load the original MC2 event collection."""
    source_path = PROJECT_ROOT / "VAST_Challenge_2026_MC2" / "MC2 data.json"
    with source_path.open(encoding="utf-8") as source_file:
        return json.load(source_file)["events"]


def write_dataset(dataset: Dict[str, Any]) -> Path:
    """Write the normalized dataset to the result directory."""
    output_path = PROJECT_ROOT / "result" / "three_txt_posting_chains_dataset.json"
    with output_path.open("w", encoding="utf-8") as output_file:
        json.dump(dataset, output_file, ensure_ascii=False, indent=2)
    return output_path


def main() -> None:
    dataset = build_dataset(load_mc2_events())
    output_path = write_dataset(dataset)
    print(f"Saved {dataset['metadata']['total_events']} events to: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full unit suite and confirm all source-coverage assertions pass**

Run: `python -m unittest test.test_extract_three_txt_posting_chains_dataset -v`

Expected: three tests pass with `OK`.

- [ ] **Step 5: Generate the real output dataset**

Run: `PYTHONIOENCODING=utf-8 python test/extract_three_txt_posting_chains_dataset.py`

Expected: `Saved 248 events to: ...result/three_txt_posting_chains_dataset.json`.

- [ ] **Step 6: Inspect the generated JSON through its public file surface**

Run:

```bash
python - <<'PY'
import json
from pathlib import Path
path = Path("result/three_txt_posting_chains_dataset.json")
data = json.loads(path.read_text(encoding="utf-8"))
print(data["metadata"])
print({name: len(chain["events"]) for name, chain in data["chains"].items()})
print([event["id"] for event in data["all_events_chronological"] if event["is_post_event"]])
PY
```

Expected output:

```text
{'description': 'Complete observable lifecycle chains for all TXT-based Saidit posts', 'source': 'VAST_Challenge_2026_MC2/MC2 data.json', 'chain_count': 3, 'total_events': 248}
{'SwiftWren.txt': 191, 'HiddenOrca.txt': 42, 'MellowOtter.txt': 15}
[27290, 98591, 373902]
```

- [ ] **Step 7: Commit the extractor, test, and generated dataset**

```bash
git add test/extract_three_txt_posting_chains_dataset.py test/test_extract_three_txt_posting_chains_dataset.py result/three_txt_posting_chains_dataset.json
git commit -m "feat: export complete TXT Saidit posting chains"
```
