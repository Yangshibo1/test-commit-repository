import json
from pathlib import Path

import pytest

from opentrace.workflow_store import WorkflowError, WorkflowStore


def test_records_real_semantic_step_chain_and_file_lineage(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    raw = project / "raw.csv"
    raw.write_text("value\n1\n2\n", encoding="utf-8")
    store = WorkflowStore(project / ".opentrace" / "workflow.sqlite3")

    run = store.start_run("分析数值分布", project, [raw])
    plan = store.set_plan(
        run["run_id"],
        [
            {
                "node_id": "profile",
                "objective": "建立原始数值数据的质量概况",
                "step_type": "analyze",
            },
            {
                "node_id": "summarize",
                "objective": "汇总清洗后数值的分布",
                "depends_on": ["profile"],
                "step_type": "analyze",
            },
        ],
    )
    assert plan["plan_version"] == 1

    first = store.start_step(
        run_id=run["run_id"],
        node_id="profile",
        objective="建立原始数值数据的质量概况",
        input_files=["raw.csv"],
        completion_condition="生成可供后续步骤使用的质量概况文件",
        expected_output_roles=["step_output", "internal_intermediate"],
    )
    profile = project / "profile.json"
    profile.write_text('{"rows": 2, "missing": 0}', encoding="utf-8")
    scratch = project / "scratch.json"
    scratch.write_text('{"checked": true}', encoding="utf-8")
    completed = store.complete_step(
        step_id=first["step_id"],
        operation_summary="统计记录数和缺失值",
        operation_types=["profile"],
        programs=[{"path": "profile.py", "language": "python", "role": "analysis"}],
        output_files=[
            {"path": "profile.json", "role": "step_output"},
            {"path": "scratch.json", "role": "internal_intermediate"},
        ],
        processing_result={"status": "success", "input_rows": 2, "output_rows": 2},
        analysis_conclusion={"summary": "数据完整，可继续分析"},
    )
    assert completed["status"] == "completed"

    second = store.start_step(
        run_id=run["run_id"],
        node_id="summarize",
        objective="汇总清洗后数值的分布",
        input_files=["profile.json"],
        completion_condition="形成明确的分布结论",
        expected_output_roles=[],
    )
    store.complete_step(
        step_id=second["step_id"],
        operation_summary="根据质量概况解释数据规模",
        processing_result={"status": "success"},
        analysis_conclusion={"summary": "样本包含两条有效记录"},
    )
    store.finish_run(run["run_id"])

    export_path = store.export_run(run["run_id"])
    exported = json.loads(export_path.read_text(encoding="utf-8"))
    assert exported["run"]["status"] == "completed"
    assert exported["run"]["initial_file_versions"][0]["path"] == str(raw.resolve())
    assert len(exported["steps"]) == 2
    assert exported["steps"][1]["input_files"][0]["sha256"] == next(
        output["sha256"]
        for output in exported["steps"][0]["output_files"]
        if output["role"] == "step_output"
    )
    assert {item["role"] for item in exported["steps"][0]["output_files"]} == {
        "step_output",
        "internal_intermediate",
    }


def test_script_name_does_not_create_a_step_and_objective_gets_warning(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    store = WorkflowStore(tmp_path / "workflow.sqlite3")
    run = store.start_run("分析数据", project, [data])
    store.set_plan(
        run["run_id"],
        [{"node_id": "n1", "objective": "运行脚本", "step_type": "transform"}],
    )

    step = store.start_step(
        run_id=run["run_id"],
        node_id="n1",
        objective="运行脚本",
        input_files=["data.csv"],
        completion_condition="脚本成功",
    )

    assert step["step_id"].startswith("step_")
    assert step["granularity_warnings"]
    assert len(store.get_state(run["run_id"])["steps"]) == 1


def test_state_machine_rejects_materially_incomplete_transitions(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    store = WorkflowStore(tmp_path / "workflow.sqlite3")
    run = store.start_run("分析数据", project, [data])

    with pytest.raises(WorkflowError, match="plan"):
        store.start_step(
            run["run_id"], "n1", "分析数据质量", [data], "得到质量结论"
        )

    store.set_plan(
        run["run_id"],
        [{"node_id": "n1", "objective": "分析数据质量"}],
    )
    step = store.start_step(
        run["run_id"], "n1", "分析数据质量", [data], "得到质量结论"
    )
    with pytest.raises(WorkflowError, match="already has active step"):
        store.start_step(
            run["run_id"], "n1", "再次分析数据质量", [data], "得到另一结论"
        )
    with pytest.raises(WorkflowError, match="output files"):
        store.complete_step(step["step_id"], "检查数据")
    with pytest.raises(WorkflowError, match="active step"):
        store.finish_run(run["run_id"])


def test_pending_human_input_blocks_new_material_step(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    store = WorkflowStore(tmp_path / "workflow.sqlite3")
    run = store.start_run("分析数据", project, [data])
    store.set_plan(run["run_id"], [{"node_id": "n1", "objective": "分析数据质量"}])

    event = store.capture_user_input(run["run_id"], "请先确认缺失值口径")
    assert event["input_event_id"] in store.gate_reason(run["run_id"])
    with pytest.raises(WorkflowError, match="unresolved user input"):
        store.start_step(
            run["run_id"], "n1", "分析数据质量", [data], "得到质量结论"
        )

    result = store.classify_user_input(
        event["input_event_id"],
        "analysis_guidance",
        structured_summary="确认缺失值口径",
    )
    assert result["creates_human_contribution"] is True
    assert "apply_user_input" in store.gate_reason(run["run_id"])
    store.apply_user_input(
        event["input_event_id"],
        workflow_effect="当前 Step 使用统一的空字符串和 NA 缺失口径",
    )
    assert store.gate_reason(run["run_id"]).startswith("Start a semantic")
