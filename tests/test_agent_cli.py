import json
from pathlib import Path

from opentrace.agent_cli import main
from opentrace.workflow_store import WorkflowStore


def test_agent_cli_records_complete_semantic_workflow(
    tmp_path: Path, monkeypatch, capsys
):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    database = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(database)
    run = store.start_run("分析数据", project, [data])
    monkeypatch.setenv("OPENTRACE_DB", str(database))
    monkeypatch.setenv("OPENTRACE_RUN_ID", run["run_id"])

    assert (
        main(
            [
                "set-plan",
                "--payload",
                json.dumps(
                    {
                        "nodes": [
                            {
                                "node_id": "n1",
                                "objective": "检查数据特征",
                                "step_type": "inspect",
                                "depends_on": [],
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "start-step",
                "--payload",
                json.dumps(
                    {
                        "node_id": "n1",
                        "objective": "检查数据特征",
                        "input_files": [str(data)],
                        "completion_condition": "得到结构和异常概览",
                        "expected_output_roles": ["step_output"],
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        == 0
    )
    started = json.loads(capsys.readouterr().out)
    step_id = started["result"]["step_id"]

    assert (
        main(
            [
                "complete-step",
                "--payload",
                json.dumps(
                    {
                        "step_id": step_id,
                        "operation_summary": "读取并汇总数据",
                        "operation_types": ["inspect", "aggregate"],
                        "processing_result": {"rows": 1},
                        "analysis_conclusion": {"summary": "未发现明显异常"},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["finish-run"]) == 0
    finished = json.loads(capsys.readouterr().out)
    assert finished["result"]["status"] == "completed"
    state = store.get_state(run["run_id"])
    assert state["steps"][0]["operation_summary"] == "读取并汇总数据"


def test_agent_cli_returns_structured_error(tmp_path: Path, monkeypatch, capsys):
    database = tmp_path / "workflow.sqlite3"
    monkeypatch.setenv("OPENTRACE_DB", str(database))
    monkeypatch.setenv("OPENTRACE_RUN_ID", "missing")

    assert main(["state"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
