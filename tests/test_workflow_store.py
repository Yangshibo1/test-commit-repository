import json
import sqlite3
from pathlib import Path

import pytest

from opentrace.workflow_store import WorkflowError, WorkflowStore


def make_run(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    raw = project / "raw.csv"
    raw.write_text("value\n1\n2\n", encoding="utf-8")
    store = WorkflowStore(project / ".opentrace" / "workflow.sqlite3")
    run = store.start_run("分析数值分布", project, [raw])
    return project, raw, store, run


def test_records_normalized_semantic_chain_and_file_lineage(tmp_path: Path):
    project, raw, store, run = make_run(tmp_path)
    plan = store.set_plan(
        run["run_id"],
        [
            {"node_id": "profile", "objective": "建立原始数据的质量概况"},
            {
                "node_id": "summarize",
                "objective": "解释数据的主要分布与异常",
                "depends_on": ["profile"],
            },
        ],
    )
    assert plan["trigger"] == "initial"

    first = store.start_step(run["run_id"], "profile", ["raw.csv"])
    store.record_hook_event(
        run["run_id"],
        "PostToolUse",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python scripts/profile.py raw.csv"},
        },
    )
    profile = project / "profile.json"
    profile.write_text('{"rows": 2, "missing": 0}', encoding="utf-8")
    store.complete_step(
        step_id=first["step_id"],
        operation_summary="读取原始文件并检查记录数与缺失值",
        result_summary="两条记录均完整。",
        analysis_conclusion=None,
        output_files=["profile.json"],
    )

    second = store.start_step(run["run_id"], "summarize", ["profile.json"])
    store.complete_step(
        step_id=second["step_id"],
        operation_summary="根据质量概况解释数据规模",
        result_summary="样本包含两条有效记录。",
        analysis_conclusion="样本过小，分布结论仅适用于描述当前文件。",
    )
    store.finish_run(run["run_id"])

    exported = json.loads(
        store.export_run(run["run_id"]).read_text(encoding="utf-8")
    )
    assert set(exported) == {
        "schema_version",
        "run",
        "plan_revisions",
        "nodes",
        "human_interventions",
        "file_lineage",
    }
    assert exported["run"]["declared_inputs"] == [
        {"path": "raw.csv", "sha256": exported["nodes"][0]["inputs"][0]["sha256"]}
    ]
    assert "size" not in exported["run"]["declared_inputs"][0]
    assert exported["plan_revisions"][0]["nodes"][0] == {
        "node_id": "profile",
        "objective": "建立原始数据的质量概况",
        "depends_on": [],
    }
    first_export = exported["nodes"][0]
    assert first_export["plan_version"] == 1
    assert first_export["operation"]["commands"] == [
        "python scripts/profile.py raw.csv"
    ]
    assert first_export["operation"]["programs"] == [
        "scripts/profile.py"
    ]
    assert first_export["outputs"][0]["path"] == "profile.json"
    assert exported["nodes"][1]["inputs"][0] == first_export["outputs"][0]
    assert exported["file_lineage"] == [
        {
            "node_id": "profile",
            "inputs": first_export["inputs"],
            "outputs": first_export["outputs"],
        }
    ]
    serialized = json.dumps(exported, ensure_ascii=False)
    for removed in (
        "execution_events",
        "processing_result",
        "algorithms",
        "parameters",
        "operation_types",
        "expected_output_roles",
        '"role"',
    ):
        assert removed not in serialized


def test_plan_and_step_invariants_are_enforced(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    with pytest.raises(WorkflowError, match="plan"):
        store.start_step(run["run_id"], "n1", [raw])
    with pytest.raises(WorkflowError, match="acyclic"):
        store.set_plan(
            run["run_id"],
            [
                {"node_id": "a", "objective": "A", "depends_on": ["b"]},
                {"node_id": "b", "objective": "B", "depends_on": ["a"]},
            ],
        )

    store.set_plan(
        run["run_id"],
        [
            {"node_id": "a", "objective": "检查数据"},
            {"node_id": "b", "objective": "解释结果", "depends_on": ["a"]},
        ],
    )
    with pytest.raises(WorkflowError, match="dependencies"):
        store.start_step(run["run_id"], "b", [raw])
    with pytest.raises(WorkflowError, match="exactly match"):
        store.start_step(run["run_id"], "a", [raw], objective="另一个目标")

    step = store.start_step(run["run_id"], "a", [raw])
    with pytest.raises(WorkflowError, match="active node"):
        store.start_step(run["run_id"], "a", [raw])
    with pytest.raises(WorkflowError, match="result_summary"):
        store.complete_step(step["step_id"], "检查数据", "")
    store.complete_step(step["step_id"], "检查数据", "检查完成")

    with pytest.raises(WorkflowError, match="already has"):
        store.start_step(run["run_id"], "a", [raw])
    with pytest.raises(WorkflowError, match="cannot remove"):
        store.set_plan(
            run["run_id"],
            [{"node_id": "b", "objective": "解释结果"}],
        )
    with pytest.raises(WorkflowError, match="every node"):
        store.finish_run(run["run_id"])


def test_step_input_must_have_file_lineage(tmp_path: Path):
    project, raw, store, run = make_run(tmp_path)
    other = project / "undeclared.csv"
    other.write_text("x\n3\n", encoding="utf-8")
    store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    with pytest.raises(WorkflowError, match="declared Run inputs"):
        store.start_step(run["run_id"], "a", [other])


def test_plan_revision_trigger_and_completed_node_preservation(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    first = store.start_step(run["run_id"], "a", [raw])
    store.complete_step(first["step_id"], "检查数据", "检查完成")

    revision = store.set_plan(
        run["run_id"],
        [
            {"node_id": "a", "objective": "检查数据"},
            {"node_id": "b", "objective": "验证异常", "depends_on": ["a"]},
        ],
        trigger="human_intervention",
        change_reason="用户要求验证异常",
    )
    assert revision["plan_version"] == 2
    second = store.start_step(run["run_id"], "b", [raw])
    assert second["plan_version"] == 2


def test_human_intervention_keeps_capture_context_and_filters_chat(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    step = store.start_step(run["run_id"], "a", [raw])

    intervention = store.capture_user_input(run["run_id"], "先验证异常")
    store.classify_user_input(intervention["input_event_id"], "challenge")
    store.apply_user_input(
        intervention["input_event_id"],
        "当前 Step 增加异常复核",
    )
    chat = store.capture_user_input(run["run_id"], "谢谢")
    store.classify_user_input(chat["input_event_id"], "conversation_only")
    store.complete_step(step["step_id"], "检查并复核异常", "复核完成")
    store.finish_run(run["run_id"])

    exported = json.loads(
        store.export_run(run["run_id"]).read_text(encoding="utf-8")
    )
    assert len(exported["human_interventions"]) == 1
    recorded = exported["human_interventions"][0]
    assert recorded["active_node_id"] == "a"
    assert recorded["plan_version"] == 1
    assert recorded["workflow_effect"] == "当前 Step 增加异常复核"


def test_abort_preserves_truth_but_hides_raw_hook_events(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    step = store.start_step(run["run_id"], "a", [raw])
    store.abort_run(run["run_id"], "Claude API parameter error")

    exported = json.loads(
        store.export_run(run["run_id"]).read_text(encoding="utf-8")
    )
    assert exported["run"]["status"] == "aborted"
    assert exported["nodes"][0]["node_id"] == "a"
    assert exported["nodes"][0]["status"] == "interrupted"
    assert "execution_events" not in exported


def test_existing_database_is_migrated_without_deleting_history(tmp_path: Path):
    database = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE plan_revisions (
            run_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            nodes_json TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, version)
        );
        CREATE TABLE steps (
            step_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            objective TEXT NOT NULL,
            target_data TEXT,
            completion_condition TEXT NOT NULL,
            expected_output_roles_json TEXT NOT NULL,
            operation_summary TEXT,
            operation_types_json TEXT,
            parameters_json TEXT,
            algorithms_json TEXT,
            programs_json TEXT,
            processing_result_json TEXT,
            analysis_conclusion_json TEXT,
            warnings_json TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT
        );
        """
    )
    connection.close()

    WorkflowStore(database)
    migrated = sqlite3.connect(database)
    plan_columns = {row[1] for row in migrated.execute("PRAGMA table_info(plan_revisions)")}
    step_columns = {row[1] for row in migrated.execute("PRAGMA table_info(steps)")}
    migrated.close()
    assert "trigger_kind" in plan_columns
    assert {"plan_version", "commands_json", "result_summary", "analysis_conclusion"} <= step_columns
