"""stdio MCP server exposing only OpenTrace recording operations."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

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


@mcp.tool(name="opentrace_set_plan")
def set_plan(nodes: List[Dict[str, Any]], reason: str = "initial plan") -> Dict[str, Any]:
    """Record Claude's current semantic analysis plan.

    Calling this again creates a new immutable plan revision.  Nodes describe
    analysis objectives, not commands, Python functions, or individual file reads.
    """

    return _store().set_plan(_run_id(), nodes, reason)


@mcp.tool(name="opentrace_start_step")
def start_step(
    node_id: str,
    objective: str,
    input_files: List[str],
    completion_condition: str,
    expected_output_roles: Optional[List[str]] = None,
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
    output_files: Optional[List[Dict[str, str]]] = None,
    processing_result: Optional[Dict[str, Any]] = None,
    analysis_conclusion: Optional[Dict[str, Any]] = None,
    operation_types: Optional[List[str]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    algorithms: Optional[List[Dict[str, Any]]] = None,
    programs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Complete the active step with a truthful semantic summary.

    Output entries use ``{"path": "...", "role": "..."}``; role is one of
    step_output, internal_intermediate, or temporary.  OpenTrace verifies and
    hashes files but does not infer the analysis meaning.
    """

    return _store().complete_step(
        step_id=step_id,
        operation_summary=operation_summary,
        output_files=output_files,
        processing_result=processing_result,
        analysis_conclusion=analysis_conclusion,
        operation_types=operation_types,
        parameters=parameters,
        algorithms=algorithms,
        programs=programs,
    )


@mcp.tool(name="opentrace_classify_user_input")
def classify_user_input(
    input_event_id: str,
    input_type: str,
    structured_summary: str = "",
    target_step_id: Optional[str] = None,
    target_plan_version: Optional[int] = None,
    workflow_effect: str = "",
) -> Dict[str, Any]:
    """Classify a user intervention captured by the UserPromptSubmit hook."""

    return _store().classify_user_input(
        input_event_id=input_event_id,
        input_type=input_type,
        structured_summary=structured_summary,
        target_step_id=target_step_id,
        target_plan_version=target_plan_version,
        workflow_effect=workflow_effect,
    )


@mcp.tool(name="opentrace_apply_user_input")
def apply_user_input(
    input_event_id: str,
    workflow_effect: str,
    target_step_id: Optional[str] = None,
    target_plan_version: Optional[int] = None,
) -> Dict[str, Any]:
    """Record how a classified human contribution actually changed the workflow."""

    return _store().apply_user_input(
        input_event_id=input_event_id,
        workflow_effect=workflow_effect,
        target_step_id=target_step_id,
        target_plan_version=target_plan_version,
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
