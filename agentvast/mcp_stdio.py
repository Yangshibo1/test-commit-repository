"""stdio MCP server exposing only AgentVAST recording operations."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from mcp.server.fastmcp import FastMCP

from agentvast.workflow_store import WorkflowError, WorkflowStore


mcp = FastMCP(
    "AgentVAST",
    instructions=(
        "AgentVAST records data-analysis workflows; it does not perform analysis. "
        "Claude must set a semantic plan, start one active node before material "
        "analysis, and complete the node with truthful inputs, operations, outputs, "
        "processing results, and conclusions."
    ),
)


def _store() -> WorkflowStore:
    database = os.environ.get("AGENTVAST_DB")
    if not database:
        raise WorkflowError("AGENTVAST_DB is not set; start Claude through agentvast run")
    return WorkflowStore(database)


def _run_id() -> str:
    run_id = os.environ.get("AGENTVAST_RUN_ID")
    if not run_id:
        raise WorkflowError(
            "AGENTVAST_RUN_ID is not set; start Claude through agentvast run"
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


@mcp.tool(name="agentvast_set_plan")
def set_plan(
    nodes_json: str,
    trigger: str = "",
    change_reason: str = "",
) -> Dict[str, Any]:
    """Record Claude's current semantic analysis plan.

    ``nodes_json`` is a JSON array of objects. Each object contains a temporary
    node_id alias, objective, depends_on, and required_artifacts. AgentVAST
    returns stable ``node-001`` style IDs which must be used for execution.
    Claude selects a non-empty subset of ``code``, ``data``, ``report``, and
    ``visualization`` for each Node. Report artifacts are JSON objects.

    Calling this again creates a new immutable plan revision when the Plan
    materially changes; later revisions require ``change_reason``. Only pending
    Nodes may change. Active/completed Node definitions must remain present and
    unchanged. Nodes describe analysis objectives, not commands, Python
    functions, or individual file reads.
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


@mcp.tool(name="agentvast_start_node")
def start_node(
    node_id: str,
) -> Dict[str, Any]:
    """Start one real semantic analysis node before material Claude tool use.

    Starting freezes the eligible Run-input and completed-Node output versions.
    Actual inputs are declared retrospectively when the node completes. A script
    or intermediate file alone is not a node.
    """

    return _store().start_step(
        run_id=_run_id(),
        node_id=node_id,
    )


@mcp.tool(name="agentvast_complete_node")
def complete_node(
    node_id: str,
    input_files: List[str],
    operation_summary: str,
    result_summary: str,
    output_files_json: str = "[]",
    analysis_conclusion: str = "",
) -> Dict[str, Any]:
    """Complete the active node with a truthful semantic summary.

    ``input_files`` lists the Run inputs and completed-Node outputs actually used.
    AgentVAST binds them to versions frozen at Node start and automatically
    discovers files created or changed in the Run result directory.
    ``output_files_json`` is optional cross-checking only. Analysis conclusions
    are optional for pure transformation nodes.
    """

    output_files = _json_list(output_files_json, "output_files_json")
    return _store().complete_node(
        run_id=_run_id(),
        node_id=node_id,
        input_files=input_files,
        operation_summary=operation_summary,
        result_summary=result_summary,
        output_files=output_files,
        analysis_conclusion=analysis_conclusion or None,
    )


@mcp.tool(name="agentvast_classify_user_input")
def classify_user_input(
    input_event_id: str,
    input_type: str,
    target_plan_version: int = 0,
    workflow_effect: str = "",
) -> Dict[str, Any]:
    """Classify a user intervention captured by the UserPromptSubmit hook."""

    return _store().classify_user_input(
        input_event_id=input_event_id,
        input_type=input_type,
        target_plan_version=target_plan_version or None,
        workflow_effect=workflow_effect,
    )


@mcp.tool(name="agentvast_apply_user_input")
def apply_user_input(
    input_event_id: str,
    workflow_effect: str,
    target_plan_version: int = 0,
) -> Dict[str, Any]:
    """Record how a classified human contribution actually changed the workflow."""

    return _store().apply_user_input(
        input_event_id=input_event_id,
        workflow_effect=workflow_effect,
        target_plan_version=target_plan_version or None,
    )


@mcp.tool(name="agentvast_get_state")
def get_state() -> Dict[str, Any]:
    """Return the current Run, latest plan, nodes, and pending user inputs."""

    return _store().get_state(_run_id())


@mcp.tool(name="agentvast_pause_for_user")
def pause_for_user() -> Dict[str, Any]:
    """Open a Node checkpoint when checkpoint mode is ``node``."""

    return _store().pause_for_user(_run_id())


@mcp.tool(name="agentvast_finish_run")
def finish_run() -> Dict[str, Any]:
    """Finish the Run after all real semantic nodes are complete."""

    store = _store()
    run_id = _run_id()
    result = store.finish_run(run_id)
    result["export_path"] = str(store.export_run(run_id))
    return result


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
