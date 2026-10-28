"""Compact Event facts on disk; expand historical aliases only for consumers."""

from copy import deepcopy
from typing import Any, Dict, Mapping

EVENT_CLASSES = {
    "user_prompt": "interaction",
    "model_response": "interaction",
    "assistant_message": "interaction",
    "tool_execution": "execution",
    "command_execution": "execution",
    "subagent_result": "delegation",
    "control_event": "control",
}


def expand_event(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Read compact and legacy Events without modifying either representation."""
    event = deepcopy(dict(value))
    scope = event["scope"] = dict(event.get("scope") or {})
    for key in ("turn_id", "response_id", "tool_use_id"):
        if event.get(key) is not None:
            scope.setdefault(key, event[key])
        event.setdefault(key, scope.get(key))
    timing = event["time"] = dict(event.get("time") or {})
    timing.setdefault("started_at", event.get("timestamp"))
    timing.setdefault("ended_at", event.get("ended_at"))
    timing.setdefault("duration_ms", None)
    event.setdefault("timestamp", timing.get("started_at"))
    event.setdefault("ended_at", timing.get("ended_at"))
    provenance = event["provenance"] = dict(event.get("provenance") or {})
    provenance.setdefault("source", "transcript")
    provenance.setdefault("source_lines", event.get("source_lines") or [])
    event.setdefault("source_lines", list(provenance["source_lines"]))
    event.setdefault(
        "evidence",
        [
            {"source": provenance["source"], "line_number": line}
            for line in provenance["source_lines"]
        ],
    )
    event.setdefault("parent_uuid", provenance.get("parent_uuid"))
    event.setdefault("message_uuid", next(iter(provenance.get("source_uuids") or []), None))
    event.setdefault("event_class", EVENT_CLASSES.get(str(event.get("event_type"))))
    event.setdefault("hidden_by_default", False)
    payload = event["payload"] = dict(event.get("payload") or {})
    if event.get("event_type") in {"tool_execution", "command_execution"}:
        payload.setdefault("duration_ms", timing.get("duration_ms"))
        payload.setdefault("observed_elapsed_ms", timing.get("observed_elapsed_ms"))
        payload.setdefault("batch_response_id", scope.get("response_id"))
        if event.get("event_type") == "command_execution":
            tool_input = payload.get("input")
            payload.setdefault(
                "command", tool_input.get("command") if isinstance(tool_input, dict) else None
            )
    elif event.get("event_type") == "model_response":
        payload.setdefault("response_kind", event.get("event_subtype"))
        payload.setdefault("is_final", payload.get("stop_reason") == "end_turn")
        payload.setdefault("record_uuids", provenance.get("source_uuids") or [])
    elif event.get("event_type") == "subagent_result":
        payload.setdefault("task_id", scope.get("task_id"))
        payload.setdefault("status", event.get("status"))
    return event


def compact_event(value: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep one authoritative location for IDs, time, and raw-record references."""
    event = expand_event(value)
    scope = event["scope"]
    for key in ("turn_id", "response_id", "tool_use_id"):
        scope[key] = event.pop(key, None)
    event["scope"] = {key: item for key, item in scope.items() if item is not None}
    timing = event["time"]
    event.pop("timestamp", None)
    event.pop("ended_at", None)
    provenance = event["provenance"]
    parent = event.pop("parent_uuid", None)
    if parent is not None:
        provenance["parent_uuid"] = parent
    message_uuid = event.pop("message_uuid", None)
    if message_uuid and message_uuid not in (provenance.get("source_uuids") or []):
        provenance.setdefault("source_uuids", []).append(message_uuid)
    event.pop("source_lines", None)
    event.pop("evidence", None)
    if event.get("event_class") == EVENT_CLASSES.get(str(event.get("event_type"))):
        event.pop("event_class", None)
    if not event.get("hidden_by_default"):
        event.pop("hidden_by_default", None)
    payload = event["payload"]
    if event.get("event_type") in {"tool_execution", "command_execution"}:
        elapsed = payload.pop("observed_elapsed_ms", None)
        if elapsed is not None:
            timing["observed_elapsed_ms"] = elapsed
        if payload.get("duration_ms") == timing.get("duration_ms"):
            payload.pop("duration_ms", None)
        if payload.get("batch_response_id") == event["scope"].get("response_id"):
            payload.pop("batch_response_id", None)
        if event.get("event_type") == "command_execution":
            tool_input = payload.get("input")
            command = tool_input.get("command") if isinstance(tool_input, dict) else None
            if payload.get("command") == command:
                payload.pop("command", None)
        structured = payload.get("structured_result")
        if isinstance(structured, dict):
            if structured.get("durationMs") == timing.get("duration_ms"):
                structured.pop("durationMs", None)
            if "exit_code" in payload and structured.get("exitCode") == payload["exit_code"]:
                structured.pop("exitCode", None)
            if "timed_out" in payload and structured.get("timedOut") == payload["timed_out"]:
                structured.pop("timedOut", None)
            # Preserve explicitly separate streams; generic tool output is not stdout.
            for key in ("stdout", "stderr"):
                if key in payload and structured.get(key) == payload[key]:
                    structured.pop(key, None)
            if not structured:
                payload.pop("structured_result", None)
        if payload.get("structured_result") is None:
            payload.pop("structured_result", None)
    elif event.get("event_type") == "model_response":
        if payload.get("response_kind") == event.get("event_subtype"):
            payload.pop("response_kind", None)
        if payload.get("is_final") == (payload.get("stop_reason") == "end_turn"):
            payload.pop("is_final", None)
        if payload.get("record_uuids") == provenance.get("source_uuids"):
            payload.pop("record_uuids", None)
    elif event.get("event_type") == "subagent_result":
        if payload.get("task_id") == event["scope"].get("task_id"):
            payload.pop("task_id", None)
        if payload.get("status") == event.get("status"):
            payload.pop("status", None)
        if payload.get("content") == payload.get("result"):
            payload.pop("content", None)
    return event
