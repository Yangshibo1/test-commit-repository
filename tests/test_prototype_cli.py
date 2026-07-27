import json
from pathlib import Path

from opentrace.cli import main
from opentrace.workflow_store import WorkflowStore


def test_run_no_launch_creates_bound_run(tmp_path: Path, capsys):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    plugin = Path(__file__).resolve().parents[1] / "claude-plugin"

    result = main(
        [
            "run",
            "--task",
            "分析数据质量",
            "--project",
            str(project),
            "--data",
            str(data),
            "--plugin-dir",
            str(plugin),
            "--no-launch",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    store = WorkflowStore(payload["database"])
    state = store.get_state(payload["run_id"])
    assert state["run"]["claude_session_id"] == payload["claude_session_id"]
    assert payload["launch_command"][1] == "--session-id"
    assert str(data.resolve()) in payload["launch_command"][-1]
