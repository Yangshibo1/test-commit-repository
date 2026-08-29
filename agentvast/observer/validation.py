"""Completeness diagnostics for passive observation sessions."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Set

from agentvast.observer.store import ensure_session_layout, iter_jsonl, read_manifest
from agentvast.observer.trace_builder import is_human_prompt, transcript_record


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


def _incomplete_message_displays(
    hooks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in hooks:
        payload = _payload(item)
        if payload.get("hook_event_name") != "MessageDisplay":
            continue
        key = "|".join(
            str(payload.get(name) or "")
            for name in ("session_id", "turn_id", "message_id")
        )
        groups[key].append(item)

    incomplete: List[Dict[str, Any]] = []
    for events in groups.values():
        payload = _payload(events[-1])
        indexes = sorted(int(_payload(item).get("index") or 0) for item in events)
        unique_indexes = sorted(set(indexes))
        expected = list(range(unique_indexes[-1] + 1)) if unique_indexes else []
        final_indexes = sorted(
            int(_payload(item).get("index") or 0)
            for item in events
            if bool(_payload(item).get("final"))
        )
        complete = bool(
            unique_indexes
            and unique_indexes == expected
            and len(indexes) == len(unique_indexes)
            and final_indexes
            and final_indexes[-1] == unique_indexes[-1]
        )
        if complete:
            continue
        incomplete.append(
            {
                "message_id": payload.get("message_id"),
                "turn_id": payload.get("turn_id"),
                "prompt_id": payload.get("prompt_id"),
                "observed_indexes": unique_indexes,
                "missing_indexes": sorted(set(expected) - set(unique_indexes)),
                "duplicate_indexes": sorted(
                    index for index in unique_indexes if indexes.count(index) > 1
                ),
                "final_seen": bool(final_indexes),
            }
        )
    return incomplete


def validate_session(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    directory = ensure_session_layout(session_id, root)
    manifest = read_manifest(session_id, root)
    hooks = list(iter_jsonl(directory / "raw" / "hooks.jsonl"))
    otel = list(iter_jsonl(directory / "raw" / "otel.jsonl"))
    transcript = list(iter_jsonl(directory / "raw" / "transcript.jsonl"))
    canonical = list(iter_jsonl(directory / "derived" / "canonical_events.jsonl"))
    derived_tool_calls = list(iter_jsonl(directory / "derived" / "tool_calls.jsonl"))
    derived_messages = list(iter_jsonl(directory / "derived" / "messages.jsonl"))
    observer_trace_path = directory / "derived" / "observer_trace.json"
    try:
        observer_trace = json.loads(observer_trace_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        observer_trace = {}

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
    hook_unmatched_ids = {item["tool_use_id"] for item in unmatched_tools}
    transcript_recovered_hook_tools = sorted(hook_unmatched_ids & transcript_tool_ids)
    unresolved_hook_tools = [
        item
        for item in unmatched_tools
        if item["tool_use_id"] not in transcript_tool_ids
    ]

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
    transcript_record_types = Counter(
        str((item.get("record") or {}).get("type") or "unknown")
        for item in transcript
        if item.get("parsed") and isinstance(item.get("record"), dict)
    )
    transcript_fallback_usable = bool(
        transcript_record_types.get("user")
        and transcript_record_types.get("assistant")
    )
    transcript_prompt_count = sum(
        1
        for item in transcript
        if transcript_record(item) is not None
        and is_human_prompt(transcript_record(item) or {})
    )
    transcript_reconstructed_tools = sum(
        1
        for item in derived_tool_calls
        if item.get("event_name") == "TranscriptToolExecution"
    )
    incomplete_message_displays = _incomplete_message_displays(hooks)
    hook_complete = not missing_events and not incomplete_message_displays
    hybrid_fallback = bool(hooks) and not hook_complete and transcript_fallback_usable
    warnings: List[str] = []
    if unresolved_hook_tools:
        warnings.append(
            "{0} tool calls could not be matched by Hook or transcript".format(
                len(unresolved_hook_tools)
            )
        )
    if transcript_recovered_hook_tools:
        warnings.append(
            "{0} missing Hook terminal events were recovered from transcript".format(
                len(transcript_recovered_hook_tools)
            )
        )
    if undecoded_otel:
        warnings.append("{0} OTLP exports were preserved but not decoded".format(undecoded_otel))
    if invalid_transcript:
        warnings.append("{0} transcript lines could not be parsed".format(invalid_transcript))
    if incomplete_message_displays:
        warnings.append(
            "{0} incomplete MessageDisplay streams were replaced by complete "
            "assistant messages from the native transcript".format(
                len(incomplete_message_displays)
            )
        )
    if otel and not canonical:
        warnings.append("derive has not produced canonical events")
    if unmatched_prompts:
        warnings.append("{0} prompts have no OTel/transcript match".format(len(unmatched_prompts)))
    if hybrid_fallback:
        warnings.append(
            "Hook capture is partial; missing events were supplemented from the "
            "native transcript"
        )
    elif not hook_complete and transcript_fallback_usable:
        warnings.append(
            "Hook capture is unavailable; canonical trajectory was reconstructed "
            "from the native transcript"
        )
    report = {
        "session_id": session_id,
        "valid": hook_complete,
        "usable": hook_complete or transcript_fallback_usable,
        "degraded": not hook_complete and transcript_fallback_usable,
        "capture_mode": (
            "hook_primary"
            if hook_complete
            else "hybrid_fallback"
            if hybrid_fallback
            else "transcript_fallback"
            if transcript_fallback_usable
            else "incomplete"
        ),
        "sources": manifest.get("sources", {}),
        "counts": {
            "hook_events": len(hooks),
            "otel_exports": len(otel),
            "transcript_records": len(transcript),
            "canonical_events": len(canonical),
            "tool_calls": len(derived_tool_calls),
            "hook_tool_calls": len(by_tool),
            "transcript_reconstructed_tool_calls": transcript_reconstructed_tools,
            "matched_tool_calls": matched_tools,
            "unmatched_tool_calls": len(unresolved_hook_tools),
            "hook_unmatched_tool_calls": len(unmatched_tools),
            "transcript_recovered_hook_tools": len(transcript_recovered_hook_tools),
            "prompts": max(event_counts.get("UserPromptSubmit", 0), transcript_prompt_count),
            "transcript_prompts": transcript_prompt_count,
            "derived_messages": len(derived_messages),
            "message_display_streams": len(
                {
                    "|".join(
                        str(_payload(item).get(name) or "")
                        for name in ("session_id", "turn_id", "message_id")
                    )
                    for item in hooks
                    if _payload(item).get("hook_event_name") == "MessageDisplay"
                }
            ),
            "incomplete_message_display_streams": len(
                incomplete_message_displays
            ),
            "prompts_with_stable_id": len(hook_prompt_ids),
            "matched_prompts": matched_prompts,
            "unmatched_prompts": len(unmatched_prompts),
            "otel_matched_tool_calls": otel_matched_tools,
            "transcript_matched_tool_calls": transcript_matched_tools,
            "observer_turns": len(observer_trace.get("turns") or []),
            "observer_events": len(observer_trace.get("events") or []),
            "filtered_non_human_user_records": (
                (observer_trace.get("diagnostics") or {}).get(
                    "filtered_non_human_user_records", 0
                )
            ),
        },
        "hook_event_counts": dict(sorted(event_counts.items())),
        "transcript_record_types": dict(sorted(transcript_record_types.items())),
        "missing_events": missing_events,
        "warnings": warnings,
        "unmatched_tools": unmatched_tools,
        "unresolved_tools": unresolved_hook_tools,
        "transcript_recovered_tools": transcript_recovered_hook_tools,
        "incomplete_message_displays": incomplete_message_displays,
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
