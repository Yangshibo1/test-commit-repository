"""Deterministic Hook/OTel/Transcript alignment for canonical trajectories."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, Iterator, List, Mapping, Optional, Set

from agentvast.observer.store import ensure_session_layout, iter_jsonl, write_jsonl
from agentvast.observer.trace_builder import (
    build_observer_trace,
    is_human_prompt,
    stable_id,
)


TOOL_TERMINALS = {"PostToolUse": True, "PostToolUseFailure": False}


def _walk(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _find_values(value: Any, keys: Iterable[str]) -> Set[str]:
    wanted = set(keys)
    results: Set[str] = set()
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        for key, child in item.items():
            if key in wanted and isinstance(child, (str, int)):
                results.add(str(child))
    return results


def _otel_attributes(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        raw_attributes = value.get("attributes")
        if isinstance(raw_attributes, list):
            for item in raw_attributes:
                if not isinstance(item, dict) or not isinstance(item.get("key"), str):
                    continue
                raw_value = item.get("value")
                if isinstance(raw_value, dict) and raw_value:
                    result[item["key"]] = next(iter(raw_value.values()))
                else:
                    result[item["key"]] = raw_value
        elif isinstance(raw_attributes, dict):
            result.update(raw_attributes)
        return result
    return {}


def _event_id() -> str:
    return "canonical_" + uuid.uuid4().hex


def _otel_event_time(record: Mapping[str, Any], attributes: Mapping[str, Any]) -> Optional[str]:
    timestamp = attributes.get("event.timestamp") or record.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        return timestamp
    raw_nanos = (
        record.get("time_unix_nano")
        or record.get("timeUnixNano")
        or record.get("start_time_unix_nano")
        or record.get("startTimeUnixNano")
    )
    try:
        return datetime.fromtimestamp(int(raw_nanos) / 1_000_000_000, timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _evidence(source: str, event_id: Any) -> Dict[str, Any]:
    return {"source": source, "event_id": str(event_id)}


def _hook_payload(event: Mapping[str, Any]) -> Dict[str, Any]:
    payload = event.get("raw_payload")
    return payload if isinstance(payload, dict) else {}


def _correlation(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": payload.get("request_id"),
        "message_uuid": payload.get("message_uuid") or payload.get("message_id"),
    }


def _message_display_state(events: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Describe whether one MessageDisplay stream is safe to treat as complete."""
    materialized = list(events)
    indexes = sorted(
        int(_hook_payload(item).get("index") or 0) for item in materialized
    )
    unique_indexes = sorted(set(indexes))
    expected_indexes = (
        list(range(unique_indexes[-1] + 1)) if unique_indexes else []
    )
    final_indexes = sorted(
        int(_hook_payload(item).get("index") or 0)
        for item in materialized
        if bool(_hook_payload(item).get("final"))
    )
    complete = bool(
        unique_indexes
        and unique_indexes == expected_indexes
        and len(indexes) == len(unique_indexes)
        and final_indexes
        and final_indexes[-1] == unique_indexes[-1]
    )
    return {
        "complete": complete,
        "indexes": unique_indexes,
        "missing_indexes": sorted(set(expected_indexes) - set(unique_indexes)),
        "duplicate_indexes": sorted(
            index for index in unique_indexes if indexes.count(index) > 1
        ),
        "final_seen": bool(final_indexes),
    }


def _transcript_tool_result(
    envelopes: Iterable[Mapping[str, Any]], tool_use_id: str
) -> Optional[Dict[str, Any]]:
    for envelope in envelopes:
        record = envelope.get("record") if envelope.get("parsed") else None
        message = record.get("message") if isinstance(record, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and str(block.get("tool_use_id") or "") == tool_use_id
            ):
                return {"block": block, "record": record, "envelope": envelope}
    return None


def derive_session(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    directory = ensure_session_layout(session_id, root)
    hooks = sorted(
        list(iter_jsonl(directory / "raw" / "hooks.jsonl")),
        key=lambda item: int(item.get("observer_sequence") or 0),
    )
    otel = list(iter_jsonl(directory / "raw" / "otel.jsonl"))
    transcript = list(iter_jsonl(directory / "raw" / "transcript.jsonl"))

    otel_by_tool: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    otel_by_prompt: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    otel_records: List[Dict[str, Any]] = []
    for export in otel:
        raw = export.get("raw_payload")
        decoded = raw.get("decoded") if isinstance(raw, dict) else None
        for item in _walk(decoded):
            if not isinstance(item, dict):
                continue
            attributes = _otel_attributes(item)
            if not attributes:
                continue
            record = {
                "record_index": len(otel_records),
                "export": export,
                "record": item,
                "attributes": attributes,
            }
            otel_records.append(record)
            tool_ids = {
                str(value)
                for key, value in attributes.items()
                if key in {"tool_use_id", "tool.use_id"} and value is not None
            }
            prompt_ids = {
                str(value)
                for key, value in attributes.items()
                if key in {"prompt.id", "prompt_id"} and value is not None
            }
            for tool_id in tool_ids:
                otel_by_tool[tool_id].append(record)
            for prompt_id in prompt_ids:
                otel_by_prompt[prompt_id].append(record)

    transcript_by_tool: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    transcript_by_prompt: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for envelope in transcript:
        record = envelope.get("record") if envelope.get("parsed") else None
        for tool_id in _find_values(record, {"tool_use_id", "tool_use_id"}):
            transcript_by_tool[tool_id].append(envelope)
        for prompt_id in _find_values(record, {"prompt_id", "prompt.id"}):
            transcript_by_prompt[prompt_id].append(envelope)

    tool_events: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    messages: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    agents: Dict[str, Dict[str, Any]] = {}
    canonical: List[Dict[str, Any]] = []
    used_otel_records: Set[int] = set()

    for event in hooks:
        payload = _hook_payload(event)
        event_name = str(payload.get("hook_event_name") or "unknown")
        tool_use_id = payload.get("tool_use_id")
        if tool_use_id:
            tool_events[str(tool_use_id)].append(event)
        if event_name == "MessageDisplay":
            key = "|".join(
                str(payload.get(name) or "")
                for name in ("session_id", "turn_id", "message_id")
            )
            messages[key].append(event)
            continue
        if event_name in {"PreToolUse", "PostToolUse", "PostToolUseFailure"}:
            continue
        if event_name in {"SubagentStart", "SubagentStop"}:
            agent_id = str(payload.get("agent_id") or "unknown")
            current = agents.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "agent_type": payload.get("agent_type"),
                    "parent_agent_id": payload.get("parent_agent_id"),
                    "started_at": None,
                    "ended_at": None,
                    "agent_transcript_path": None,
                    "last_assistant_message": None,
                    "origin": "observed",
                    "evidence": [],
                },
            )
            current["evidence"].append(_evidence("hook", event["observer_event_id"]))
            if event_name == "SubagentStart":
                current["started_at"] = event.get("observer_received_at")
            else:
                current["ended_at"] = event.get("observer_received_at")
                current["agent_transcript_path"] = payload.get("agent_transcript_path")
                current["last_assistant_message"] = payload.get("last_assistant_message")

        canonical_event = {
            "event_id": _event_id(),
            "event_time": event.get("observer_received_at"),
            "event_order": None,
            "session_id": payload.get("session_id") or session_id,
            "prompt_id": payload.get("prompt_id"),
            "turn_id": payload.get("turn_id"),
            "agent_id": payload.get("agent_id") or "main",
            "parent_agent_id": payload.get("parent_agent_id"),
            "event_type": (
                "user_prompt"
                if event_name == "UserPromptSubmit"
                else "tool_batch"
                if event_name == "PostToolBatch"
                else "lifecycle"
            ),
            "event_name": event_name,
            "origin": "observed",
            "payload": (
                {"prompt": payload.get("prompt")}
                if event_name == "UserPromptSubmit"
                else payload
            ),
            "correlation": _correlation(payload),
            "evidence": [_evidence("hook", event["observer_event_id"])],
        }
        if event_name == "PostToolBatch":
            batch_id = payload.get("batch_id") or (
                "derived_batch_" + str(event["observer_event_id"])
            )
            canonical_event["batch"] = {
                "batch_id": batch_id,
                "origin": "observed" if payload.get("batch_id") else "derived",
                "tool_use_ids": sorted(
                    _find_values(payload.get("tool_results"), {"tool_use_id"})
                ),
            }
        prompt_id = payload.get("prompt_id")
        if prompt_id:
            for record in otel_by_prompt.get(str(prompt_id), []):
                export = record["export"]
                canonical_event["evidence"].append(
                    _evidence("otel", export["observer_event_id"])
                )
                used_otel_records.add(int(record["record_index"]))
            for envelope in transcript_by_prompt.get(str(prompt_id), []):
                canonical_event["evidence"].append(
                    _evidence("transcript", "line:{0}".format(envelope["line_number"]))
                )
        canonical.append(canonical_event)

    tool_calls: List[Dict[str, Any]] = []
    for tool_use_id, events in tool_events.items():
        ordered = sorted(events, key=lambda item: int(item.get("observer_sequence") or 0))
        payloads = [_hook_payload(item) for item in ordered]
        pre = next((p for p in payloads if p.get("hook_event_name") == "PreToolUse"), None)
        terminal_payload = next(
            (p for p in reversed(payloads) if p.get("hook_event_name") in TOOL_TERMINALS),
            None,
        )
        terminal_event = next(
            (
                item
                for item in reversed(ordered)
                if _hook_payload(item).get("hook_event_name") in TOOL_TERMINALS
            ),
            None,
        )
        basis = terminal_payload or pre or {}
        evidence = [_evidence("hook", item["observer_event_id"]) for item in ordered]
        for record in otel_by_tool.get(tool_use_id, []):
            export = record["export"]
            evidence.append(_evidence("otel", export["observer_event_id"]))
            used_otel_records.add(int(record["record_index"]))
        for envelope in transcript_by_tool.get(tool_use_id, []):
            evidence.append(
                _evidence("transcript", "line:{0}".format(envelope["line_number"]))
            )
        transcript_result = _transcript_tool_result(
            transcript_by_tool.get(tool_use_id, []), tool_use_id
        )
        success = (
            TOOL_TERMINALS.get(str(terminal_payload.get("hook_event_name")))
            if terminal_payload
            else not bool(transcript_result["block"].get("is_error"))
            if transcript_result
            else None
        )
        canonical_event = {
            "event_id": _event_id(),
            "event_time": (
                terminal_event.get("observer_received_at")
                if terminal_event
                else transcript_result["record"].get("timestamp")
                if transcript_result
                else ordered[0].get("observer_received_at")
            ),
            "event_order": None,
            "session_id": basis.get("session_id") or session_id,
            "prompt_id": basis.get("prompt_id"),
            "turn_id": basis.get("turn_id"),
            "agent_id": basis.get("agent_id") or "main",
            "parent_agent_id": basis.get("parent_agent_id"),
            "event_type": "tool_execution",
            "origin": "observed",
            "tool": {
                "tool_use_id": tool_use_id,
                "name": basis.get("tool_name"),
                "input": basis.get("tool_input"),
                "output": (
                    terminal_payload.get("tool_response")
                    if terminal_payload
                    else transcript_result["block"].get("content")
                    if transcript_result
                    else None
                ),
                "error": (
                    terminal_payload.get("error")
                    if terminal_payload
                    else transcript_result["block"].get("content")
                    if transcript_result and transcript_result["block"].get("is_error")
                    else None
                ),
                "success": success,
                "duration_ms": terminal_payload.get("duration_ms") if terminal_payload else None,
            },
            "correlation": _correlation(basis),
            "evidence": evidence,
        }
        tool_calls.append(canonical_event)
        canonical.append(canonical_event)

    rebuilt_messages: List[Dict[str, Any]] = []
    incomplete_display_groups = 0
    complete_display_contents: Set[str] = set()
    for _, events in messages.items():
        ordered = sorted(
            events,
            key=lambda item: int(_hook_payload(item).get("index") or 0),
        )
        display_state = _message_display_state(ordered)
        if not display_state["complete"]:
            # The immutable Hook fragments remain in raw/hooks.jsonl. Do not
            # promote a truncated stream to a canonical assistant message;
            # the native transcript below is the deterministic fallback.
            incomplete_display_groups += 1
            continue
        payload = _hook_payload(ordered[-1])
        content = "".join(
            str(_hook_payload(item).get("delta") or "") for item in ordered
        )
        message = {
            "event_id": _event_id(),
            "event_time": ordered[-1].get("observer_received_at"),
            "event_order": None,
            "session_id": payload.get("session_id") or session_id,
            "prompt_id": payload.get("prompt_id"),
            "turn_id": payload.get("turn_id"),
            "agent_id": payload.get("agent_id") or "main",
            "parent_agent_id": payload.get("parent_agent_id"),
            "event_type": "assistant_message",
            "origin": "derived",
            "message": {
                "message_id": payload.get("message_id"),
                "content": content,
                "final": True,
                "delta_count": len(ordered),
                "capture_complete": True,
            },
            "correlation": _correlation(payload),
            "evidence": [_evidence("hook", item["observer_event_id"]) for item in ordered],
        }
        complete_display_contents.add(content)
        rebuilt_messages.append(message)
        canonical.append(message)

    # Older Claude Code versions may not support MessageDisplay or newer Hook
    # events. The native transcript remains an observed source, so use it as a
    # deterministic fallback without assigning workflow semantics.
    hook_prompt_ids = {
        str(_hook_payload(item).get("prompt_id"))
        for item in hooks
        if _hook_payload(item).get("hook_event_name") == "UserPromptSubmit"
        and _hook_payload(item).get("prompt_id")
    }
    transcript_tool_uses: Dict[str, Dict[str, Any]] = {}
    transcript_tool_results: Dict[str, Dict[str, Any]] = {}
    for envelope in transcript:
        if not envelope.get("parsed") or not isinstance(envelope.get("record"), dict):
            continue
        record = envelope["record"]
        record_type = str(record.get("type") or "")
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("id"):
                transcript_tool_uses[str(block["id"])] = {
                    "block": block,
                    "record": record,
                    "envelope": envelope,
                }
            if block.get("type") == "tool_result" and block.get("tool_use_id"):
                transcript_tool_results[str(block["tool_use_id"])] = {
                    "block": block,
                    "record": record,
                    "envelope": envelope,
                }

        prompt_id = record.get("promptId") or record.get("prompt_id")
        evidence = [_evidence("transcript", "line:{0}".format(envelope["line_number"]))]
        if record_type == "user" and not blocks:
            if not isinstance(content, str) or not content:
                continue
            if not is_human_prompt(record):
                continue
            if prompt_id and str(prompt_id) in hook_prompt_ids:
                continue
            prompt_event = {
                "event_id": _event_id(),
                "event_time": record.get("timestamp"),
                "event_order": None,
                "session_id": record.get("sessionId") or session_id,
                "prompt_id": prompt_id,
                "turn_id": record.get("uuid"),
                "parent_message_uuid": record.get("parentUuid"),
                "agent_id": "main",
                "parent_agent_id": None,
                "event_type": "user_prompt",
                "event_name": "TranscriptUserMessage",
                "origin": "observed",
                "message": {
                    "message_id": record.get("uuid"),
                    "role": "user",
                    "content": content,
                },
                "correlation": {
                    "request_id": None,
                    "message_uuid": record.get("uuid"),
                },
                "evidence": evidence,
            }
            rebuilt_messages.append(prompt_event)
            canonical.append(prompt_event)
        elif record_type == "assistant" and (
            not messages or incomplete_display_groups
        ):
            text_blocks = [
                str(block.get("text") or "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            visible_text = "".join(text_blocks)
            if not visible_text:
                continue
            if visible_text in complete_display_contents:
                continue
            assistant_event = {
                "event_id": _event_id(),
                "event_time": record.get("timestamp"),
                "event_order": None,
                "session_id": record.get("sessionId") or session_id,
                "prompt_id": prompt_id,
                "turn_id": record.get("uuid"),
                "parent_message_uuid": record.get("parentUuid"),
                "agent_id": "main",
                "parent_agent_id": None,
                "event_type": "assistant_message",
                "event_name": "TranscriptAssistantMessage",
                "origin": "observed",
                "message": {
                    "message_id": message.get("id") or record.get("uuid"),
                    "role": "assistant",
                    "content": visible_text,
                    "model": message.get("model"),
                    "usage": message.get("usage"),
                    "capture_complete": True,
                    "capture_source": "transcript_fallback",
                },
                "correlation": {
                    "request_id": message.get("id"),
                    "message_uuid": record.get("uuid"),
                },
                "evidence": evidence,
            }
            rebuilt_messages.append(assistant_event)
            canonical.append(assistant_event)

    for tool_use_id, observed_use in transcript_tool_uses.items():
        if tool_use_id in tool_events:
            continue
        result = transcript_tool_results.get(tool_use_id)
        use_block = observed_use["block"]
        use_record = observed_use["record"]
        evidence = [
            _evidence(
                "transcript",
                "line:{0}".format(observed_use["envelope"]["line_number"]),
            )
        ]
        if result:
            evidence.append(
                _evidence(
                    "transcript",
                    "line:{0}".format(result["envelope"]["line_number"]),
                )
            )
        result_block = result["block"] if result else {}
        use_message = use_record.get("message")
        transcript_tool = {
            "event_id": _event_id(),
            "event_time": (
                result["record"].get("timestamp") if result else use_record.get("timestamp")
            ),
            "event_order": None,
            "session_id": use_record.get("sessionId") or session_id,
            "prompt_id": use_record.get("promptId") or use_record.get("prompt_id"),
            "turn_id": use_record.get("uuid"),
            "parent_message_uuid": use_record.get("parentUuid"),
            "agent_id": "main",
            "parent_agent_id": None,
            "event_type": "tool_execution",
            "event_name": "TranscriptToolExecution",
            "origin": "observed",
            "tool": {
                "tool_use_id": tool_use_id,
                "name": use_block.get("name"),
                "input": use_block.get("input"),
                "output": result_block.get("content") if result else None,
                "error": (
                    result_block.get("content")
                    if result and result_block.get("is_error")
                    else None
                ),
                "success": (
                    not bool(result_block.get("is_error")) if result else None
                ),
                "duration_ms": None,
                "structured_output": (
                    result["record"].get("toolUseResult") if result else None
                ),
                "started_at": use_record.get("timestamp"),
                "ended_at": result["record"].get("timestamp") if result else None,
            },
            "correlation": {
                "request_id": (
                    use_message.get("id") if isinstance(use_message, dict) else None
                ),
                "message_uuid": use_record.get("uuid"),
                "response_id": (
                    use_message.get("id") if isinstance(use_message, dict) else None
                ),
            },
            "evidence": evidence,
        }
        tool_calls.append(transcript_tool)
        canonical.append(transcript_tool)

    decoded_export_ids = {
        str(record["export"].get("observer_event_id")) for record in otel_records
    }
    for record in otel_records:
        if int(record["record_index"]) in used_otel_records:
            continue
        export = record["export"]
        export_id = str(export.get("observer_event_id"))
        attributes = record["attributes"]
        canonical.append(
            {
                "event_id": _event_id(),
                "event_time": _otel_event_time(record["record"], attributes)
                or export.get("observer_received_at"),
                "event_order": None,
                "session_id": session_id,
                "prompt_id": attributes.get("prompt.id") or attributes.get("prompt_id"),
                "turn_id": attributes.get("turn_id"),
                "agent_id": attributes.get("agent_id") or "main",
                "parent_agent_id": attributes.get("parent_agent_id"),
                "event_type": "telemetry",
                "event_name": attributes.get("event.name") or attributes.get("name"),
                "origin": "observed",
                "telemetry": {
                    "attributes": attributes,
                    "record": record["record"],
                },
                "correlation": {
                    "request_id": attributes.get("request_id"),
                    "message_uuid": attributes.get("message.uuid"),
                },
                "evidence": [_evidence("otel", export_id)],
            }
        )

    for export in otel:
        export_id = str(export.get("observer_event_id"))
        if export_id in decoded_export_ids:
            continue
        raw = export.get("raw_payload") or {}
        canonical.append(
            {
                "event_id": _event_id(),
                "event_time": export.get("observer_received_at"),
                "event_order": None,
                "session_id": session_id,
                "prompt_id": None,
                "turn_id": None,
                "agent_id": "main",
                "parent_agent_id": None,
                "event_type": "telemetry_export",
                "origin": "observed",
                "telemetry": {
                    "request_path": raw.get("request_path") if isinstance(raw, dict) else None,
                    "decoded_format": raw.get("decoded_format") if isinstance(raw, dict) else None,
                },
                "correlation": {"request_id": None, "message_uuid": None},
                "evidence": [_evidence("otel", export_id)],
            }
        )

    for event in canonical:
        event["event_id"] = stable_id(
            "canonical",
            session_id,
            event.get("event_type"),
            event.get("event_name"),
            (event.get("tool") or {}).get("tool_use_id"),
            (event.get("message") or {}).get("message_id"),
            event.get("correlation"),
            event.get("evidence"),
        )
    canonical.sort(key=lambda item: (str(item.get("event_time") or ""), item["event_id"]))
    for index, event in enumerate(canonical, start=1):
        event["event_order"] = index
        event["field_origins"] = {
            "event_id": "derived",
            "event_order": "derived",
            "event_time": "observed",
            "session_id": "observed",
            "prompt_id": "observed",
            "turn_id": "observed",
            "agent_id": "observed",
            "parent_agent_id": (
                "observed" if event.get("parent_agent_id") is not None else "derived"
            ),
            "evidence": "derived",
        }

    write_jsonl(directory / "derived" / "canonical_events.jsonl", canonical)
    write_jsonl(directory / "derived" / "messages.jsonl", rebuilt_messages)
    write_jsonl(directory / "derived" / "tool_calls.jsonl", tool_calls)
    write_jsonl(directory / "derived" / "agents.jsonl", agents.values())
    observer_trace = build_observer_trace(session_id, str(directory.parent))
    return {
        "session_id": session_id,
        "canonical_event_count": len(canonical),
        "tool_call_count": len(tool_calls),
        "message_count": len(rebuilt_messages),
        "agent_count": len(agents),
        "otel_export_count": len(otel),
        "transcript_record_count": len(transcript),
        "observer_turn_count": len(observer_trace["turns"]),
        "observer_event_count": len(observer_trace["events"]),
    }
