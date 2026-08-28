"""Completeness diagnostics for passive observation sessions."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Set

from agentvast.observer.store import ensure_session_layout, iter_jsonl, read_manifest


def _payload(event: Dict[str, Any]) -> Dict[str, Any]:
    value = event.get("raw_payload")
    return value if isinstance(value, dict) else {}


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _ids_from_value(value: Any, keys: Set[str]) -> Set[str]:
    result: Set[str] = set()
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        attributes = item.get("attributes")
        if isinstance(attributes, list):
            for attribute in attributes:
                if not isinstance(attribute, dict) or attribute.get("key") not in keys:
                    continue
                raw_value = attribute.get("value")
                if isinstance(raw_value, dict) and raw_value:
                    result.add(str(next(iter(raw_value.values()))))
        for key, child in item.items():
            if key in keys and isinstance(child, (str, int)):
                result.add(str(child))
    return result


def validate_session(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    directory = ensure_session_layout(session_id, root)
    manifest = read_manifest(session_id, root)
    hooks = list(iter_jsonl(directory / "raw" / "hooks.jsonl"))
    otel = list(iter_jsonl(directory / "raw" / "otel.jsonl"))
    transcript = list(iter_jsonl(directory / "raw" / "transcript.jsonl"))
    canonical = list(iter_jsonl(directory / "derived" / "canonical_events.jsonl"))

    event_counts = Counter(str(_payload(item).get("hook_event_name") or "unknown") for item in hooks)
    by_tool: DefaultDict[str, Set[str]] = defaultdict(set)
    for item in hooks:
        payload = _payload(item)
        tool_id = payload.get("tool_use_id")
        if tool_id:
            by_tool[str(tool_id)].add(str(payload.get("hook_event_name")))
    unmatched_tools: List[Dict[str, Any]] = []
    matched_tools = 0
    for tool_id, events in sorted(by_tool.items()):
        has_pre = "PreToolUse" in events
        has_terminal = bool(events & {"PostToolUse", "PostToolUseFailure"})
        if has_pre and has_terminal:
            matched_tools += 1
        else:
            unmatched_tools.append(
                {
                    "tool_use_id": tool_id,
                    "events": sorted(events),
                    "missing": (
                        "terminal_event" if has_pre else "pre_tool_use"
                    ),
                }
            )

    otel_tool_ids: Set[str] = set()
    otel_prompt_ids: Set[str] = set()
    for item in otel:
        raw = _payload(item)
        decoded = raw.get("decoded") if isinstance(raw, dict) else None
        otel_tool_ids.update(_ids_from_value(decoded, {"tool_use_id", "tool.use_id"}))
        otel_prompt_ids.update(_ids_from_value(decoded, {"prompt_id", "prompt.id"}))
    transcript_tool_ids: Set[str] = set()
    transcript_prompt_ids: Set[str] = set()
    for envelope in transcript:
        record = envelope.get("record") if envelope.get("parsed") else None
        transcript_tool_ids.update(_ids_from_value(record, {"tool_use_id"}))
        transcript_prompt_ids.update(_ids_from_value(record, {"prompt_id", "prompt.id"}))

    hook_prompt_ids = {
        str(_payload(item).get("prompt_id"))
        for item in hooks
        if _payload(item).get("hook_event_name") == "UserPromptSubmit"
        and _payload(item).get("prompt_id")
    }
    unmatched_prompts = sorted(
        prompt_id
        for prompt_id in hook_prompt_ids
        if prompt_id not in otel_prompt_ids and prompt_id not in transcript_prompt_ids
    )
    matched_prompts = len(hook_prompt_ids) - len(unmatched_prompts)
    otel_matched_tools = len(set(by_tool) & otel_tool_ids)
    transcript_matched_tools = len(set(by_tool) & transcript_tool_ids)

    missing_events: List[str] = []
    if not event_counts.get("SessionStart"):
        missing_events.append("SessionStart")
    if not event_counts.get("UserPromptSubmit"):
        missing_events.append("UserPromptSubmit")
    if not (event_counts.get("Stop") or event_counts.get("SessionEnd")):
        missing_events.append("Stop_or_SessionEnd")
    if not manifest.get("sources", {}).get("transcript"):
        missing_events.append("TranscriptSnapshot")

    undecoded_otel = sum(
        bool((_payload(item) or {}).get("decode_error")) for item in otel
    )
    invalid_transcript = sum(not bool(item.get("parsed")) for item in transcript)
    warnings: List[str] = []
    if unmatched_tools:
        warnings.append("{0} tool calls could not be fully matched".format(len(unmatched_tools)))
    if undecoded_otel:
        warnings.append("{0} OTLP exports were preserved but not decoded".format(undecoded_otel))
    if invalid_transcript:
        warnings.append("{0} transcript lines could not be parsed".format(invalid_transcript))
    if otel and not canonical:
        warnings.append("derive has not produced canonical events")
    if unmatched_prompts:
        warnings.append("{0} prompts have no OTel/transcript match".format(len(unmatched_prompts)))

    report = {
        "session_id": session_id,
        "valid": not missing_events,
        "sources": manifest.get("sources", {}),
        "counts": {
            "hook_events": len(hooks),
            "otel_exports": len(otel),
            "transcript_records": len(transcript),
            "canonical_events": len(canonical),
            "tool_calls": len(by_tool),
            "matched_tool_calls": matched_tools,
            "unmatched_tool_calls": len(unmatched_tools),
            "prompts": event_counts.get("UserPromptSubmit", 0),
            "prompts_with_stable_id": len(hook_prompt_ids),
            "matched_prompts": matched_prompts,
            "unmatched_prompts": len(unmatched_prompts),
            "otel_matched_tool_calls": otel_matched_tools,
            "transcript_matched_tool_calls": transcript_matched_tools,
        },
        "hook_event_counts": dict(sorted(event_counts.items())),
        "missing_events": missing_events,
        "warnings": warnings,
        "unmatched_tools": unmatched_tools,
        "unmatched_prompts": unmatched_prompts,
    }
    diagnostics = directory / "diagnostics"
    (diagnostics / "missing_events.json").write_text(
        json.dumps(missing_events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (diagnostics / "unmatched_events.json").write_text(
        json.dumps(
            {"tools": unmatched_tools, "prompts": unmatched_prompts},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (diagnostics / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report
