import json
import sqlite3
from pathlib import Path

import pytest

from agentvast.workflow_store import WorkflowError, WorkflowStore


def make_run(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    raw = project / "raw.csv"
    raw.write_text("value\n1\n2\n", encoding="utf-8")
    store = WorkflowStore(project / ".agentvast" / "workflow.sqlite3")
    run = store.start_run("分析数值分布", project, [raw], checkpoint_mode="none")
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
    profile_id = plan["node_mapping"]["profile"]
    summarize_id = plan["node_mapping"]["summarize"]

    first = store.start_step(run["run_id"], profile_id)
    store.record_hook_event(
        run["run_id"],
        "PostToolUse",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "python scripts/profile.py raw.csv"},
        },
    )
    profile = Path(run["result_root"]) / "data" / f"{profile_id}_profile.json"
    profile.write_text('{"rows": 2, "missing": 0}', encoding="utf-8")
    store.complete_step(
        step_id=first["step_id"],
        input_files=["raw.csv"],
        operation_summary="读取原始文件并检查记录数与缺失值",
        result_summary="两条记录均完整。",
        analysis_conclusion=None,
        output_files=[profile],
    )

    second = store.start_step(run["run_id"], summarize_id)
    store.complete_step(
        step_id=second["step_id"],
        input_files=[profile],
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
    first_plan_node = exported["plan_revisions"][0]["nodes"][0]
    assert first_plan_node["node_id"] == profile_id
    assert first_plan_node["objective"] == "建立原始数据的质量概况"
    assert first_plan_node["depends_on"] == []
    first_export = exported["nodes"][0]
    assert first_export["plan_version"] == 1
    assert first_export["operation"]["commands"] == [
        "python scripts/profile.py raw.csv"
    ]
    assert first_export["operation"]["programs"] == []
    assert first_export["outputs"][0]["path"].endswith(
        f"data/{profile_id}_profile.json"
    )
    assert exported["nodes"][1]["inputs"][0] == first_export["outputs"][0]
    assert exported["file_lineage"] == [
        {
            "node_id": profile_id,
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
        store.start_step(run["run_id"], "n1")
    with pytest.raises(WorkflowError, match="acyclic"):
        store.set_plan(
            run["run_id"],
            [
                {"node_id": "a", "objective": "检查甲数据", "depends_on": ["b"]},
                {"node_id": "b", "objective": "检查乙数据", "depends_on": ["a"]},
            ],
        )

    plan = store.set_plan(
        run["run_id"],
        [
            {"node_id": "a", "objective": "检查数据"},
            {"node_id": "b", "objective": "解释结果", "depends_on": ["a"]},
        ],
    )
    a_id = plan["node_mapping"]["a"]
    b_id = plan["node_mapping"]["b"]
    with pytest.raises(WorkflowError, match="dependencies"):
        store.start_step(run["run_id"], b_id)
    with pytest.raises(WorkflowError, match="exactly match"):
        store.start_step(run["run_id"], a_id, objective="另一个目标")

    step = store.start_step(run["run_id"], a_id)
    with pytest.raises(WorkflowError, match="active node"):
        store.start_step(run["run_id"], a_id)
    with pytest.raises(WorkflowError, match="result_summary"):
        store.complete_step(step["step_id"], [raw], "检查数据", "")
    store.complete_step(step["step_id"], [raw], "检查数据", "检查完成")

    with pytest.raises(WorkflowError, match="already completed"):
        store.start_step(run["run_id"], a_id)
    with pytest.raises(WorkflowError, match="cannot be removed"):
        store.set_plan(
            run["run_id"],
            [{"node_id": b_id, "objective": "解释结果"}],
        )
    with pytest.raises(WorkflowError, match="every node"):
        store.finish_run(run["run_id"])


def test_external_input_is_discovered_at_completion(tmp_path: Path):
    project, raw, store, run = make_run(tmp_path)
    other = project / "undeclared.csv"
    other.write_text("x\n3\n", encoding="utf-8")
    plan = store.set_plan(
        run["run_id"], [{"node_id": "a", "objective": "检查数据"}]
    )
    step = store.start_step(run["run_id"], plan["node_mapping"]["a"])
    completed = store.complete_step(
        step["step_id"], [other], "读取新增输入", "新增输入包含一条记录"
    )
    assert completed["input_file_versions"][0]["path"] == str(other.resolve())


def test_plan_revision_trigger_and_completed_node_preservation(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    plan = store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    a_id = plan["node_mapping"]["a"]
    first = store.start_step(run["run_id"], a_id)
    store.complete_step(first["step_id"], [raw], "检查数据", "检查完成")

    revision = store.set_plan(
        run["run_id"],
        [
            {"node_id": a_id, "objective": "检查数据"},
            {"node_id": "b", "objective": "验证异常", "depends_on": [a_id]},
        ],
        trigger="human_intervention",
        change_reason="用户要求验证异常",
    )
    assert revision["plan_version"] == 2
    second = store.start_step(run["run_id"], revision["node_mapping"]["b"])
    assert second["plan_version"] == 2


def test_human_intervention_keeps_capture_context_and_filters_chat(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    plan = store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    a_id = plan["node_mapping"]["a"]
    step = store.start_step(run["run_id"], a_id)

    intervention = store.capture_user_input(run["run_id"], "先验证异常")
    store.classify_user_input(intervention["input_event_id"], "challenge")
    store.apply_user_input(
        intervention["input_event_id"],
        "当前 Step 增加异常复核",
    )
    chat = store.capture_user_input(run["run_id"], "谢谢")
    store.classify_user_input(chat["input_event_id"], "conversation_only")
    store.complete_step(step["step_id"], [raw], "检查并复核异常", "复核完成")
    store.finish_run(run["run_id"])

    exported = json.loads(
        store.export_run(run["run_id"]).read_text(encoding="utf-8")
    )
    assert len(exported["human_interventions"]) == 1
    recorded = exported["human_interventions"][0]
    assert recorded["active_node_id"] == a_id
    assert recorded["plan_version"] == 1
    assert recorded["workflow_effect"] == "当前 Step 增加异常复核"


def test_abort_preserves_truth_but_hides_raw_hook_events(tmp_path: Path):
    _, raw, store, run = make_run(tmp_path)
    plan = store.set_plan(run["run_id"], [{"node_id": "a", "objective": "检查数据"}])
    a_id = plan["node_mapping"]["a"]
    step = store.start_step(run["run_id"], a_id)
    store.abort_run(run["run_id"], "Claude API parameter error")

    exported = json.loads(
        store.export_run(run["run_id"]).read_text(encoding="utf-8")
    )
    assert exported["run"]["status"] == "aborted"
    assert exported["nodes"][0]["node_id"] == a_id
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


def test_every_plan_revision_requires_current_user_approval(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    store = WorkflowStore(project / ".agentvast" / "workflow.sqlite3")
    run = store.start_run("分析数据", project, [data], checkpoint_mode="plan")

    initial = store.set_plan(
        run["run_id"], [{"node_id": "profile", "objective": "检查数据结构"}]
    )
    profile_id = initial["node_mapping"]["profile"]
    state = store.get_state(run["run_id"])
    assert state["run"]["awaiting_user"] == 1
    assert state["run"]["checkpoint_kind"] == "plan"
    assert state["run"]["plan_approved_version"] is None

    approval = store.capture_user_input(run["run_id"], "确认初始计划")
    store.classify_user_input(approval["input_event_id"], "checkpoint_continue")
    state = store.get_state(run["run_id"])
    assert state["run"]["awaiting_user"] == 0
    assert state["run"]["plan_approved_version"] == 1

    step = store.start_step(run["run_id"], profile_id)
    store.complete_step(step["step_id"], [data], "检查数据", "检查完成")
    revised = store.set_plan(
        run["run_id"],
        [
            {"node_id": profile_id, "objective": "检查数据结构"},
            {
                "node_id": "analyze",
                "objective": "分析数据分布",
                "depends_on": [profile_id],
            },
        ],
        trigger="agent_replan",
        change_reason="数据结构检查完成后增加分布分析",
    )
    analyze_id = revised["node_mapping"]["analyze"]
    state = store.get_state(run["run_id"])
    assert state["plan"]["version"] == 2
    assert state["run"]["awaiting_user"] == 1
    assert state["run"]["checkpoint_kind"] == "plan"
    assert state["run"]["plan_approved_version"] == 1

    with pytest.raises(WorkflowError, match="checkpoint"):
        store.start_step(run["run_id"], analyze_id)
    with pytest.raises(WorkflowError, match="checkpoint user response"):
        store.set_plan(
            run["run_id"],
            revised["nodes"],
            trigger="agent_replan",
            change_reason="不应在未批准时继续叠加 Revision",
        )

    second_approval = store.capture_user_input(run["run_id"], "确认修订计划")
    store.classify_user_input(
        second_approval["input_event_id"], "checkpoint_continue"
    )
    state = store.get_state(run["run_id"])
    assert state["run"]["plan_approved_version"] == 2
    assert state["run"]["awaiting_user"] == 0
    assert store.start_step(run["run_id"], analyze_id)["plan_version"] == 2


def test_web_plan_edit_replaces_checkpoint_with_new_revision(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    store = WorkflowStore(project / ".agentvast" / "workflow.sqlite3")
    run = store.start_run("分析数据", project, [], checkpoint_mode="plan")
    initial = store.set_plan(
        run["run_id"], [{"node_id": "profile", "objective": "检查数据结构"}]
    )

    replacement = store.set_plan(
        run["run_id"],
        [
            {
                "node_id": initial["nodes"][0]["node_id"],
                "objective": "检查数据结构与完整性",
            }
        ],
        trigger="human_intervention",
        change_reason="用户在 Web 中细化分析目标",
        replace_plan_checkpoint=True,
    )

    state = store.get_state(run["run_id"])
    assert replacement["plan_version"] == 2
    assert replacement["next_action"] == "present-plan-and-wait-for-user"
    assert state["run"]["awaiting_user"] == 1
    assert state["run"]["checkpoint_kind"] == "plan"
    assert state["plan"]["version"] == 2
