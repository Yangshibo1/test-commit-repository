"""Command-line entry point for the OpenTrace Claude Code prototype."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from opentrace.workflow_store import WorkflowError, WorkflowStore


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent
DEFAULT_PLUGIN_DIR = REPOSITORY_ROOT / "claude-plugin"


def default_db(project_root: Path) -> Path:
    return project_root / ".opentrace" / "workflow.sqlite3"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opentrace",
        description="Record Claude Code data-analysis workflows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Create a Run and start Claude Code")
    run.add_argument("--task", required=True, help="Data-analysis task for Claude Code")
    run.add_argument("--project", default=".", help="Claude Code project directory")
    run.add_argument(
        "--data",
        nargs="+",
        default=[],
        help="Initial data files, relative to the project or absolute",
    )
    run.add_argument("--db", help="SQLite database path")
    run.add_argument("--plugin-dir", default=str(DEFAULT_PLUGIN_DIR))
    run.add_argument("--claude-command", default="claude")
    run.add_argument(
        "--no-launch",
        action="store_true",
        help="Create the Run and print launch information without starting Claude",
    )

    resume = subparsers.add_parser("resume", help="Resume Claude Code for an existing Run")
    resume.add_argument("run_id")
    resume.add_argument("--project", default=".")
    resume.add_argument("--db")
    resume.add_argument("--plugin-dir", default=str(DEFAULT_PLUGIN_DIR))
    resume.add_argument("--claude-command", default="claude")
    resume.add_argument("--no-launch", action="store_true")

    state = subparsers.add_parser("state", help="Print current Run state")
    state.add_argument("run_id")
    state.add_argument("--project", default=".")
    state.add_argument("--db")

    export = subparsers.add_parser("export", help="Export a Run as JSON")
    export.add_argument("run_id")
    export.add_argument("--project", default=".")
    export.add_argument("--db")
    export.add_argument("--output")

    abort = subparsers.add_parser(
        "abort", help="Mark an unusable Run as aborted without deleting history"
    )
    abort.add_argument("run_id")
    abort.add_argument("--reason", required=True)
    abort.add_argument("--project", default=".")
    abort.add_argument("--db")

    return parser


def _project_and_store(args: argparse.Namespace) -> Tuple[Path, WorkflowStore]:
    project = Path(args.project).resolve()
    db_path = Path(args.db).resolve() if args.db else default_db(project)
    return project, WorkflowStore(db_path)


def _claude_environment(
    store: WorkflowStore, run_id: str, project: Path
) -> Dict[str, str]:
    environment = os.environ.copy()
    python_directory = str(Path(sys.executable).resolve().parent)
    environment["PATH"] = python_directory + os.pathsep + environment.get("PATH", "")
    environment.update(
        {
            "OPENTRACE_RUN_ID": run_id,
            "OPENTRACE_DB": str(store.db_path),
            "OPENTRACE_PROJECT_ROOT": str(project),
            "OPENTRACE_PYTHON": sys.executable,
        }
    )
    return environment


def _resolve_claude(command: str) -> str:
    resolved = shutil.which(command)
    if resolved is None:
        raise WorkflowError(
            f"Claude Code executable was not found: {command}. "
            "Install Claude Code or pass --claude-command."
        )
    return resolved


def _run_claude(
    command: str,
    arguments: List[str],
    project: Path,
    environment: Dict[str, str],
) -> int:
    executable = _resolve_claude(command)
    return subprocess.run(
        [executable, *arguments],
        cwd=str(project),
        env=environment,
        check=False,
    ).returncode


def command_run(args: argparse.Namespace) -> int:
    project, store = _project_and_store(args)
    result = store.start_run(
        task_description=args.task,
        original_request=args.task,
        project_root=project,
        input_files=args.data,
    )
    run_id = result["run_id"]
    session_id = result["claude_session_id"]
    plugin_dir = Path(args.plugin_dir).resolve()
    if not plugin_dir.is_dir():
        raise WorkflowError(f"OpenTrace plugin directory does not exist: {plugin_dir}")

    prompt = (
        f"[OPENTRACE_INITIAL_TASK run_id={run_id}]\n"
        f"{args.task}\n\n"
        "Declared input files:\n"
        + "\n".join(
            f"- {item['path']}" for item in result["initial_file_versions"]
        )
        + "\n\n"
        "OpenTrace only records this workflow. You own all data analysis. "
        "Use the declared input files rather than searching for substitutes. "
        "Use the OpenTrace MCP tools to set a semantic plan before material work."
    )
    launch = {
        **result,
        "database": str(store.db_path),
        "plugin_dir": str(plugin_dir),
        "launch_command": [
            args.claude_command,
            "--session-id",
            session_id,
            "--plugin-dir",
            str(plugin_dir),
            prompt,
        ],
    }
    print(json.dumps(launch, ensure_ascii=False, indent=2))
    if args.no_launch:
        return 0
    return _run_claude(
        args.claude_command,
        launch["launch_command"][1:],
        project,
        _claude_environment(store, run_id, project),
    )


def command_resume(args: argparse.Namespace) -> int:
    project, store = _project_and_store(args)
    state = store.get_state(args.run_id)
    run = state["run"]
    plugin_dir = Path(args.plugin_dir).resolve()
    arguments = [
        "--resume",
        run["claude_session_id"],
        "--plugin-dir",
        str(plugin_dir),
    ]
    result = {
        "run_id": args.run_id,
        "claude_session_id": run["claude_session_id"],
        "database": str(store.db_path),
        "launch_command": [args.claude_command, *arguments],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.no_launch:
        return 0
    return _run_claude(
        args.claude_command,
        arguments,
        project,
        _claude_environment(store, args.run_id, project),
    )


def command_state(args: argparse.Namespace) -> int:
    _, store = _project_and_store(args)
    print(json.dumps(store.get_state(args.run_id), ensure_ascii=False, indent=2))
    return 0


def command_export(args: argparse.Namespace) -> int:
    _, store = _project_and_store(args)
    path = store.export_run(args.run_id, args.output)
    print(str(path))
    return 0


def command_abort(args: argparse.Namespace) -> int:
    _, store = _project_and_store(args)
    result = store.abort_run(args.run_id, args.reason)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return command_run(args)
        if args.command == "resume":
            return command_resume(args)
        if args.command == "state":
            return command_state(args)
        if args.command == "export":
            return command_export(args)
        if args.command == "abort":
            return command_abort(args)
        parser.error(f"unsupported command: {args.command}")
    except WorkflowError as error:
        parser.exit(2, f"OpenTrace error: {error}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
