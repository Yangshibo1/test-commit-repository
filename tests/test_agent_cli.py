import json
from pathlib import Path

from agentvast.agent_cli import main
from agentvast.workflow_store import WorkflowStore


def test_agent_cli_records_complete_semantic_workflow(
    tmp_path: Path, monkeypatch, capsys
):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    database = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(database)
    run = store.start_run("分析数据", project, [data], checkpoint_mode="none")
    monkeypatch.setenv("AGENTVAST_DB", str(database))
    monkeypatch.setenv("AGENTVAST_RUN_ID", run["run_id"])

    assert main(
        [
            "set-plan",
            "--payload",
            json.dumps(
                {
                    "nodes": [
                        {
                            "node_id": "n1",
                            "objective": "检查数据特征",
                            "depends_on": [],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        ]
    ) == 0
    plan_result = json.loads(capsys.readouterr().out)
    node_id = plan_result["result"]["node_mapping"]["n1"]

    assert main(
        [
            "start-node",
            "--payload",
            json.dumps(
                {"node_id": node_id},
                ensure_ascii=False,
            ),
        ]
    ) == 0
    started = json.loads(capsys.readouterr().out)
    assert started["result"]["node_id"] == node_id

    assert main(
        [
            "complete-node",
            "--payload",
            json.dumps(
                {
                    "node_id": node_id,
                    "input_files": [str(data)],
                    "operation_summary": "读取并汇总数据",
                    "result_summary": "读取到一条完整记录。",
                    "analysis_conclusion": "未发现明显异常。",
                    "output_files": [],
                },
                ensure_ascii=False,
            ),
        ]
    ) == 0
    capsys.readouterr()

    assert main(["finish-run"]) == 0
    finished = json.loads(capsys.readouterr().out)
    assert finished["result"]["status"] == "completed"
    state = store.get_state(run["run_id"])
    assert state["nodes"][0]["operation_summary"] == "读取并汇总数据"
    assert state["nodes"][0]["result_summary"] == "读取到一条完整记录。"


def test_agent_cli_rejects_legacy_complete_step_shape(
    tmp_path: Path, monkeypatch, capsys
):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    database = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(database)
    run = store.start_run("分析数据", project, [data], checkpoint_mode="none")
    plan = store.set_plan(
        run["run_id"], [{"node_id": "n1", "objective": "检查数据"}]
    )
    step = store.start_step(run["run_id"], plan["node_mapping"]["n1"])
    monkeypatch.setenv("AGENTVAST_DB", str(database))
    monkeypatch.setenv("AGENTVAST_RUN_ID", run["run_id"])

    assert main(
        [
            "complete-step",
            "--payload",
            json.dumps(
                {
                    "step_id": step["step_id"],
                    "operation_summary": "检查",
                    "processing_result": {"rows": 1},
                }
            ),
        ]
    ) == 2
    assert "processing_result" in json.loads(capsys.readouterr().err)["error"]


def test_agent_cli_returns_structured_error(tmp_path: Path, monkeypatch, capsys):
    database = tmp_path / "workflow.sqlite3"
    monkeypatch.setenv("AGENTVAST_DB", str(database))
    monkeypatch.setenv("AGENTVAST_RUN_ID", "missing")

    assert main(["state"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
