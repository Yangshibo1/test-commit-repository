import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from agentvast.observer.event_merger import derive_session
from agentvast.observer.store import create_session
from agentvast.observer.transcript_reader import snapshot_transcript
from agentvast.semantic.pipeline import (
    SemanticWorkflowPartialError,
    _bounded_value_with_meta,
    _evidence_digest,
    run_semantic_workflow,
)
from agentvast.semantic.provider import SemanticConfig, SemanticProvider, SemanticProviderError


@pytest.fixture
def semantic_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTVAST_SEMANTIC_CONCURRENCY", "4")
    root = tmp_path / "observations"
    session_id = "performance-session"
    source = tmp_path / "transcript.jsonl"
    records = []
    for index in range(6):
        records.extend(
            [
                {
                    "type": "user",
                    "sessionId": session_id,
                    "uuid": f"user-{index}",
                    "timestamp": f"2026-01-01T00:00:{index * 2:02d}+00:00",
                    "origin": {"kind": "human"},
                    "promptSource": "typed",
                    "message": {"role": "user", "content": f"总结数据第 {index} 部分"},
                },
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "uuid": f"assistant-{index}",
                    "parentUuid": f"user-{index}",
                    "timestamp": f"2026-01-01T00:00:{index * 2 + 1:02d}+00:00",
                    "message": {
                        "id": f"response-{index}",
                        "role": "assistant",
                        "stop_reason": "end_turn",
                        "content": [{"type": "text", "text": f"完成第 {index} 部分"}],
                    },
                },
            ]
        )
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    create_session(session_id, tmp_path, root)
    snapshot_transcript(session_id, source, root, attempts=1, delay=0)
    derive_session(session_id, str(root))
    return session_id, root


class MeasuredProvider:
    def __init__(self, fail=False, model="gpt-6-luna"):
        self.config = SemanticConfig("https://semantic.invalid", "test", model)
        self.fail = fail
        self.lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0
        self.barrier = threading.Barrier(4)
        self.stages = []

    def complete(self, prompt, stage, json_schema=None):
        with self.lock:
            self.stages.append(stage)
        source = json.loads(prompt.split("SOURCE:\n", 1)[1].split("\n\nJSON_SCHEMA:", 1)[0])
        if stage == "episode_boundaries":
            candidates = source["candidates"]
            return {
                "schema_version": "semantic-boundaries/0.1",
                "boundaries": [
                    {
                        "left_candidate_id": left["candidate_episode_id"],
                        "right_candidate_id": right["candidate_episode_id"],
                        "decision": "SPLIT",
                        "same_intent": False,
                        "reason": "不同用户任务",
                        "evidence_event_ids": [left["semantic_event_ids"][0]],
                        "confidence_level": "high",
                    }
                    for left, right in zip(candidates, candidates[1:])
                ],
            }
        if stage.startswith("semantic_annotation"):
            index = int(stage.rsplit("_", 1)[1])
            with self.lock:
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            try:
                # Force overlap and out-of-order completion without relying on
                # machine speed. Resume may have fewer than four remaining.
                if index <= 4 and not getattr(self, "resuming", False):
                    self.barrier.wait(timeout=5)
                if self.fail and index == 2:
                    raise SemanticProviderError(
                        "disconnect", stage=stage, retryable=True, attempts=1
                    )
                time.sleep((7 - index) * 0.005)
                episode = source["episode_evidence"]
                evidence = episode["allowed_event_ids"]
                return {
                    "schema_version": "semantic-annotation/0.2",
                    "nodes": [
                        {
                            "episode_ids": [episode["episode_id"]],
                            "title": f"总结阶段{index}",
                            "primary_activity": "Communication",
                            "activity_tags": [],
                            "objective": {"value": "总结用户数据", "evidence_event_ids": evidence},
                            "summary": {"value": "已返回数据摘要", "evidence_event_ids": evidence},
                            "outcome_claims": [],
                            "model_confidence": "medium",
                            "uncertainty_reason": "",
                            "abstained": False,
                        }
                    ],
                }
            finally:
                with self.lock:
                    self.active -= 1
        return {"schema_version": "semantic-relations/0.1", "relations": []}


def test_concurrent_annotation_keeps_order_and_measures_wall_time(semantic_session):
    session_id, root = semantic_session
    provider = MeasuredProvider()
    progress = []
    workflow = run_semantic_workflow(
        session_id, str(root), provider=provider, progress_callback=progress.append
    )
    assert provider.maximum_active == 4
    assert workflow["validation"]["valid"]
    assert [node["title"] for node in workflow["semantic_nodes"]] == [
        f"总结阶段{i}" for i in range(1, 7)
    ]
    metrics = workflow["inference_run"]
    assert metrics["model"] == "gpt-6-luna"
    assert metrics["call_count"] == metrics["request_count"] == 8
    assert metrics["elapsed_seconds"] > 0
    assert (
        sum(stage["elapsed_seconds"] for stage in metrics["stage_timings"])
        <= metrics["elapsed_seconds"] + 0.01
    )
    assert progress[-1]["call_count"] == 8
    percentages = [item["percent"] for item in progress]
    assert percentages == sorted(percentages)
    # Changing the model invalidates a complete cache even with identical events.
    changed = MeasuredProvider(model="another-model")
    newer = run_semantic_workflow(session_id, str(root), provider=changed)
    assert newer["inference_run"]["model"] == "another-model"
    assert newer["inference_run"]["inference_id"] != metrics["inference_id"]


def test_parallel_failure_preserves_other_checkpoints_and_resumes(semantic_session):
    session_id, root = semantic_session
    provider = MeasuredProvider(fail=True)
    with pytest.raises(SemanticWorkflowPartialError) as captured:
        run_semantic_workflow(session_id, str(root), provider=provider)
    inference_id = captured.value.inference_id
    stage_root = root / session_id / "derived/semantic_stages" / inference_id
    state = json.loads((stage_root / "inference_state.json").read_text())
    assert state["failed_episode"] == 2
    assert state["completed_episode_count"] == 3
    assert set(state["completed_episodes"]) == {
        json.loads(path.read_text())["episode_id"]
        for path in (stage_root / "annotations").glob("*-validation.json")
    }
    resumed_provider = MeasuredProvider()
    resumed_provider.resuming = True
    resumed = run_semantic_workflow(
        session_id, str(root), provider=resumed_provider, resume_inference=inference_id
    )
    assert resumed["validation"]["valid"]
    assert "episode_boundaries" not in resumed_provider.stages
    assert not {
        "semantic_annotation_001",
        "semantic_annotation_003",
        "semantic_annotation_004",
    } & set(resumed_provider.stages)
    assert resumed["inference_run"]["call_count"] == 9  # includes failed call
    assert resumed["inference_run"]["elapsed_seconds"] >= state["elapsed_seconds"]


def test_digest_uses_total_budget_and_retains_error_and_conclusion():
    text = (
        "开始\n"
        + "\n".join(f"row {i}: " + "x" * 100 for i in range(100))
        + "\nERROR: 文件不存在\n结论：不能确认结果"
    )
    digest = _evidence_digest(text, 1200)
    fragments = [
        digest["opening_excerpt"],
        digest["conclusion_excerpt"],
        *digest["headings"],
        *digest["key_lines"],
    ]
    assert sum(map(len, fragments)) <= 1200
    assert digest["truncated"] and digest["original_length"] == len(text)
    assert digest["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert "ERROR: 文件不存在" in "".join(fragments)
    assert "结论：不能确认结果" in "".join(fragments)
    value, meta = _bounded_value_with_meta(
        {"file_path": "/data/result.json", "content": ["x" * 2000] * 40}, 1200
    )
    assert len(value["file_path"]) + sum(map(len, value["content"])) <= 1200
    assert value["file_path"] == "/data/result.json"
    assert meta["truncated"]


def test_provider_counts_format_fallback_and_usage():
    from urllib.error import HTTPError

    class Provider(SemanticProvider):
        def _post(self, payload):
            if payload["response_format"]["type"] == "json_schema":
                raise HTTPError("https://semantic.invalid", 400, "unsupported", {}, None)
            return {
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }

    provider = Provider(
        SemanticConfig("https://semantic.invalid", "test", "gpt-6-luna", request_interval_seconds=0)
    )
    meta = provider.complete("JSON", "test", json_schema={"type": "object"})[
        "_semantic_provider_meta"
    ]
    assert meta["http_requests"] == 2 and meta["attempts"] == 1
    assert meta["input_chars"] == 4
    assert meta["usage"]["prompt_tokens"] == 12


def test_provider_limits_request_starts_without_serializing_responses():
    from concurrent.futures import ThreadPoolExecutor

    class Provider(SemanticProvider):
        def __init__(self):
            super().__init__(
                SemanticConfig(
                    "https://semantic.invalid",
                    "test",
                    "gpt-6-luna",
                    request_interval_seconds=0.025,
                    response_mode="json_object",
                )
            )
            self.starts = []
            self.active = 0
            self.maximum_active = 0
            self.lock = threading.Lock()

        def _post(self, payload):
            with self.lock:
                self.starts.append(time.monotonic())
                self.active += 1
                self.maximum_active = max(self.maximum_active, self.active)
            time.sleep(0.12)
            with self.lock:
                self.active -= 1
            return {"choices": [{"message": {"content": '{"ok":true}'}}]}

    provider = Provider()
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda i: provider.complete("JSON", f"annotation_{i}"), range(4)))
    assert all(value["ok"] for value in values)
    assert provider.maximum_active >= 2
    assert all(
        right - left >= 0.015
        for left, right in zip(sorted(provider.starts), sorted(provider.starts)[1:])
    )


def test_progress_api_returns_latest_completed_metrics(semantic_session, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from agentvast.web_server import create_app

    session_id, root = semantic_session
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    monkeypatch.setenv("AGENTVAST_SEMANTIC_MODEL", "gpt-6-luna")
    workflow = run_semantic_workflow(session_id, str(root), provider=MeasuredProvider())
    # An earlier interrupted run must not hide the latest successful result.
    earlier = (
        root / session_id / "derived/semantic_stages/semantic-000000000000/inference_state.json"
    )
    earlier.parent.mkdir(parents=True)
    earlier.write_text(json.dumps({"status": "partial", "inference_id": "semantic-000000000000"}))
    import os

    os.utime(earlier, (1, 1))
    client = TestClient(create_app(tmp_path))
    progress = client.get(f"/api/observations/{session_id}/semantic/progress").json()
    assert progress["status"] == "ready"
    assert progress["model"] == "gpt-6-luna"
    assert progress["call_count"] == workflow["inference_run"]["call_count"]
    assert progress["stage_timings"]
    idle = client.get("/api/observations/unused-session/semantic/progress").json()
    assert idle["status"] == "idle" and idle["model"] == "gpt-6-luna"
