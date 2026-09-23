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


TRACE_SCHEMA_VERSION = "observer-trace/2.0"
SUPPORTED_TRACE_SCHEMA_VERSIONS = {"observer-trace/1.0", TRACE_SCHEMA_VERSION}
LOCAL_MARKERS = (
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-name>",
)
COMMAND_TOOL_NAMES = {
    "bash",
    "command",
    "exec",
    "execute",
    "powershell",
    "shell",
    "terminal",
}
CONTROL_EVENT_SUBTYPES = {
    "context_compacted": ("compact", "compaction"),
    "execution_cancelled": ("cancel", "cancelled", "canceled"),
    "execution_interrupted": ("interrupt", "interrupted"),
    "execution_resumed": ("resume", "resumed"),
    "model_changed": ("model_change", "model_switch"),
    "permission_denied": ("permission_denied", "permission denied"),
    "rate_limited": ("rate_limit", "rate limit"),
    "session_terminated": ("session_terminated", "session terminated"),
    "tool_timeout": ("timeout", "timed_out", "timed out"),
}
ARTIFACT_SUFFIXES = {
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".parquet",
    ".xlsx",
    ".xls",
    ".md",
    ".txt",
    ".docx",
    ".pdf",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".py",
    ".ipynb",
}


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


def _is_command_tool(name: Any) -> bool:
    return str(name or "").strip().lower() in COMMAND_TOOL_NAMES


def _tool_event_subtype(name: Any) -> str:
    lowered = str(name or "").strip().lower()
    if lowered in {"read"}:
        return "file_read"
    if lowered in {"write"}:
        return "file_write"
    if lowered in {"edit", "multiedit", "notebookedit"}:
        return "file_modify"
    if lowered in {"glob", "grep", "search"}:
        return "path_search"
    if lowered == "taskcreate":
        return "task_create"
    if lowered == "taskupdate":
        return "task_update"
    if lowered in {"taskget", "tasklist"}:
        return "task_query"
    if lowered in {"agent", "task"}:
        return "agent_delegation"
    if lowered == "enterplanmode":
        return "plan_enter"
    if lowered == "exitplanmode":
        return "plan_exit"
    return "tool_call"


def _response_kind(visible_text: str, tool_ids: Iterable[str]) -> str:
    has_text = bool(str(visible_text or "").strip())
    has_tools = bool(list(tool_ids))
    if has_text and has_tools:
        return "mixed"
    if has_tools:
        return "tool_request"
    return "text"


def _control_event_subtype(record: Mapping[str, Any]) -> Optional[str]:
    searchable = " ".join(
        str(record.get(key) or "")
        for key in ("subtype", "event", "reason", "stopReason", "error")
    ).lower()
    for subtype, markers in CONTROL_EVENT_SUBTYPES.items():
        if any(marker in searchable for marker in markers):
            return subtype
    return None


def _event_actor(actor_type: str, actor_id: Optional[str] = None) -> Dict[str, Any]:
    return {"type": actor_type, "id": actor_id} if actor_id else {"type": actor_type}


def _event_scope(
    session_id: str,
    *,
    turn_id: Optional[str] = None,
    response_id: Optional[str] = None,
    tool_use_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "response_id": response_id,
        "tool_use_id": tool_use_id,
        "agent_run_id": None,
        "task_id": task_id,
    }


def _event_time(started_at: Any, ended_at: Any = None, duration_ms: Any = None) -> Dict[str, Any]:
    return {
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
    }


def _event_provenance(
    source_lines: Iterable[int],
    source_uuids: Iterable[Any] = (),
) -> Dict[str, Any]:
    lines = sorted(set(int(line) for line in source_lines))
    uuids = [str(value) for value in source_uuids if value]
    return {
        "source": "transcript",
        "source_lines": lines,
        "source_uuids": list(dict.fromkeys(uuids)),
    }


def _evidence(lines: Iterable[int]) -> List[Dict[str, Any]]:
    return [{"source": "transcript", "line_number": int(line)} for line in sorted(set(lines))]


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp-" + stable_id("write", os.getpid(), path))
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(str(temporary), str(path))


def _artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls"}:
        return "dataset"
    if suffix in {".md", ".txt", ".docx", ".pdf"}:
        return "report"
    if suffix in {".html", ".htm", ".png", ".jpg", ".jpeg", ".gif", ".svg"}:
        return "visualization"
    if suffix in {".py", ".ipynb"}:
        return "code"
    return "file"


def _resolved_artifact_path(raw_path: Any, cwd: Optional[str]) -> Optional[Path]:
    value = str(raw_path or "").strip().strip('"\'')
    if not value or not cwd:
        return None
    try:
        project_root = Path(cwd).resolve()
        candidate = Path(os.path.expandvars(value)).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        candidate = candidate.resolve()
        candidate.relative_to(project_root)
        return candidate
    except (OSError, RuntimeError, ValueError):
        return None


def _display_artifact_path(path: Path, cwd: Optional[str]) -> str:
    if cwd:
        try:
            return path.relative_to(Path(cwd).resolve()).as_posix()
        except (OSError, ValueError):
            pass
    return str(path)


def _reported_path_candidates(value: Any) -> List[str]:
    if value is None:
        return []
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    candidates: List[str] = []
    creation_markers = re.compile(
        r"\b(saved?|wrote|written|created?|generated?|exported?|converted|output)\b|"
        r"保存|写入|创建|生成|导出|输出",
        flags=re.IGNORECASE,
    )
    for line in text.splitlines() or [text]:
        if not creation_markers.search(line):
            continue
        candidates.extend(match[1] for match in re.findall(r"([\"'])(.+?)\1", line))
        for token in re.split(r"\s+", line):
            cleaned = token.strip("\"'`()[]{}<>,;:")
            if cleaned:
                candidates.append(cleaned)
    return [
        candidate
        for candidate in candidates
        if Path(candidate).suffix.lower() in ARTIFACT_SUFFIXES
    ]


def _shell_redirect_candidates(command: str) -> List[str]:
    result: List[str] = []
    pattern = re.compile(r"(?:^|\s)(?:>|>>)\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s;&|]+))")
    for match in pattern.finditer(command):
        value = next((item for item in match.groups() if item), "")
        if Path(value).suffix.lower() in ARTIFACT_SUFFIXES:
            result.append(value)
    return result


def derive_trace_artifacts(
    session_id: str,
    cwd: Optional[str],
    events: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Derive file artifacts already evidenced by transcript tool events."""
    artifacts: Dict[str, Dict[str, Any]] = {}
    for event in events:
        if (
            event.get("event_type") not in {"tool_execution", "command_execution"}
            or event.get("status") != "success"
        ):
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        tool_name = str(payload.get("name") or event.get("title") or "")
        lowered = tool_name.lower()
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        candidates: List[Tuple[str, str, str]] = []
        if lowered == "write":
            candidates.append(
                (
                    str(tool_input.get("file_path") or tool_input.get("path") or ""),
                    "created",
                    "tool_input",
                )
            )
        elif lowered in {"edit", "multiedit", "notebookedit"}:
            candidates.append(
                (
                    str(
                        tool_input.get("file_path")
                        or tool_input.get("notebook_path")
                        or tool_input.get("path")
                        or ""
                    ),
                    "modified",
                    "tool_input",
                )
            )
        elif lowered in {"bash", "shell", "powershell"}:
            command = str(tool_input.get("command") or "")
            candidates.extend(
                (path, "created", "shell_redirect")
                for path in _shell_redirect_candidates(command)
            )
            candidates.extend(
                (path, "created", "tool_output")
                for path in _reported_path_candidates(payload.get("output"))
            )

        for raw_path, operation, source in candidates:
            resolved = _resolved_artifact_path(raw_path, cwd)
            if resolved is None or not resolved.is_file():
                continue
            normalized = os.path.normcase(str(resolved))
            artifact = artifacts.setdefault(
                normalized,
                {
                    "artifact_id": stable_id("artifact", session_id, normalized),
                    "name": resolved.name,
                    "path": _display_artifact_path(resolved, cwd),
                    "artifact_type": _artifact_type(resolved),
                    "exists": True,
                    "evidence_event_ids": [],
                    "operations": [],
                },
            )
            event_id = str(event.get("event_id") or "")
            if event_id and event_id not in artifact["evidence_event_ids"]:
                artifact["evidence_event_ids"].append(event_id)
                artifact["operations"].append(
                    {
                        "event_id": event_id,
                        "operation": operation,
                        "source": source,
                    }
                )
    return list(artifacts.values())


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
    telemetry: List[Dict[str, Any]] = []
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
                "event_class": "interaction",
                "event_type": "user_prompt",
                "event_subtype": str(record.get("promptSource") or "human_message"),
                "timestamp": record.get("timestamp"),
                "ended_at": None,
                "turn_id": current_turn,
                "parent_uuid": record.get("parentUuid"),
                "message_uuid": record.get("uuid"),
                "response_id": None,
                "tool_use_id": None,
                "status": "observed",
                "origin": "observed",
                "actor": _event_actor("user"),
                "scope": _event_scope(session_id, turn_id=current_turn),
                "time": _event_time(record.get("timestamp")),
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
                "provenance": _event_provenance([line_number], [record.get("uuid")]),
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
                "event_class": "delegation",
                "event_type": "subagent_result",
                "event_subtype": "final_result",
                "timestamp": record.get("timestamp"),
                "ended_at": None,
                "turn_id": current_turn,
                "parent_uuid": record.get("parentUuid"),
                "message_uuid": record.get("uuid"),
                "response_id": None,
                "tool_use_id": _xml_value(content, "tool-use-id"),
                "status": _xml_value(content, "status") or "observed",
                "origin": "observed",
                "actor": _event_actor("subagent", task_id or None),
                "scope": _event_scope(
                    session_id,
                    turn_id=current_turn,
                    tool_use_id=_xml_value(content, "tool-use-id"),
                    task_id=task_id,
                ),
                "time": _event_time(record.get("timestamp")),
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
                "provenance": _event_provenance([line_number], [record.get("uuid")]),
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
        response_kind = _response_kind(visible_text, tools)
        is_final = stop_reason == "end_turn"
        event_id = stable_id("event", session_id, "response", turn_id, response_id)
        event = {
            "event_id": event_id,
            "sequence": 0,
            "event_class": "interaction",
            "event_type": "model_response",
            "event_subtype": response_kind,
            "timestamp": first["record"].get("timestamp"),
            "ended_at": ordered[-1]["record"].get("timestamp"),
            "turn_id": turn_id,
            "parent_uuid": first["record"].get("parentUuid"),
            "message_uuid": first["record"].get("uuid"),
            "response_id": response_id,
            "tool_use_id": None,
            "status": ("complete" if is_final or visible_text else "observed"),
            "origin": "derived" if len(ordered) > 1 else "observed",
            "actor": _event_actor("agent", "main_agent"),
            "scope": _event_scope(
                session_id,
                turn_id=turn_id,
                response_id=response_id,
            ),
            "time": _event_time(
                first["record"].get("timestamp"),
                ordered[-1]["record"].get("timestamp"),
            ),
            "title": (
                "工具批次 · {0} 个调用".format(len(tools))
                if tools
                else "Claude 最终回答"
                if is_final
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
                "response_kind": response_kind,
                "is_final": is_final,
                "text": visible_text,
                "usage": message.get("usage"),
                "tool_use_ids": tools,
                "record_uuids": record_uuids,
            },
            "evidence": _evidence(item["line_number"] for item in ordered),
            "source_lines": [item["line_number"] for item in ordered],
            "provenance": _event_provenance(
                (item["line_number"] for item in ordered),
                record_uuids,
            ),
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
        tool_name = str(block.get("name") or "Tool")
        is_command = _is_command_tool(tool_name)
        tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
        event_type = "command_execution" if is_command else "tool_execution"
        event_subtype = "shell_command" if is_command else _tool_event_subtype(tool_name)
        payload = {
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
        }
        if is_command:
            payload.update(
                {
                    "shell": tool_name.lower(),
                    "command": tool_input.get("command"),
                    "working_directory": (
                        tool_input.get("workdir")
                        or tool_input.get("cwd")
                        or manifest.get("cwd")
                    ),
                    "exit_code": (
                        structured_result.get("exitCode")
                        if isinstance(structured_result, dict)
                        else None
                    ),
                    "stdout": result_block.get("content") if result else None,
                    "stderr": (
                        result_block.get("content")
                        if result and bool(result_block.get("is_error"))
                        else None
                    ),
                    "timed_out": status == "incomplete",
                    "background": bool(tool_input.get("run_in_background")),
                }
            )
        event = {
            "event_id": event_id,
            "sequence": 0,
            "event_class": "execution",
            "event_type": event_type,
            "event_subtype": event_subtype,
            "timestamp": use["record"].get("timestamp"),
            "ended_at": result_record.get("timestamp") if result else None,
            "turn_id": use.get("turn_id"),
            "parent_uuid": use["record"].get("parentUuid"),
            "message_uuid": use["record"].get("uuid"),
            "response_id": use.get("response_id"),
            "tool_use_id": tool_use_id,
            "status": status,
            "origin": "derived",
            "actor": _event_actor("agent", "main_agent"),
            "scope": _event_scope(
                session_id,
                turn_id=use.get("turn_id"),
                response_id=use.get("response_id"),
                tool_use_id=tool_use_id,
            ),
            "time": _event_time(
                use["record"].get("timestamp"),
                result_record.get("timestamp") if result else None,
                duration_ms,
            ),
            "title": tool_name,
            "summary": _tool_summary(tool_name, block.get("input")),
            "payload": payload,
            "evidence": _evidence(source_lines),
            "source_lines": sorted(source_lines),
            "provenance": _event_provenance(
                source_lines,
                [use["record"].get("uuid"), result_record.get("uuid")],
            ),
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

    # Build a compact turn graph including asynchronous Subagent results. Keep
    # ``next`` for temporal audit compatibility, while also emitting the
    # deterministic causal edges used by the execution DAG.
    event_by_id = {str(event.get("event_id") or ""): event for event in events}
    for turn in turns:
        turn_id = turn["turn_id"]
        stage_items = sorted(
            (
                event
                for event in events
                if event.get("turn_id") == turn_id
                and event.get("event_type")
                in {"model_response", "subagent_result"}
            ),
            key=lambda item: (min(item.get("source_lines") or [0]), item["event_id"]),
        )
        cursor = [prompt_event_by_turn[turn_id]]
        for stage in stage_items:
            for source in cursor:
                add_relation(source, stage["event_id"], "next")
                source_event = event_by_id.get(source, {})
                source_type = str(source_event.get("event_type") or "")
                if source == prompt_event_by_turn[turn_id]:
                    add_relation(source, stage["event_id"], "prompts")
                elif source_type in {"tool_execution", "command_execution", "subagent_result"}:
                    add_relation(source, stage["event_id"], "result_feeds")
            if stage.get("event_type") == "subagent_result":
                cursor = [stage["event_id"]]
                continue
            tools = [
                tool_event_by_id[tool_id]
                for tool_id in stage.get("payload", {}).get("tool_use_ids", [])
                if tool_id in tool_event_by_id
            ]
            cursor = tools or [stage["event_id"]]

    # A task notification carries the originating Agent tool-use id when the
    # transcript provides one. This is stronger evidence than parentUuid and
    # avoids treating the raw message-storage chain as an execution dependency.
    for event in events:
        if event.get("event_type") != "subagent_result":
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        if tool_use_id and tool_use_id in tool_event_by_id:
            add_relation(tool_event_by_id[tool_use_id], event["event_id"], "spawns")

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

    # Promote only system records that alter control flow. Routine lifecycle
    # records remain compact telemetry and never become workflow nodes.
    system_event_count = 0
    for line_number, record in parsed:
        record_type = str(record.get("type") or "")
        if record_type == "system":
            is_local = record.get("subtype") == "local_command"
            if is_local:
                local_command_count += 1
                continue
            system_event_count += 1
            control_subtype = _control_event_subtype(record)
            if control_subtype:
                event_id = stable_id("event", session_id, "control", line_number)
                events.append(
                    {
                        "event_id": event_id,
                        "sequence": 0,
                        "event_class": "control",
                        "event_type": "control_event",
                        "event_subtype": control_subtype,
                        "timestamp": record.get("timestamp"),
                        "ended_at": None,
                        "turn_id": line_to_turn.get(line_number),
                        "parent_uuid": record.get("parentUuid"),
                        "message_uuid": record.get("uuid"),
                        "response_id": None,
                        "tool_use_id": record.get("toolUseID"),
                        "status": (
                            "error"
                            if control_subtype
                            in {
                                "execution_cancelled",
                                "execution_interrupted",
                                "permission_denied",
                                "rate_limited",
                                "session_terminated",
                                "tool_timeout",
                            }
                            else "observed"
                        ),
                        "origin": "observed",
                        "actor": _event_actor("system"),
                        "scope": _event_scope(
                            session_id,
                            turn_id=line_to_turn.get(line_number),
                            tool_use_id=record.get("toolUseID"),
                        ),
                        "time": _event_time(record.get("timestamp")),
                        "title": "控制事件 · {0}".format(control_subtype),
                        "summary": _text_preview(
                            record.get("content") or record.get("stopReason")
                        ),
                        "payload": {
                            "control_kind": control_subtype,
                            "reason": record.get("stopReason") or record.get("reason"),
                            "system_subtype": record.get("subtype"),
                        },
                        "evidence": _evidence([line_number]),
                        "source_lines": [line_number],
                        "provenance": _event_provenance(
                            [line_number], [record.get("uuid")]
                        ),
                        "hidden_by_default": False,
                    }
                )
                if record.get("uuid"):
                    uuid_to_event[str(record["uuid"])] = event_id
            else:
                telemetry.append(
                    {
                        "telemetry_id": stable_id(
                            "telemetry", session_id, line_number
                        ),
                        "timestamp": record.get("timestamp"),
                        "turn_id": line_to_turn.get(line_number),
                        "subtype": record.get("subtype") or "system",
                        "duration_ms": record.get("durationMs"),
                        "hook_count": record.get("hookCount"),
                        "stop_reason": record.get("stopReason"),
                        "source_lines": [line_number],
                    }
                )

    event_priority = {
        "user_prompt": 0,
        "model_response": 1,
        "tool_execution": 2,
        "command_execution": 2,
        "subagent_result": 1,
        "control_event": 3,
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
        turn["tool_call_count"] = sum(
            event["event_type"] in {"tool_execution", "command_execution"}
            for event in visible
        )
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
                event.get("event_type") == "model_response"
                and bool(event.get("payload", {}).get("is_final"))
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
    tool_events = [
        event
        for event in events
        if event["event_type"] in {"tool_execution", "command_execution"}
    ]
    command_events = [
        event for event in events if event["event_type"] == "command_execution"
    ]
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
        "artifacts": derive_trace_artifacts(
            session_id,
            manifest.get("cwd")
            or next((record.get("cwd") for _, record in parsed if record.get("cwd")), None),
            events,
        ),
        "telemetry": telemetry,
        "metrics": {
            "human_prompt_count": len(turns),
            "visible_event_count": len(visible_events),
            "model_response_count": sum(
                event["event_type"] == "model_response" for event in visible_events
            ),
            "tool_call_count": len(tool_events),
            "command_execution_count": len(command_events),
            "tool_error_count": sum(event["status"] == "error" for event in tool_events),
            "incomplete_tool_count": len(incomplete_tools),
            "local_command_count": local_command_count,
            "system_event_count": system_event_count,
            "telemetry_record_count": len(telemetry),
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
    events_output = directory / "derived" / "events.jsonl"
    events_output.write_text(
        "".join(
            json.dumps(event, ensure_ascii=False, default=str) + "\n"
            for event in events
        ),
        encoding="utf-8",
    )
    update_manifest(
        session_id,
        {
            "files": {
                "observer_trace": "derived/observer_trace.json",
                "workflow_events": "derived/events.jsonl",
            }
        },
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
    if (
        not isinstance(value, dict)
        or value.get("schema_version") not in SUPPORTED_TRACE_SCHEMA_VERSIONS
    ):
        raise ValueError("observer_trace.json has an unsupported schema")
    value["artifacts"] = derive_trace_artifacts(
        session_id,
        (value.get("session") or {}).get("cwd"),
        value.get("events") or [],
    )
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
