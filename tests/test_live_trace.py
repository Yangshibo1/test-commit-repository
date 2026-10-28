import json
import os
from pathlib import Path

import pytest

from agentvast.observer.live_trace import (
    capture_append,
    enable_live_trace,
    sync_live_trace,
    live_state,
    analyze_next_turn,
    live_event_workflow,
    retry_live_turns,
    request_turn_analysis,
)
from agentvast.observer.store import create_session, append_raw_event, update_manifest, iter_jsonl
from agentvast.observer.trace_builder import load_observer_trace


@pytest.fixture
def live(tmp_path, monkeypatch):
    root = tmp_path / "observations"
    source = tmp_path / "claude.jsonl"
    source.write_bytes(b"")
    session = "live-test"
    monkeypatch.setenv("AGENTVAST_OBSERVER_REGISTRY", str(tmp_path / "registry"))
    create_session(session, tmp_path, root)
    enable_live_trace(session, root)
    update_manifest(
        session,
        {"transcript_source_path": str(source), "live_activated_at": "2020-01-01T00:00:00Z"},
        root,
    )
    return session, root, source


def append(source, *records):
    with source.open("ab") as stream:
        for record in records:
            stream.write((json.dumps(record, ensure_ascii=False) + "\n").encode())


def prompt(uuid="u1", text="读取数据"):
    return {
        "type": "user",
        "uuid": uuid,
        "origin": {"kind": "human"},
        "timestamp": "2026-10-27T00:00:00Z",
        "message": {"content": text},
    }


def final(uuid="f1", parent="u1", text="已完成"):
    return {
        "type": "assistant",
        "uuid": uuid,
        "parentUuid": parent,
        "timestamp": "2026-10-27T00:00:01Z",
        "message": {
            "id": uuid,
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": text}],
        },
    }


def hook(live, name, **payload):
    session, root, _ = live
    return append_raw_event(session, "hook", {"hook_event_name": name, **payload}, root)


def close_turn(live):
    session, root, source = live
    append(source, prompt(), final())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "Stop", last_assistant_message="已完成")
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    return request_turn_analysis(session, [state["turns"][0]["turn_id"]], root)


def fake_runner(session, root, **kwargs):
    from agentvast.semantic.pipeline import _load_semantic_event_source

    trace, _, _, trace_sha, events_sha = _load_semantic_event_source(session, root)
    value = {
        "schema_version": "event-workflow/0.3",
        "session_id": session,
        "source_hashes": {"events": events_sha, "trace": trace_sha},
        "event_summaries": [{"event_id": e["event_id"]} for e in trace["events"]],
        "event_importance": [{"event_id": e["event_id"]} for e in trace["events"]],
        "logical_relations": [],
        "relation_assessments": [],
        "validation": {"valid": True, "event_count": len(trace["events"]), "relation_count": 0},
        "inference_run": {"inference_id": "test", "model": "test", "reasoning_effort": "medium"},
    }
    (Path(root) / session / "derived/event_workflow.json").write_text(json.dumps(value))
    return value


def test_complete_lines_and_utf8_resume_without_duplicate_records(live):
    session, root, source = live
    raw = (json.dumps(prompt(), ensure_ascii=False) + "\n").encode()
    split = raw.index("读".encode()) + 1
    source.write_bytes(raw[:split])
    state = capture_append(session, source, root)
    assert state["record_count"] == 0 and state["offset"] == 0
    with source.open("ab") as f:
        f.write(raw[split:])
    assert capture_append(session, source, root)["record_count"] == 1
    assert capture_append(session, source, root)["record_count"] == 1
    # Replay the exact UUID record after truncation/replacement: still one fact.
    replacement = source.with_suffix(".new")
    replacement.write_bytes(raw)
    os.replace(replacement, source)
    assert capture_append(session, source, root)["record_count"] == 1
    append(source, final())
    assert capture_append(session, source, root)["record_count"] == 2


def test_truncate_and_regrow_same_inode_is_detected_and_invalid_lines_preserved(live):
    session, root, source = live
    append(source, prompt())
    first = capture_append(session, source, root)
    source.write_bytes(b"not-json\n" + (json.dumps(final()) + "\n").encode())
    second = capture_append(session, source, root)
    assert second["generation"] != first["generation"]
    assert second["record_count"] == 3
    state = sync_live_trace(session, root, now=100)
    assert state["trace_revision"] == 1
    assert any(not r["parsed"] for r in iter_jsonl(root / session / "raw/transcript.jsonl"))


def test_stop_waits_for_final_record_and_quiet_window(live):
    session, root, source = live
    append(source, prompt())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "Stop", last_assistant_message="已完成")
    assert sync_live_trace(session, root, now=100)["turns"][0]["execution_state"] == "settling"
    append(source, final())
    assert sync_live_trace(session, root, now=101)["turns"][0]["execution_state"] == "settling"
    state = sync_live_trace(session, root, now=103)
    assert state["turns"][0]["execution_state"] == "completed"
    assert state["turns"][0]["analysis_state"] == "idle"
    assert state["turns"][0]["revision"] == 1
    assert sync_live_trace(session, root, now=105)["turns"][0]["revision"] == 1


def test_silence_or_subagent_stop_does_not_complete_a_turn(live):
    session, root, source = live
    append(source, prompt(), final())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "SubagentStop")
    hook(live, "Stop", agent_id="child")
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=200)
    assert state["turns"][0]["execution_state"] == "running"
    assert not state["turns"][0].get("revision")


def test_partial_line_blocks_last_turn_closure(live):
    session, root, source = live
    close_turn(live)
    with source.open("ab") as stream:
        stream.write(b'{"uuid":')
    state = sync_live_trace(session, root, now=104)
    assert state["turns"][0]["execution_state"] == "settling"


def test_next_turn_does_not_invalidate_previous_snapshot_or_result(live):
    session, root, source = live
    first = close_turn(live)["turns"][0]
    frozen = (Path(first["snapshot_root"]) / session / "derived/observer_trace.json").read_bytes()
    calls = []

    def runner(*args, **kwargs):
        calls.append(kwargs["root"])
        return fake_runner(*args, **kwargs)

    assert analyze_next_turn(session, root, runner)
    assert not analyze_next_turn(session, root, runner)
    append(source, prompt("u2", "生成图表"))
    hook(live, "UserPromptSubmit", prompt="生成图表")
    state = sync_live_trace(session, root, now=106)
    assert state["turns"][0]["revision"] == 1
    assert state["turns"][0]["analysis_state"] == "ready"
    assert state["turns"][1]["execution_state"] == "running"
    assert len(live_event_workflow(session, root)["event_summaries"]) == 2
    assert (
        Path(first["snapshot_root"]) / session / "derived/observer_trace.json"
    ).read_bytes() == frozen
    assert len(calls) == 1


def test_new_revision_retains_old_snapshot_and_failed_job_is_explicitly_retryable(live):
    session, root, source = live
    first = close_turn(live)["turns"][0]

    def fail(*args, **kwargs):
        raise RuntimeError("temporary error")

    assert analyze_next_turn(session, root, fail)
    assert live_state(session, root)["turns"][0]["analysis_state"] == "partial"
    assert not analyze_next_turn(session, root, fail)
    retry_live_turns(session, root)
    assert analyze_next_turn(session, root, fake_runner)
    # Additional final text in the same original turn is a new immutable version.
    append(source, final("f2", text="已补充结果"))
    hook(live, "Stop", last_assistant_message="已补充结果")
    sync_live_trace(session, root, now=110)
    state = sync_live_trace(session, root, now=112)
    assert state["turns"][0]["revision"] == 2
    assert Path(first["snapshot_root"]).is_dir()
    assert live_event_workflow(session, root) is None


def test_session_end_does_not_relabel_a_successful_stop_as_interrupted(live):
    session, root, source = live
    close_turn(live)
    hook(live, "SessionEnd")
    assert sync_live_trace(session, root, now=104)["turns"][0]["execution_state"] == "completed"


def test_failure_and_missing_stop_are_partial_execution(live):
    session, root, source = live
    append(source, prompt())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "StopFailure")
    sync_live_trace(session, root, now=100)
    assert sync_live_trace(session, root, now=102)["turns"][0]["execution_state"] == "failed"
    append(source, prompt("u2", "next"))
    hook(live, "UserPromptSubmit", prompt="next")
    update_manifest(session, {"ended_at": "2026-10-27T02:00:00Z"}, root)
    assert sync_live_trace(session, root, now=104)["turns"][1]["execution_state"] == "interrupted"


def test_unpersisted_new_prompt_stop_must_not_close_previous_turn(live):
    session, root, source = live
    append(source, prompt(), final())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "UserPromptSubmit", prompt="尚未写入的新任务")
    hook(live, "Stop", last_assistant_message="已完成")
    sync_live_trace(session, root, now=100)
    assert sync_live_trace(session, root, now=102)["turns"][0]["execution_state"] == "running"


def test_stop_can_match_final_text_when_transcript_omits_stop_reason(live):
    session, root, source = live
    response = final()
    response["message"].pop("stop_reason")
    append(source, prompt(), response)
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(
        live,
        "Stop",
        last_assistant_message="已完成",
        background_tasks=[{"id": "task", "status": "running"}],
    )
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    assert state["turns"][0]["execution_state"] == "completed"
    assert state["turns"][0]["boundary"]["pending_background_tasks"] == 1


def test_capture_commit_recovers_projection_after_a_crash(live):
    session, root, source = live
    append(source, prompt())
    # Capture committed, process crashed before writing JSON projections/state.
    assert capture_append(session, source, root)["record_count"] == 1
    state = sync_live_trace(session, root, now=100)
    assert state["capture"]["record_count"] == 1
    assert len(load_observer_trace(session, root)["turns"]) == 1
    assert len(list(iter_jsonl(root / session / "raw/transcript.jsonl"))) == 1


def test_inflight_old_revision_cannot_overwrite_new_version(live):
    session, root, source = live
    close_turn(live)

    def runner(*args, **kwargs):
        append(source, final("f2", text="已更新"))
        hook(live, "Stop", last_assistant_message="已更新")
        sync_live_trace(session, root, now=110)
        sync_live_trace(session, root, now=112)
        return fake_runner(*args, **kwargs)

    assert analyze_next_turn(session, root, runner)
    turn = live_state(session, root)["turns"][0]
    assert turn["revision"] == 2 and turn["analysis_state"] == "idle"
    assert live_event_workflow(session, root) is None


def test_web_background_service_collects_and_publishes_without_terminal_exit(
    live, monkeypatch, tmp_path
):
    from fastapi.testclient import TestClient
    from agentvast.web_server import create_app
    import agentvast.observer.live_trace as module
    import time

    session, root, source = live
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    real = module.analyze_next_turn
    monkeypatch.setattr(module, "analyze_next_turn", lambda sid, r: real(sid, r, fake_runner))
    append(source, prompt(), final())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "Stop", last_assistant_message="已完成")
    app = create_app(tmp_path)
    app.state.live_trace_service.interval = 0.03
    with TestClient(app) as client:
        state = {}
        submitted = False
        for _ in range(160):
            state = client.get(f"/api/observations/{session}/live").json()
            if state.get("turns") and state["turns"][0].get("revision") and not submitted:
                assert state["turns"][0]["analysis_state"] == "idle"
                assert (
                    client.post(
                        f"/api/observations/{session}/live/analyze",
                        json={"turn_ids": [state["turns"][0]["turn_id"]]},
                    ).status_code
                    == 200
                )
                submitted = True
            if state.get("turns") and state["turns"][0].get("analysis_state") == "ready":
                break
            time.sleep(0.02)
        assert state["turns"][0]["analysis_state"] == "ready", state
        trace = client.get(f"/api/observations/{session}/trace").json()
        assert trace["live"]["enabled"]
        workflow = client.get(f"/api/observations/{session}/live/event-workflow").json()
        assert len(workflow["scope"]["turns"]) == 1
        assert len(workflow["event_summaries"]) == 2
        assert client.get(f"/api/observations/{session}/transcript").status_code == 200
        assert client.post(f"/api/observations/{session}/live/retry").status_code == 200


def test_rotation_dedup_keeps_projection_line_numbers_consistent(live):
    session, root, source = live
    append(source, prompt())
    sync_live_trace(session, root, now=100)
    replacement = source.with_suffix(".new")
    replacement.write_bytes(source.read_bytes())
    os.replace(replacement, source)
    capture_append(session, source, root)
    append(source, final())
    sync_live_trace(session, root, now=102)
    assert [r["line_number"] for r in iter_jsonl(root / session / "raw/transcript.jsonl")] == [1, 2]
    assert len((root / session / "transcript/transcript.jsonl").read_text().splitlines()) == 2


def test_late_subagent_result_revises_its_original_turn(live):
    session, root, source = live
    tool = {
        "type": "assistant",
        "uuid": "spawn",
        "parentUuid": "u1",
        "message": {
            "id": "spawn",
            "content": [
                {
                    "type": "tool_use",
                    "id": "task-call",
                    "name": "Agent",
                    "input": {"description": "复核"},
                }
            ],
        },
    }
    returned = {
        "type": "user",
        "uuid": "started",
        "parentUuid": "spawn",
        "message": {
            "content": [
                {"type": "tool_result", "tool_use_id": "task-call", "content": "Task started"}
            ]
        },
    }
    append(source, prompt(), tool, returned, final(parent="started"))
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "Stop", last_assistant_message="已完成")
    sync_live_trace(session, root, now=100)
    first = sync_live_trace(session, root, now=102)["turns"][0]
    append(source, prompt("u2", "后续问题"))
    hook(live, "UserPromptSubmit", prompt="后续问题")
    sync_live_trace(session, root, now=104)
    append(
        source,
        {
            "type": "user",
            "uuid": "late",
            "origin": {"kind": "task-notification"},
            "message": {
                "content": "<task-notification><task-id>task-1</task-id><tool-use-id>task-call</tool-use-id><status>completed</status><result>复核完成</result></task-notification>"
            },
        },
    )
    sync_live_trace(session, root, now=106)
    state = sync_live_trace(session, root, now=108)
    assert state["turns"][0]["turn_id"] == first["turn_id"]
    assert state["turns"][0]["revision"] == 2
    assert state["turns"][1]["execution_state"] == "running"
    events = load_observer_trace(session, root)["events"]
    late = next(e for e in events if e["event_type"] == "subagent_result")
    assert late["scope"]["turn_id"] == first["turn_id"]


def test_resume_clears_the_previous_session_end(live):
    session, root, source = live
    update_manifest(session, {"ended_at": "2026-10-27T02:00:00Z"}, root)
    enable_live_trace(session, root)
    append(source, prompt())
    assert sync_live_trace(session, root, now=100)["turns"][0]["execution_state"] == "running"


def test_historical_completed_turns_are_not_automatically_sent_to_model(live):
    session, root, source = live
    append(source, prompt(), final())
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "Stop", last_assistant_message="已完成")
    update_manifest(session, {"live_activated_at": "2099-01-01T00:00:00Z"}, root)
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    assert state["turns"][0]["analysis_state"] == "historical"
    assert not analyze_next_turn(session, root, fake_runner)


def test_analysis_process_lock_prevents_duplicate_jobs(live):
    from agentvast.observer.locking import InterProcessFileLock

    session, root, source = live
    close_turn(live)
    with InterProcessFileLock(root / session / "live/analysis.lock"):
        assert not analyze_next_turn(session, root, fake_runner)
    assert analyze_next_turn(session, root, fake_runner)
    assert not analyze_next_turn(session, root, fake_runner)


def test_session_end_publishes_a_new_ui_revision_without_invalidating_turn(live):
    session, root, source = live
    before = close_turn(live)
    update_manifest(session, {"ended_at": "2026-10-27T02:00:00Z"}, root)
    after = sync_live_trace(session, root, now=104)
    assert after["trace_revision"] > before["trace_revision"]
    assert after["turns"][0]["revision"] == before["turns"][0]["revision"]


def test_execution_boundary_correction_creates_a_new_analysis_version(live):
    session, root, source = live
    initial = close_turn(live)["turns"][0]
    hook(live, "StopFailure")
    updated = sync_live_trace(session, root, now=104)["turns"][0]
    assert updated["execution_state"] == "failed"
    assert updated["revision"] == initial["revision"] + 1
    assert updated["snapshot_execution"] == "failed"


def test_repeated_prompt_hook_context_uses_prompt_id_and_closes_followup(live):
    session, root, source = live
    p1 = prompt()
    p1["promptId"] = "p1"
    f1 = final()
    f1["promptId"] = "p1"
    p2 = prompt("u2", "继续分析")
    p2["promptId"] = "p2"
    f2 = final("f2", "u2", "后续已完成")
    f2["promptId"] = "p2"
    append(source, p1, f1, p2, f2)
    hook(live, "UserPromptSubmit", prompt="读取数据", prompt_id="p1")
    hook(live, "Stop", last_assistant_message="已完成", prompt_id="p1")
    hook(live, "UserPromptSubmit", prompt="继续分析", prompt_id="p2")
    hook(live, "UserPromptSubmit", prompt="同一轮追加的规划上下文", prompt_id="p2")
    hook(live, "Stop", last_assistant_message="后续已完成", prompt_id="p2")
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    assert len(state["turns"]) == 2
    assert all(t["execution_state"] == "completed" for t in state["turns"])
    assert all(t["analysis_state"] == "idle" for t in state["turns"])
    request_turn_analysis(session, [t["turn_id"] for t in state["turns"]], root)
    assert analyze_next_turn(session, root, fake_runner)
    assert analyze_next_turn(session, root, fake_runner)
    assert not analyze_next_turn(session, root, fake_runner)
    assert len(live_event_workflow(session, root)["scope"]["turns"]) == 2


def test_system_prompt_loops_keep_the_human_turn_and_async_stops_use_their_prompt_id(live):
    session, root, source = live
    p1 = prompt()
    p1["promptId"] = "p1"
    f1 = final()
    f1["promptId"] = "p1"
    system = {
        "type": "user",
        "uuid": "notice",
        "isMeta": True,
        "origin": {"kind": "peer"},
        "promptSource": "system",
        "promptId": "auto",
        "message": {"content": "后台通知上下文"},
    }
    f2 = final("f2", "notice", "通知已处理")
    f2["promptId"] = "auto"
    p2 = prompt("u2", "下一轮任务")
    p2["promptId"] = "p2"
    f3 = final("f3", "u2", "第二轮完成")
    f3["promptId"] = "p2"
    append(source, p1, f1, system, f2, p2, f3)
    hook(live, "UserPromptSubmit", prompt="读取数据", prompt_id="p1")
    hook(live, "UserPromptSubmit", prompt="后台通知上下文", prompt_id="auto")
    hook(live, "UserPromptSubmit", prompt="下一轮任务", prompt_id="p2")
    # A delayed stop for the automatic loop must not close the newer human turn.
    hook(live, "Stop", last_assistant_message="通知已处理", prompt_id="auto")
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    assert len(state["turns"]) == 2
    assert state["turns"][0]["execution_state"] == "completed"
    assert state["turns"][1]["execution_state"] == "running"
    hook(live, "Stop", last_assistant_message="第二轮完成", prompt_id="p2")
    assert sync_live_trace(session, root, now=104)["turns"][1]["execution_state"] == "completed"


def test_hook_prompt_id_still_works_with_older_transcript_missing_prompt_id(live):
    session, root, source = live
    append(source, prompt(), final())
    hook(live, "UserPromptSubmit", prompt="读取数据", prompt_id="new-hook-id")
    hook(live, "UserPromptSubmit", prompt="注入上下文", prompt_id="new-hook-id")
    hook(live, "Stop", last_assistant_message="已完成", prompt_id="new-hook-id")
    sync_live_trace(session, root, now=100)
    assert sync_live_trace(session, root, now=102)["turns"][0]["execution_state"] == "completed"


def test_superseded_worker_releases_queue_and_preserves_current_revision(live):
    session, root, source = live
    close_turn(live)

    def obsolete_runner(*args, **kwargs):
        append(source, final("changed", "u1", "补充结果"))
        hook(live, "Stop", last_assistant_message="补充结果")
        sync_live_trace(session, root, now=110)
        sync_live_trace(session, root, now=112)
        kwargs["cancel_check"]()
        pytest.fail("obsolete analysis must stop before any further model call")

    assert analyze_next_turn(session, root, obsolete_runner)
    state = live_state(session, root)
    assert state["turns"][0]["revision"] == 2
    assert state["turns"][0]["analysis_state"] == "idle"
    request_turn_analysis(session, [state["turns"][0]["turn_id"]], root)
    assert state["active_analysis"]["status"] == "superseded"
    assert analyze_next_turn(session, root, fake_runner)
    assert live_state(session, root)["turns"][0]["analysis_state"] == "ready"


def test_actual_analysis_progress_is_exposed_separately_from_queued_versions(live):
    session, root, source = live
    close_turn(live)

    def runner(*args, **kwargs):
        kwargs["progress_callback"]({"percent": 42, "message": "摘要完成 6/12"})
        state = live_state(session, root)
        assert state["active_analysis"]["percent"] == 42
        assert state["active_analysis"]["status"] == "running"
        return fake_runner(*args, **kwargs)

    assert analyze_next_turn(session, root, runner)
    assert live_state(session, root)["active_analysis"]["status"] == "ready"


def test_completed_turns_never_start_models_until_selected(live):
    session, root, source = live
    append(source, prompt(), final(), prompt("u2", "继续"), final("f2", "u2", "完成后续"))
    hook(live, "UserPromptSubmit", prompt="读取数据")
    hook(live, "Stop", last_assistant_message="已完成")
    hook(live, "UserPromptSubmit", prompt="继续")
    hook(live, "Stop", last_assistant_message="完成后续")
    sync_live_trace(session, root, now=100)
    state = sync_live_trace(session, root, now=102)
    assert state["analysis_mode"] == "manual"
    assert all(t["analysis_state"] == "idle" for t in state["turns"])
    assert not analyze_next_turn(session, root, fake_runner)
    selected = state["turns"][1]["turn_id"]
    request_turn_analysis(session, [selected], root)
    assert analyze_next_turn(session, root, fake_runner)
    state = sync_live_trace(session, root, now=104)
    assert state["turns"][0]["analysis_state"] == "idle"
    assert state["turns"][1]["analysis_state"] == "ready"
    assert not analyze_next_turn(session, root, fake_runner)
    previous = state["turns"][1]["revision"]
    request_turn_analysis(session, [selected], root, force=True)
    assert live_state(session, root)["turns"][1]["revision"] == previous + 1
    assert live_state(session, root)["turns"][0]["analysis_state"] == "idle"


def test_manual_selection_is_atomic_and_works_for_historical_sessions(live):
    session, root, source = live
    state = close_turn(live)
    update_manifest(session, {"live_trace_enabled": False}, root)
    selected = state["turns"][0]["turn_id"]
    before = live_state(session, root)
    with pytest.raises(ValueError):
        request_turn_analysis(session, [selected, "unknown-turn"], root)
    assert live_state(session, root) == before
    with pytest.raises(ValueError):
        request_turn_analysis(session, [], root)
    request_turn_analysis(session, [selected], root, force=True)
    assert analyze_next_turn(session, root, fake_runner)
    assert live_state(session, root)["turns"][0]["analysis_state"] == "ready"


def test_old_automatic_queue_entries_are_not_executed(live):
    session, root, source = live
    state = close_turn(live)
    path = root / session / "live/state.json"
    state["turns"][0].pop("analysis_requested", None)
    path.write_text(json.dumps(state))
    assert not analyze_next_turn(session, root, fake_runner)
    current = sync_live_trace(session, root, now=104)
    assert current["turns"][0]["analysis_state"] == "idle"


def test_manual_force_preserves_annotation_context_and_clears_old_auto_status(live):
    session, root, source = live
    original = close_turn(live)["turns"][0]
    old_context = json.loads(
        (Path(original["snapshot_root"]) / session / "derived/observer_trace.json").read_text()
    )["history_context"]
    state = request_turn_analysis(session, [original["turn_id"]], root, force=True)
    current = state["turns"][0]
    new_context = json.loads(
        (Path(current["snapshot_root"]) / session / "derived/observer_trace.json").read_text()
    )["history_context"]
    assert new_context == old_context
    current.pop("analysis_requested", None)
    state["active_analysis"] = {
        "turn_id": current["turn_id"],
        "revision": current["revision"],
        "status": "running",
        "percent": 53,
    }
    (root / session / "live/state.json").write_text(json.dumps(state))
    state = sync_live_trace(session, root, now=104)
    assert state["active_analysis"]["status"] == "stopped"
    assert state["turns"][0]["analysis_state"] == "idle"
