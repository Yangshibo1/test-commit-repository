"""Build a deterministic, read-only execution trace from Claude transcripts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Mapping, Optional, Set, Tuple

from agentvast.observer.store import (
    default_observations_root,
    ensure_session_layout,
    iter_jsonl,
    read_manifest,
    session_directory,
    update_manifest,
)


TRACE_SCHEMA_VERSION = "observer-trace/1.0"
LOCAL_MARKERS = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-name>",
)


def stable_id(prefix: str, *parts: Any) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]
    return "{0}_{1}".format(prefix, digest)


def transcript_record(envelope: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    record = envelope.get("record") if envelope.get("parsed") else None
    return record if isinstance(record, dict) else None


def message_content(record: Mapping[str, Any]) -> Any:
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


def is_human_prompt(record: Mapping[str, Any]) -> bool:
    """Return true only for a real human-authored task/follow-up message."""
    if record.get("type") != "user" or bool(record.get("isMeta")):
        return False
    content = message_content(record)
    if not isinstance(content, str) or not content.strip():
        return False
    if any(marker in content for marker in LOCAL_MARKERS):
        return False
    origin = record.get("origin")
    origin_kind = origin.get("kind") if isinstance(origin, dict) else None
    prompt_source = str(record.get("promptSource") or "").lower()
    return bool(origin_kind == "human" or prompt_source in {"typed", "pasted", "voice"})


def is_subagent_notification(record: Mapping[str, Any]) -> bool:
    if record.get("type") != "user":
        return False
    content = message_content(record)
    if not isinstance(content, str):
        return False
    origin = record.get("origin")
    origin_kind = origin.get("kind") if isinstance(origin, dict) else None
    return origin_kind == "task-notification" or "<task-notification>" in content


def _xml_value(text: str, name: str) -> Optional[str]:
    match = re.search(r"<{0}>(.*?)</{0}>".format(re.escape(name)), text, flags=re.DOTALL)
    return match.group(1).strip() if match else None


def is_local_user_record(record: Mapping[str, Any]) -> bool:
    if record.get("type") != "user":
        return False
    content = message_content(record)
    return isinstance(content, str) and any(marker in content for marker in LOCAL_MARKERS)


def _iso_milliseconds(start: Any, end: Any) -> Optional[int]:
    try:
        left = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        right = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return max(0, int((right - left).total_seconds() * 1000))
    except (TypeError, ValueError):
        return None


def _text_preview(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_summary(name: str, tool_input: Any) -> str:
    if not isinstance(tool_input, dict):
        return name
    for key in ("description", "file_path", "path", "pattern", "query", "command"):
        if tool_input.get(key):
            return _text_preview(tool_input[key])
    return name


def _evidence(lines: Iterable[int]) -> List[Dict[str, Any]]:
    return [{"source": "transcript", "line_number": int(line)} for line in sorted(set(lines))]


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp-" + stable_id("write", os.getpid(), path))
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def build_observer_trace(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    directory = ensure_session_layout(session_id, root)
    manifest = read_manifest(session_id, root)
    envelopes = list(iter_jsonl(directory / "raw" / "transcript.jsonl"))
    parsed: List[Tuple[int, Dict[str, Any]]] = []
    for envelope in envelopes:
        record = transcript_record(envelope)
        if record is not None:
            parsed.append((int(envelope.get("line_number") or 0), record))

    events: List[Dict[str, Any]] = []
    relations: List[Dict[str, Any]] = []
    relation_keys: Set[Tuple[str, str, str]] = set()
    turns: List[Dict[str, Any]] = []
    line_to_turn: Dict[int, Optional[str]] = {}
    uuid_to_event: Dict[str, str] = {}
    current_turn: Optional[str] = None
    prompt_event_by_turn: Dict[str, str] = {}
    filtered_non_human_users = 0
    local_command_count = 0
    subagent_result_count = 0

    def add_relation(source: str, target: str, relation_type: str) -> None:
        if not source or not target or source == target:
            return
        key = (source, target, relation_type)
        if key in relation_keys:
            return
        relation_keys.add(key)
        relations.append(
            {
                "relation_id": stable_id("rel", session_id, *key),
                "from": source,
                "to": target,
                "type": relation_type,
                "origin": "derived",
            }
        )

    # First pass: identify genuine human turns and classify transcript-only metadata.
    for line_number, record in parsed:
        if is_human_prompt(record):
            message_uuid = str(record.get("uuid") or "line-{0}".format(line_number))
            current_turn = stable_id("turn", session_id, message_uuid)
            event_id = stable_id("event", session_id, "prompt", message_uuid)
            content = str(message_content(record) or "")
            prompt_event = {
                "event_id": event_id,
                "sequence": 0,
                "event_type": "user_prompt",
                "timestamp": record.get("timestamp"),
                "ended_at": None,
                "turn_id": current_turn,
                "parent_uuid": record.get("parentUuid"),
                "message_uuid": record.get("uuid"),
                "response_id": None,
                "tool_use_id": None,
                "status": "observed",
                "origin": "observed",
                "title": "用户任务",
                "summary": _text_preview(content),
                "payload": {
                    "content": content,
                    "prompt_source": record.get("promptSource"),
                    "origin": record.get("origin"),
                    "permission_mode": record.get("permissionMode"),
                },
                "evidence": _evidence([line_number]),
                "source_lines": [line_number],
                "hidden_by_default": False,
            }
            events.append(prompt_event)
            prompt_event_by_turn[current_turn] = event_id
            if record.get("uuid"):
                uuid_to_event[str(record["uuid"])] = event_id
            turns.append(
                {
                    "turn_id": current_turn,
                    "prompt_event_id": event_id,
                    "prompt": content,
                    "started_at": record.get("timestamp"),
                    "ended_at": None,
                    "event_ids": [],
                    "tool_call_count": 0,
                    "error_count": 0,
                    "status": "observed",
                }
            )
            line_to_turn[line_number] = current_turn
            continue

        if is_subagent_notification(record):
            subagent_result_count += 1
            content = str(message_content(record) or "")
            task_id = _xml_value(content, "task-id")
            task_summary = _xml_value(content, "summary") or "子 Agent 结果"
            result_text = _xml_value(content, "result") or content
            event_id = stable_id("event", session_id, "subagent-result", task_id or line_number)
            event = {
                "event_id": event_id,
                "sequence": 0,
                "event_type": "subagent_result",
                "timestamp": record.get("timestamp"),
                "ended_at": None,
                "turn_id": current_turn,
                "parent_uuid": record.get("parentUuid"),
                "message_uuid": record.get("uuid"),
                "response_id": None,
                "tool_use_id": _xml_value(content, "tool-use-id"),
                "status": _xml_value(content, "status") or "observed",
                "origin": "observed",
                "title": "子 Agent 结果 · {0}".format(task_summary),
                "summary": _text_preview(result_text),
                "payload": {
                    "task_id": task_id,
                    "task_summary": task_summary,
                    "status": _xml_value(content, "status"),
                    "output_file": _xml_value(content, "output-file"),
                    "result": result_text,
                    "content": content,
                },
                "evidence": _evidence([line_number]),
                "source_lines": [line_number],
                "hidden_by_default": False,
            }
            events.append(event)
            if record.get("uuid"):
                uuid_to_event[str(record["uuid"])] = event_id
            line_to_turn[line_number] = current_turn
            continue
        if record.get("type") == "user" and isinstance(message_content(record), str):
            filtered_non_human_users += 1
            if is_local_user_record(record):
                local_command_count += 1
                content = str(message_content(record) or "")
                event_id = stable_id("event", session_id, "local", line_number)
                event = {
                    "event_id": event_id,
                    "sequence": 0,
                    "event_type": "local_command",
                    "timestamp": record.get("timestamp"),
                    "ended_at": None,
                    "turn_id": None,
                    "parent_uuid": record.get("parentUuid"),
                    "message_uuid": record.get("uuid"),
                    "response_id": None,
                    "tool_use_id": None,
                    "status": "observed",
                    "origin": "observed",
                    "title": "本地命令",
                    "summary": _text_preview(content),
                    "payload": {"content": content},
                    "evidence": _evidence([line_number]),
                    "source_lines": [line_number],
                    "hidden_by_default": True,
                }
                events.append(event)
                if record.get("uuid"):
                    uuid_to_event[str(record["uuid"])] = event_id
            line_to_turn[line_number] = None
            continue
        line_to_turn[line_number] = current_turn

    # Collect tool results before grouping assistant responses.
    tool_results: Dict[str, Dict[str, Any]] = {}
    orphan_result_ids: Set[str] = set()
    for line_number, record in parsed:
        if record.get("type") != "user":
            continue
        content = message_content(record)
        if not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_use_id = str(block.get("tool_use_id") or "")
            if not tool_use_id:
                continue
            tool_results[tool_use_id] = {
                "block": block,
                "record": record,
                "line_number": line_number,
                "block_index": block_index,
                "structured_result": record.get("toolUseResult"),
            }

    response_groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    tool_uses: Dict[str, Dict[str, Any]] = {}
    duplicate_tool_ids: Set[str] = set()
    for line_number, record in parsed:
        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        response_id = str(message.get("id") or record.get("uuid") or line_number)
        turn_id = line_to_turn.get(line_number)
        group_key = "{0}|{1}".format(turn_id or "unassigned", response_id)
        response_groups[group_key].append(
            {"line_number": line_number, "record": record, "message": message}
        )
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_use_id = str(block.get("id") or "")
            if not tool_use_id:
                continue
            if tool_use_id in tool_uses:
                duplicate_tool_ids.add(tool_use_id)
            tool_uses[tool_use_id] = {
                "block": block,
                "record": record,
                "message": message,
                "line_number": line_number,
                "block_index": block_index,
                "turn_id": turn_id,
                "response_key": group_key,
                "response_id": response_id,
            }

    response_event_by_key: Dict[str, str] = {}
    response_tool_ids: DefaultDict[str, List[str]] = defaultdict(list)
    for tool_use_id, use in tool_uses.items():
        response_tool_ids[use["response_key"]].append(tool_use_id)

    for group_key, group in response_groups.items():
        ordered = sorted(group, key=lambda item: item["line_number"])
        first = ordered[0]
        message = first["message"]
        record = first["record"]
        stop_reason = next(
            (
                item["message"].get("stop_reason")
                for item in reversed(ordered)
                if item["message"].get("stop_reason")
            ),
            None,
        )
        response_id = str(message.get("id") or record.get("uuid"))
        turn_id = line_to_turn.get(first["line_number"])
        text_blocks: List[str] = []
        record_uuids: List[str] = []
        for item in ordered:
            raw_content = item["message"].get("content")
            if isinstance(raw_content, list):
                text_blocks.extend(
                    str(block.get("text") or "")
                    for block in raw_content
                    if isinstance(block, dict) and block.get("type") == "text"
                )
            if item["record"].get("uuid"):
                record_uuids.append(str(item["record"]["uuid"]))
        visible_text = "".join(text_blocks)
        tools = sorted(
            response_tool_ids.get(group_key, []),
            key=lambda tool_id: (
                int(tool_uses[tool_id]["line_number"]),
                int(tool_uses[tool_id]["block_index"]),
            ),
        )
        event_type = "model_response" if tools else "assistant_message"
        event_id = stable_id("event", session_id, "response", turn_id, response_id)
        event = {
            "event_id": event_id,
            "sequence": 0,
            "event_type": event_type,
            "timestamp": first["record"].get("timestamp"),
            "ended_at": ordered[-1]["record"].get("timestamp"),
            "turn_id": turn_id,
            "parent_uuid": first["record"].get("parentUuid"),
            "message_uuid": first["record"].get("uuid"),
            "response_id": response_id,
            "tool_use_id": None,
            "status": ("complete" if stop_reason == "end_turn" or visible_text else "observed"),
            "origin": "derived" if len(ordered) > 1 else "observed",
            "title": (
                "工具批次 · {0} 个调用".format(len(tools))
                if tools
                else "Claude 最终回答"
                if stop_reason == "end_turn"
                else "Claude 消息"
            ),
            "summary": (
                ", ".join(
                    str(tool_uses[tool_id]["block"].get("name") or "tool") for tool_id in tools
                )
                if tools
                else _text_preview(visible_text)
            ),
            "payload": {
                "model": message.get("model"),
                "effort": record.get("effort"),
                "stop_reason": stop_reason,
                "text": visible_text,
                "usage": message.get("usage"),
                "tool_use_ids": tools,
                "record_uuids": record_uuids,
            },
            "evidence": _evidence(item["line_number"] for item in ordered),
            "source_lines": [item["line_number"] for item in ordered],
            "hidden_by_default": False,
        }
        events.append(event)
        response_event_by_key[group_key] = event_id
        for item in ordered:
            if item["record"].get("uuid"):
                uuid_to_event[str(item["record"]["uuid"])] = event_id

    tool_event_by_id: Dict[str, str] = {}
    for tool_use_id, use in sorted(tool_uses.items(), key=lambda item: int(item[1]["line_number"])):
        result = tool_results.get(tool_use_id)
        block = use["block"]
        result_block = result["block"] if result else {}
        result_record = result["record"] if result else {}
        structured_result = result.get("structured_result") if result else None
        duration_ms = (
            structured_result.get("durationMs") if isinstance(structured_result, dict) else None
        )
        event_id = stable_id("event", session_id, "tool", tool_use_id)
        status = (
            "error"
            if result and bool(result_block.get("is_error"))
            else "success"
            if result
            else "incomplete"
        )
        source_lines = [int(use["line_number"])]
        if result:
            source_lines.append(int(result["line_number"]))
        event = {
            "event_id": event_id,
            "sequence": 0,
            "event_type": "tool_execution",
            "timestamp": use["record"].get("timestamp"),
            "ended_at": result_record.get("timestamp") if result else None,
            "turn_id": use.get("turn_id"),
            "parent_uuid": use["record"].get("parentUuid"),
            "message_uuid": use["record"].get("uuid"),
            "response_id": use.get("response_id"),
            "tool_use_id": tool_use_id,
            "status": status,
            "origin": "derived",
            "title": str(block.get("name") or "Tool"),
            "summary": _tool_summary(str(block.get("name") or "Tool"), block.get("input")),
            "payload": {
                "name": block.get("name"),
                "input": block.get("input"),
                "output": result_block.get("content") if result else None,
                "is_error": bool(result_block.get("is_error")) if result else None,
                "structured_result": structured_result,
                "duration_ms": duration_ms,
                "observed_elapsed_ms": _iso_milliseconds(
                    use["record"].get("timestamp"),
                    result_record.get("timestamp") if result else None,
                ),
                "batch_response_id": use.get("response_id"),
            },
            "evidence": _evidence(source_lines),
            "source_lines": sorted(source_lines),
            "hidden_by_default": False,
        }
        events.append(event)
        tool_event_by_id[tool_use_id] = event_id
        uuid_to_event[str(use["record"].get("uuid") or "")] = response_event_by_key.get(
            use["response_key"], event_id
        )
        if result and result_record.get("uuid"):
            uuid_to_event[str(result_record["uuid"])] = event_id
        add_relation(response_event_by_key.get(use["response_key"], ""), event_id, "invokes")

    # Build a compact turn graph including asynchronous Subagent results.
    for turn in turns:
        turn_id = turn["turn_id"]
        stage_items = sorted(
            (
                event
                for event in events
                if event.get("turn_id") == turn_id
                and event.get("event_type")
                in {"model_response", "assistant_message", "subagent_result"}
            ),
            key=lambda item: (min(item.get("source_lines") or [0]), item["event_id"]),
        )
        cursor = [prompt_event_by_turn[turn_id]]
        for stage in stage_items:
            for source in cursor:
                add_relation(source, stage["event_id"], "next")
            if stage.get("event_type") == "subagent_result":
                cursor = [stage["event_id"]]
                continue
            tools = [
                tool_event_by_id[tool_id]
                for tool_id in stage.get("payload", {}).get("tool_use_ids", [])
                if tool_id in tool_event_by_id
            ]
            cursor = tools or [stage["event_id"]]

    # Preserve raw parent relationships separately from the compact execution graph.
    known_uuids = {str(record.get("uuid")) for _, record in parsed if record.get("uuid")}
    broken_parent_uuids: Set[str] = set()
    for _, record in parsed:
        child_uuid = record.get("uuid")
        parent_uuid = record.get("parentUuid")
        if parent_uuid and str(parent_uuid) not in known_uuids:
            broken_parent_uuids.add(str(parent_uuid))
        child_event = uuid_to_event.get(str(child_uuid or ""))
        parent_event = uuid_to_event.get(str(parent_uuid or ""))
        if parent_event and child_event:
            add_relation(parent_event, child_event, "parent")

    # Retain selected system evidence without mixing it into the task graph.
    system_event_count = 0
    for line_number, record in parsed:
        record_type = str(record.get("type") or "")
        if record_type == "system":
            is_local = record.get("subtype") == "local_command"
            if is_local:
                local_command_count += 1
            else:
                system_event_count += 1
            event_id = stable_id("event", session_id, "system", line_number)
            event = {
                "event_id": event_id,
                "sequence": 0,
                "event_type": "local_command" if is_local else "system_event",
                "timestamp": record.get("timestamp"),
                "ended_at": None,
                "turn_id": line_to_turn.get(line_number),
                "parent_uuid": record.get("parentUuid"),
                "message_uuid": record.get("uuid"),
                "response_id": None,
                "tool_use_id": record.get("toolUseID"),
                "status": "observed",
                "origin": "observed",
                "title": (
                    "本地命令" if is_local else "系统事件 · {0}".format(record.get("subtype") or "system")
                ),
                "summary": _text_preview(record.get("content") or record.get("stopReason")),
                "payload": record,
                "evidence": _evidence([line_number]),
                "source_lines": [line_number],
                "hidden_by_default": True,
            }
            events.append(event)

    event_priority = {
        "user_prompt": 0,
        "model_response": 1,
        "tool_execution": 2,
        "assistant_message": 3,
        "subagent_result": 1,
        "system_event": 8,
        "local_command": 9,
    }
    events.sort(
        key=lambda item: (
            min(item.get("source_lines") or [0]),
            event_priority.get(str(item.get("event_type")), 5),
            item["event_id"],
        )
    )
    for sequence, event in enumerate(events, start=1):
        event["sequence"] = sequence

    event_by_id = {event["event_id"]: event for event in events}
    for turn in turns:
        turn_events = [event for event in events if event.get("turn_id") == turn["turn_id"]]
        visible = [event for event in turn_events if not event.get("hidden_by_default")]
        turn["event_ids"] = [event["event_id"] for event in visible]
        turn["tool_call_count"] = sum(event["event_type"] == "tool_execution" for event in visible)
        turn["error_count"] = sum(event.get("status") == "error" for event in visible)
        turn["ended_at"] = next(
            (
                event.get("ended_at") or event.get("timestamp")
                for event in reversed(visible)
                if event.get("ended_at") or event.get("timestamp")
            ),
            turn.get("started_at"),
        )
        turn["status"] = (
            "complete"
            if any(
                event.get("event_type") == "assistant_message"
                and event.get("payload", {}).get("stop_reason") == "end_turn"
                for event in visible
            )
            else "incomplete"
        )

    cost_state = next(
        (record for _, record in reversed(parsed) if record.get("type") == "cost-state"),
        {},
    )
    modes = [record.get("mode") for _, record in parsed if record.get("type") == "mode"]
    permission_modes = [
        record.get("permissionMode")
        for _, record in parsed
        if record.get("type") == "permission-mode"
    ]
    assistant_models = Counter(
        str((record.get("message") or {}).get("model"))
        for _, record in parsed
        if record.get("type") == "assistant"
        and isinstance(record.get("message"), dict)
        and (record.get("message") or {}).get("model")
    )
    timestamps = [str(record.get("timestamp")) for _, record in parsed if record.get("timestamp")]
    record_types = Counter(str(record.get("type") or "unknown") for _, record in parsed)
    incomplete_tools = sorted(set(tool_uses) - set(tool_results))
    orphan_result_ids = set(tool_results) - set(tool_uses)
    tool_events = [event for event in events if event["event_type"] == "tool_execution"]
    visible_events = [event for event in events if not event.get("hidden_by_default")]
    trace = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "session": {
            "session_id": session_id,
            "source": "transcript_only",
            "started_at": manifest.get("started_at") or (min(timestamps) if timestamps else None),
            "ended_at": manifest.get("ended_at") or (max(timestamps) if timestamps else None),
            "cwd": manifest.get("cwd")
            or next((record.get("cwd") for _, record in parsed if record.get("cwd")), None),
            "claude_code_version": manifest.get("claude_code_version")
            or next((record.get("version") for _, record in parsed if record.get("version")), None),
            "mode": modes[-1] if modes else None,
            "permission_mode": permission_modes[-1] if permission_modes else None,
            "primary_model": assistant_models.most_common(1)[0][0] if assistant_models else None,
            "transcript_record_count": len(envelopes),
            "parsed_record_count": len(parsed),
        },
        "turns": turns,
        "events": events,
        "relations": sorted(
            relations,
            key=lambda item: (
                event_by_id.get(item["from"], {}).get("sequence", 0),
                event_by_id.get(item["to"], {}).get("sequence", 0),
                item["type"],
            ),
        ),
        "artifacts": [],
        "metrics": {
            "human_prompt_count": len(turns),
            "visible_event_count": len(visible_events),
            "model_response_count": sum(
                event["event_type"] in {"model_response", "assistant_message"}
                for event in visible_events
            ),
            "tool_call_count": len(tool_events),
            "tool_error_count": sum(event["status"] == "error" for event in tool_events),
            "incomplete_tool_count": len(incomplete_tools),
            "local_command_count": local_command_count,
            "system_event_count": system_event_count,
            "subagent_result_count": subagent_result_count,
            "total_cost_usd": cost_state.get("totalCostUSD"),
            "total_duration_ms": cost_state.get("totalDuration"),
            "total_api_duration_ms": cost_state.get("totalAPIDuration"),
            "total_tool_duration_ms": cost_state.get("totalToolDuration"),
            "total_lines_added": cost_state.get("totalLinesAdded"),
            "total_lines_removed": cost_state.get("totalLinesRemoved"),
            "model_usage": cost_state.get("modelUsage") or {},
        },
        "diagnostics": {
            "usable": bool(turns and tool_uses and response_groups),
            "invalid_transcript_lines": len(envelopes) - len(parsed),
            "filtered_non_human_user_records": filtered_non_human_users,
            "incomplete_tool_calls": incomplete_tools,
            "orphan_tool_results": sorted(orphan_result_ids),
            "duplicate_tool_use_ids": sorted(duplicate_tool_ids),
            "broken_parent_uuids": sorted(broken_parent_uuids),
            "record_type_counts": dict(sorted(record_types.items())),
            "notes": [
                "Execution structure is observed or deterministically derived; "
                "no semantic Plan was inferred.",
                "observed_elapsed_ms is transcript wall-clock separation, not exact tool runtime.",
            ],
        },
    }
    output = directory / "derived" / "observer_trace.json"
    _write_json_atomic(output, trace)
    update_manifest(
        session_id,
        {"files": {"observer_trace": "derived/observer_trace.json"}},
        root,
    )
    return trace


def load_observer_trace(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    path = session_directory(session_id, root) / "derived" / "observer_trace.json"
    if not path.is_file():
        raise FileNotFoundError(
            "observer_trace.json does not exist; run 'agentvast observe derive {0}'".format(
                session_id
            )
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != TRACE_SCHEMA_VERSION:
        raise ValueError("observer_trace.json has an unsupported schema")
    return value


def list_observer_sessions(root: Optional[str] = None) -> List[Dict[str, Any]]:
    """List already-derived sessions without creating or modifying any files."""
    observations_root = Path(root).expanduser().resolve() if root else default_observations_root()
    if not observations_root.is_dir():
        return []
    sessions: List[Dict[str, Any]] = []
    for directory in observations_root.iterdir():
        if not directory.is_dir():
            continue
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        trace_path = directory / "derived" / "observer_trace.json"
        semantic_path = directory / "derived" / "semantic_workflow.json"
        reviewed_semantic_path = directory / "derived" / "semantic_workflow_reviewed.json"
        validation_path = directory / "diagnostics" / "validation_report.json"
        trace: Dict[str, Any] = {}
        validation: Dict[str, Any] = {}
        semantic: Dict[str, Any] = {}
        try:
            if trace_path.is_file():
                trace = json.loads(trace_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            trace = {}
        try:
            if validation_path.is_file():
                validation = json.loads(validation_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            validation = {}
        try:
            if semantic_path.is_file():
                semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
            if reviewed_semantic_path.is_file() and semantic:
                reviewed_semantic = json.loads(reviewed_semantic_path.read_text(encoding="utf-8"))
                if (reviewed_semantic.get("inference_run") or {}).get("inference_id") == (
                    semantic.get("inference_run") or {}
                ).get("inference_id"):
                    semantic = reviewed_semantic
        except (OSError, ValueError, TypeError):
            semantic = {}
        sessions.append(
            {
                "session_id": manifest.get("session_id") or directory.name,
                "started_at": manifest.get("started_at"),
                "ended_at": manifest.get("ended_at"),
                "cwd": manifest.get("cwd"),
                "claude_code_version": manifest.get("claude_code_version"),
                "sources": manifest.get("sources") or {},
                "derived": bool(trace),
                "capture_mode": validation.get("capture_mode"),
                "valid": validation.get("valid"),
                "usable": validation.get("usable"),
                "metrics": trace.get("metrics") or {},
                "semantic_available": bool(semantic),
                "semantic_method": (
                    (semantic.get("inference_run") or {}).get("method") if semantic else None
                ),
                "semantic_node_count": len(semantic.get("semantic_nodes") or []),
                "semantic_valid": (
                    (semantic.get("validation") or {}).get("valid") if semantic else None
                ),
            }
        )
    return sorted(sessions, key=lambda item: str(item.get("started_at") or ""), reverse=True)
