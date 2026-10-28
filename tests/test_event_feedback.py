import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentvast.observer.event_feedback import build_feedback, read_feedback
from agentvast.web_server import TerminalSession, create_app


def sample_trace():
    return {
        "session": {"session_id": "feedback-test"},
        "turns": [{"turn_id": "turn-1", "prompt": "分析会议数据", "status": "complete"}],
        "events": [
            {
                "event_id": "event-1",
                "sequence": 12,
                "scope": {"turn_id": "turn-1"},
                "event_type": "command_execution",
                "status": "success",
                "title": "计算均值",
                "summary": "读取数据计算均值",
                "payload": {"command": "python analyze.py", "stdout": "x" * 9000},
                "provenance": {"source_lines": [8, 9]},
            }
        ],
        "relations": [],
        "artifacts": [
            {
                "path": "/project/analyze.py",
                "operations": [{"event_id": "event-1", "operation": "executed"}],
            }
        ],
    }


def test_prompt_keeps_user_opinion_and_provenance_with_bounded_facts():
    trace = sample_trace()
    original = copy.deepcopy(trace)
    workflow = {
        "event_summaries": [
            {"event_id": "event-1", "title": "按会议类型聚合", "behavior_summary": "计算各组平均值"}
        ],
        "event_importance": [{"event_id": "event-1", "level": "key_result"}],
    }
    value = build_feedback(trace, "event-1", "先去除重复记录，再重新计算均值。", workflow)
    assert value["status"] == "draft"
    for text in (
        "event-1",
        "分析会议数据",
        "/project/analyze.py",
        "python analyze.py",
        "先去除重复记录",
        "ai_interpretation_reference",
        "key_result",
        "source_lines",
        "上下文已截断",
    ):
        assert text in value["prompt"]
    assert len(value["prompt"]) < 8000
    assert trace == original
    assert "不要将修改记录本身当作已经重新执行" in value["prompt"]


@pytest.mark.parametrize("content", ["", "  ", "x" * 6001, "注入\x1b[201~", "abc\rdef"])
def test_feedback_rejects_empty_oversized_and_terminal_control_input(content):
    with pytest.raises(ValueError):
        build_feedback(sample_trace(), "event-1", content)


def test_feedback_requires_a_real_event():
    with pytest.raises(LookupError):
        build_feedback(sample_trace(), "missing-event", "修改均值")


@pytest.fixture
def feedback_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    root = tmp_path / "observations"
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    trace = sample_trace()
    state = {"turns": [{"turn_id": "turn-1", "execution_state": "completed"}]}
    monkeypatch.setattr(
        "agentvast.web_server.load_observer_trace", lambda *args: copy.deepcopy(trace)
    )
    monkeypatch.setattr("agentvast.web_server.live_event_workflow", lambda *args: None)
    monkeypatch.setattr("agentvast.web_server.live_state", lambda *args: state)
    monkeypatch.setattr("agentvast.web_server.read_manifest", lambda *args: {})
    writes = []
    process = SimpleNamespace(isalive=lambda: True, write=writes.append)
    session = TerminalSession(
        process, tmp_path, "claude", True, "feedback-test", tmp_path / "workflow.sqlite3", root
    )
    app = create_app(tmp_path)
    app.state.terminal_manager.current = session
    return SimpleNamespace(
        client=TestClient(app),
        root=root,
        writes=writes,
        process=process,
        session=session,
        state=state,
        app=app,
    )


def prepare(f):
    response = f.client.post(
        "/api/observations/feedback-test/events/event-1/feedback",
        json={"content": "先去重，再重新计算均值"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    url = "/api/observations/feedback-test/event-feedback/" + body["feedback"]["feedback_id"]
    return body, url


def test_preview_never_writes_to_terminal_and_send_submits_exact_preview_once(feedback_client):
    f = feedback_client
    raw = f.root / "feedback-test/raw/transcript.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"original transcript\n")
    body, url = prepare(f)
    assert body["delivery"]["can_send"]
    assert f.writes == []
    request = {"terminal_session_id": f.session.session_id, "prompt": "not the reviewed prompt"}
    for _ in range(2):
        response = f.client.post(url + "/send", json=request)
        assert response.status_code == 200, response.text
        assert response.json()["feedback"]["status"] == "submitted"
    assert f.writes == ["\x1b[200~" + body["feedback"]["prompt"] + "\x1b[201~", "\r"]
    assert f.client.get(url).json()["feedback"]["status"] == "submitted"
    assert raw.read_bytes() == b"original transcript\n"


@pytest.mark.parametrize("execution", ["running", "settling"])
def test_busy_agent_keeps_draft_without_automatic_dispatch(feedback_client, execution):
    f = feedback_client
    f.state["turns"][-1]["execution_state"] = execution
    body, url = prepare(f)
    assert not body["delivery"]["can_send"]
    response = f.client.post(url + "/send", json={"terminal_session_id": f.session.session_id})
    assert response.status_code == 409
    assert (
        read_feedback("feedback-test", body["feedback"]["feedback_id"], f.root)["status"] == "draft"
    )
    assert not f.writes
    f.state["turns"][-1]["execution_state"] = "completed"
    assert f.client.get(url).json()["delivery"]["can_send"]


def test_other_session_and_stale_terminal_never_receive_feedback(feedback_client):
    f = feedback_client
    _, url = prepare(f)
    assert f.client.post(url + "/send", json={"terminal_session_id": "stale"}).status_code == 409
    f.session.claude_session_id = f.session.observer_session_id = "another-session"
    response = f.client.post(url + "/send", json={"terminal_session_id": f.session.session_id})
    assert response.status_code == 409
    assert "另一个会话" in response.json()["detail"]
    assert not f.writes


def test_existing_terminal_draft_is_preserved(feedback_client):
    f = feedback_client
    asyncio.run(f.session.write("尚未提交的内容"))
    body, url = prepare(f)
    assert not body["delivery"]["can_send"]
    assert (
        f.client.post(url + "/send", json={"terminal_session_id": f.session.session_id}).status_code
        == 409
    )
    assert f.writes == ["尚未提交的内容"]
    asyncio.run(f.session.write("\x15"))
    assert f.client.get(url).json()["delivery"]["can_send"]


def test_failed_delivery_is_not_retried_implicitly(feedback_client):
    f = feedback_client
    _, url = prepare(f)

    def fail(data):
        f.writes.append(data)
        raise OSError("connection closed during write")

    f.process.write = fail
    for _ in range(2):
        response = f.client.post(url + "/send", json={"terminal_session_id": f.session.session_id})
        assert response.status_code == 409
    assert len(f.writes) == 1
    assert f.client.get(url).json()["feedback"]["status"] == "delivery_uncertain"


def test_feedback_endpoint_validates_event_text_and_path(feedback_client):
    c = feedback_client.client
    assert (
        c.post(
            "/api/observations/feedback-test/events/missing/feedback", json={"content": "修正"}
        ).status_code
        == 404
    )
    assert (
        c.post(
            "/api/observations/feedback-test/events/event-1/feedback", json={"content": ""}
        ).status_code
        == 400
    )
    assert (
        c.get("/api/observations/feedback-test/event-feedback/not-a-feedback-id").status_code == 404
    )


def test_prompt_submission_cannot_interleave_with_terminal_keystrokes(feedback_client):
    f = feedback_client

    async def scenario():
        submit = asyncio.create_task(f.session.submit_prompt("多行\nprompt"))
        await asyncio.sleep(0.01)
        human = asyncio.create_task(f.session.write("next draft"))
        await asyncio.gather(submit, human)

    asyncio.run(scenario())
    assert f.writes == ["\x1b[200~多行\nprompt\x1b[201~", "\r", "next draft"]
    assert f.session.input_pending
