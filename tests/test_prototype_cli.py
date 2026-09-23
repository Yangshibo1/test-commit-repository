import json
from pathlib import Path

from agentvast.cli import _claude_environment, main
from agentvast.web_server import (
    _open_local_file,
    _pty_arguments,
    _resolve_observer_artifact_file,
)
from agentvast.workflow_store import WorkflowStore


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
    assert "--dangerously-skip-permissions" in payload["launch_command"]
    assert "--session-id" in payload["launch_command"]
    assert str(data.resolve()) in payload["launch_command"][-1]


def test_web_terminal_always_uses_full_permissions(tmp_path: Path, monkeypatch):
    claude = tmp_path / "claude.exe"
    claude.write_bytes(b"")
    monkeypatch.setattr("agentvast.web_server._resolve_claude", lambda _command: str(claude))

    arguments = _pty_arguments(
        "claude",
        "session-web",
        tmp_path / "plugin",
        False,
    )

    assert arguments[1] == "--dangerously-skip-permissions"


def test_observer_artifact_link_only_opens_recorded_project_file(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    artifact = project / "report.md"
    artifact.write_text("# report\n", encoding="utf-8")
    trace = {
        "session": {"cwd": str(project)},
        "artifacts": [{"artifact_id": "artifact-1", "path": "report.md"}],
    }

    assert _resolve_observer_artifact_file(trace, "artifact-1") == artifact.resolve()

    outside = tmp_path / "outside.md"
    outside.write_text("outside\n", encoding="utf-8")
    trace["artifacts"] = [{"artifact_id": "artifact-2", "path": str(outside)}]
    try:
        _resolve_observer_artifact_file(trace, "artifact-2")
    except PermissionError:
        pass
    else:
        raise AssertionError("artifact links must not escape the observed project")


def test_open_local_file_uses_windows_default_application(tmp_path: Path, monkeypatch):
    artifact = tmp_path / "report.md"
    artifact.write_text("# report\n", encoding="utf-8")
    opened = []
    monkeypatch.setattr("agentvast.web_server.sys.platform", "win32")
    monkeypatch.setattr(
        "agentvast.web_server.os.startfile",
        lambda value: opened.append(value),
        raising=False,
    )

    _open_local_file(artifact)

    assert opened == [str(artifact)]


def test_abort_command_keeps_failed_run_history(tmp_path: Path, capsys):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    store = WorkflowStore(project / ".agentvast" / "workflow.sqlite3")
    run = store.start_run("分析数据", project, [data])

    result = main(
        [
            "abort",
            run["run_id"],
            "--project",
            str(project),
            "--reason",
            "Claude API error",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "aborted"
    assert store.get_state(run["run_id"])["run"]["status"] == "aborted"


def test_claude_environment_configures_cli_recorder_without_tool_search_override(
    tmp_path: Path,
):
    project = tmp_path / "project"
    project.mkdir()
    store = WorkflowStore(tmp_path / "workflow.sqlite3")

    run = store.start_run("测试环境变量", project, [], checkpoint_mode="none")
    environment = _claude_environment(
        store, run["run_id"], project, compact_window=200_000, compact_percent=80
    )

    assert environment["AGENTVAST_RUN_ID"] == run["run_id"]
    assert environment["AGENTVAST_DB"] == str(store.db_path)
    assert str(Path(__file__).resolve().parents[1]) in environment["PYTHONPATH"]
    assert "ENABLE_TOOL_SEARCH" not in environment
    assert environment["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "200000"
    assert environment["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "80"
