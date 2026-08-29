import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentvast.cli import main as agentvast_main
from agentvast.observer.cli import _environment
from agentvast.observer.event_merger import derive_session
from agentvast.observer.hook_collector import collect_event
from agentvast.observer.otel_collector import record_otel_request
from agentvast.observer.store import (
    append_raw_event,
    create_session,
    iter_jsonl,
    read_manifest,
    register_session_root,
)
from agentvast.observer.transcript_reader import snapshot_transcript
from agentvast.observer.trace_builder import list_observer_sessions
from agentvast.observer.validation import validate_session
from agentvast.paths import expose_repository_to_python


def hook(session_id: str, event_name: str, **values):
    return {
        "session_id": session_id,
        "cwd": values.pop("cwd", "C:/analysis"),
        "transcript_path": values.pop("transcript_path", "C:/transcript.jsonl"),
        "hook_event_name": event_name,
        **values,
    }


def test_hook_collector_preserves_raw_payload_and_monotonic_sequence(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(tmp_path))
    session_id = "session-observer"
    first_payload = hook(session_id, "SessionStart", model="claude-test")
    second_payload = hook(session_id, "UserPromptSubmit", prompt="inspect data")

    first = collect_event(first_payload)
    second = collect_event(second_payload)

    assert first["raw_payload"] == first_payload
    assert second["raw_payload"] == second_payload
    assert first["observer_sequence"] == 1
    assert second["observer_sequence"] == 2
    assert first["observer_event_id"] != second["observer_event_id"]
    stored = list(iter_jsonl(tmp_path / session_id / "raw" / "hooks.jsonl"))
    assert [item["observer_sequence"] for item in stored] == [1, 2]
    manifest = read_manifest(session_id, tmp_path)
    assert manifest["sources"]["hooks"] is True
    assert manifest["transcript_source_path"] == "C:/transcript.jsonl"


def test_transcript_snapshot_keeps_raw_and_invalid_lines(tmp_path: Path):
    session_id = "session-transcript"
    source = tmp_path / "claude.jsonl"
    source.write_text('{"type":"user","text":"hello"}\nnot-json\n', encoding="utf-8")
    root = tmp_path / "observations"
    create_session(session_id, tmp_path, root)

    result = snapshot_transcript(
        session_id, source, root, attempts=1, delay=0
    )

    assert result["record_count"] == 2
    assert result["invalid_record_count"] == 1
    assert (root / session_id / "transcript" / "transcript.jsonl").read_text(
        encoding="utf-8"
    ) == source.read_text(encoding="utf-8")
    envelopes = list(iter_jsonl(root / session_id / "raw" / "transcript.jsonl"))
    assert envelopes[0]["parsed"] is True
    assert envelopes[1] == {
        "line_number": 2,
        "parsed": False,
        "raw_line": "not-json",
    }


def test_transcript_only_session_builds_degraded_canonical_trajectory(tmp_path: Path):
    session_id = "session-transcript-fallback"
    root = tmp_path / "observations"
    source = tmp_path / "native-transcript.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "promptId": "prompt-1",
            "uuid": "user-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {"role": "user", "content": "inspect data"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-1",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "message": {
                "id": "message-1",
                "role": "assistant",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Read",
                        "input": {"file_path": "data.csv"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "user-2",
            "timestamp": "2026-01-01T00:00:02+00:00",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "rows=10",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-2",
            "timestamp": "2026-01-01T00:00:03+00:00",
            "message": {
                "id": "message-2",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "Inspection complete."}],
            },
        },
    ]
    source.write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    create_session(session_id, tmp_path, root)
    snapshot_transcript(session_id, source, root, attempts=1, delay=0)

    derived = derive_session(session_id, str(root))
    report = validate_session(session_id, str(root))

    assert derived["tool_call_count"] == 1
    assert derived["message_count"] == 2
    assert report["valid"] is False
    assert report["usable"] is True
    assert report["degraded"] is True
    assert report["capture_mode"] == "transcript_fallback"
    assert report["counts"]["tool_calls"] == 1
    assert report["counts"]["transcript_reconstructed_tool_calls"] == 1
    assert report["counts"]["prompts"] == 1
    assert "reconstructed from the native transcript" in " ".join(report["warnings"])
    tools = list(iter_jsonl(root / session_id / "derived" / "tool_calls.jsonl"))
    assert tools[0]["tool"]["name"] == "Read"
    assert tools[0]["tool"]["output"] == "rows=10"


def test_transcript_trace_filters_local_commands_and_rebuilds_tool_batch(tmp_path: Path):
    session_id = "session-observer-trace"
    root = tmp_path / "observations"
    source = tmp_path / "trace.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "prompt-uuid",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "origin": {"kind": "human"},
            "promptSource": "typed",
            "message": {"role": "user", "content": "检查数据"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-a",
            "parentUuid": "prompt-uuid",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "message": {
                "id": "response-batch",
                "role": "assistant",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-a",
                        "name": "Glob",
                        "input": {"pattern": "*"},
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-b",
            "parentUuid": "assistant-a",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "message": {
                "id": "response-batch",
                "role": "assistant",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-b",
                        "name": "Read",
                        "input": {"file_path": "data.txt", "pages": ""},
                    }
                ],
            },
        },
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "result-a",
            "parentUuid": "assistant-a",
            "timestamp": "2026-01-01T00:00:02+00:00",
            "toolUseResult": {"durationMs": 25, "filenames": ["data.txt"]},
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool-a", "content": "data.txt"}
                ],
            },
        },
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "result-b",
            "parentUuid": "assistant-b",
            "timestamp": "2026-01-01T00:00:02+00:00",
            "toolUseResult": "invalid pages",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-b",
                        "content": "invalid pages",
                        "is_error": True,
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-final",
            "parentUuid": "result-a",
            "timestamp": "2026-01-01T00:00:03+00:00",
            "message": {
                "id": "response-final",
                "role": "assistant",
                "model": "claude-test",
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "检查完成"}],
            },
        },
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "exit-uuid",
            "timestamp": "2026-01-01T00:00:04+00:00",
            "message": {"role": "user", "content": "<command-name>/exit</command-name>"},
        },
    ]
    source.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )
    create_session(session_id, tmp_path, root)
    snapshot_transcript(session_id, source, root, attempts=1, delay=0)

    derive_session(session_id, str(root))
    trace_path = root / session_id / "derived" / "observer_trace.json"
    first = json.loads(trace_path.read_text(encoding="utf-8"))
    first_ids = [item["event_id"] for item in first["events"]]
    canonical_path = root / session_id / "derived" / "canonical_events.jsonl"
    first_canonical_ids = [item["event_id"] for item in iter_jsonl(canonical_path)]
    derive_session(session_id, str(root))
    second = json.loads(trace_path.read_text(encoding="utf-8"))

    assert first["metrics"]["human_prompt_count"] == 1
    assert first["metrics"]["tool_call_count"] == 2
    assert first["metrics"]["tool_error_count"] == 1
    assert first["diagnostics"]["filtered_non_human_user_records"] == 1
    responses = [item for item in first["events"] if item["event_type"] == "model_response"]
    assert len(responses) == 1
    assert responses[0]["payload"]["tool_use_ids"] == ["tool-a", "tool-b"]
    tools = [item for item in first["events"] if item["event_type"] == "tool_execution"]
    glob = next(item for item in tools if item["tool_use_id"] == "tool-a")
    assert glob["payload"]["duration_ms"] == 25
    assert glob["payload"]["structured_result"]["filenames"] == ["data.txt"]
    assert first_ids == [item["event_id"] for item in second["events"]]
    assert first_canonical_ids == [item["event_id"] for item in iter_jsonl(canonical_path)]
    sessions = list_observer_sessions(str(root))
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["metrics"]["human_prompt_count"] == 1
    messages = list(iter_jsonl(root / session_id / "derived" / "messages.jsonl"))
    assert [item["event_type"] for item in messages] == [
        "user_prompt",
        "assistant_message",
    ]


def test_otel_collector_preserves_exact_body_and_decodes_json(tmp_path: Path):
    session_id = "session-otel"
    body = json.dumps({"resourceLogs": [{"scopeLogs": []}]}).encode("utf-8")

    event = record_otel_request(
        session_id,
        "/v1/logs",
        {"Content-Type": "application/json"},
        body,
        str(tmp_path),
    )

    payload = event["raw_payload"]
    assert base64.b64decode(payload["body_base64"]) == body
    assert payload["decoded"] == {"resourceLogs": [{"scopeLogs": []}]}
    assert payload["decoded_format"] == "json"


def test_otel_collector_preserves_undecodable_protobuf(tmp_path: Path):
    body = b"\x08\xff\x00not-valid-otlp"

    event = record_otel_request(
        "session-otel-binary",
        "/v1/logs",
        {"Content-Type": "application/x-protobuf"},
        body,
        str(tmp_path),
    )

    payload = event["raw_payload"]
    assert base64.b64decode(payload["body_base64"]) == body
    assert payload["decoded"] is None
    assert payload["decode_error"]


def test_merger_reconstructs_tool_message_and_valid_session(tmp_path: Path):
    root = tmp_path / "observations"
    session_id = "session-derive"
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"prompt_id": "prompt-1", "tool_use_id": "tool-1"}) + "\n",
        encoding="utf-8",
    )
    create_session(session_id, tmp_path, root)
    events = [
        hook(session_id, "SessionStart", transcript_path=str(transcript)),
        hook(
            session_id,
            "UserPromptSubmit",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            prompt="inspect data",
        ),
        hook(
            session_id,
            "MessageDisplay",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            turn_id="turn-1",
            message_id="display-1",
            index=0,
            final=False,
            delta="I will inspect ",
        ),
        hook(
            session_id,
            "MessageDisplay",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            turn_id="turn-1",
            message_id="display-1",
            index=1,
            final=True,
            delta="the data.",
        ),
        hook(
            session_id,
            "PreToolUse",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            tool_use_id="tool-1",
            tool_name="Read",
            tool_input={"file_path": "data.csv"},
        ),
        hook(
            session_id,
            "PostToolUse",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            tool_use_id="tool-1",
            tool_name="Read",
            tool_input={"file_path": "data.csv"},
            tool_response={"filePath": "data.csv", "success": True},
        ),
        hook(
            session_id,
            "Stop",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            last_assistant_message="done",
        ),
        hook(session_id, "SessionEnd", transcript_path=str(transcript), reason="other"),
    ]
    for payload in events:
        append_raw_event(session_id, "hook", payload, root)
    otel_payload = {
        "resourceLogs": [
            {
                "scopeLogs": [
                    {
                        "logRecords": [
                            {
                                "attributes": [
                                    {
                                        "key": "tool_use_id",
                                        "value": {"stringValue": "tool-1"},
                                    },
                                    {
                                        "key": "prompt.id",
                                        "value": {"stringValue": "prompt-1"},
                                    },
                                    {
                                        "key": "event.name",
                                        "value": {"stringValue": "tool_result"},
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    record_otel_request(
        session_id,
        "/v1/logs",
        {"Content-Type": "application/json"},
        json.dumps(otel_payload).encode("utf-8"),
        str(root),
    )
    snapshot_transcript(session_id, transcript, root, attempts=1, delay=0)

    derived = derive_session(session_id, str(root))
    report = validate_session(session_id, str(root))

    assert derived["tool_call_count"] == 1
    assert derived["message_count"] == 1
    tool_calls = list(iter_jsonl(root / session_id / "derived" / "tool_calls.jsonl"))
    assert tool_calls[0]["tool"]["success"] is True
    assert tool_calls[0]["tool"]["input"] == {"file_path": "data.csv"}
    assert tool_calls[0]["field_origins"]["event_order"] == "derived"
    assert {item["source"] for item in tool_calls[0]["evidence"]} == {
        "hook",
        "otel",
        "transcript",
    }
    messages = list(iter_jsonl(root / session_id / "derived" / "messages.jsonl"))
    assert messages[0]["message"]["content"] == "I will inspect the data."
    assert messages[0]["origin"] == "derived"
    assert report["valid"] is True
    assert report["counts"]["matched_tool_calls"] == 1
    assert report["counts"]["otel_matched_tool_calls"] == 1
    assert report["counts"]["transcript_matched_tool_calls"] == 1
    assert report["counts"]["matched_prompts"] == 1


def test_incomplete_message_display_falls_back_to_complete_transcript(tmp_path: Path):
    root = tmp_path / "observations"
    session_id = "session-incomplete-message"
    transcript = tmp_path / "transcript.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "promptId": "prompt-1",
            "uuid": "user-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {"role": "user", "content": "summarize"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-1",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "message": {
                "id": "response-1",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "完整的中文回答"}],
            },
        },
    ]
    transcript.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )
    create_session(session_id, tmp_path, root)
    events = [
        hook(session_id, "SessionStart", transcript_path=str(transcript)),
        hook(
            session_id,
            "UserPromptSubmit",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            prompt="summarize",
        ),
        hook(
            session_id,
            "MessageDisplay",
            transcript_path=str(transcript),
            prompt_id="prompt-1",
            turn_id="turn-1",
            message_id="display-1",
            index=9,
            final=False,
            delta="残缺且乱码的片段",
        ),
        hook(session_id, "SessionEnd", transcript_path=str(transcript)),
    ]
    for payload in events:
        append_raw_event(session_id, "hook", payload, root)
    snapshot_transcript(session_id, transcript, root, attempts=1, delay=0)

    derive_session(session_id, str(root))
    report = validate_session(session_id, str(root))
    messages = list(iter_jsonl(root / session_id / "derived" / "messages.jsonl"))
    assistant_messages = [
        item for item in messages if item["event_type"] == "assistant_message"
    ]

    assert len(assistant_messages) == 1
    assert assistant_messages[0]["message"]["content"] == "完整的中文回答"
    assert assistant_messages[0]["message"]["capture_source"] == "transcript_fallback"
    assert report["valid"] is False
    assert report["usable"] is True
    assert report["capture_mode"] == "hybrid_fallback"
    assert report["counts"]["message_display_streams"] == 1
    assert report["counts"]["incomplete_message_display_streams"] == 1
    assert report["incomplete_message_displays"][0]["observed_indexes"] == [9]
    assert report["incomplete_message_displays"][0]["final_seen"] is False
    assert "incomplete MessageDisplay" in " ".join(report["warnings"])


def test_observe_cli_no_launch_creates_passive_manifest(
    tmp_path: Path, capsys, monkeypatch
):
    project = tmp_path / "project"
    project.mkdir()
    root = tmp_path / "observations"
    monkeypatch.setenv("AGENTVAST_OBSERVER_REGISTRY", str(tmp_path / "registry"))
    plugin = Path(__file__).resolve().parents[1] / "claude-observer-plugin"

    result = agentvast_main(
        [
            "observe",
            "start",
            "--project",
            str(project),
            "--session-id",
            "session-cli",
            "--storage-root",
            str(root),
            "--plugin-dir",
            str(plugin),
            "--no-otel",
            "--no-launch",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["observer_mode"] == "passive"
    assert payload["hook_profile"] == "modern"
    assert payload["launch_command"][1:] == [
        "--session-id",
        "session-cli",
        "--plugin-dir",
        str(plugin.resolve()),
    ]
    manifest = read_manifest("session-cli", root)
    assert manifest["cwd"] == str(project.resolve())
    assert manifest["sources"] == {
        "hooks": False,
        "otel": False,
        "transcript": False,
        "raw_api": False,
    }

    with pytest.raises(SystemExit) as duplicate:
        agentvast_main(
            [
                "observe",
                "start",
                "--project",
                str(project),
                "--session-id",
                "session-cli",
                "--storage-root",
                str(root),
                "--plugin-dir",
                str(plugin),
                "--no-otel",
                "--no-launch",
            ]
        )
    assert duplicate.value.code == 2
    assert "cannot be overwritten" in capsys.readouterr().err

def test_observer_plugin_never_declares_control_output():
    plugin = Path(__file__).resolve().parents[1] / "claude-observer-plugin"
    hooks = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    serialized = json.dumps(hooks)

    assert "permissionDecision" not in serialized
    assert "additionalContext" not in serialized
    assert "stopReason" not in serialized
    assert "UserPromptSubmit" in hooks["hooks"]
    assert "PostToolUse" in hooks["hooks"]
    assert "SessionEnd" in hooks["hooks"]
    assert "${CLAUDE_PLUGIN_ROOT}/scripts/hook_collector.py" in serialized
    assert "MessageDisplay" in hooks["hooks"]
    assert "PostToolBatch" in hooks["hooks"]
    assert '"async": true' in serialized
    assert "async" not in hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]


def test_observer_environment_preserves_user_runtime_paths(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PATH", "C:\\user-runtime")
    monkeypatch.setenv("PYTHONPATH", "C:\\user-pythonpath")
    monkeypatch.setenv("AGENTVAST_OBSERVER_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENTVAST_OBSERVER_SESSION_ID", "hidden-session")
    monkeypatch.setenv("AGENTVAST_OBSERVER_REGISTRY", str(tmp_path / "registry"))

    environment = _environment()

    assert environment["PATH"] == "C:\\user-runtime"
    assert environment["PYTHONPATH"] == "C:\\user-pythonpath"
    assert not any(name.startswith("AGENTVAST_OBSERVER_") for name in environment)


def test_plugin_hook_runner_is_silent_without_changing_pythonpath(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "observations"
    project = tmp_path / "external-project"
    project.mkdir()
    registry = tmp_path / "registry"
    monkeypatch.setenv("AGENTVAST_OBSERVER_REGISTRY", str(registry))
    register_session_root("session-silent", root)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    runner = (
        Path(__file__).resolve().parents[1]
        / "claude-observer-plugin"
        / "scripts"
        / "hook_collector.py"
    )
    payload = hook("session-silent", "UserPromptSubmit", prompt="hello")

    result = subprocess.run(
        [sys.executable, str(runner)],
        input=json.dumps(payload),
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert (root / "session-silent" / "raw" / "hooks.jsonl").exists()


def test_concurrent_hook_processes_keep_unique_contiguous_sequence(tmp_path: Path):
    root = tmp_path / "observations"
    environment = os.environ.copy()
    expose_repository_to_python(environment)
    code = (
        "import sys; "
        "from agentvast.observer.store import append_raw_event; "
        "root,session,worker=sys.argv[1:4]; "
        "[append_raw_event(session,'hook',{'hook_event_name':'PostToolUse',"
        "'session_id':session,'worker':worker,'index':i},root) for i in range(10)]"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(root), "session-concurrent", str(index)],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(4)
    ]
    errors = []
    for process in processes:
        _, stderr = process.communicate(timeout=20)
        if process.returncode:
            errors.append(stderr)
    assert not errors

    events = list(
        iter_jsonl(root / "session-concurrent" / "raw" / "hooks.jsonl")
    )
    sequences = sorted(item["observer_sequence"] for item in events)
    assert len(events) == 40
    assert sequences == list(range(1, 41))
    assert len({item["observer_event_id"] for item in events}) == 40


def test_partial_hook_terminal_event_is_recovered_from_transcript(tmp_path: Path):
    root = tmp_path / "observations"
    session_id = "session-hybrid"
    source = tmp_path / "hybrid.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": session_id,
            "promptId": "prompt-1",
            "uuid": "user-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "message": {"role": "user", "content": "read data"},
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-1",
            "timestamp": "2026-01-01T00:00:01+00:00",
            "message": {
                "id": "message-1",
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool-hybrid",
                        "name": "Read",
                        "input": {"file_path": "data.csv"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "sessionId": session_id,
            "uuid": "user-2",
            "timestamp": "2026-01-01T00:00:02+00:00",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-hybrid",
                        "content": "rows=10",
                    }
                ],
            },
        },
        {
            "type": "assistant",
            "sessionId": session_id,
            "uuid": "assistant-2",
            "timestamp": "2026-01-01T00:00:03+00:00",
            "message": {
                "id": "message-2",
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
            },
        },
    ]
    source.write_text(
        "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8"
    )
    create_session(session_id, tmp_path, root)
    append_raw_event(
        session_id,
        "hook",
        hook(session_id, "SessionStart", transcript_path=str(source)),
        root,
    )
    append_raw_event(
        session_id,
        "hook",
        hook(
            session_id,
            "PreToolUse",
            transcript_path=str(source),
            prompt_id="prompt-1",
            tool_use_id="tool-hybrid",
            tool_name="Read",
            tool_input={"file_path": "data.csv"},
        ),
        root,
    )
    append_raw_event(
        session_id,
        "hook",
        hook(session_id, "SessionEnd", transcript_path=str(source)),
        root,
    )
    snapshot_transcript(session_id, source, root, attempts=1, delay=0)

    derive_session(session_id, str(root))
    report = validate_session(session_id, str(root))
    tools = list(iter_jsonl(root / session_id / "derived" / "tool_calls.jsonl"))

    assert tools[0]["tool"]["output"] == "rows=10"
    assert tools[0]["tool"]["success"] is True
    assert report["capture_mode"] == "hybrid_fallback"
    assert report["counts"]["unmatched_tool_calls"] == 0
    assert report["counts"]["transcript_recovered_hook_tools"] == 1
