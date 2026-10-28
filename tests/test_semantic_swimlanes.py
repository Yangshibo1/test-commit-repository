from copy import deepcopy
import json
import time

import pytest

from agentvast.observer.store import create_session
from agentvast.semantic import SEMANTIC_SCHEMA_VERSION
from agentvast.semantic.provider import SemanticConfig, SemanticProviderError
from agentvast.semantic.swimlanes import load_swimlanes, run_swimlanes, swimlane_progress, validate_groups


def source_workflow():
    return {"schema_version": SEMANTIC_SCHEMA_VERSION, "source_trace": {"session_id": "lanes-test"},
            "inference_run": {"inference_id": "original-stages"},
            "episodes": [{"episode_id": "ep" + str(i), "turn_id": "task-a"} for i in range(1, 7)],
            "semantic_nodes": [{"node_id": "n" + str(i), "sequence": i, "episode_ids": ["ep" + str(i)],
                                "title": "原阶段" + str(i), "event_ids": ["event" + str(i)],
                                "objective": {"value": "同一分析任务"}, "summary": {"value": "已记录行为"}}
                               for i in range(1, 7)],
            "relations": [{"relation_id": "next" + str(i), "from_node_id": "n" + str(i),
                           "to_node_id": "n" + str(i + 1), "type": "NEXT"} for i in range(1, 6)] + [
                {"relation_id": "fix", "from_node_id": "n5", "to_node_id": "n3", "type": "REFINES"}]}


def output():
    return {"groups": [{"lane": lane, "node_ids": ids, "title": "子目标" + str(i),
                        "summary": "保留原始阶段的关键结果与限制", "reason": "服务同一连续子目标", "confidence": "medium"}
                       for i, (lane, ids) in enumerate([
                           ("input", ["n1"]), ("planning", ["n2"]), ("execution", ["n3", "n4"]),
                           ("revision", ["n5"]), ("execution", ["n6"])])]}


@pytest.fixture
def session(tmp_path):
    root = tmp_path / "observations"
    create_session("lanes-test", tmp_path, root)
    path = root / "lanes-test" / "derived/semantic_workflow.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(source_workflow()))
    return root, path


class Provider:
    def __init__(self, failure=False):
        self.config = SemanticConfig("https://semantic.invalid", "test", "gpt-6.1-sol", reasoning_effort="medium")
        self.calls = []
        self.failure = failure

    def complete(self, prompt, stage, json_schema=None):
        self.calls.append(stage)
        if self.failure:
            raise SemanticProviderError("temporary failure")
        return output()


def test_valid_groups_preserve_stages_and_semantic_endpoints():
    assert validate_groups(output(), source_workflow()) == []
    bad = output()
    bad["groups"][2]["node_ids"] = ["n4", "n3"]
    assert validate_groups(bad, source_workflow())
    bad = output()
    bad["groups"][2]["node_ids"].append("n5")
    bad["groups"].pop(3)
    assert "cannot hide a semantic relation inside an aggregate" in validate_groups(bad, source_workflow())


@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown", "lane", "blank"])
def test_invalid_model_groupings_are_rejected(change):
    bad = output()
    if change == "missing": bad["groups"].pop()
    if change == "duplicate": bad["groups"][2]["node_ids"].append("n4")
    if change == "unknown": bad["groups"][0]["node_ids"] = ["unknown"]
    if change == "lane": bad["groups"][0]["lane"] = "random"
    if change == "blank": bad["groups"][0]["summary"] = " "
    assert validate_groups(bad, source_workflow())


def test_no_cross_turn_or_unknown_turn_merges():
    source = source_workflow()
    source["episodes"][3]["turn_id"] = "task-b"
    assert validate_groups(output(), source)
    source["episodes"][3]["turn_id"] = None
    assert validate_groups(output(), source)


def test_single_call_cache_and_source_change_invalidation(session):
    root, path = session
    original = path.read_bytes()
    provider = Provider()
    result = run_swimlanes("lanes-test", str(root), provider=provider)
    assert len(result["groups"]) == 5 and result["validation"]["stage_count"] == 6
    assert result["inference_run"]["reasoning_effort"] == "medium"
    assert provider.calls == ["semantic_swimlanes"]
    assert run_swimlanes("lanes-test", str(root), provider=provider) == result
    assert provider.calls == ["semantic_swimlanes"]
    assert path.read_bytes() == original
    assert swimlane_progress("lanes-test", str(root))["status"] == "ready"
    source = source_workflow()
    source["semantic_nodes"][0]["title"] = "复核后的标题"
    path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="已更新"):
        load_swimlanes("lanes-test", str(root))
    second = run_swimlanes("lanes-test", str(root), provider=provider)
    assert second["source_hash"] != result["source_hash"]
    assert len(list((root / "lanes-test/derived/semantic_swimlanes").glob("*.json"))) == 1


def test_partial_failure_retry_and_structural_repair(session):
    root, _ = session
    with pytest.raises(SemanticProviderError):
        run_swimlanes("lanes-test", str(root), provider=Provider(failure=True))
    assert swimlane_progress("lanes-test", str(root))["status"] == "partial"

    class Repair(Provider):
        def complete(self, prompt, stage, json_schema=None):
            value = super().complete(prompt, stage, json_schema)
            if stage == "semantic_swimlanes": value["groups"].pop()
            return value

    provider = Repair()
    result = run_swimlanes("lanes-test", str(root), provider=provider)
    assert provider.calls == ["semantic_swimlanes", "semantic_swimlanes_repair"]
    assert result["validation"]["valid"]


def test_source_changed_while_running_does_not_overwrite_result(session):
    root, path = session
    baseline = run_swimlanes("lanes-test", str(root), provider=Provider())
    class Changed(Provider):
        def complete(self, prompt, stage, json_schema=None):
            result = super().complete(prompt, stage, json_schema)
            source = source_workflow()
            source["semantic_nodes"][0]["title"] = "并发修改"
            path.write_text(json.dumps(source))
            return result
    with pytest.raises(ValueError, match="原阶段已改变"):
        run_swimlanes("lanes-test", str(root), force=True, provider=Changed())
    stored = json.loads((root / "lanes-test/derived/semantic_swimlanes.json").read_text())
    assert stored == baseline


def test_budget_keeps_all_stages_without_calling_model(session, monkeypatch):
    root, path = session
    source = source_workflow()
    source["semantic_nodes"][0]["summary"]["value"] = "内容" * 10000
    path.write_text(json.dumps(source))
    monkeypatch.setenv("AGENTVAST_EVENT_GLOBAL_MAX_CHARS", "10000")
    provider = Provider()
    with pytest.raises(ValueError, match="超出聚合预算"):
        run_swimlanes("lanes-test", str(root), provider=provider)
    assert provider.calls == []


def test_swimlane_api_generate_poll_and_read(session, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from agentvast.web_server import create_app
    import agentvast.semantic.swimlanes as module
    root, _ = session
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    monkeypatch.setenv("AGENTVAST_SEMANTIC_API_BASE_URL", "https://semantic.invalid")
    monkeypatch.setenv("AGENTVAST_SEMANTIC_MODEL", "gpt-6.1-sol")
    run = module.run_swimlanes
    monkeypatch.setattr(module, "run_swimlanes", lambda *args, **kwargs: run(*args, provider=Provider(), **kwargs))
    with TestClient(create_app(tmp_path)) as client:
        endpoint = "/api/observations/lanes-test/semantic/swimlanes"
        assert client.get(endpoint).status_code == 404
        assert client.post(endpoint + "/generate", json={}).status_code == 200
        for _ in range(100):
            progress = client.get(endpoint + "/progress").json()
            if progress["status"] == "ready": break
            time.sleep(.01)
        assert progress["status"] == "ready"
        assert client.get(endpoint).json()["validation"]["group_count"] == 5
