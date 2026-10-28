from copy import deepcopy
import json
import time

import pytest

from agentvast.observer.store import create_session, iter_jsonl
from agentvast.observer.trace_builder import build_observer_trace, load_observer_trace
from agentvast.observer.transcript_reader import snapshot_transcript
from agentvast.semantic.event_workflow import (
    EventWorkflowError,
    run_event_workflow,
    validate_relations,
    load_event_workflow,
)
from agentvast.semantic.provider import SemanticConfig, SemanticProvider, SemanticProviderError


@pytest.fixture
def event_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTVAST_EVENT_BATCH_SIZE", "3")
    root = tmp_path / "observations"
    session = "event-test"
    records = [
        {
            "type": "user",
            "uuid": "user",
            "origin": {"kind": "human"},
            "message": {"content": "分析 sales.csv 缺失值并汇报"},
        },
        {
            "type": "assistant",
            "uuid": "request",
            "parentUuid": "user",
            "message": {
                "id": "response",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "read",
                        "name": "Read",
                        "input": {"file_path": "sales.csv"},
                    },
                    {
                        "type": "tool_use",
                        "id": "command",
                        "name": "Bash",
                        "input": {"command": "python analyze.py sales.csv"},
                    },
                    {
                        "type": "tool_use",
                        "id": "agent",
                        "name": "Agent",
                        "input": {"description": "复核缺失值"},
                    },
                ],
            },
        },
        {
            "type": "user",
            "uuid": "r1",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "read", "content": "5 rows"}]
            },
        },
        {
            "type": "user",
            "uuid": "r2",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "command", "content": "missing_rate=40%"}
                ]
            },
        },
        {
            "type": "user",
            "uuid": "r3",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "agent", "content": "started"}]
            },
        },
        {
            "type": "user",
            "uuid": "task",
            "origin": {"kind": "task-notification"},
            "message": {
                "content": "<task-notification><task-id>task-1</task-id><tool-use-id>agent</tool-use-id><status>completed</status><result>confirmed 40%</result></task-notification>"
            },
        },
        {
            "type": "assistant",
            "uuid": "final",
            "message": {
                "id": "final-response",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "缺失率 40%，需要清洗。"}],
            },
        },
        {
            "type": "system",
            "uuid": "control",
            "subtype": "context_compacted",
            "content": "Context compacted",
        },
    ]
    source = tmp_path / "transcript.jsonl"
    source.write_text("".join(json.dumps(record) + "\n" for record in records))
    create_session(session, tmp_path, root)
    snapshot_transcript(session, source, root, attempts=1, delay=0)
    build_observer_trace(session, str(root))
    trace = load_observer_trace(session, str(root))
    return session, root, trace


class FixtureProvider:
    def __init__(self, trace, fail_stage=None):
        self.config = SemanticConfig(
            "https://semantic.invalid",
            "test",
            "gpt-6.1-sol",
            annotation_concurrency=3,
            reasoning_effort="medium",
        )
        self.events = {event["event_id"]: event for event in trace["events"]}
        self.calls = []
        self.fail_stage = fail_stage

    def complete(self, prompt, stage, json_schema=None):
        self.calls.append(stage)
        if self.fail_stage and self.fail_stage in stage:
            raise SemanticProviderError("fixture interruption", retryable=True)
        source = json.loads(prompt.split("SOURCE:\n", 1)[1].split("\nJSON_SCHEMA:", 1)[0])
        if "annotation" in stage:
            # Out-of-order batches exercise deterministic assembly and checkpoints.
            time.sleep(0.01 if stage.endswith("001") else 0.02)
            summaries = []
            for item in source["events"]:
                event = self.events[item["event_id"]]
                summaries.append(
                    {
                        "event_id": event["event_id"],
                        "title": event["title"],
                        "behavior_summary": "描述已记录的行为",
                        "objects": [],
                        "inputs": [],
                        "outputs": [],
                        "fact_basis": "unknown",
                        "evidence_refs": [
                            {
                                "event_id": event["event_id"],
                                "field": "/status",
                                "quote": event["status"],
                            }
                        ],
                        "uncertainty": [],
                        "confidence": "medium",
                    }
                )
            return {"events": summaries}
        if stage == "event_relations":
            command = next(
                event
                for event in self.events.values()
                if event["event_type"] == "command_execution"
            )
            final = next(
                event for event in self.events.values() if event["payload"].get("is_final")
            )
            return {
                "relations": [
                    {
                        "from": command["event_id"],
                        "to": final["event_id"],
                        "type": "SUPPORTS_RESULT",
                        "label": "支撑缺失率结论",
                        "explanation": "命令输出与最终报告一致",
                        "connection_basis": "最终报告引用命令输出的 40% 缺失率",
                        "limitations": [],
                        "context_evidence_refs": [],
                        "confidence": "medium",
                        "evidence_refs": [
                            {
                                "event_id": command["event_id"],
                                "field": "/payload/output",
                                "quote": "40%",
                            },
                            {
                                "event_id": final["event_id"],
                                "field": "/payload/text",
                                "quote": "40%",
                            },
                        ],
                    }
                ]
            }
        if stage == "event_relation_review":
            return {
                "reviews": [
                    {
                        "relation_id": relation["relation_id"],
                        "review_status": "accepted",
                        "condition_check": "met",
                        "exclusion_check": "clear",
                        "reason": "两端记录具有一致口径，报告明确使用统计值",
                        "confidence": "medium",
                        "limitations": [],
                    }
                    for relation in source["proposals"]
                ]
            }
        if stage == "event_importance":
            return {
                "importance": [
                    {
                        "event_id": event["event_id"],
                        "level": {
                            "user_prompt": "key_decision",
                            "command_execution": "key_turning_point",
                            "subagent_result": "key_result",
                        }.get(event["event_type"], "normal_execution"),
                        "reason": "对应任务中的已记录行为",
                        "related_event_ids": [],
                        "confidence": "medium",
                    }
                    for event in self.events.values()
                ]
            }
        raise AssertionError(stage)


def test_all_six_types_cache_and_order(event_session):
    session, root, trace = event_session
    provider = FixtureProvider(trace)
    result = run_event_workflow(session, str(root), provider=provider)
    assert result["validation"]["valid"]
    assert [item["event_id"] for item in result["event_summaries"]] == [
        event["event_id"] for event in trace["events"]
    ]
    assert len({event["event_type"] for event in trace["events"]}) == 6
    pure_request = next(
        event
        for event in trace["events"]
        if event["event_type"] == "model_response" and event["payload"].get("tool_use_ids")
    )
    assert pure_request["event_id"] in {item["event_id"] for item in result["event_summaries"]}
    assert len(result["event_importance"]) == len(trace["events"])
    assert {item["level"] for item in result["event_importance"]} == {
        "key_decision",
        "normal_execution",
        "key_turning_point",
        "key_result",
    }
    assert result["logical_relations"][0]["evidence_check"] == "quotes_matched"
    assert result["inference_run"]["model"] == "gpt-6.1-sol"
    assert result["inference_run"]["reasoning_effort"] == "medium"
    assert result["inference_run"]["call_count"] == 6
    assert len(list(iter_jsonl(root / session / "derived/event_semantics.jsonl"))) == len(
        trace["events"]
    )
    calls = len(provider.calls)
    assert run_event_workflow(session, str(root), provider=provider) == result
    assert len(provider.calls) == calls
    changed = FixtureProvider(trace)
    changed.config.reasoning_effort = "high"
    newer = run_event_workflow(session, str(root), provider=changed)
    assert newer["inference_run"]["inference_id"] != result["inference_run"]["inference_id"]
    assert len(changed.calls) == 6


def test_partial_resume_does_not_repeat_successful_annotations(event_session):
    session, root, trace = event_session
    broken = FixtureProvider(trace, "event_relations")
    with pytest.raises(SemanticProviderError):
        run_event_workflow(session, str(root), provider=broken)
    state_path = next((root / session / "derived/event_workflow_stages").glob("*/state.json"))
    assert json.loads(state_path.read_text())["status"] == "partial"
    repaired = FixtureProvider(trace)
    result = run_event_workflow(session, str(root), provider=repaired)
    assert result["validation"]["valid"]
    assert repaired.calls == ["event_relations", "event_relation_review", "event_importance"]
    assert result["inference_run"]["call_count"] == 7


def test_unknown_ids_bad_quotes_and_cycles_rejected(event_session):
    _, _, trace = event_session
    provider = FixtureProvider(trace)
    source = {event["event_id"]: event for event in trace["events"]}
    value = provider.complete("SOURCE:\n{}\nJSON_SCHEMA:{}", "event_relations")
    hard = [r for r in trace["relations"] if r["type"] in {"invokes", "spawns"}]
    assert validate_relations(value, source, hard) == []
    bad = deepcopy(value)
    bad["relations"][0]["evidence_refs"][0]["quote"] = "unobserved conclusion"
    assert validate_relations(bad, source, hard)
    bad = deepcopy(value)
    bad["relations"][0]["from"] = "made-up-event"
    assert validate_relations(bad, source, hard)
    bad = deepcopy(value)
    reverse = deepcopy(bad["relations"][0])
    reverse["from"], reverse["to"] = reverse["to"], reverse["from"]
    bad["relations"].append(reverse)
    assert any("cycle" in error for error in validate_relations(bad, source, hard))


def test_stale_result_and_global_budget(event_session, monkeypatch):
    session, root, trace = event_session
    run_event_workflow(session, str(root), provider=FixtureProvider(trace))
    events_path = root / session / "derived/events.jsonl"
    events_path.write_text(events_path.read_text() + "\n")
    with pytest.raises(EventWorkflowError, match="更新"):
        load_event_workflow(session, str(root))

    class Verbose(FixtureProvider):
        def complete(self, prompt, stage, json_schema=None):
            result = super().complete(prompt, stage, json_schema)
            if "annotation" in stage:
                for item in result["events"]:
                    item["outputs"] = ["x" * 1500] * 10
            return result

    monkeypatch.setenv("AGENTVAST_EVENT_GLOBAL_MAX_CHARS", "10000")
    provider = Verbose(trace)
    with pytest.raises(EventWorkflowError, match="预算"):
        run_event_workflow(session, str(root), force=True, provider=provider)
    assert not any(stage == "event_relations" for stage in provider.calls)


def test_model_wire_keeps_medium_when_format_downgrades():
    from io import BytesIO
    from urllib.error import HTTPError

    class Wire(SemanticProvider):
        def __init__(self):
            super().__init__(
                SemanticConfig(
                    "https://semantic.invalid",
                    "test",
                    "gpt-6.1-sol",
                    request_interval_seconds=0,
                    reasoning_effort="medium",
                )
            )
            self.requests = []

        def _post(self, payload):
            self.requests.append(payload)
            if len(self.requests) == 1:
                raise HTTPError(
                    "https://semantic.invalid", 400, "unsupported schema", {}, BytesIO()
                )
            return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = Wire()
    provider.complete("test JSON", "event_annotation", json_schema={"type": "object"})
    assert len(provider.requests) == 2
    for payload in provider.requests:
        assert payload["model"] == "gpt-6.1-sol"
        assert payload["reasoning_effort"] == "medium"
        assert "temperature" not in payload
        assert "max_completion_tokens" in payload


def test_structured_quotes_ignore_json_formatting_but_preserve_values(event_session):
    from agentvast.semantic.event_workflow import _ref_errors

    _, _, trace = event_session
    event = next(e for e in trace["events"] if e["event_type"] == "command_execution")
    mapping = {event["event_id"]: event}
    ref = {
        "event_id": event["event_id"],
        "field": "/payload/input",
        "quote": '{"command":"python analyze.py sales.csv"}',
    }
    assert _ref_errors([ref], mapping, set(mapping)) == []
    ref["quote"] = '{"command":"pythonanalyze.py sales.csv"}'
    assert _ref_errors([ref], mapping, set(mapping))


def test_sorted_partial_json_quotes_match_the_digest_without_changing_values():
    from agentvast.semantic.event_workflow import _facts, _ref_errors

    event = {
        "event_id": "event-sorted-input",
        "sequence": 1,
        "event_type": "tool_execution",
        "event_subtype": "file_read",
        "status": "success",
        "payload": {"input": {"file_path": "a file.csv", "offset": 1, "limit": 260}},
    }
    mapping = {event["event_id"]: event}
    quoted = '"limit":260,"offset":1'
    digest = next(fact for fact in _facts(event)["facts"] if fact["field"] == "/payload/input")
    assert quoted in digest["value"]["text"]
    ref = {"event_id": event["event_id"], "field": "/payload/input", "quote": quoted}
    assert _ref_errors([ref], mapping, set(mapping)) == []
    for invalid in ['"limit":261,"offset":1', '"file_path":"afile.csv"', '"unknown":260']:
        assert _ref_errors([{**ref, "quote": invalid}], mapping, set(mapping))
    # String evidence is still verbatim, including whitespace.
    assert _ref_errors(
        [{**ref, "field": "/payload/input/file_path", "quote": "afile.csv"}],
        mapping,
        set(mapping),
    )


def test_resume_accepts_cached_partial_quote_from_sorted_json(event_session):
    session, root, trace = event_session
    transcript = root.parent / "transcript.jsonl"
    records = [json.loads(line) for line in transcript.read_text().splitlines()]
    records[1]["message"]["content"][1]["input"].update(offset=1, limit=260)
    transcript.write_text("".join(json.dumps(record) + "\n" for record in records))
    snapshot_transcript(session, transcript, root, attempts=1, delay=0)
    build_observer_trace(session, str(root))
    trace = load_observer_trace(session, str(root))
    with pytest.raises(SemanticProviderError):
        run_event_workflow(session, str(root), provider=FixtureProvider(trace, "event_relations"))
    stages = next((root / session / "derived/event_workflow_stages").iterdir())
    command = next(e for e in trace["events"] if e["event_type"] == "command_execution")
    quote = '"limit":260,"offset":1'
    assert quote not in json.dumps(command["payload"]["input"], separators=(",", ":"))
    for path in stages.glob("event_annotation_???-raw.json"):
        raw = json.loads(path.read_text())
        item = next((e for e in raw["events"] if e["event_id"] == command["event_id"]), None)
        if item is not None:
            item["evidence_refs"] = [
                {"event_id": command["event_id"], "field": "/payload/input", "quote": quote}
            ]
            path.write_text(json.dumps(raw))
            stages.joinpath(path.name.replace("-raw.json", ".json")).unlink()
            break
    provider = FixtureProvider(trace, "event_annotation")
    result = run_event_workflow(session, str(root), provider=provider)
    assert result["validation"]["valid"]
    assert provider.calls == ["event_relations", "event_relation_review", "event_importance"]


def test_evidence_aliases_resolve_to_fields_in_compact_events(event_session):
    from agentvast.semantic.event_workflow import _canonical_refs
    from agentvast.observer.event_schema import compact_event

    _, _, trace = event_session
    event = next(e for e in trace["events"] if e["event_type"] == "command_execution")
    ref = {
        "event_id": event["event_id"],
        "field": "/payload/command",
        "quote": "python analyze.py sales.csv",
    }
    result = _canonical_refs({"evidence_refs": [ref]}, {event["event_id"]: event})
    assert result["evidence_refs"][0]["field"] == "/payload/input/command"
    assert compact_event(event)["payload"]["input"]["command"] == ref["quote"]
    assert ref["field"] == "/payload/command"


def test_dead_worker_progress_offers_checkpoint_resume(event_session):
    from agentvast.semantic.event_workflow import event_workflow_progress

    session, root, _ = event_session
    path = root / session / "derived/event_workflow_stages/interrupted/state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "running", "worker_pid": 2147483647, "percent": 50}))
    state = event_workflow_progress(session, str(root))
    assert state["status"] == "partial"
    assert state["percent"] == 50
    assert "检查点" in state["message"]


def test_event_api_generate_poll_and_read(event_session, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from agentvast.web_server import create_app
    import agentvast.semantic.event_workflow as module

    session, root, trace = event_session
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    monkeypatch.setenv("AGENTVAST_SEMANTIC_API_BASE_URL", "https://semantic.invalid")
    monkeypatch.setenv("AGENTVAST_SEMANTIC_MODEL", "gpt-6.1-sol")
    real_run = module.run_event_workflow
    monkeypatch.setattr(
        module,
        "run_event_workflow",
        lambda *args, **kwargs: real_run(*args, provider=FixtureProvider(trace), **kwargs),
    )
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/observations/{session}/event-workflow").status_code == 404
        response = client.post(
            f"/api/observations/{session}/event-workflow/generate",
            json={"force": False, "resume": True},
        )
        assert response.status_code == 200
        for _ in range(100):
            state = client.get(f"/api/observations/{session}/event-workflow/progress").json()
            if state["status"] == "ready":
                break
            time.sleep(0.02)
        assert state["status"] == "ready", state
        result = client.get(f"/api/observations/{session}/event-workflow").json()
        assert result["validation"]["event_count"] == len(trace["events"])
        assert result["inference_run"]["reasoning_effort"] == "medium"


def test_catalog_matches_the_preserved_table():
    from pathlib import Path
    from agentvast.semantic.event_relations import CATALOG, CATALOG_VERSION

    table = (
        Path(__file__).resolve().parents[1] / "docs/EventLogicalRelationCatalog.md"
    ).read_text()
    documented = []
    for line in table.splitlines():
        if line.startswith("| `"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 5:
                continue
            documented.append(
                dict(
                    zip(
                        ["type", "meaning", "required", "excluded", "example"],
                        [cells[0].strip("`"), *cells[1:]],
                    )
                )
            )
    assert CATALOG == documented
    assert len(CATALOG) == 13
    assert CATALOG_VERSION == "event-relations/0.2"


@pytest.mark.parametrize("verdict", ["candidate", "rejected"])
def test_unaccepted_relations_do_not_influence_graph_or_importance(event_session, verdict):
    session, root, trace = event_session

    class Reviewed(FixtureProvider):
        def complete(self, prompt, stage, json_schema=None):
            result = super().complete(prompt, stage, json_schema)
            source = json.loads(prompt.split("SOURCE:\n", 1)[1].split("\nJSON_SCHEMA:", 1)[0])
            if stage == "event_relations":
                assert len(source["relation_catalog"]) == 13
            if stage == "event_relation_review":
                assert source["original_evidence_fields"]
                result["reviews"][0].update(
                    review_status=verdict,
                    condition_check="uncertain" if verdict == "candidate" else "unmet",
                    reason="连接依据尚不能证明消费" if verdict == "candidate" else "不符合成立条件",
                )
            if stage == "event_importance":
                assert source["logical_relations"] == []
                assert all(value["logical"] == 0 for value in source["neighbor_counts"].values())
            return result

    workflow = run_event_workflow(session, str(root), provider=Reviewed(trace))
    assert workflow["logical_relations"] == []
    assert workflow["relation_assessments"][0]["review_status"] == verdict
    assert workflow["validation"][verdict + "_relation_count"] == 1


def test_review_schema_and_deterministic_gates(event_session):
    from agentvast.semantic.event_workflow import (
        validate_relation_reviews,
        finalize_relation_reviews,
    )

    _, _, trace = event_session
    provider = FixtureProvider(trace)
    proposal = provider.complete("SOURCE:\n{}\nJSON_SCHEMA:{}", "event_relations")["relations"][0]
    proposal["relation_id"] = "relation-test"
    review = {
        "relation_id": "relation-test",
        "review_status": "accepted",
        "condition_check": "met",
        "exclusion_check": "clear",
        "reason": "证据支持",
        "confidence": "high",
        "limitations": [],
    }
    assert validate_relation_reviews({"reviews": [review]}, [proposal]) == []
    assert validate_relation_reviews({"reviews": []}, [proposal])
    assert validate_relation_reviews(
        {"reviews": [{**review, "condition_check": "uncertain"}]}, [proposal]
    )
    assert validate_relation_reviews({"reviews": [{**review, "confidence": "low"}]}, [proposal])
    events = {e["event_id"]: e for e in trace["events"]}
    low = {**proposal, "confidence": "low"}
    assert finalize_relation_reviews([low], [review], events, [])[0]["review_status"] == "candidate"
    back = {**proposal, "from": proposal["to"], "to": proposal["from"]}
    result = finalize_relation_reviews(
        [back], [review], events, [{"from": proposal["from"], "to": proposal["to"]}]
    )
    assert result[0]["review_status"] == "rejected"
    assert result[0]["deterministic_issues"]


def test_upgrade_reuses_annotations_and_archives_legacy_result(event_session):
    session, root, trace = event_session
    workflow = run_event_workflow(session, str(root), provider=FixtureProvider(trace))
    legacy = deepcopy(workflow)
    legacy.update(schema_version="event-workflow/0.1", fingerprint="legacy-fingerprint")
    base = root / session / "derived"
    (base / "event_workflow.json").write_text(json.dumps(legacy))
    state_path = next((base / "event_workflow_stages").glob("*/state.json"))
    state = json.loads(state_path.read_text())
    state["fingerprint"] = "legacy-fingerprint"
    state_path.write_text(json.dumps(state))
    assert load_event_workflow(session, str(root))["schema_version"] == "event-workflow/0.1"
    upgraded = FixtureProvider(trace)
    result = run_event_workflow(session, str(root), provider=upgraded)
    assert upgraded.calls == ["event_relations", "event_relation_review", "event_importance"]
    assert result["schema_version"] == "event-workflow/0.3"
    assert result["catalog_version"] == "event-relations/0.2"
    assert json.loads(next((base / "event_workflows").glob("*.json")).read_text()) == legacy


def test_review_failure_resumes_without_repeating_proposals(event_session):
    session, root, trace = event_session
    with pytest.raises(SemanticProviderError):
        run_event_workflow(
            session, str(root), provider=FixtureProvider(trace, "event_relation_review")
        )
    provider = FixtureProvider(trace)
    run_event_workflow(session, str(root), provider=provider)
    assert provider.calls == ["event_relation_review", "event_importance"]


def test_review_budget_preserves_proposals_for_resume(event_session, monkeypatch):
    session, root, trace = event_session

    class Budgeted(FixtureProvider):
        def complete(self, prompt, stage, json_schema=None):
            result = super().complete(prompt, stage, json_schema)
            if stage == "event_relations":
                monkeypatch.setenv("AGENTVAST_EVENT_GLOBAL_MAX_CHARS", "10000")
            return result

    provider = Budgeted(trace)
    with pytest.raises(EventWorkflowError, match="event_relation_review.*预算"):
        run_event_workflow(session, str(root), provider=provider)
    assert "event_relation_review" not in provider.calls
    monkeypatch.setenv("AGENTVAST_EVENT_GLOBAL_MAX_CHARS", "220000")
    resumed = FixtureProvider(trace)
    run_event_workflow(session, str(root), provider=resumed)
    assert resumed.calls == ["event_relation_review", "event_importance"]


def test_bridge_citations_are_preserved_without_replacing_endpoint_proof(event_session):
    from agentvast.semantic.event_workflow import _canonical_refs

    _, _, trace = event_session
    provider = FixtureProvider(trace)
    value = provider.complete("SOURCE:\n{}\nJSON_SCHEMA:{}", "event_relations")
    relation = value["relations"][0]
    bridge = next(e for e in trace["events"] if e["event_type"] == "user_prompt")
    ref = {"event_id": bridge["event_id"], "field": "/payload/content", "quote": "sales.csv"}
    relation["evidence_refs"].append(ref)
    mapping = {e["event_id"]: e for e in trace["events"]}
    canonical = _canonical_refs(value, mapping)
    assert canonical["relations"][0]["context_evidence_refs"] == [ref]
    assert len(value["relations"][0]["evidence_refs"]) == 3  # Raw audit is untouched.
    assert validate_relations(canonical, mapping, []) == []
    bad = deepcopy(canonical)
    bad["relations"][0]["context_evidence_refs"][0]["quote"] = "unobserved claim"
    assert validate_relations(bad, mapping, [])
    bad = deepcopy(canonical)
    bad["relations"][0]["evidence_refs"] = bad["relations"][0]["evidence_refs"][:1]
    assert validate_relations(bad, mapping, [])


def test_empty_proposals_are_allowed_without_an_unnecessary_review_call(event_session):
    session, root, trace = event_session

    class Empty(FixtureProvider):
        def complete(self, prompt, stage, json_schema=None):
            result = super().complete(prompt, stage, json_schema)
            return {"relations": []} if stage == "event_relations" else result

    provider = Empty(trace)
    workflow = run_event_workflow(session, str(root), provider=provider)
    assert workflow["logical_relations"] == workflow["relation_assessments"] == []
    assert "event_relation_review" not in provider.calls


def test_role_validation_rejects_legacy_duplicate_and_unrelated_annotations():
    from agentvast.semantic.event_workflow import validate_importance

    mapping = {key: {} for key in ["a", "b", "c", "d"]}
    value = {
        "importance": [
            {
                "event_id": key,
                "level": role,
                "reason": "任务作用依据",
                "related_event_ids": [],
                "confidence": "medium",
            }
            for key, role in zip(
                mapping, ["key_decision", "normal_execution", "key_turning_point", "key_result"]
            )
        ]
    }
    assert validate_importance(value, mapping, []) == []
    for legacy in ["core", "supporting", "background", "invented"]:
        invalid = deepcopy(value)
        invalid["importance"][0]["level"] = legacy
        assert validate_importance(invalid, mapping, [])
    invalid = deepcopy(value)
    invalid["importance"][0]["related_event_ids"] = ["b"]
    assert validate_importance(invalid, mapping, [])
    assert not validate_importance(invalid, mapping, [{"from": "a", "to": "b"}])
    invalid = deepcopy(value)
    invalid["importance"][1]["event_id"] = "a"
    assert validate_importance(invalid, mapping, [])


def test_v02_ratings_stay_readable_and_upgrade_without_relabeling_facts(event_session):
    session, root, trace = event_session
    workflow = run_event_workflow(session, str(root), provider=FixtureProvider(trace))
    legacy = deepcopy(workflow)
    legacy.update(schema_version="event-workflow/0.2", fingerprint="old-three-level-ratings")
    for item in legacy["event_importance"]:
        item["level"] = "core" if item["level"] != "normal_execution" else "supporting"
    base = root / session / "derived"
    (base / "event_workflow.json").write_text(json.dumps(legacy))
    old = load_event_workflow(session, str(root))
    assert old["event_importance"] == legacy["event_importance"]
    state_path = next((base / "event_workflow_stages").glob("*/state.json"))
    state = json.loads(state_path.read_text())
    state["fingerprint"] = legacy["fingerprint"]
    state_path.write_text(json.dumps(state))
    provider = FixtureProvider(trace)
    new = run_event_workflow(session, str(root), provider=provider)
    assert new["schema_version"] == "event-workflow/0.3"
    assert provider.calls == ["event_relations", "event_relation_review", "event_importance"]
    assert new["event_summaries"] == old["event_summaries"]
    assert load_observer_trace(session, str(root))["events"] == trace["events"]
    assert json.loads(next((base / "event_workflows").glob("*.json")).read_text()) == legacy


def test_turn_snapshot_runs_original_semantic_pipeline(event_session):
    from agentvast.observer.live_trace import (
        enable_live_trace,
        request_turn_analysis,
        sync_live_trace,
        analyze_next_turn,
        live_event_workflow,
    )
    from agentvast.observer.store import append_raw_event, update_manifest

    session, root, trace = event_session
    enable_live_trace(session, root)
    update_manifest(session, {"live_activated_at": "2020-01-01T00:00:00Z"}, root)
    append_raw_event(
        session,
        "hook",
        {"hook_event_name": "UserPromptSubmit", "prompt": "分析 sales.csv 缺失值并汇报"},
        root,
    )
    append_raw_event(
        session,
        "hook",
        {"hook_event_name": "Stop", "last_assistant_message": "缺失率 40%，需要清洗。"},
        root,
    )
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    assert state["turns"][0]["analysis_state"] == "idle"
    request_turn_analysis(session, [state["turns"][0]["turn_id"]], root)

    def runner(sid, root, **kwargs):
        source = load_observer_trace(sid, root)
        return run_event_workflow(sid, root, provider=FixtureProvider(source), **kwargs)

    assert analyze_next_turn(session, root, runner)
    result = live_event_workflow(session, root)
    assert result["validation"]["valid"]
    assert result["scope"]["cross_turn_inference"] is False
    assert result["inference_run"]["model"] == "gpt-6.1-sol"
    assert len(result["event_summaries"]) == state["turns"][0]["event_count"]


def test_annotation_cache_reused_across_turn_versions_when_only_end_state_changes(
    event_session, tmp_path
):
    import shutil

    session, root, trace = event_session
    path = root / session / "derived/observer_trace.json"
    raw = json.loads(path.read_text())
    raw["history_context"] = {"recent_user_tasks": []}
    raw["analysis_scope"] = {
        "type": "turn",
        "execution_state": "interrupted",
        "cross_turn_inference": False,
    }
    path.write_text(json.dumps(raw))
    run_event_workflow(session, root, provider=FixtureProvider(trace))
    next_root = tmp_path / "next-version"
    shutil.copytree(root / session, next_root / session)
    shutil.rmtree(next_root / session / "derived/event_workflow_stages")
    (next_root / session / "derived/event_workflow.json").unlink()
    next_path = next_root / session / "derived/observer_trace.json"
    raw["analysis_scope"]["execution_state"] = "completed"
    next_path.write_text(json.dumps(raw))
    provider = FixtureProvider(trace)
    result = run_event_workflow(
        session, next_root, provider=provider, annotation_cache_roots=[root]
    )
    assert result["validation"]["valid"]
    assert not any(stage.startswith("event_annotation") for stage in provider.calls)
    assert provider.calls == ["event_relations", "event_relation_review", "event_importance"]
    # Changed Event facts must still get new semantic annotation.
    third_root = tmp_path / "changed-version"
    shutil.copytree(next_root / session, third_root / session)
    shutil.rmtree(third_root / session / "derived/event_workflow_stages")
    (third_root / session / "derived/event_workflow.json").unlink()
    from agentvast.observer.store import write_jsonl

    facts = list(iter_jsonl(third_root / session / "derived/events.jsonl"))
    facts[-1]["payload"]["new_fact"] = "改变后的事实"
    write_jsonl(third_root / session / "derived/events.jsonl", facts)
    raw["events"][-1]["payload"]["new_fact"] = "改变后的事实"
    (third_root / session / "derived/observer_trace.json").write_text(json.dumps(raw))
    changed = FixtureProvider(load_observer_trace(session, third_root))
    run_event_workflow(
        session, third_root, provider=changed, annotation_cache_roots=[root, next_root]
    )
    assert len([stage for stage in changed.calls if stage.startswith("event_annotation")]) == 1
