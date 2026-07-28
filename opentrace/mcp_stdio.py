"""stdio MCP server exposing only OpenTrace recording operations."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from opentrace.workflow_store import WorkflowError, WorkflowStore


mcp = FastMCP(
    "OpenTrace",
    instructions=(
        "OpenTrace records data-analysis workflows; it does not perform analysis. "
        "Claude must set a semantic plan, start one active step before material "
        "analysis, and complete the step with truthful inputs, operations, outputs, "
        "processing results, and conclusions."
    ),
)


def _store() -> WorkflowStore:
    database = os.environ.get("OPENTRACE_DB")
    if not database:
        raise WorkflowError("OPENTRACE_DB is not set; start Claude through opentrace run")
    return WorkflowStore(database)


def _run_id() -> str:
    run_id = os.environ.get("OPENTRACE_RUN_ID")
    if not run_id:
        raise WorkflowError(
            "OPENTRACE_RUN_ID is not set; start Claude through opentrace run"
        )
    return run_id


def _json_list(value: str, field_name: str) -> List[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise WorkflowError(f"{field_name} must be valid JSON: {error}") from error
    if not isinstance(parsed, list):
        raise WorkflowError(f"{field_name} must contain a JSON array")
    return parsed


@mcp.tool(name="opentrace_set_plan")
def set_plan(
    nodes_json: str,
    trigger: str = "",
    change_reason: str = "",
) -> Dict[str, Any]:
    """Record Claude's current semantic analysis plan.

    ``nodes_json`` is a JSON array of objects. Each object contains node_id,
    objective and optional depends_on.

    Calling this again creates a new immutable plan revision.  Nodes describe
    analysis objectives, not commands, Python functions, or individual file reads.
    """

    nodes = _json_list(nodes_json, "nodes_json")
    if not all(isinstance(node, dict) for node in nodes):
        raise WorkflowError("every nodes_json entry must be an object")
    return _store().set_plan(
        _run_id(),
        nodes,
        trigger=trigger or None,
        change_reason=change_reason or None,
    )


@mcp.tool(name="opentrace_start_step")
def start_step(
    node_id: str,
    input_files: List[str],
) -> Dict[str, Any]:
    """Start one real semantic analysis step before material Claude tool use.

    A script or intermediate file alone is not a step.  Keep commands and retries
    inside the active step unless Claude must inspect a result before deciding the
    next semantic action, or an output becomes another step's input.
    """

    return _store().start_step(
        run_id=_run_id(),
        node_id=node_id,
        input_files=input_files,
    )


@mcp.tool(name="opentrace_complete_step")
def complete_step(
    step_id: str,
    operation_summary: str,
    result_summary: str,
    output_files_json: str = "[]",
    analysis_conclusion: str = "",
) -> Dict[str, Any]:
    """Complete the active step with a truthful semantic summary.

    ``output_files_json`` is a JSON array of file paths. Analysis conclusions
    are optional for pure transformation steps.
    """

    output_files = _json_list(output_files_json, "output_files_json")
    return _store().complete_step(
        step_id=step_id,
        operation_summary=operation_summary,
        result_summary=result_summary,
        output_files=output_files,
        analysis_conclusion=analysis_conclusion or None,
    )


@mcp.tool(name="opentrace_classify_user_input")
def classify_user_input(
    input_event_id: str,
    input_type: str,
    target_step_id: str = "",
    target_plan_version: int = 0,
    workflow_effect: str = "",
) -> Dict[str, Any]:
    """Classify a user intervention captured by the UserPromptSubmit hook."""

    return _store().classify_user_input(
        input_event_id=input_event_id,
        input_type=input_type,
        target_step_id=target_step_id or None,
        target_plan_version=target_plan_version or None,
        workflow_effect=workflow_effect,
    )


@mcp.tool(name="opentrace_apply_user_input")
def apply_user_input(
    input_event_id: str,
    workflow_effect: str,
    target_step_id: str = "",
    target_plan_version: int = 0,
) -> Dict[str, Any]:
    """Record how a classified human contribution actually changed the workflow."""

    return _store().apply_user_input(
        input_event_id=input_event_id,
        workflow_effect=workflow_effect,
        target_step_id=target_step_id or None,
        target_plan_version=target_plan_version or None,
    )


@mcp.tool(name="opentrace_get_state")
def get_state() -> Dict[str, Any]:
    """Return the current Run, latest plan, steps, and pending user inputs."""

    return _store().get_state(_run_id())


@mcp.tool(name="opentrace_finish_run")
def finish_run() -> Dict[str, Any]:
    """Finish the Run after all real semantic steps are complete."""

    return _store().finish_run(_run_id())


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
