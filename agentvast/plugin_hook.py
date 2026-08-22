"""Claude Code hook bridge for the AgentVAST prototype.

Hooks observe Claude Code. They never execute data analysis or manufacture
semantic Node descriptions.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from agentvast.workflow_store import WorkflowError, WorkflowStore


_CONTROL_ID_PATTERN = re.compile(
    r"\[AGENTVAST_CONTROL\s+id=(control_[A-Za-z0-9_-]+)\]",
    re.IGNORECASE,
)


def _read_input() -> Dict[str, Any]:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def _context_output(event: str, context: str) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        }
    }


def _deny(reason: str) -> Dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def _trim(value: Any, limit: int = 20_000) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return value
    return {
        "truncated": True,
        "original_characters": len(encoded),
        "preview": encoded[:limit],
    }


def _store_and_run(
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[Tuple[WorkflowStore, str]]:
    database = os.environ.get("AGENTVAST_DB")
    run_id = os.environ.get("AGENTVAST_RUN_ID")
    if not database:
        return None
    store = WorkflowStore(database)
    if run_id:
        return store, run_id
    session_id = str(
        (payload or {}).get("session_id")
        or os.environ.get("AGENTVAST_CLAUDE_SESSION_ID")
        or ""
    )
    active = store.active_run_for_session(session_id)
    if active is None:
        return None
    return store, str(active["run_id"])


def session_start(payload: Dict[str, Any]) -> Dict[str, Any]:
    resolved = _store_and_run(payload)
    if resolved is None:
        return {}
    store, run_id = resolved
    state = store.get_state(run_id)
    active = next(
        (node for node in state["nodes"] if node["status"] == "active"), None
    )
    context = {
        "agentvast_run_id": run_id,
        "role_boundary": (
            "Claude Code performs all data analysis. AgentVAST only records and "
            "validates the real workflow."
        ),
        "required_flow": (
            "Use the built-in Bash tool to run python -m agentvast.agent_cli "
            "recording commands; do not use AgentVAST MCP tools. When the user did "
            "not supply initial files, use Glob, Grep, and Read to understand the "
            "task before set-plan. Initial or declared files are not a whitelist. "
            "After start-node, use any relevant accessible files normally and list "
            "the files actually used in complete-node; AgentVAST observes previously "
            "unknown external inputs at completion. "
            "Write every Plan Node objective in Chinese. First run set-plan "
            "with a JSON payload. Every executed Node must match a node in the current "
            "Plan Revision, and changed objectives, dependencies, or artifact "
            "requirements require a revised "
            "Plan first. Run start-node before material "
            "Read/Bash/Write/Edit analysis, then complete-node truthfully using the "
            "same node_id and the files actually used. Before a Node starts, while "
            "it is active, and after it completes, you may revise the Plan when real "
            "findings change the analysis path. Only future pending Nodes may be "
            "changed or removed; active/completed Node definitions are immutable. "
            "After every Node in the current Plan is completed, end the turn but keep "
            "the Run active for follow-up analysis. A later user request extends the "
            "same Run through a new Plan Revision. Do not call finish-run unless the "
            "user explicitly starts a New Task Trace or asks to close the trace."
        ),
        "record_command_contract": (
            "Syntax: python -m agentvast.agent_cli ACTION --payload '<JSON object>'. "
            "declare-inputs fields: input_files. This is an optional early hint, not "
            "a prerequisite and not an input whitelist. "
            "set-plan fields: nodes[{node_id, objective, depends_on, "
            "required_artifacts}], optional trigger; change_reason is required after "
            "the initial Plan and an unchanged Plan must not create a Revision. "
            "required_artifacts uses any Claude-selected non-empty subset of code, "
            "data, report, and visualization. Neither every Node nor the Plan as a "
            "whole must cover predefined categories. "
            "Submitted node_id values are aliases: after set-plan, use only the "
            "AgentVAST-assigned node-001 style IDs returned in nodes/node_mapping. "
            "start-node fields: node_id. Starting establishes the execution boundary "
            "and freezes versions of inputs already known at that moment; it does not "
            "limit which accessible files may be used or record final inputs. "
            "complete-node fields: node_id, input_files, operation_summary, optional "
            "output_files, result_summary, analysis_conclusion(string or null), "
            "analysis_outcome(answered, partial, insufficient_data, blocked, failed, "
            "or not_assessed). "
            "input_files must list all external files and completed-Node outputs "
            "actually used during this Node, including files first discovered while "
            "the Node was active. "
            "Human-input shorthand: python -m agentvast.agent_cli "
            "classify-user-input INPUT_ID INPUT_TYPE, then, after any real Plan "
            "revision or execution change, python -m agentvast.agent_cli "
            "apply-user-input INPUT_ID \"REAL_WORKFLOW_EFFECT\". "
            "A semantic Node is one independently explainable and verifiable analysis "
            "objective. A script, command, retry, or intermediate file alone is not a "
            "Node. Saving, writing, exporting, or confirming a file is part of the "
            "semantic node that produces or consumes it, not a separate Plan node. "
            "Keep implementation actions inside the current Node unless they have an "
            "independent analysis goal or their result must be evaluated before deciding "
            "the next node. pause-for-user takes no payload."
        ),
        "artifact_contract": (
            f"Write every analysis artifact under {state['run']['result_root']}, "
            "using its category directory: code, data, report, or visualization. "
            "These four directories already exist; do not create alternate result "
            "directories. "
            "Every newly created filename must start with the active Node ID plus "
            "underscore, for example node-002_profile.py. A later Node may read and "
            "edit a completed Node's artifact in place, but it must declare the "
            "pre-edit file version in input_files; AgentVAST records the edited "
            "version as the later Node's output. Use persistent "
            ".py or .ipynb files for substantive Python analysis and execute the "
            "recorded code file; do not perform substantive analysis with python -c. "
            "Report artifacts use valid JSON objects in the report directory, not "
            "Markdown. "
            "AgentVAST discovers changed artifacts automatically at complete-node and "
            "rejects missing, empty, undeclared edits, wrongly named new files, or "
            "unexecuted required artifacts."
        ),
        "dynamic_plan_contract": (
            "Plan Revisions may add, remove, or change only future pending Nodes. "
            "Every active/completed Node must remain present with the same objective, "
            "dependencies, and required artifact categories."
        ),
        "checkpoint_contract": (
            f"This Run uses checkpoint mode "
            f"'{state['run']['checkpoint_mode'] or 'plan'}'. In plan mode, set-plan "
            "automatically opens a checkpoint for every newly created Plan Revision "
            "before material analysis continues. Print the task and the complete "
            "current Plan in terminal. Stable Node IDs, "
            "Chinese objectives, dependencies, and required artifact types must "
            "exactly match the structured Web Plan. End with: 'Plan 已生成，请在右侧"
            "查看、编辑或确认。' and end the turn; explicit "
            "approval must be classified as "
            "checkpoint_continue. After approval, execute automatically until another "
            "Plan Revision is created; that Revision must be presented and approved "
            "again. There is no final checkpoint. In node mode, every Plan Revision "
            "is also approved and pause-for-user is additionally used after every "
            "completed Node. In none mode, no checkpoint is required."
        ),
        "declared_initial_files": [
            item["path"] for item in state["run"]["initial_file_versions"]
        ],
        "plan": state["plan"],
        "active_node": active,
        "pending_user_inputs": state["pending_user_inputs"],
    }
    store.record_hook_event(run_id, "SessionStart", _trim(payload))
    return _context_output("SessionStart", json.dumps(context, ensure_ascii=False))


def user_prompt_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(payload.get("prompt") or "")
    control_match = _CONTROL_ID_PATTERN.search(prompt)
    if control_match:
        database = os.environ.get("AGENTVAST_DB")
        session_id = str(
            payload.get("session_id")
            or os.environ.get("AGENTVAST_CLAUDE_SESSION_ID")
            or ""
        )
        if not database:
            return _context_output(
                "UserPromptSubmit",
                "AgentVAST control token received, but no database is configured.",
            )
        store = WorkflowStore(database)
        try:
            control = store.consume_control_message(
                control_match.group(1), session_id
            )
        except WorkflowError as error:
            return _context_output(
                "UserPromptSubmit",
                "Invalid AgentVAST control token: {0}".format(error),
            )
        state = store.get_state(control["run_id"])
        store.record_hook_event(
            control["run_id"],
            "ControlMessageConsumed",
            _trim(
                {
                    "hook_event_name": "UserPromptSubmit",
                    "session_id": session_id,
                    "control_id": control["control_id"],
                    "kind": control["kind"],
                }
            ),
        )
        return _context_output(
            "UserPromptSubmit",
            json.dumps(
                {
                    "agentvast_control": {
                        "control_id": control["control_id"],
                        "kind": control["kind"],
                        "payload": control["payload"],
                    },
                    "agentvast_run_id": control["run_id"],
                    "run_status": state["run"]["status"],
                    "plan": state["plan"],
                    "active_node": next(
                        (
                            node
                            for node in state["nodes"]
                            if node["status"] == "active"
                        ),
                        None,
                    ),
                    "pending_user_inputs": state["pending_user_inputs"],
                    "instruction": (
                        "This is an internal AgentVAST control message, not human "
                        "analysis input. Follow its stored payload and the "
                        "data-analysis recording contract."
                    ),
                },
                ensure_ascii=False,
            ),
        )
    resolved = _store_and_run(payload)
    if resolved is None:
        return {}
    store, run_id = resolved
    if prompt.startswith(
        (
            "[AGENTVAST_INITIAL_TASK ",
            "[AGENTVAST_CONTINUATION_TASK ",
            "[AGENTVAST_ACTIVATE ",
            "[AGENTVAST_CONTROL ",
        )
    ):
        state = store.get_state(run_id)
        return _context_output(
            "UserPromptSubmit",
            json.dumps(
                {
                    "agentvast_run_id": run_id,
                    "status": state["run"]["status"],
                    "plan": state["plan"],
                    "active_node": next(
                        (
                            node
                            for node in state["nodes"]
                            if node["status"] == "active"
                        ),
                        None,
                    ),
                    "pending_user_inputs": state["pending_user_inputs"],
                    "instruction": (
                        "Treat this as AgentVAST control input, not human analysis "
                        "content. Follow the explicit control instruction and the "
                        "data-analysis recording skill."
                    ),
                },
                ensure_ascii=False,
            ),
        )
    state_before_input = store.get_state(run_id)
    completed_ids = {
        node["node_id"]
        for node in state_before_input["nodes"]
        if node["status"] == "completed"
    }
    plan_complete = bool(state_before_input["plan"]) and all(
        node["node_id"] in completed_ids
        for node in state_before_input["plan"]["nodes"]
    )
    event = store.capture_user_input(
        run_id=run_id,
        original_text=prompt,
        claude_session_id=payload.get("session_id"),
    )
    return _context_output(
        "UserPromptSubmit",
        (
            "AgentVAST captured this human input as "
            f"{event['input_event_id']}. Before the next material analysis tool, "
            "run exactly: python -m agentvast.agent_cli classify-user-input "
            f"{event['input_event_id']} INPUT_TYPE. Replace INPUT_TYPE with one of "
            "conversation_only, checkpoint_continue, analysis_guidance, "
            "planning_input, or challenge. Human input is not "
            "itself a Node. Use checkpoint_continue only for an explicit approval "
            "or instruction to continue at an AgentVAST checkpoint. For guidance, "
            "planning_input, and challenge, also call "
            "python -m agentvast.agent_cli apply-user-input "
            f"{event['input_event_id']} \"REAL_WORKFLOW_EFFECT\" after recording "
            "its real workflow effect. "
            + (
                "The current Plan is complete but the Run intentionally remains "
                "active. Treat this as follow-up analysis in the same trace: keep "
                "all completed Node definitions, add Chinese pending Nodes in a new "
                "Plan Revision when needed, present that complete Revision, and stop "
                "for Web editing or approval before starting its pending Nodes. Reuse "
                "existing artifacts. Do not start a new Run or call finish-run. "
                if plan_complete
                else ""
            )
            + (
                f"This response targets a {event['checkpoint_kind']} checkpoint."
                if event.get("checkpoint_kind")
                else ""
            )
        ),
    )


_RECORDER_EXECUTABLE = (
    r"(?:agentvast-agent|python(?:\.exe)?\s+-m\s+agentvast\.agent_cli)"
)
_PAYLOAD_ACTIONS = (
    "declare-inputs",
    "set-plan",
    "start-node",
    "complete-node",
    "start-step",
    "complete-step",
    "classify-user-input",
    "apply-user-input",
)
_NO_PAYLOAD_ACTIONS = ("state", "status", "pause-for-user", "finish-run")
_NON_MATERIAL_TOOLS = {
    "AskUserQuestion",
    "EnterPlanMode",
    "ExitPlanMode",
    "Skill",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskOutput",
    "TaskStop",
    "TaskUpdate",
    "TodoWrite",
    "ToolSearch",
}


def _same_path(left: str, right: str) -> bool:
    try:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(
            str(Path(right).resolve())
        )
    except (OSError, ValueError):
        return False


def _without_project_cd(command: str) -> Optional[str]:
    stripped = command.strip()
    match = re.match(
        r"""^cd\s+(?:"([^"]+)"|'([^']+)'|([^\s&]+))\s*&&\s*(.+)$""",
        stripped,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return stripped

    requested_directory = next(
        value for value in match.groups()[:3] if value is not None
    )
    project_root = os.environ.get("AGENTVAST_PROJECT_ROOT")
    if not project_root or not _same_path(requested_directory, project_root):
        return None
    return match.group(4).strip()


def _recording_command(command: str) -> Optional[Dict[str, Any]]:
    body = _without_project_cd(command)
    if body is None:
        return None

    if re.fullmatch(
        rf"{_RECORDER_EXECUTABLE}\s+(?:--help|-h)",
        body,
        re.IGNORECASE,
    ):
        return {"action": "help", "payload": {}}

    no_payload = re.fullmatch(
        rf"{_RECORDER_EXECUTABLE}\s+({'|'.join(_NO_PAYLOAD_ACTIONS)})",
        body,
        re.IGNORECASE,
    )
    if no_payload:
        return {"action": no_payload.group(1).lower(), "payload": {}}

    classify_shorthand = re.fullmatch(
        rf"{_RECORDER_EXECUTABLE}\s+classify-user-input\s+"
        r"(input_[A-Za-z0-9_-]+)\s+"
        r"(conversation_only|checkpoint_continue|analysis_guidance|"
        r"planning_input|challenge)",
        body,
        re.IGNORECASE,
    )
    if classify_shorthand:
        return {
            "action": "classify-user-input",
            "payload": {
                "input_event_id": classify_shorthand.group(1),
                "input_type": classify_shorthand.group(2).lower(),
            },
        }

    apply_shorthand = re.fullmatch(
        rf"{_RECORDER_EXECUTABLE}\s+apply-user-input\s+"
        r"(input_[A-Za-z0-9_-]+)\s+(.+)",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if apply_shorthand:
        effect = apply_shorthand.group(2).strip()
        if (
            len(effect) >= 2
            and effect[0] == effect[-1]
            and effect[0] in {"'", '"'}
        ):
            effect = effect[1:-1]
        if effect:
            return {
                "action": "apply-user-input",
                "payload": {
                    "input_event_id": apply_shorthand.group(1),
                    "workflow_effect": effect,
                },
            }

    with_payload = re.fullmatch(
        rf"{_RECORDER_EXECUTABLE}\s+({'|'.join(_PAYLOAD_ACTIONS)})"
        r"\s+--payload\s+'(.*)'",
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if with_payload is None:
        return None

    raw_payload = with_payload.group(2)
    # A literal apostrophe terminates Bash single-quote protection.
    if "'" in raw_payload:
        return None
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return {"action": with_payload.group(1).lower(), "payload": parsed}


def _is_recording_command(payload: Dict[str, Any]) -> bool:
    if payload.get("tool_name") != "Bash":
        return False
    command = str((payload.get("tool_input") or {}).get("command") or "")
    return _recording_command(command) is not None


def _is_material_tool(payload: Dict[str, Any]) -> bool:
    tool_name = str(payload.get("tool_name") or "")
    if not tool_name:
        return True
    if tool_name == "Bash" and _is_recording_command(payload):
        return False
    return tool_name not in _NON_MATERIAL_TOOLS


def _is_read_only_input_discovery(
    payload: Dict[str, Any], store: WorkflowStore, run_id: str
) -> bool:
    """Allow only Claude's read-only file selection outside a semantic Node."""

    return (
        str(payload.get("tool_name") or "") in {"Glob", "Grep", "Read"}
        and store.can_discover_inputs(run_id)
    )


def _uses_inline_python(payload: Dict[str, Any]) -> bool:
    if payload.get("tool_name") not in {"Bash", "PowerShell"}:
        return False
    command = str((payload.get("tool_input") or {}).get("command") or "")
    return bool(
        re.search(
            r"(?:^|[;&|])\s*(?:python(?:\.exe)?|py)\s+(?:-[^\s]+\s+)*"
            r"(?:-c\b|-($|\s)|<<)",
            command,
            re.IGNORECASE,
        )
    )


def _direct_file_input(payload: Dict[str, Any]) -> Optional[str]:
    tool_name = str(payload.get("tool_name") or "")
    field = {
        "Read": "file_path",
        "Edit": "file_path",
        "MultiEdit": "file_path",
        "NotebookEdit": "notebook_path",
    }.get(tool_name)
    if not field:
        return None
    value = (payload.get("tool_input") or {}).get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def pre_tool_use(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _is_recording_command(payload):
        return {}
    if not _is_material_tool(payload):
        return {}
    resolved = _store_and_run(payload)
    if resolved is None:
        return {}
    store, run_id = resolved
    if _is_read_only_input_discovery(payload, store, run_id):
        return {}
    reason = store.gate_reason(run_id)
    if reason:
        store.record_hook_event(
            run_id,
            "PreToolUseBlocked",
            _trim({**payload, "agentvast_reason": reason}),
        )
        return _deny(reason)
    if _uses_inline_python(payload):
        state = store.get_state(run_id)
        active = next(
            (node for node in state["nodes"] if node["status"] == "active"),
            None,
        )
        node_id = active["node_id"] if active else "active-node"
        reason = (
            "Substantive inline Python is not recordable as a verifiable artifact. "
            f"Write the code to {state['run']['result_root']}\\code\\"
            f"{node_id}_<name>.py and execute that file."
        )
        store.record_hook_event(
            run_id,
            "PreToolUseBlocked",
            _trim({**payload, "agentvast_reason": reason}),
        )
        return _deny(reason)
    file_input = _direct_file_input(payload)
    if file_input:
        try:
            store.freeze_active_input(run_id, file_input)
        except (OSError, WorkflowError):
            # The actual tool remains authoritative. A missing path may be a file
            # creation or a tool-specific path that becomes available later.
            pass
    return {}


def observed_event(event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_material_tool(payload):
        return {}
    resolved = _store_and_run(payload)
    if resolved is None:
        return {}
    store, run_id = resolved
    store.record_hook_event(run_id, event_name, _trim(payload))
    return {}


def stop(payload: Dict[str, Any]) -> Dict[str, Any]:
    resolved = _store_and_run(payload)
    if resolved is None:
        return {}
    store, run_id = resolved
    state = store.get_state(run_id)
    if state["run"]["status"] in {"completed", "aborted", "failed"}:
        return {}
    if state["run"]["awaiting_user"]:
        return {}
    if state["plan"] is None:
        declared = state["run"].get("initial_file_versions") or []
        return {
            "decision": "block",
            "reason": (
                "Use read-only discovery to understand the task, then set the "
                "Chinese AgentVAST Plan. Inputs may be discovered and recorded after "
                "a semantic Node starts."
                if not declared
                else "Set the Chinese AgentVAST semantic Plan before ending this task."
            ),
        }
    active = next(
        (node for node in state["nodes"] if node["status"] == "active"), None
    )
    if active:
        return {
            "decision": "block",
            "reason": (
                f"AgentVAST node {active['node_id']} is still active. Complete it "
                "with the real result before ending this turn."
            ),
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": (
                    "AgentVAST only needs the semantic record; continue the analysis "
                    "only if required, then run python -m agentvast.agent_cli "
                    "complete-node."
                ),
            },
        }
    pending = state["pending_user_inputs"]
    if pending:
        pending_input = pending[0]
        if pending_input["status"] == "classified":
            reason = (
                "Run: python -m agentvast.agent_cli apply-user-input "
                f"{pending_input['input_event_id']} "
                "\"REAL_WORKFLOW_EFFECT\""
            )
        else:
            reason = (
                "Run: python -m agentvast.agent_cli classify-user-input "
                f"{pending_input['input_event_id']} INPUT_TYPE; replace "
                "INPUT_TYPE with conversation_only, checkpoint_continue, "
                "analysis_guidance, planning_input, or challenge"
            )
        return {
            "decision": "block",
            "reason": reason,
        }
    completed_nodes = {
        node["node_id"] for node in state["nodes"] if node["status"] == "completed"
    }
    checkpoint_mode = state["run"]["checkpoint_mode"] or "plan"
    if (
        checkpoint_mode in {"plan", "node"}
        and state["run"].get("plan_approved_version")
        != state["plan"]["version"]
    ):
        return {
            "decision": "block",
            "reason": (
                "Print the task and complete current Plan. Stable Node IDs, Chinese "
                "objectives, dependencies, and artifact types must exactly match the "
                "structured Web Plan. End with: Plan 已生成，请在右侧查看、编辑或确认。 "
                "Every new Revision requires approval. If the user challenged the "
                "Plan, revise it first; set-plan opens the checkpoint automatically."
            ),
        }
    unfinished = [
        node["node_id"]
        for node in state["plan"]["nodes"]
        if node["node_id"] not in completed_nodes
    ]
    if unfinished:
        if checkpoint_mode == "node":
            latest_completed = next(
                (
                    node
                    for node in reversed(state["nodes"])
                    if node["status"] == "completed"
                ),
                None,
            )
            if (
                latest_completed
                and state["run"]["checkpoint_approved_node_id"]
                != latest_completed["node_id"]
            ):
                return {
                    "decision": "block",
                    "reason": (
                        "Run python -m agentvast.agent_cli pause-for-user, "
                        "present the completed Node, and ask whether to continue."
                    ),
                }
        return {
            "decision": "block",
            "reason": (
                "Complete every node in the current AgentVAST Plan before ending: "
                + ", ".join(unfinished)
            ),
        }
    if checkpoint_mode == "node":
        latest_completed = next(
            (
                node
                for node in reversed(state["nodes"])
                if node["status"] == "completed"
            ),
            None,
        )
        if (
            latest_completed
            and state["run"]["checkpoint_approved_node_id"]
            != latest_completed["node_id"]
        ):
            return {
                "decision": "block",
                "reason": (
                    "Run python -m agentvast.agent_cli pause-for-user, present "
                    "the completed Node, and ask whether to continue."
                ),
            }
    if (
        checkpoint_mode == "final"
        and state["run"]["final_approved_plan_version"]
        != state["plan"]["version"]
    ):
        return {
            "decision": "block",
            "reason": (
                "Run python -m agentvast.agent_cli pause-for-user, present the "
                "completed analysis, and ask for explicit final confirmation."
            ),
        }
    # A completed Plan is an idle boundary, not the end of the trace. The same
    # Run remains active so the next user turn can append a truthful Revision.
    return {}


HANDLERS = {
    "SessionStart": session_start,
    "UserPromptSubmit": user_prompt_submit,
    "PreToolUse": pre_tool_use,
    "PostToolUse": lambda payload: observed_event("PostToolUse", payload),
    "PostToolUseFailure": lambda payload: observed_event(
        "PostToolUseFailure", payload
    ),
    "StopFailure": lambda payload: observed_event("StopFailure", payload),
    "PreCompact": lambda payload: observed_event("PreCompact", payload),
    "PostCompact": lambda payload: observed_event("PostCompact", payload),
    "SessionEnd": lambda payload: observed_event("SessionEnd", payload),
    "Stop": stop,
}


def main() -> int:
    payload = _read_input()
    event_name = payload.get("hook_event_name")
    handler = HANDLERS.get(event_name)
    if handler is None:
        return 0
    try:
        result = handler(payload)
    except Exception as error:
        if event_name == "PreToolUse":
            result = _deny(f"AgentVAST recorder error: {error}")
        elif event_name == "Stop":
            result = {
                "decision": "block",
                "reason": (
                    "AgentVAST could not verify that this Run is complete: "
                    f"{error}"
                ),
            }
        else:
            result = _context_output(
                str(event_name),
                f"AgentVAST recorder error: {error}. Do not claim this event was recorded.",
            )
    if result:
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
