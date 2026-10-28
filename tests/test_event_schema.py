import json
from copy import deepcopy

import pytest

from agentvast.observer.event_schema import compact_event, expand_event
from agentvast.observer.store import create_session, iter_jsonl
from agentvast.observer.trace_builder import build_observer_trace, load_observer_trace
from agentvast.observer.transcript_reader import snapshot_transcript
from agentvast.semantic.pipeline import build_key_information_events, run_semantic_workflow


def derive_records(tmp_path, records):
    source = tmp_path / "source.jsonl"
    original = "".join(json.dumps(record) + "\n" for record in records)
    source.write_text(original)
    root = tmp_path / "observations"
    create_session("event-fixture", tmp_path, root)
    snapshot_transcript("event-fixture", source, root, attempts=1, delay=0)
    build_observer_trace("event-fixture", str(root))
    assert (root / "event-fixture/transcript/transcript.jsonl").read_text() == original
    compact = list(iter_jsonl(root / "event-fixture/derived/events.jsonl"))
    loaded = load_observer_trace("event-fixture", str(root))
    return root, compact, loaded


def transcript_records(tool="Read", with_result=True):
    records = [
        {
            "type": "user",
            "uuid": "prompt",
            "origin": {"kind": "human"},
            "message": {"content": "检查数据"},
            "timestamp": "2026-01-01T00:00:00Z",
        },
        {
            "type": "assistant",
            "uuid": "request",
            "parentUuid": "prompt",
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {
                "id": "response",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": tool,
                        "input": (
                            {"command": "python analyze.py"}
                            if tool == "Bash"
                            else {"file_path": "data.csv"}
                        ),
                    }
                ],
            },
        },
    ]
    if with_result:
        records.append(
            {
                "type": "user",
                "uuid": "result",
                "parentUuid": "request",
                "timestamp": "2026-01-01T00:00:02Z",
                "toolUseResult": {"durationMs": 12, "exitCode": 0},
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-1",
                            "content": "2 rows",
                            "is_error": False,
                        }
                    ]
                },
            }
        )
    return records


def test_compact_events_preserve_relationships_and_consumer_aliases(tmp_path):
    root, events, loaded = derive_records(tmp_path, transcript_records("Bash"))
    event = next(item for item in events if item["event_type"] == "command_execution")
    assert (
        not {
            "timestamp",
            "ended_at",
            "turn_id",
            "response_id",
            "tool_use_id",
            "source_lines",
            "evidence",
            "message_uuid",
            "parent_uuid",
            "event_class",
        }
        & event.keys()
    )
    assert event["scope"]["tool_use_id"] == "tool-1"
    assert event["time"]["duration_ms"] == 12
    assert event["provenance"]["source_lines"] == [2, 3]
    assert event["payload"]["input"]["command"] == "python analyze.py"
    assert (
        not {"command", "duration_ms", "batch_response_id", "observed_elapsed_ms"}
        & event["payload"].keys()
    )
    restored = next(item for item in loaded["events"] if item["event_id"] == event["event_id"])
    assert restored["tool_use_id"] == "tool-1"
    assert restored["payload"]["command"] == "python analyze.py"
    assert restored["source_lines"] == [2, 3]
    assert restored["event_class"] == "execution"
    ids = {item["event_id"] for item in events}
    assert all(item["from"] in ids and item["to"] in ids for item in loaded["relations"])
    assert any(
        item["type"] == "invokes" and item["to"] == event["event_id"]
        for item in loaded["relations"]
    )
    stored_trace = json.loads((root / "event-fixture/derived/observer_trace.json").read_text())
    assert stored_trace["events"] == events
    # Rules-only processing consumes the compact event stream through the same adapter.
    workflow = run_semantic_workflow("event-fixture", str(root), rules_only=True)
    assert workflow["validation"]["valid"]
    assert event["event_id"] in {
        eid for node in workflow["semantic_nodes"] for eid in node["event_ids"]
    }


def test_identical_tool_records_keep_all_sources_without_repeating_content(tmp_path):
    records = transcript_records()
    records.insert(2, {**deepcopy(records[1]), "uuid": "request-copy"})
    records.append({**deepcopy(records[-1]), "uuid": "result-copy"})
    root, events, loaded = derive_records(tmp_path, records)
    tools = [event for event in events if event["event_type"] == "tool_execution"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["status"] == "success"
    assert tool["payload"]["output"] == "2 rows"
    assert "alternate_results" not in tool["payload"]
    assert tool["provenance"]["source_lines"] == [2, 3, 4, 5]
    assert {item["block_index"] for item in tool["provenance"]["source_blocks"]} == {0}
    assert loaded["diagnostics"]["duplicate_tool_result_ids"] == ["tool-1"]
    assert loaded["diagnostics"]["conflicting_tool_result_ids"] == []
    before = [(event["event_id"], event["scope"]) for event in events]
    build_observer_trace("event-fixture", str(root))
    after = list(iter_jsonl(root / "event-fixture/derived/events.jsonl"))
    assert before == [(event["event_id"], event["scope"]) for event in after]


@pytest.mark.parametrize("request_conflict", [False, True])
def test_different_records_remain_separate_evidence_not_concatenated(tmp_path, request_conflict):
    records = transcript_records()
    duplicate = deepcopy(records[1 if request_conflict else 2])
    duplicate["uuid"] = "different"
    if request_conflict:
        duplicate["message"]["content"][0]["input"]["file_path"] = "other.csv"
        records.insert(2, duplicate)
    else:
        duplicate["message"]["content"][0]["content"] = "3 rows"
        records.append(duplicate)
    _, events, loaded = derive_records(tmp_path, records)
    tool = next(event for event in events if event["event_type"] == "tool_execution")
    assert tool["status"] == "conflicting"
    assert tool["time"]["duration_ms"] is None
    flag = "request_conflict" if request_conflict else "result_conflict"
    alternatives = "alternate_requests" if request_conflict else "alternate_results"
    assert tool["payload"][flag]
    assert len(tool["payload"][alternatives]) == 1
    if request_conflict:
        assert tool["payload"]["input"]["file_path"] == "data.csv"
        assert tool["payload"][alternatives][0]["input"]["file_path"] == "other.csv"
    else:
        assert tool["payload"]["output"] == "3 rows"
        assert tool["payload"][alternatives][0]["output"] == "2 rows"
    projected = next(
        event
        for event in build_key_information_events(loaded)
        if event["event_id"] == tool["event_id"]
    )
    assert projected["tool"][flag]
    assert projected["tool"][alternatives]


def test_missing_result_does_not_claim_timeout_or_separate_output_streams(tmp_path):
    _, events, _ = derive_records(tmp_path, transcript_records("Bash", with_result=False))
    command = next(event for event in events if event["event_type"] == "command_execution")
    assert command["status"] == "incomplete"
    assert command["payload"]["timed_out"] is None
    assert command["payload"]["stdout"] is None
    assert command["payload"]["stderr"] is None


def test_trace_api_expands_compact_facts_for_existing_pages(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from agentvast.web_server import create_app

    root, events, _ = derive_records(tmp_path, transcript_records("Bash"))
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/api/observations/event-fixture/trace")
        assert response.status_code == 200
        event = next(
            item for item in response.json()["events"] if item["event_type"] == "command_execution"
        )
        assert event["event_id"] in {item["event_id"] for item in events}
        assert event["tool_use_id"] == "tool-1"
        assert event["source_lines"] == [2, 3]
        assert event["payload"]["command"] == "python analyze.py"
        assert event["payload"]["output"] == "2 rows"


def test_explicit_streams_and_timeout_keep_their_evidence(tmp_path):
    records = transcript_records("Bash")
    records[-1]["toolUseResult"].update(stdout="out", stderr="err", timedOut=True)
    _, events, loaded = derive_records(tmp_path, records)
    command = next(event for event in events if event["event_type"] == "command_execution")
    assert command["payload"]["output"] == "2 rows"
    assert command["payload"]["stdout"] == "out"
    assert command["payload"]["stderr"] == "err"
    assert command["payload"]["timed_out"] is True
    projection = next(
        event
        for event in build_key_information_events(loaded)
        if event["event_id"] == command["event_id"]
    )
    assert projection["command"]["output"]["text"] == "2 rows"
    assert projection["command"]["stdout"]["text"] == "out"


@pytest.mark.parametrize(
    "event_type",
    [
        "user_prompt",
        "model_response",
        "tool_execution",
        "command_execution",
        "subagent_result",
        "control_event",
    ],
)
def test_compaction_is_idempotent_and_does_not_mutate_source(event_type):
    value = {
        "event_id": "event-1",
        "event_type": event_type,
        "event_subtype": "text",
        "turn_id": "turn-1",
        "status": "observed",
        "timestamp": "start",
        "ended_at": "end",
        "source_lines": [1],
        "payload": {"content": "test"},
        "message_uuid": "uuid-1",
    }
    original = deepcopy(value)
    compact = compact_event(value)
    assert value == original
    assert compact_event(expand_event(compact)) == compact
    restored = expand_event(compact)
    assert restored["event_id"] == value["event_id"]
    assert restored["turn_id"] == "turn-1"
    assert restored["source_lines"] == [1]
    assert restored["payload"]["content"] == "test"


@pytest.mark.parametrize("tool_input", [[], "malformed input"])
def test_non_object_command_input_is_preserved_as_evidence(tool_input):
    event = {
        "event_id": "event-1",
        "event_type": "command_execution",
        "payload": {"name": "Bash", "input": tool_input, "output": None},
    }
    compact = compact_event(event)
    assert compact["payload"]["input"] == tool_input
    assert expand_event(compact)["payload"]["command"] is None
