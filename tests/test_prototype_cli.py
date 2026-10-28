import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentvast.cli import _claude_environment, main
from agentvast.web_server import (
    _PosixPtyProcess,
    TerminalSession,
    _open_local_file,
    _pty_arguments,
    _resolve_observer_artifact_file,
    create_app,
)
from agentvast.workflow_store import WorkflowStore
from agentvast.observer.store import create_session, update_manifest


def test_web_transcript_serves_original_snapshot_without_deriving(tmp_path: Path, monkeypatch):
    pytest.importorskip("httpx")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    root = tmp_path / "observations"
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(root))
    snapshot = root / "session-original" / "transcript" / "transcript.jsonl"
    snapshot.parent.mkdir(parents=True)
    original = b'{"type":"user","message":{"content":"hello"}}\r\ninvalid json\n'
    snapshot.write_bytes(original)
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/observations/session-original/transcript")

    assert response.status_code == 200
    assert response.content == original
    assert response.headers["cache-control"] == "no-store"
    assert not (root / "session-original" / "derived").exists()
    assert client.get("/api/observations/session-missing/transcript").status_code == 404
    assert not (root / "session-missing").exists()
    assert client.get("/api/observations/invalid!session/transcript").status_code == 404


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


@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY is unavailable")
def test_posix_terminal_starts_at_requested_size_and_resizes(tmp_path: Path):
    process = _PosixPtyProcess.spawn(
        [
            sys.executable,
            "-u",
            "-c",
            "import os; print(tuple(os.get_terminal_size()), flush=True); "
            "input(); print(tuple(os.get_terminal_size()), flush=True)",
        ],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        dimensions=(43, 151),
    )
    try:
        output = ""
        while "(151, 43)" not in output:
            output += process.read(4096)
        process.setwinsize(28, 76)
        process.write("\n")
        while "(76, 28)" not in output:
            output += process.read(4096)
        assert "(151, 43)" in output
        assert "(76, 28)" in output
        assert process._collect_exit(block=True)
        assert process.exitstatus == 0
    finally:
        process.close(True)


@pytest.mark.skipif(os.name != "posix", reason="Bash wrapper is POSIX-only")
def test_claude_wrapper_preserves_native_configuration_and_arguments(tmp_path: Path):
    wrapper = tmp_path / "claude_ccs.sh"
    wrapper.write_text((Path(__file__).resolve().parents[1] / "claude_ccs.sh").read_text())
    (tmp_path / ".env").write_text("echo 'project config was loaded'; exit 99\n")
    executable = tmp_path / "claude"
    executable.write_text(
        "#!{0}\nimport os, sys, json\n"
        "print(json.dumps({{'args': sys.argv[1:], 'base': os.getenv('ANTHROPIC_BASE_URL'), "
        "'key': os.getenv('ANTHROPIC_API_KEY')}}))\n".format(sys.executable)
    )
    executable.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(wrapper), "--resume", "session-native"],
        env={
            "PATH": os.defpath,
            "CLAUDE_BIN": str(executable),
            "ANTHROPIC_BASE_URL": "https://user-config.example",
            "ANTHROPIC_API_KEY": "test-user-key",
            "AGENTVAST_SEMANTIC_MODEL": "old-model",
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert json.loads(result.stdout) == {
        "args": ["--resume", "session-native"],
        "base": "https://user-config.example",
        "key": "test-user-key",
    }


@pytest.mark.skipif(os.name != "posix", reason="POSIX PTY is unavailable")
def test_posix_web_terminal_process_supports_interactive_io(tmp_path: Path):
    process = _PosixPtyProcess.spawn(
        [
            sys.executable,
            "-u",
            "-c",
            "value = input(); print('VALUE:' + value, flush=True)",
        ],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        dimensions=(30, 100),
    )

    try:
        process.setwinsize(40, 120)
        process.write("hello\n")
        output = ""
        while process.isalive() or "VALUE:hello" not in output:
            try:
                output += process.read(4096)
            except EOFError:
                break
        assert "VALUE:hello" in output
        assert not process.isalive()
        assert process.exitstatus == 0
    finally:
        process.close(True)


def test_web_terminal_finalizes_passive_observation(tmp_path: Path):
    session_id = "session-web-observer"
    project = tmp_path / "project"
    project.mkdir()
    root = tmp_path / "observations"
    transcript = tmp_path / "transcript.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "prompt-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "origin": {"kind": "human"},
            "promptSource": "typed",
            "message": {"role": "user", "content": "hello"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "response-1",
            "parentUuid": "prompt-1",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "message": {
                "id": "message-1",
                "role": "assistant",
                "model": "test-model",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "hello back"}],
            },
        },
    ]
    transcript.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    create_session(session_id, project, root)
    update_manifest(session_id, {"transcript_source_path": str(transcript)}, root)
    session = TerminalSession(
        process=SimpleNamespace(isalive=lambda: False, exitstatus=0, closed=True),
        project_root=project,
        claude_command="claude",
        full_permissions=True,
        claude_session_id=session_id,
        database_path=project / ".agentvast" / "workflow.sqlite3",
        observer_root=root,
    )

    asyncio.run(session.finalize_observation())

    directory = root / session_id
    assert session.observer_status == "ready"
    assert session.observer_derived is True
    assert (directory / "raw" / "transcript.jsonl").is_file()
    assert (directory / "derived" / "events.jsonl").is_file()
    assert (directory / "derived" / "observer_trace.json").is_file()
    assert (directory / "diagnostics" / "validation_report.json").is_file()


def test_terminal_size_follows_interacting_client_and_releases_on_disconnect(tmp_path: Path):
    sizes = []
    session = TerminalSession(
        process=SimpleNamespace(
            isalive=lambda: True, setwinsize=lambda rows, cols: sizes.append((rows, cols))
        ),
        project_root=tmp_path,
        claude_command="claude",
        full_permissions=True,
        claude_session_id="size-test",
        database_path=tmp_path / "db.sqlite3",
        observer_root=tmp_path,
    )

    async def scenario():
        desktop, _ = session.subscribe()
        preview, _ = session.subscribe()
        await session.resize(40, 160, client=desktop)
        await session.resize(30, 45, client=preview)
        assert sizes[-1] == (40, 160)
        await session.claim_size(desktop)
        count = len(sizes)
        await session.resize(60, 200, client=preview)
        assert len(sizes) == count
        await session.resize(35, 110, client=desktop)
        assert sizes[-1] == (35, 110)
        await session.claim_size(preview)
        assert sizes[-1] == (60, 200)
        session.unsubscribe(preview)
        await session.resize(28, 80, client=desktop)
        assert sizes[-1] == (28, 80)
        session.release_size(desktop)
        assert not session._client_sizes

    asyncio.run(scenario())


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


def test_unchanged_terminal_sizes_do_not_redraw_pty(tmp_path: Path):
    sizes = []
    session = TerminalSession(
        process=SimpleNamespace(
            isalive=lambda: True, setwinsize=lambda rows, cols: sizes.append((rows, cols))
        ),
        project_root=tmp_path,
        claude_command="claude",
        full_permissions=True,
        claude_session_id="resize-dedup",
        database_path=tmp_path / "db.sqlite3",
        observer_root=tmp_path,
    )

    async def scenario():
        desktop, _ = session.subscribe()
        preview, _ = session.subscribe()
        await session.resize(40, 160, client=desktop)
        for _ in range(20):
            await session.resize(40, 160, client=desktop)
            await session.resize(24, 80, client=preview)
            await session.claim_size(desktop)
        assert sizes == [(40, 160)]
        await session.resize(45, 170, client=desktop)
        assert sizes == [(40, 160), (45, 170)]
        for _ in range(10):
            await session.resize(24, 80, client=preview)
        assert len(sizes) == 2

    asyncio.run(scenario())


def test_pty_write_preserves_utf8_when_os_write_is_partial(monkeypatch):
    from agentvast.web_server import _PosixPtyProcess

    received = bytearray()
    interrupted = [False]

    def partial_write(fd, data):
        if not interrupted[0]:
            interrupted[0] = True
            raise InterruptedError
        chunk = data[:2]
        received.extend(chunk)
        return len(chunk)

    monkeypatch.setattr("agentvast.web_server.os.write", partial_write)
    process = _PosixPtyProcess(123, 42)
    value = "连续追问与中文输入 🚀"
    assert process.write(value) == len(value.encode())
    assert received.decode() == value
