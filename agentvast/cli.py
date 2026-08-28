"""Command-line entry point for the AgentVAST Claude Code prototype."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agentvast.paths import expose_repository_to_python, workflow_database
from agentvast.workflow_store import WorkflowError, WorkflowStore


PACKAGE_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = PACKAGE_ROOT.parent
DEFAULT_PLUGIN_DIR = REPOSITORY_ROOT / "claude-plugin"
DEFAULT_AUTO_COMPACT_WINDOW = 200_000
DEFAULT_AUTO_COMPACT_PERCENT = 80


def default_db(project_root: Path) -> Path:
    return workflow_database(project_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentvast",
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
        "--compact-window",
        type=int,
        default=DEFAULT_AUTO_COMPACT_WINDOW,
        help="Token window used to calculate Claude Code auto-compaction",
    )
    run.add_argument(
        "--compact-percent",
        type=int,
        default=DEFAULT_AUTO_COMPACT_PERCENT,
        help="Auto-compact when this percentage of the configured window is used",
    )
    run.add_argument(
        "--checkpoint",
        choices=["plan", "node", "none"],
        default="plan",
        help=(
            "Human review cadence: after every plan revision (default), after "
            "every plan revision and every node, or none"
        ),
    )
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
    resume.add_argument(
        "--compact-window",
        type=int,
        default=DEFAULT_AUTO_COMPACT_WINDOW,
    )
    resume.add_argument(
        "--compact-percent",
        type=int,
        default=DEFAULT_AUTO_COMPACT_PERCENT,
    )
    resume.add_argument(
        "--fresh-session",
        action="store_true",
        help=(
            "Continue the active AgentVAST Run in a new Claude session, using "
            "SQLite state instead of the previous conversation context"
        ),
    )
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

    review = subparsers.add_parser(
        "review", help="Generate derived Reviewer assets for a completed Run"
    )
    review.add_argument("run_id")
    review.add_argument("--project", default=".")
    review.add_argument("--db")
    review.add_argument(
        "--force",
        action="store_true",
        help="Create a new review revision even when the current one is up to date",
    )

    review_status = subparsers.add_parser(
        "review-status", help="Print Reviewer generation status for a Run"
    )
    review_status.add_argument("run_id")
    review_status.add_argument("--project", default=".")
    review_status.add_argument("--db")

    abort = subparsers.add_parser(
        "abort", help="Mark an unusable Run as aborted without deleting history"
    )
    abort.add_argument("run_id")
    abort.add_argument("--reason", required=True)
    abort.add_argument("--project", default=".")
    abort.add_argument("--db")

    web = subparsers.add_parser(
        "web", help="Start the local Web terminal service for Claude Code"
    )
    web.add_argument("--project", default=".", help="Default Claude project directory")
    web.add_argument("--host", default="127.0.0.1", help="Web service bind address")
    web.add_argument("--port", type=int, default=8765, help="Web service port")
    web.add_argument("--claude-command", default="claude")
    web.add_argument("--plugin-dir", default=str(DEFAULT_PLUGIN_DIR))

    observe = subparsers.add_parser(
        "observe", help="Passively observe Claude Code without workflow enforcement"
    )
    from agentvast.observer.cli import configure_parser as configure_observer_parser

    configure_observer_parser(observe)

    return parser


def _project_and_store(args: argparse.Namespace) -> Tuple[Path, WorkflowStore]:
    project = Path(args.project).resolve()
    db_path = Path(args.db).resolve() if args.db else default_db(project)
    return project, WorkflowStore(db_path)


def _claude_environment(
    store: WorkflowStore,
    run_id: str,
    project: Path,
    compact_window: int,
    compact_percent: int,
) -> Dict[str, str]:
    if compact_window <= 0:
        raise WorkflowError("--compact-window must be greater than zero")
    if not 1 <= compact_percent <= 100:
        raise WorkflowError("--compact-percent must be between 1 and 100")
    environment = os.environ.copy()
    run = store.get_state(run_id)["run"]
    python_directory = str(Path(sys.executable).resolve().parent)
    environment["PATH"] = python_directory + os.pathsep + environment.get("PATH", "")
    expose_repository_to_python(environment)
    environment.update(
        {
            "AGENTVAST_RUN_ID": run_id,
            "AGENTVAST_DB": str(store.db_path),
            "AGENTVAST_PROJECT_ROOT": str(project),
            "AGENTVAST_RESULT_ROOT": str(run["result_root"]),
            "AGENTVAST_PYTHON": sys.executable,
            "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(compact_window),
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": str(compact_percent),
        }
    )
    environment.pop("DISABLE_AUTO_COMPACT", None)
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
        checkpoint_mode=args.checkpoint,
    )
    run_id = result["run_id"]
    session_id = result["claude_session_id"]
    plugin_dir = Path(args.plugin_dir).resolve()
    if not plugin_dir.is_dir():
        raise WorkflowError(f"AgentVAST plugin directory does not exist: {plugin_dir}")

    input_instruction = (
        "No initial file was supplied. Use read-only discovery to understand the "
        "task before set-plan. After a Node starts, use relevant accessible files "
        "normally and record the files actually used in complete-node; previously "
        "unknown external inputs will be observed then."
        if not result["initial_file_versions"]
        else "The supplied files are initial context, not an input whitelist."
    )
    prompt = (
        f"[AGENTVAST_INITIAL_TASK run_id={run_id}]\n"
        f"{args.task}\n\n"
        "Declared input files:\n"
        + "\n".join(
            f"- {item['path']}" for item in result["initial_file_versions"]
        )
        + "\n\n"
        "AgentVAST only records this workflow. You own all data analysis. "
        + input_instruction
        + " "
        f"Save all artifacts under {result['result_root']} using the code, data, "
        "report, and visualization subdirectories. "
        "Use python -m agentvast.agent_cli recording commands to set a semantic "
        "Chinese plan before material work. start-node establishes the boundary; declare "
        "the files actually used when complete-node records the finished work. "
        "Revise the Plan whenever findings change it; AgentVAST preserves prior "
        "Revisions and actual Node executions. "
        f"This Run uses checkpoint mode '{result['checkpoint_mode']}'. "
        "In plan mode, print the task and complete returned Plan. Stable Node IDs, "
        "Chinese objectives, dependencies, and artifact types must exactly match "
        "the structured Web Plan. End with 'Plan 已生成，请在右侧查看、编辑或确认。' "
        "and wait for approval before any "
        "material analysis; after approval execute without a final checkpoint. "
        "After the current Plan completes, keep the Run active for later rounds "
        "instead of calling finish-run automatically. "
        "A checkpoint pauses the Claude turn but keeps the AgentVAST Run active. "
        "Do not use MCP for AgentVAST in this Run."
    )
    launch = {
        **result,
        "database": str(store.db_path),
        "plugin_dir": str(plugin_dir),
        "auto_compact_window": args.compact_window,
        "auto_compact_percent": args.compact_percent,
        "launch_command": [
            args.claude_command,
            "--dangerously-skip-permissions",
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
        _claude_environment(
            store,
            run_id,
            project,
            args.compact_window,
            args.compact_percent,
        ),
    )


def command_resume(args: argparse.Namespace) -> int:
    project, store = _project_and_store(args)
    state = store.get_state(args.run_id)
    run = state["run"]
    if run["status"] != "active":
        raise WorkflowError(
            f"Run {args.run_id} is {run['status']} and cannot be resumed. "
            "Start a new Run for additional analysis."
        )
    plugin_dir = Path(args.plugin_dir).resolve()
    if not plugin_dir.is_dir():
        raise WorkflowError(f"AgentVAST plugin directory does not exist: {plugin_dir}")
    if args.fresh_session:
        session_id = str(uuid.uuid4())
        all_artifacts: List[str] = []
        result_root = Path(run["result_root"])
        if result_root.is_dir():
            all_artifacts = sorted(
                path.relative_to(result_root).as_posix()
                for path in result_root.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix.lower() not in {".pyc", ".pyo"}
            )
        artifacts = all_artifacts[:200]
        completed = [
            {
                "node_id": node["node_id"],
                "objective": node["objective"],
                "result_summary": node["result_summary"],
                "analysis_conclusion": node["analysis_conclusion"],
            }
            for node in state["nodes"]
            if node["status"] == "completed"
        ]
        active = next(
            (
                {
                    "node_id": node["node_id"],
                    "objective": node["objective"],
                    "started_at": node["started_at"],
                }
                for node in state["nodes"]
                if node["status"] == "active"
            ),
            None,
        )
        continuation = {
            "task": run["task_description"],
            "plan": state["plan"],
            "completed_nodes": completed,
            "active_node": active,
            "pending_user_inputs": state["pending_user_inputs"],
            "existing_result_artifacts": artifacts,
            "existing_result_artifact_count": len(all_artifacts),
            "artifact_list_truncated": len(all_artifacts) > len(artifacts),
            "result_root": run["result_root"],
        }
        prompt = (
            f"[AGENTVAST_CONTINUATION_TASK run_id={args.run_id}]\n"
            "Continue this active AgentVAST Run in a fresh Claude session after "
            "the previous session was interrupted. Do not redo completed Nodes or "
            "rewrite their Plan definitions. Later Nodes may use or edit their "
            "artifacts with truthful versioned input/output recording. If a Node is "
            "active, inspect its existing Run artifacts and "
            "compare its objective with the original task before continuing. If the "
            "active objective contains a mistaken premise, preserve that historical "
            "fact, record the work already done truthfully when it satisfies the "
            "completion conditions, then revise the Plan. Earlier revisions and "
            "actual executions remain historical records. AgentVAST "
            "SQLite remains the source of workflow state.\n\n"
            "Recovery state:\n"
            + json.dumps(continuation, ensure_ascii=False)
        )
        arguments = [
            "--dangerously-skip-permissions",
            "--session-id",
            session_id,
            "--plugin-dir",
            str(plugin_dir),
            prompt,
        ]
    else:
        session_id = run["claude_session_id"]
        arguments = [
            "--dangerously-skip-permissions",
            "--resume",
            session_id,
            "--plugin-dir",
            str(plugin_dir),
        ]
    result = {
        "run_id": args.run_id,
        "claude_session_id": session_id,
        "resume_mode": "fresh" if args.fresh_session else "same_session",
        "database": str(store.db_path),
        "auto_compact_window": args.compact_window,
        "auto_compact_percent": args.compact_percent,
        "launch_command": [args.claude_command, *arguments],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.no_launch:
        return 0
    if args.fresh_session:
        store.rotate_claude_session(
            args.run_id,
            session_id,
            reason="fresh_session_recovery",
        )
    return _run_claude(
        args.claude_command,
        arguments,
        project,
        _claude_environment(
            store,
            args.run_id,
            project,
            args.compact_window,
            args.compact_percent,
        ),
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


def command_review(args: argparse.Namespace) -> int:
    project, store = _project_and_store(args)
    state = store.get_state(args.run_id)
    if state["run"]["status"] != "completed":
        raise WorkflowError("Reviewer can only process a completed Run")
    workflow_path = store.export_run(args.run_id)
    try:
        from agentvast.reviewer import review_run

        manifest = review_run(project, workflow_path, force=args.force)
    except (RuntimeError, ValueError, OSError) as error:
        raise WorkflowError("Reviewer failed: {0}".format(error)) from error
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def command_review_status(args: argparse.Namespace) -> int:
    _, store = _project_and_store(args)
    state = store.get_state(args.run_id)
    try:
        from agentvast.reviewer import review_status

        status = review_status(Path(state["run"]["result_root"]))
    except (RuntimeError, ValueError, OSError) as error:
        raise WorkflowError("Could not read Reviewer status: {0}".format(error)) from error
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def command_abort(args: argparse.Namespace) -> int:
    _, store = _project_and_store(args)
    result = store.abort_run(args.run_id, args.reason)
    result["export_path"] = str(store.export_run(args.run_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def command_web(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise WorkflowError(f"project directory does not exist: {project}")
    if not 1 <= args.port <= 65535:
        raise WorkflowError("--port must be between 1 and 65535")
    try:
        import uvicorn

        from agentvast.web_server import WebDependencyError, create_app
    except ImportError as error:
        raise WorkflowError(
            'AgentVAST Web dependencies are not installed. '
            'Run: python -m pip install -e ".[web]"'
        ) from error
    try:
        app = create_app(
            project,
            args.claude_command,
            Path(args.plugin_dir).resolve(),
        )
    except WebDependencyError as error:
        raise WorkflowError(str(error)) from error

    print(f"AgentVAST Web terminal service: http://{args.host}:{args.port}")
    print(f"Default Claude project: {project}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
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
        if args.command == "review":
            return command_review(args)
        if args.command == "review-status":
            return command_review_status(args)
        if args.command == "abort":
            return command_abort(args)
        if args.command == "web":
            return command_web(args)
        if args.command == "observe":
            from agentvast.observer.cli import execute as execute_observer

            try:
                return execute_observer(args)
            except (OSError, RuntimeError, ValueError) as error:
                raise WorkflowError("Observer failed: {0}".format(error)) from error
        parser.error(f"unsupported command: {args.command}")
    except WorkflowError as error:
        parser.exit(2, f"AgentVAST error: {error}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
