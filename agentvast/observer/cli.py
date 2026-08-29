"""CLI lifecycle for passive Claude Code observation sessions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentvast.observer.event_merger import derive_session
from agentvast.observer.otel_collector import decode_available
from agentvast.observer.store import (
    create_session,
    default_observations_root,
    ensure_session_layout,
    iter_jsonl,
    read_manifest,
    register_session_root,
    session_directory,
    update_manifest,
)
from agentvast.observer.transcript_reader import finalize_session
from agentvast.observer.validation import validate_session
from agentvast.paths import expose_repository_to_python, resolve_user_path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBSERVER_PLUGIN = REPOSITORY_ROOT / "claude-observer-plugin"


def configure_parser(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="observe_command", required=True)

    start = subparsers.add_parser("start", help="Start a passive Claude observation session")
    start.add_argument("--project", default=".")
    start.add_argument("--session-id")
    start.add_argument("--storage-root")
    start.add_argument("--claude-command", default="claude")
    start.add_argument("--plugin-dir", default=str(DEFAULT_OBSERVER_PLUGIN))
    start.add_argument("--permission-mode")
    start.add_argument("--otel-host", default="127.0.0.1")
    start.add_argument("--otel-port", type=int, default=0)
    start.add_argument("--no-otel", action="store_true")
    start.add_argument("--capture-api-bodies", action="store_true")
    start.add_argument("--drain-seconds", type=float, default=1.0)
    start.add_argument("--no-launch", action="store_true")

    status = subparsers.add_parser("status", help="Show one observer session")
    status.add_argument("session_id", nargs="?")
    status.add_argument("--storage-root")

    stop = subparsers.add_parser("stop", help="Finalize transcript and manifest")
    stop.add_argument("session_id", nargs="?")
    stop.add_argument("--storage-root")
    stop.add_argument(
        "--transcript-path",
        help="Recover/finalize from an explicitly supplied Claude transcript path",
    )

    sessions = subparsers.add_parser("sessions", help="List observer sessions")
    sessions.add_argument("--storage-root")

    derive = subparsers.add_parser("derive", help="Build canonical observed trajectory")
    derive.add_argument("session_id")
    derive.add_argument("--storage-root")

    validate = subparsers.add_parser("validate", help="Validate observation completeness")
    validate.add_argument("session_id")
    validate.add_argument("--storage-root")

    semantic = subparsers.add_parser(
        "semantic", help="Build an evidence-grounded semantic workflow"
    )
    semantic.add_argument("session_id")
    semantic.add_argument("--storage-root")
    semantic.add_argument(
        "--rules-only",
        action="store_true",
        help="Use conservative deterministic annotations without a model",
    )
    semantic.add_argument("--force", action="store_true")

    export = subparsers.add_parser("export", help="Export an observation session as ZIP")
    export.add_argument("session_id")
    export.add_argument("--storage-root")
    export.add_argument("--output")


def _root(value: Optional[str]) -> Path:
    return resolve_user_path(value) if value else default_observations_root()


def _resolve_claude(command: str) -> str:
    value = str(command or "").strip().strip('"')
    candidate = Path(os.path.expandvars(value)).expanduser()
    if candidate.is_file():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if not resolved:
        raise RuntimeError("Claude Code executable was not found: {0}".format(value))
    return resolved


def _claude_version(executable: str) -> Optional[str]:
    command = _claude_arguments(executable, ["--version"])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or result.stderr).strip() or None


def _claude_arguments(executable: str, arguments: List[str]) -> List[str]:
    if Path(executable).suffix.lower() in {".cmd", ".bat"}:
        return [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            executable,
            *arguments,
        ]
    return [executable, *arguments]


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as stream:
        stream.bind((host, 0))
        return int(stream.getsockname()[1])


def _wait_for_collector(
    endpoint: str, diagnostics_path: Optional[Path] = None, timeout: float = 5.0
) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last_error: Optional[BaseException] = None
    while time.monotonic() < deadline:
        try:
            with opener.open(endpoint.rstrip("/") + "/health", timeout=0.5) as response:
                if response.status == 200:
                    return
        except BaseException as error:
            last_error = error
            time.sleep(0.05)
    suffix = " Review {0}.".format(diagnostics_path) if diagnostics_path is not None else ""
    raise RuntimeError("OTel collector did not become ready: {0}.{1}".format(last_error, suffix))


def _collector_process(
    session_id: str, root: Path, host: str, port: int, environment: Dict[str, str]
) -> subprocess.Popen:
    command = [
        sys.executable,
        "-m",
        "agentvast.observer.otel_collector",
        "--session-id",
        session_id,
        "--root",
        str(root),
        "--host",
        host,
        "--port",
        str(port),
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    collector_environment = environment.copy()
    expose_repository_to_python(collector_environment)
    diagnostics = ensure_session_layout(session_id, root) / "diagnostics"
    stdout = (diagnostics / "otel_collector.stdout.log").open("ab")
    stderr = (diagnostics / "otel_collector.stderr.log").open("ab")
    try:
        return subprocess.Popen(
            command,
            env=collector_environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()


def _environment() -> Dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "AGENTVAST_OBSERVER_ROOT",
        "AGENTVAST_OBSERVER_SESSION_ID",
        "AGENTVAST_OBSERVER_REGISTRY",
    ):
        environment.pop(name, None)
    return environment


def _observation_counts(session_id: str, root: Path) -> Dict[str, int]:
    directory = ensure_session_layout(session_id, root)
    return {
        "hook_events": sum(1 for _ in iter_jsonl(directory / "raw" / "hooks.jsonl")),
        "otel_exports": sum(1 for _ in iter_jsonl(directory / "raw" / "otel.jsonl")),
        "transcript_records": sum(1 for _ in iter_jsonl(directory / "raw" / "transcript.jsonl")),
        "canonical_events": sum(
            1 for _ in iter_jsonl(directory / "derived" / "canonical_events.jsonl")
        ),
    }


def _sessions(root: Path) -> List[Dict[str, Any]]:
    if not root.is_dir():
        return []
    result: List[Dict[str, Any]] = []
    for path in root.iterdir():
        if not path.is_dir() or not (path / "manifest.json").exists():
            continue
        manifest = read_manifest(path.name, root)
        result.append(
            {
                "session_id": path.name,
                "started_at": manifest.get("started_at"),
                "ended_at": manifest.get("ended_at"),
                "cwd": manifest.get("cwd"),
                "sources": manifest.get("sources"),
            }
        )
    return sorted(result, key=lambda item: str(item.get("started_at") or ""), reverse=True)


def _select_session(session_id: Optional[str], root: Path) -> str:
    if session_id:
        return session_id
    sessions = _sessions(root)
    if not sessions:
        raise RuntimeError("no observer sessions exist")
    active = [item for item in sessions if not item.get("ended_at")]
    return str((active or sessions)[0]["session_id"])


def command_start(args: argparse.Namespace) -> int:
    project = resolve_user_path(args.project)
    if not project.is_dir():
        raise RuntimeError("Claude project directory does not exist: {0}".format(project))
    root = _root(args.storage_root)
    session_id = args.session_id or str(uuid.uuid4())
    existing_directory = session_directory(session_id, root)
    if (existing_directory / "manifest.json").exists():
        raise RuntimeError(
            "observer session already exists and cannot be overwritten: {0}".format(session_id)
        )
    plugin_dir = resolve_user_path(args.plugin_dir)
    if not plugin_dir.is_dir():
        raise RuntimeError("observer plugin directory does not exist: {0}".format(plugin_dir))
    if shutil.which("python") is None:
        raise RuntimeError(
            "observer hooks require the existing Claude environment to provide "
            "a 'python' command in PATH"
        )
    executable = _resolve_claude(args.claude_command) if not args.no_launch else args.claude_command
    version = _claude_version(executable) if not args.no_launch else None
    create_session(
        session_id,
        project,
        root,
        claude_code_version=version,
        raw_api=args.capture_api_bodies,
    )
    register_session_root(session_id, root)
    update_manifest(
        session_id,
        {"collector": {"hook_profile": "modern"}},
        root,
    )
    environment = _environment()
    arguments = ["--session-id", session_id, "--plugin-dir", str(plugin_dir)]
    if args.permission_mode:
        arguments.extend(["--permission-mode", args.permission_mode])

    collector: Optional[subprocess.Popen] = None
    endpoint: Optional[str] = None
    port = args.otel_port
    if not args.no_otel:
        port = port or (4318 if args.no_launch else _free_port(args.otel_host))
        endpoint = "http://{0}:{1}".format(args.otel_host, port)
        environment.update(
            {
                "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                "OTEL_LOGS_EXPORTER": "otlp",
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
                "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
                "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": endpoint + "/v1/logs",
                "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": endpoint + "/v1/traces",
                "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": endpoint + "/v1/metrics",
                "OTEL_LOG_USER_PROMPTS": "1",
                "OTEL_LOG_TOOL_DETAILS": "1",
            }
        )
    if args.capture_api_bodies:
        api_dir = ensure_session_layout(session_id, root) / "raw" / "api"
        environment["OTEL_LOG_RAW_API_BODIES"] = "file:{0}".format(api_dir)

    launch = {
        "observer_mode": "passive",
        "session_id": session_id,
        "project": str(project),
        "storage_root": str(root),
        "session_directory": str(ensure_session_layout(session_id, root)),
        "plugin_dir": str(plugin_dir),
        "hook_profile": "modern",
        "otel_endpoint": endpoint,
        "otel_decode_available": decode_available(),
        "capture_raw_api": bool(args.capture_api_bodies),
        "launch_command": _claude_arguments(str(executable), arguments),
    }
    print(json.dumps(launch, ensure_ascii=False, indent=2))
    if args.no_launch:
        return 0

    try:
        if endpoint:
            collector = _collector_process(session_id, root, args.otel_host, port, environment)
            _wait_for_collector(
                endpoint,
                ensure_session_layout(session_id, root)
                / "diagnostics"
                / "otel_collector.stderr.log",
            )
            update_manifest(
                session_id,
                {
                    "sources": {"otel": True},
                    "collector": {
                        "otel_endpoint": endpoint,
                        "otel_decode_available": decode_available(),
                        "otel_collector_pid": collector.pid,
                    },
                },
                root,
            )
        result = subprocess.run(
            _claude_arguments(str(executable), arguments),
            cwd=str(project),
            env=environment,
            check=False,
        )
        return int(result.returncode)
    finally:
        try:
            if not args.no_launch and args.drain_seconds > 0:
                time.sleep(min(args.drain_seconds, 10.0))
            finalize_session(session_id, root)
        finally:
            if collector is not None and collector.poll() is None:
                collector.terminate()
                try:
                    collector.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    collector.kill()


def execute(args: argparse.Namespace) -> int:
    root = _root(getattr(args, "storage_root", None))
    if args.observe_command == "start":
        return command_start(args)
    if args.observe_command == "sessions":
        print(json.dumps(_sessions(root), ensure_ascii=False, indent=2))
        return 0
    session_id = _select_session(getattr(args, "session_id", None), root)
    if args.observe_command == "status":
        print(
            json.dumps(
                {
                    "manifest": read_manifest(session_id, root),
                    "counts": _observation_counts(session_id, root),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.observe_command == "stop":
        print(
            json.dumps(
                finalize_session(
                    session_id,
                    root,
                    transcript_path=getattr(args, "transcript_path", None),
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.observe_command == "derive":
        print(json.dumps(derive_session(session_id, str(root)), ensure_ascii=False, indent=2))
        return 0
    if args.observe_command == "validate":
        print(json.dumps(validate_session(session_id, str(root)), ensure_ascii=False, indent=2))
        return 0
    if args.observe_command == "semantic":
        from agentvast.semantic.pipeline import run_semantic_workflow

        workflow = run_semantic_workflow(
            session_id,
            str(root),
            rules_only=bool(args.rules_only),
            force=bool(args.force),
        )
        print(
            json.dumps(
                {
                    "session_id": session_id,
                    "inference_id": workflow["inference_run"]["inference_id"],
                    "method": workflow["inference_run"]["method"],
                    "episode_count": len(workflow["episodes"]),
                    "semantic_node_count": len(workflow["semantic_nodes"]),
                    "relation_count": len(workflow["relations"]),
                    "valid": workflow["validation"]["valid"],
                    "warnings": workflow["inference_run"]["warnings"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.observe_command == "export":
        directory = ensure_session_layout(session_id, root)
        output = (
            Path(args.output).expanduser().resolve()
            if args.output
            else Path.cwd() / ("agentvast-observation-" + session_id + ".zip")
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        base = str(output.with_suffix(""))
        archive = shutil.make_archive(base, "zip", root_dir=str(directory))
        if Path(archive) != output:
            os.replace(archive, output)
        print(str(output))
        return 0
    raise RuntimeError("unsupported observe command: {0}".format(args.observe_command))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="agentvast observe")
    configure_parser(parser)
    try:
        return execute(parser.parse_args(argv))
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, "AgentVAST observer error: {0}\n".format(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
