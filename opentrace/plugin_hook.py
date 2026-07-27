"""Claude Code hook bridge for the OpenTrace prototype.

Hooks observe Claude Code.  They never execute data analysis or manufacture
semantic step descriptions.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Tuple

from opentrace.workflow_store import WorkflowError, WorkflowStore


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


def _store_and_run() -> Tuple[WorkflowStore, str]:
    database = os.environ.get("OPENTRACE_DB")
    run_id = os.environ.get("OPENTRACE_RUN_ID")
    if not database or not run_id:
        raise WorkflowError("OpenTrace hook environment is not configured")
    return WorkflowStore(database), run_id


def session_start(payload: Dict[str, Any]) -> Dict[str, Any]:
    store, run_id = _store_and_run()
    state = store.get_state(run_id)
    active = next(
        (step for step in state["steps"] if step["status"] == "active"), None
    )
    context = {
        "opentrace_run_id": run_id,
        "role_boundary": (
            "Claude Code performs all data analysis. OpenTrace only records and "
            "validates the real workflow."
        ),
        "required_flow": (
            "Set a semantic plan, start one step before material "
            "Read/Bash/Write/Edit analysis, then complete it truthfully. Do not "
            "create a step merely because a Python script or intermediate file exists."
        ),
        "plan": state["plan"],
        "active_step": active,
        "pending_user_inputs": state["pending_user_inputs"],
    }
    store.record_hook_event(run_id, "SessionStart", _trim(payload))
    return _context_output("SessionStart", json.dumps(context, ensure_ascii=False))


def user_prompt_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(payload.get("prompt") or "")
    if prompt.startswith("[OPENTRACE_INITIAL_TASK "):
        return {}
    store, run_id = _store_and_run()
    event = store.capture_user_input(
        run_id=run_id,
        original_text=prompt,
        claude_session_id=payload.get("session_id"),
    )
    return _context_output(
        "UserPromptSubmit",
        (
            "OpenTrace captured this human input as "
            f"{event['input_event_id']}. Before the next material analysis tool, "
            "call opentrace_classify_user_input with conversation_only, "
            "analysis_guidance, planning_input, or challenge. Human input is not "
            "itself a Step. For the last three types, also call "
            "opentrace_apply_user_input after recording its real workflow effect."
        ),
    )


def pre_tool_use(payload: Dict[str, Any]) -> Dict[str, Any]:
    store, run_id = _store_and_run()
    reason = store.gate_reason(run_id)
    if reason:
        store.record_hook_event(
            run_id,
            "PreToolUseBlocked",
            _trim({**payload, "opentrace_reason": reason}),
        )
        return _deny(reason)
    return {}


def observed_event(event_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    store, run_id = _store_and_run()
    store.record_hook_event(run_id, event_name, _trim(payload))
    return {}


def stop(payload: Dict[str, Any]) -> Dict[str, Any]:
    store, run_id = _store_and_run()
    state = store.get_state(run_id)
    active = next(
        (step for step in state["steps"] if step["status"] == "active"), None
    )
    if active:
        return {
            "decision": "block",
            "reason": (
                f"OpenTrace step {active['step_id']} is still active. Complete it "
                "with the real result before ending this turn."
            ),
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": (
                    "OpenTrace only needs the semantic record; continue the analysis "
                    "only if required, then call opentrace_complete_step."
                ),
            },
        }
    pending = state["pending_user_inputs"]
    if pending:
        return {
            "decision": "block",
            "reason": (
                "Classify the pending OpenTrace user input before ending: "
                f"{pending[0]['input_event_id']}"
            ),
        }
    return {}


HANDLERS = {
    "SessionStart": session_start,
    "UserPromptSubmit": user_prompt_submit,
    "PreToolUse": pre_tool_use,
    "PostToolUse": lambda payload: observed_event("PostToolUse", payload),
    "PostToolUseFailure": lambda payload: observed_event(
        "PostToolUseFailure", payload
    ),
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
            result = _deny(f"OpenTrace recorder error: {error}")
        else:
            result = _context_output(
                str(event_name),
                f"OpenTrace recorder error: {error}. Do not claim this event was recorded.",
            )
    if result:
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
