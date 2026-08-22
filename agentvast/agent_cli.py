"""Gateway-compatible recording commands for Claude Code.

The command only writes structured workflow records. It never performs data
analysis. Claude Code invokes it through its built-in Bash tool, avoiding
custom MCP tool calls on gateways that do not support ``tool_reference``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set

from agentvast.workflow_store import WorkflowError, WorkflowStore


def _store_and_run() -> tuple[WorkflowStore, str]:
    database = os.environ.get("AGENTVAST_DB")
    run_id = os.environ.get("AGENTVAST_RUN_ID")
    if not database:
        raise WorkflowError(
            "AgentVAST database is not configured; start Claude through AgentVAST"
        )
    store = WorkflowStore(database)
    if run_id:
        return store, run_id
    session_id = os.environ.get("AGENTVAST_CLAUDE_SESSION_ID", "")
    active = store.active_run_for_session(session_id)
    if active is None:
        raise WorkflowError(
            "this Claude session has no active AgentVAST Run; start recording "
            "from the AgentVAST Web interface"
        )
    return store, str(active["run_id"])


def _payload(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        result = json.loads(value)
    except json.JSONDecodeError as error:
        raise WorkflowError(f"--payload must be valid JSON: {error}") from error
    if not isinstance(result, dict):
        raise WorkflowError("--payload must contain a JSON object")
    return result


def _required(payload: Dict[str, Any], name: str) -> Any:
    value = payload.get(name)
    if value is None or value == "":
        raise WorkflowError(f"payload field is required: {name}")
    return value


def _only_fields(payload: Dict[str, Any], allowed: Set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise WorkflowError(
            "unsupported payload fields: " + ", ".join(unknown)
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentvast-agent",
        description="Record Claude Code workflow events in the current AgentVAST Run.",
        epilog=(
            "Human-input shorthand: classify-user-input INPUT_ID INPUT_TYPE; "
            "apply-user-input INPUT_ID WORKFLOW_EFFECT"
        ),
    )
    parser.add_argument(
        "action",
        choices=[
            "declare-inputs",
            "set-plan",
            "start-node",
            "complete-node",
            "start-step",
            "complete-step",
            "classify-user-input",
            "apply-user-input",
            "pause-for-user",
            "state",
            "status",
            "finish-run",
        ],
    )
    parser.add_argument(
        "--payload",
        help="One JSON object containing the fields for this recording action",
    )
    parser.add_argument(
        "values",
        nargs="*",
        help=(
            "Shorthand positional values for classify-user-input and "
            "apply-user-input"
        ),
    )
    return parser


def _command_payload(
    action: str,
    payload_value: Optional[str],
    values: List[str],
) -> Dict[str, Any]:
    payload = _payload(payload_value)
    if payload and values:
        raise WorkflowError("use either --payload or positional shorthand, not both")
    if not values:
        return payload
    if action == "classify-user-input" and len(values) == 2:
        return {
            "input_event_id": values[0],
            "input_type": values[1],
        }
    if action == "apply-user-input" and len(values) >= 2:
        return {
            "input_event_id": values[0],
            "workflow_effect": " ".join(values[1:]),
        }
    raise WorkflowError(
        "positional shorthand is only supported as "
        "'classify-user-input INPUT_ID INPUT_TYPE' or "
        "'apply-user-input INPUT_ID WORKFLOW_EFFECT'; "
        "use --payload for all other actions"
    )


def execute(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    store, run_id = _store_and_run()

    if action == "declare-inputs":
        _only_fields(payload, {"input_files"})
        input_files = _required(payload, "input_files")
        if (
            not isinstance(input_files, list)
            or not input_files
            or not all(
                isinstance(path, str) and path.strip() for path in input_files
            )
        ):
            raise WorkflowError(
                "payload.input_files must be a non-empty array of file paths"
            )
        return store.declare_run_inputs(run_id, input_files)

    if action == "set-plan":
        _only_fields(payload, {"nodes", "trigger", "change_reason"})
        nodes = _required(payload, "nodes")
        if not isinstance(nodes, list) or not all(
            isinstance(node, dict) for node in nodes
        ):
            raise WorkflowError("payload.nodes must be an array of objects")
        return store.set_plan(
            run_id=run_id,
            nodes=nodes,
            trigger=payload.get("trigger"),
            change_reason=payload.get("change_reason"),
        )

    if action in {"start-node", "start-step"}:
        _only_fields(payload, {"node_id", "objective"})
        result = store.start_step(
            run_id=run_id,
            node_id=str(_required(payload, "node_id")),
            objective=str(payload.get("objective") or ""),
        )
        if action == "start-node":
            result.pop("step_id", None)
        return result

    if action in {"complete-node", "complete-step"}:
        identity_field = "node_id" if action == "complete-node" else "step_id"
        _only_fields(
            payload,
            {
                identity_field,
                "input_files",
                "operation_summary",
                "output_files",
                "result_summary",
                "analysis_conclusion",
                "analysis_outcome",
            },
        )
        output_files = payload.get("output_files", [])
        if not isinstance(output_files, list):
            raise WorkflowError("payload.output_files must be an array")
        input_files = payload.get("input_files", [])
        if not isinstance(input_files, list) or not all(
            isinstance(path, str) and path.strip() for path in input_files
        ):
            raise WorkflowError(
                "payload.input_files must be an array of file path strings"
            )
        conclusion = payload.get("analysis_conclusion")
        if conclusion is not None and not isinstance(conclusion, str):
            raise WorkflowError(
                "payload.analysis_conclusion must be a string or null"
            )
        values = {
            "input_files": input_files,
            "operation_summary": str(_required(payload, "operation_summary")),
            "result_summary": str(_required(payload, "result_summary")),
            "output_files": output_files,
            "analysis_conclusion": conclusion,
            "analysis_outcome": str(
                payload.get("analysis_outcome") or "not_assessed"
            ),
        }
        if action == "complete-node":
            result = store.complete_node(
                run_id=run_id,
                node_id=str(_required(payload, "node_id")),
                **values,
            )
            result.pop("step_id", None)
            return result
        return store.complete_step(
            step_id=str(_required(payload, "step_id")),
            **values,
        )

    if action == "classify-user-input":
        _only_fields(
            payload,
            {
                "input_event_id",
                "input_type",
                "target_plan_version",
                "workflow_effect",
            },
        )
        return store.classify_user_input(
            input_event_id=str(_required(payload, "input_event_id")),
            input_type=str(_required(payload, "input_type")),
            target_plan_version=payload.get("target_plan_version"),
            workflow_effect=str(payload.get("workflow_effect") or ""),
        )

    if action == "apply-user-input":
        _only_fields(
            payload,
            {
                "input_event_id",
                "workflow_effect",
                "target_plan_version",
            },
        )
        return store.apply_user_input(
            input_event_id=str(_required(payload, "input_event_id")),
            workflow_effect=str(_required(payload, "workflow_effect")),
            target_plan_version=payload.get("target_plan_version"),
        )

    if action in {"state", "status"}:
        return store.get_state(run_id)

    if action == "pause-for-user":
        _only_fields(payload, set())
        return store.pause_for_user(run_id)

    if action == "finish-run":
        result = store.finish_run(run_id)
        result["export_path"] = str(store.export_run(run_id))
        return result

    raise WorkflowError(f"unsupported action: {action}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = execute(
            args.action,
            _command_payload(args.action, args.payload, args.values),
        )
    except WorkflowError as error:
        print(
            json.dumps(
                {"ok": False, "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"ok": True, "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
