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


def _json_object(value: str, field_name: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise WorkflowError(f"{field_name} must be valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise WorkflowError(f"{field_name} must contain a JSON object")
    return parsed


@mcp.tool(name="opentrace_set_plan")
def set_plan(nodes_json: str, reason: str = "initial plan") -> Dict[str, Any]:
    """Record Claude's current semantic analysis plan.

    ``nodes_json`` is a JSON array of objects. Each object contains node_id,
    objective, step_type, and optional depends_on.

    Calling this again creates a new immutable plan revision.  Nodes describe
    analysis objectives, not commands, Python functions, or individual file reads.
    """

    nodes = _json_list(nodes_json, "nodes_json")
    if not all(isinstance(node, dict) for node in nodes):
        raise WorkflowError("every nodes_json entry must be an object")
    return _store().set_plan(_run_id(), nodes, reason)


@mcp.tool(name="opentrace_start_step")
def start_step(
    node_id: str,
    objective: str,
    input_files: List[str],
    completion_condition: str,
    expected_output_roles: List[str],
    target_data: str = "",
) -> Dict[str, Any]:
    """Start one real semantic analysis step before material Claude tool use.

    A script or intermediate file alone is not a step.  Keep commands and retries
    inside the active step unless Claude must inspect a result before deciding the
    next semantic action, or an output becomes another step's input.
    """

    return _store().start_step(
        run_id=_run_id(),
        node_id=node_id,
        objective=objective,
        input_files=input_files,
        completion_condition=completion_condition,
        expected_output_roles=expected_output_roles,
        target_data=target_data,
    )


@mcp.tool(name="opentrace_complete_step")
def complete_step(
    step_id: str,
    operation_summary: str,
    output_files_json: str = "[]",
    processing_result_json: str = "{}",
    analysis_conclusion_json: str = "{}",
    operation_types: List[str] = [],
    parameters_json: str = "{}",
    algorithms_json: str = "[]",
    programs_json: str = "[]",
) -> Dict[str, Any]:
    """Complete the active step with a truthful semantic summary.

    Fields ending in ``_json`` contain serialized JSON arrays or objects.
    Output entries use ``{"path": "...", "role": "..."}``; role is one of
    step_output, internal_intermediate, or temporary.
    """

    output_files = _json_list(output_files_json, "output_files_json")
    algorithms = _json_list(algorithms_json, "algorithms_json")
    programs = _json_list(programs_json, "programs_json")
    return _store().complete_step(
        step_id=step_id,
        operation_summary=operation_summary,
        output_files=output_files,
        processing_result=_json_object(
            processing_result_json, "processing_result_json"
        ),
        analysis_conclusion=_json_object(
            analysis_conclusion_json, "analysis_conclusion_json"
        ),
        operation_types=operation_types,
        parameters=_json_object(parameters_json, "parameters_json"),
        algorithms=algorithms,
        programs=programs,
    )


@mcp.tool(name="opentrace_classify_user_input")
def classify_user_input(
    input_event_id: str,
    input_type: str,
    structured_summary: str = "",
    target_step_id: str = "",
    target_plan_version: int = 0,
    workflow_effect: str = "",
) -> Dict[str, Any]:
    """Classify a user intervention captured by the UserPromptSubmit hook."""

    return _store().classify_user_input(
        input_event_id=input_event_id,
        input_type=input_type,
        structured_summary=structured_summary,
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
