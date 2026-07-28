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

from opentrace.workflow_store import WorkflowError, WorkflowStore


def _store_and_run() -> tuple[WorkflowStore, str]:
    database = os.environ.get("OPENTRACE_DB")
    run_id = os.environ.get("OPENTRACE_RUN_ID")
    if not database or not run_id:
        raise WorkflowError(
            "OpenTrace environment is not configured; start Claude with opentrace run"
        )
    return WorkflowStore(database), run_id


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
        prog="opentrace-agent",
        description="Record Claude Code workflow events in the current OpenTrace Run.",
    )
    parser.add_argument(
        "action",
        choices=[
            "set-plan",
            "start-step",
            "complete-step",
            "classify-user-input",
            "apply-user-input",
            "state",
            "status",
            "finish-run",
        ],
    )
    parser.add_argument(
        "--payload",
        help="One JSON object containing the fields for this recording action",
    )
    return parser


def execute(action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    store, run_id = _store_and_run()

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

    if action == "start-step":
        _only_fields(payload, {"node_id", "input_files", "objective"})
        input_files = _required(payload, "input_files")
        if not isinstance(input_files, list):
            raise WorkflowError("payload.input_files must be an array")
        return store.start_step(
            run_id=run_id,
            node_id=str(_required(payload, "node_id")),
            input_files=input_files,
            objective=str(payload.get("objective") or ""),
        )

    if action == "complete-step":
        _only_fields(
            payload,
            {
                "step_id",
                "operation_summary",
                "output_files",
                "result_summary",
                "analysis_conclusion",
            },
        )
        output_files = payload.get("output_files", [])
        if not isinstance(output_files, list):
            raise WorkflowError("payload.output_files must be an array")
        conclusion = payload.get("analysis_conclusion")
        if conclusion is not None and not isinstance(conclusion, str):
            raise WorkflowError(
                "payload.analysis_conclusion must be a string or null"
            )
        return store.complete_step(
            step_id=str(_required(payload, "step_id")),
            operation_summary=str(_required(payload, "operation_summary")),
            result_summary=str(_required(payload, "result_summary")),
            output_files=output_files,
            analysis_conclusion=conclusion,
        )

    if action == "classify-user-input":
        _only_fields(
            payload,
            {
                "input_event_id",
                "input_type",
                "target_step_id",
                "target_plan_version",
                "workflow_effect",
            },
        )
        return store.classify_user_input(
            input_event_id=str(_required(payload, "input_event_id")),
            input_type=str(_required(payload, "input_type")),
            target_step_id=payload.get("target_step_id"),
            target_plan_version=payload.get("target_plan_version"),
            workflow_effect=str(payload.get("workflow_effect") or ""),
        )

    if action == "apply-user-input":
        _only_fields(
            payload,
            {
                "input_event_id",
                "workflow_effect",
                "target_step_id",
                "target_plan_version",
            },
        )
        return store.apply_user_input(
            input_event_id=str(_required(payload, "input_event_id")),
            workflow_effect=str(_required(payload, "workflow_effect")),
            target_step_id=payload.get("target_step_id"),
            target_plan_version=payload.get("target_plan_version"),
        )

    if action in {"state", "status"}:
        return store.get_state(run_id)

    if action == "finish-run":
        result = store.finish_run(run_id)
        result["export_path"] = str(store.export_run(run_id))
        return result

    raise WorkflowError(f"unsupported action: {action}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = execute(args.action, _payload(args.payload))
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
