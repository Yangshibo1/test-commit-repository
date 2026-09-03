"""Semantic workflow reconstruction and deterministic evidence validation."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from agentvast.observer.store import session_directory, update_manifest
from agentvast.observer.trace_builder import load_observer_trace, stable_id
from agentvast.semantic import SEMANTIC_PROCESSOR_VERSION, SEMANTIC_SCHEMA_VERSION
from agentvast.semantic.prompts import (
    ACTIVITY_TYPES,
    ANNOTATION_SCHEMA,
    BOUNDARY_SCHEMA,
    RELATION_SCHEMA,
    annotation_prompt,
    relation_prompt,
    repair_prompt,
    segmentation_prompt,
)
from agentvast.semantic.provider import SemanticConfig, SemanticProvider, SemanticProviderError


ALLOWED_RELATIONS = {"VALIDATES", "REFINES", "USES_RESULT_FROM", "RETRY_OF"}


class SemanticWorkflowError(RuntimeError):
    """Raised when a semantic workflow cannot be safely generated or loaded."""


class SemanticWorkflowPartialError(SemanticWorkflowError):
    """Raised when an inference checkpoint was saved and can be resumed."""

    def __init__(self, message: str, state: Mapping[str, Any]):
        self.state = dict(state)
        self.inference_id = str(state.get("inference_id") or "")
        self.retryable = bool(state.get("retryable"))
        suffix = (
            " Inference checkpoint: {0}; resume with --resume {0}.".format(
                self.inference_id
            )
            if self.retryable and self.inference_id
            else ""
        )
        super().__init__(message + suffix)


ProgressCallback = Callable[[Dict[str, Any]], None]


def _emit_progress(
    callback: Optional[ProgressCallback],
    stage: str,
    percent: int,
    message: str,
    current: Optional[int] = None,
    total: Optional[int] = None,
) -> None:
    if callback is None:
        return
    callback(
        {
            "stage": stage,
            "percent": max(0, min(int(percent), 100)),
            "message": message,
            "current": current,
            "total": total,
            "updated_at": _utc_now(),
        }
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _value_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_inference_state(stage_root: Path, state: Dict[str, Any], **updates: Any) -> None:
    state.update(updates)
    state["updated_at"] = _utc_now()
    _write_json(stage_root / "inference_state.json", state)


def _load_resumable_stage(
    stages_root: Path,
    resume_inference: str,
    compatibility: Mapping[str, Any],
) -> Tuple[Path, Dict[str, Any]]:
    if resume_inference != "auto":
        if not re.fullmatch(r"semantic-[0-9a-f]{12}", resume_inference):
            raise SemanticWorkflowError(
                "Semantic inference ID must match semantic-<12 lowercase hex characters>"
            )
        candidates = [stages_root / resume_inference]
    else:
        candidates = sorted(
            (path for path in stages_root.glob("semantic-*") if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    for stage_root in candidates:
        state_path = stage_root / "inference_state.json"
        try:
            state = (
                _read_json(state_path)
                if state_path.is_file()
                else _migrate_legacy_inference_state(stage_root, compatibility)
            )
        except (OSError, ValueError, TypeError):
            continue
        if not isinstance(state, dict):
            continue
        if all(state.get(key) == value for key, value in compatibility.items()):
            if state.get("status") in {"partial", "failed", "running", "retrying"}:
                return stage_root, state
    requested = "latest compatible partial inference" if resume_inference == "auto" else resume_inference
    raise SemanticWorkflowError("No resumable semantic inference found: {0}".format(requested))


def _migrate_legacy_inference_state(
    stage_root: Path, compatibility: Mapping[str, Any]
) -> Optional[Dict[str, Any]]:
    """Create a checkpoint state for pre-resume semantic stage directories."""
    candidate_path = stage_root / "candidate_blocks.json"
    event_path = stage_root / "key_information_events.json"
    boundary_request_path = stage_root / "boundary_request.json"
    episodes_path = stage_root / "episodes.json"
    if not all(
        path.is_file()
        for path in (candidate_path, event_path, boundary_request_path, episodes_path)
    ):
        return None
    candidates = _read_json(candidate_path)
    event_record = _read_json(event_path)
    boundary_request = _read_json(boundary_request_path)
    episodes = _read_json(episodes_path)
    if not isinstance(candidates, list) or not isinstance(episodes, list):
        return None
    if _value_sha256(candidates) != compatibility.get("candidate_sha256"):
        return None
    if event_record.get("source_trace_sha256") != compatibility.get("source_trace_sha256"):
        return None
    if boundary_request.get("prompt_version") != compatibility.get("prompt_version"):
        return None
    completed: List[str] = []
    annotation_root = stage_root / "annotations"
    for index, episode in enumerate(episodes):
        validation_path = annotation_root / "annotation-{0:03d}-validation.json".format(index + 1)
        if not validation_path.is_file():
            break
        completed.append(str(episode.get("episode_id") or ""))
    state = {
        **compatibility,
        "inference_id": stage_root.name,
        "status": "partial",
        "stage": "semantic_annotation",
        "percent": 34 + int(46 * len(completed) / max(1, len(episodes))),
        "episode_count": len(episodes),
        "completed_episode_count": len(completed),
        "completed_episodes": completed,
        "failed_episode": len(completed) + 1 if len(completed) < len(episodes) else None,
        "retryable": True,
        "error": "Migrated from a semantic run created before checkpoint support",
        "created_at": datetime.fromtimestamp(
            stage_root.stat().st_mtime, timezone.utc
        ).isoformat(),
        "migrated_legacy_checkpoint": True,
    }
    for response_path in [
        *sorted(annotation_root.glob("annotation-*-raw-response.json"), reverse=True),
        stage_root / "boundary_raw_response.json",
    ]:
        if not response_path.is_file():
            continue
        response = _read_json(response_path)
        meta = response.get("_semantic_provider_meta") if isinstance(response, dict) else None
        mode = meta.get("response_mode") if isinstance(meta, dict) else None
        if mode in {"json_schema", "json_object", "text"}:
            state["response_mode"] = mode
            break
    _write_inference_state(stage_root, state)
    return state


def _preview(value: Any, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _ordered_unique(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: Set[str] = set()
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _event_payload_for_model(
    event: Mapping[str, Any],
    lineage_event_ids: Optional[Sequence[str]] = None,
    source_response_event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Project one observed Event into bounded, model-visible semantic evidence."""
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    result: Dict[str, Any] = {
        "event_id": event.get("event_id"),
        "sequence": event.get("sequence"),
        "turn_id": event.get("turn_id"),
        "event_type": event.get("event_type"),
        "title": _preview(event.get("title"), 240),
        "summary": _preview(event.get("summary"), 600),
        "status": event.get("status"),
        "origin": event.get("origin"),
        "source_lines": event.get("source_lines") or [],
        "lineage_event_ids": _ordered_unique(
            lineage_event_ids or [str(event.get("event_id") or "")]
        ),
    }
    if source_response_event_id:
        result["source_response_event_id"] = source_response_event_id
    if event.get("event_type") == "tool_execution":
        compact_input, input_meta = _bounded_value_with_meta(payload.get("input"), 1200)
        result["tool"] = {
            "name": payload.get("name"),
            "input": compact_input,
            "input_meta": input_meta,
            "output": _evidence_digest(payload.get("output"), 2400),
            "is_error": bool(payload.get("is_error")),
        }
    elif event.get("event_type") == "user_prompt":
        result["text"] = _evidence_digest(payload.get("content"), 4000)
    elif event.get("event_type") == "assistant_message":
        result["text"] = _evidence_digest(payload.get("text"), 4000)
    elif event.get("event_type") == "subagent_result":
        result["subagent"] = {
            "task_id": payload.get("task_id"),
            "task_summary": _preview(payload.get("task_summary"), 500),
            "status": payload.get("status"),
            "result": _evidence_digest(payload.get("result"), 6000),
        }
    return result


def build_key_information_events(trace: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Build the ordered, deterministic Event set exposed to semantic inference."""
    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    event_by_id = {
        str(event.get("event_id")): event
        for event in events
        if isinstance(event, dict) and event.get("event_id")
    }
    response_by_tool: Dict[str, str] = {}
    for relation in trace.get("relations") or []:
        if not isinstance(relation, dict) or relation.get("type") != "invokes":
            continue
        response_id = str(relation.get("from") or "")
        tool_id = str(relation.get("to") or "")
        if response_id in event_by_id and tool_id in event_by_id:
            response_by_tool[tool_id] = response_id

    key_events: List[Dict[str, Any]] = []
    allowed_types = {"user_prompt", "tool_execution", "subagent_result", "assistant_message"}
    for event in events:
        if (
            not isinstance(event, dict)
            or event.get("hidden_by_default")
            or event.get("event_type") not in allowed_types
            or not event.get("event_id")
        ):
            continue
        event_id = str(event["event_id"])
        response_id = response_by_tool.get(event_id)
        lineage = [response_id, event_id] if response_id else [event_id]
        key_events.append(
            _event_payload_for_model(
                event,
                lineage_event_ids=[item for item in lineage if item],
                source_response_event_id=response_id,
            )
        )
    return sorted(key_events, key=lambda item: int(item.get("sequence") or 0))


def _key_event_payloads(events: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Compatibility helper for callers that already selected observed Events."""
    return [
        _event_payload_for_model(event)
        for event in events
        if event.get("event_type") != "model_response" and not event.get("hidden_by_default")
    ]


def build_candidate_episodes(trace: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Compatibility entry point for deterministic Candidate Block construction."""
    return _build_candidate_blocks(trace, build_key_information_events(trace))


def _build_candidate_blocks(
    trace: Mapping[str, Any], key_events: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    relations = trace.get("relations") if isinstance(trace.get("relations"), list) else []
    event_by_id = {
        str(event.get("event_id")): event
        for event in events
        if isinstance(event, dict) and event.get("event_id")
    }
    key_event_by_id = {
        str(event.get("event_id")): dict(event)
        for event in key_events
        if isinstance(event, Mapping) and event.get("event_id")
    }
    invoked: Dict[str, List[str]] = {}
    for relation in relations:
        if not isinstance(relation, dict) or relation.get("type") != "invokes":
            continue
        invoked.setdefault(str(relation.get("from")), []).append(str(relation.get("to")))

    candidates: List[Dict[str, Any]] = []
    for turn in trace.get("turns") or []:
        if not isinstance(turn, dict):
            continue
        turn_id = str(turn.get("turn_id") or "")
        prompt_id = str(turn.get("prompt_event_id") or "")
        responses = sorted(
            (
                event
                for event in events
                if isinstance(event, dict)
                and event.get("turn_id") == turn_id
                and event.get("event_type") in {"model_response", "assistant_message"}
                and not event.get("hidden_by_default")
            ),
            key=lambda item: int(item.get("sequence") or 0),
        )
        terminal_response_id = next(
            (
                str(response.get("event_id"))
                for response in reversed(responses)
                if response.get("event_type") == "assistant_message"
            ),
            None,
        )
        atomic: List[Dict[str, Any]] = []
        for response in responses:
            response_id = str(response.get("event_id"))
            event_ids: List[str] = [response_id]
            event_ids.extend(
                sorted(
                    (tool_id for tool_id in invoked.get(response_id, []) if tool_id in event_by_id),
                    key=lambda event_id: int(event_by_id[event_id].get("sequence") or 0),
                )
            )
            candidate_id = stable_id(
                "candidate", trace.get("session", {}).get("session_id"), event_ids
            )
            candidate_events = [event_by_id[event_id] for event_id in event_ids]
            semantic_events = [
                key_event_by_id[event_id] for event_id in event_ids if event_id in key_event_by_id
            ]
            semantic_event_ids = [str(event["event_id"]) for event in semantic_events]
            tool_names = {
                str((event.get("payload") or {}).get("name") or event.get("title") or "")
                for event in candidate_events
                if event.get("event_type") == "tool_execution"
            }
            lifecycle_tools = {
                "Agent",
                "Skill",
                "TaskCreate",
                "TaskGet",
                "TaskList",
                "TaskUpdate",
            }
            if response_id == terminal_response_id:
                candidate_kind = "terminal_response"
            elif response.get("event_type") == "assistant_message":
                candidate_kind = "progress_response"
            elif tool_names and tool_names <= lifecycle_tools:
                candidate_kind = "lifecycle"
            else:
                candidate_kind = "execution"
            atomic.append(
                {
                    "candidate_episode_id": candidate_id,
                    "turn_id": turn_id,
                    "event_ids": event_ids,
                    "semantic_event_ids": semantic_event_ids,
                    "events": semantic_events,
                    "candidate_kind": candidate_kind,
                    "semantic_anchors": (
                        ["terminal_response"] if candidate_kind == "terminal_response" else []
                    ),
                    "boundary_basis": [
                        "model_response_boundary",
                        "response_transition",
                    ],
                }
            )

        for subagent in sorted(
            (
                event
                for event in events
                if isinstance(event, dict)
                and event.get("turn_id") == turn_id
                and event.get("event_type") == "subagent_result"
                and not event.get("hidden_by_default")
            ),
            key=lambda item: int(item.get("sequence") or 0),
        ):
            event_id = str(subagent.get("event_id"))
            task_id = str((subagent.get("payload") or {}).get("task_id") or event_id)
            atomic.append(
                {
                    "candidate_episode_id": stable_id(
                        "candidate",
                        trace.get("session", {}).get("session_id"),
                        event_id,
                    ),
                    "turn_id": turn_id,
                    "event_ids": [event_id],
                    "semantic_event_ids": [event_id],
                    "events": [key_event_by_id[event_id]],
                    "candidate_kind": "subagent_result",
                    "semantic_anchors": ["subagent_result:{0}".format(task_id)],
                    "boundary_basis": ["subagent_result_boundary"],
                }
            )

        atomic.sort(
            key=lambda candidate: min(
                int(event_by_id[event_id].get("sequence") or 0)
                for event_id in candidate["event_ids"]
            )
        )
        if atomic and prompt_id in key_event_by_id:
            atomic[0]["event_ids"] = [prompt_id] + atomic[0]["event_ids"]
            atomic[0]["semantic_event_ids"] = _ordered_unique(
                [prompt_id] + list(atomic[0].get("semantic_event_ids") or [])
            )
            atomic[0]["events"] = [key_event_by_id[prompt_id]] + atomic[0]["events"]
            atomic[0]["boundary_basis"] = [
                "human_prompt_boundary",
                *atomic[0]["boundary_basis"],
            ]
            atomic[0]["semantic_anchors"] = [
                "human_task",
                *atomic[0].get("semantic_anchors", []),
            ]
        candidates.extend(_collapse_lifecycle_candidates(atomic))

    # A failed tool followed by the same tool/target succeeding is one recovery Episode.
    merged: List[Dict[str, Any]] = []
    index = 0
    while index < len(candidates):
        current = candidates[index]
        if index + 1 < len(candidates) and _is_retry_pair(current, candidates[index + 1]):
            following = candidates[index + 1]
            event_ids = current["event_ids"] + [
                event_id
                for event_id in following["event_ids"]
                if event_id not in current["event_ids"]
            ]
            merged.append(
                {
                    "candidate_episode_id": stable_id(
                        "candidate",
                        current["candidate_episode_id"],
                        following["candidate_episode_id"],
                    ),
                    "turn_id": current["turn_id"],
                    "event_ids": event_ids,
                    "semantic_event_ids": _ordered_unique(
                        list(current.get("semantic_event_ids") or [])
                        + list(following.get("semantic_event_ids") or [])
                    ),
                    "events": current["events"] + following["events"],
                    "candidate_kind": "execution",
                    "semantic_anchors": _ordered_unique(
                        list(current.get("semantic_anchors") or [])
                        + list(following.get("semantic_anchors") or [])
                    ),
                    "boundary_basis": ["error_retry_recovery"],
                    "merged_candidate_ids": [
                        current["candidate_episode_id"],
                        following["candidate_episode_id"],
                    ],
                }
            )
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def _collapse_lifecycle_candidates(
    candidates: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Collapse adjacent orchestration/progress records before semantic inference."""
    collapsed: List[Dict[str, Any]] = []
    buffer: List[Dict[str, Any]] = []

    def flush() -> None:
        if not buffer:
            return
        if len(buffer) == 1:
            collapsed.append(buffer[0])
        else:
            event_ids = _ordered_unique(
                event_id for candidate in buffer for event_id in candidate["event_ids"]
            )
            collapsed.append(
                {
                    "candidate_episode_id": stable_id(
                        "candidate",
                        [candidate["candidate_episode_id"] for candidate in buffer],
                    ),
                    "turn_id": buffer[0]["turn_id"],
                    "event_ids": event_ids,
                    "semantic_event_ids": _ordered_unique(
                        event_id
                        for candidate in buffer
                        for event_id in candidate.get("semantic_event_ids") or []
                    ),
                    "events": [event for candidate in buffer for event in candidate["events"]],
                    "candidate_kind": "lifecycle",
                    "semantic_anchors": _ordered_unique(
                        anchor
                        for candidate in buffer
                        for anchor in candidate.get("semantic_anchors") or []
                    ),
                    "boundary_basis": ["collapsed_orchestration_block"],
                    "merged_candidate_ids": [
                        candidate["candidate_episode_id"] for candidate in buffer
                    ],
                }
            )
        buffer.clear()

    for candidate in candidates:
        if candidate.get("candidate_kind") in {"lifecycle", "progress_response"}:
            buffer.append(candidate)
            continue
        flush()
        collapsed.append(candidate)
    flush()
    return collapsed


def _boundary_candidate_view(candidate: Mapping[str, Any]) -> Dict[str, Any]:
    """Build a compact evidence view specifically for adjacent boundary decisions."""
    raw_events = [event for event in candidate.get("events") or [] if isinstance(event, dict)]
    deduplicated: List[Tuple[int, Dict[str, Any]]] = []
    seen_event_signatures: Set[Tuple[str, str, str]] = set()
    tool_counts: Dict[str, int] = {}
    for index, event in enumerate(raw_events):
        tool = event.get("tool") if isinstance(event.get("tool"), dict) else {}
        tool_name = str(tool.get("name") or "")
        if tool_name:
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
        signature = (
            str(event.get("event_type") or ""),
            tool_name,
            _preview(event.get("summary"), 120),
        )
        if signature in seen_event_signatures:
            continue
        seen_event_signatures.add(signature)
        deduplicated.append((index, event))
    prioritized = sorted(
        deduplicated,
        key=lambda item: (
            0
            if item[1].get("event_type") in {"user_prompt", "subagent_result", "assistant_message"}
            else 1
            if item[1].get("status") == "error"
            else 2,
            item[0],
        ),
    )[:8]
    selected_events = [event for _, event in sorted(prioritized, key=lambda item: item[0])]
    event_summaries: List[Dict[str, Any]] = []
    for event in selected_events:
        item: Dict[str, Any] = {
            "event_id": event.get("event_id"),
            "event_type": event.get("event_type"),
            "title": _preview(event.get("title"), 120),
            "summary": _preview(event.get("summary"), 220),
            "status": event.get("status"),
        }
        tool = event.get("tool") if isinstance(event.get("tool"), dict) else {}
        if tool:
            tool_input = tool.get("input") if isinstance(tool.get("input"), dict) else {}
            item["tool"] = {
                "name": tool.get("name"),
                "intent_fields": {
                    key: _bounded_value(tool_input.get(key), 180)
                    for key in (
                        "description",
                        "taskId",
                        "status",
                        "file_path",
                        "path",
                        "pattern",
                        "command",
                    )
                    if tool_input.get(key) is not None
                },
                "is_error": tool.get("is_error"),
            }
        subagent = event.get("subagent") if isinstance(event.get("subagent"), dict) else {}
        if subagent:
            result_digest = (
                subagent.get("result") if isinstance(subagent.get("result"), dict) else {}
            )
            item["subagent"] = {
                "task_id": subagent.get("task_id"),
                "task_summary": subagent.get("task_summary"),
                "status": subagent.get("status"),
                "result_signals": {
                    "headings": list(result_digest.get("headings") or [])[:8],
                    "key_lines": list(result_digest.get("key_lines") or [])[:8],
                    "original_length": result_digest.get("original_length"),
                    "truncated": result_digest.get("truncated"),
                },
            }
        event_summaries.append(item)
    return {
        "candidate_episode_id": candidate.get("candidate_episode_id"),
        "turn_id": candidate.get("turn_id"),
        "candidate_kind": candidate.get("candidate_kind"),
        "semantic_anchors": candidate.get("semantic_anchors") or [],
        "boundary_basis": candidate.get("boundary_basis") or [],
        "semantic_event_ids": candidate.get("semantic_event_ids") or [],
        "event_count": len(raw_events),
        "omitted_event_count": max(0, len(raw_events) - len(selected_events)),
        "tool_counts": tool_counts,
        "key_events": event_summaries,
    }


def _tool_events(candidate: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        event
        for event in candidate.get("events") or []
        if isinstance(event, dict) and event.get("event_type") == "tool_execution"
    ]


def _tool_signature(event: Mapping[str, Any]) -> Tuple[str, str]:
    tool = event.get("tool") if isinstance(event.get("tool"), dict) else {}
    tool_input = tool.get("input") if isinstance(tool.get("input"), dict) else {}
    target = next(
        (
            str(tool_input.get(key))
            for key in ("file_path", "path", "pattern", "query", "command")
            if tool_input.get(key)
        ),
        "",
    )
    return str(tool.get("name") or ""), target.lower()


def _is_retry_pair(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    if first.get("turn_id") != second.get("turn_id"):
        return False
    failed = [event for event in _tool_events(first) if event.get("status") == "error"]
    succeeded = [event for event in _tool_events(second) if event.get("status") == "success"]
    for failed_event in failed:
        failed_name, failed_target = _tool_signature(failed_event)
        for success_event in succeeded:
            success_name, success_target = _tool_signature(success_event)
            if failed_name and failed_name == success_name:
                if not failed_target or not success_target:
                    return True
                if (
                    failed_target == success_target
                    or failed_target in success_target
                    or success_target in failed_target
                ):
                    return True
    return False


def _boundary_validation_errors(
    candidates: List[Dict[str, Any]], value: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    _reject_extra_keys(
        value,
        {"schema_version", "boundaries", "_semantic_provider_meta"},
        "$",
        errors,
    )
    if value.get("schema_version") != "semantic-boundaries/0.1":
        errors.append({"path": "schema_version", "error": "must equal semantic-boundaries/0.1"})
    raw_boundaries = value.get("boundaries")
    if not isinstance(raw_boundaries, list):
        return errors + [{"path": "boundaries", "error": "must be an array"}]
    expected_pairs = [
        (left["candidate_episode_id"], right["candidate_episode_id"])
        for left, right in zip(candidates, candidates[1:])
    ]
    seen: List[Tuple[str, str]] = []
    candidate_by_id = {
        str(candidate["candidate_episode_id"]): candidate for candidate in candidates
    }
    for index, boundary in enumerate(raw_boundaries):
        path = "boundaries[{0}]".format(index)
        if not isinstance(boundary, dict):
            errors.append({"path": path, "error": "must be an object"})
            continue
        _reject_extra_keys(
            boundary,
            {
                "left_candidate_id",
                "right_candidate_id",
                "decision",
                "same_intent",
                "reason",
                "evidence_event_ids",
                "confidence_level",
            },
            path,
            errors,
        )
        pair = (
            str(boundary.get("left_candidate_id") or ""),
            str(boundary.get("right_candidate_id") or ""),
        )
        seen.append(pair)
        if pair not in expected_pairs:
            errors.append({"path": path, "error": "candidate IDs are not an adjacent pair"})
        decision = boundary.get("decision")
        if decision not in {"MERGE", "SPLIT"}:
            errors.append({"path": path + ".decision", "error": "must be MERGE or SPLIT"})
        if not isinstance(boundary.get("same_intent"), bool):
            errors.append({"path": path + ".same_intent", "error": "must be boolean"})
        if decision == "MERGE" and boundary.get("same_intent") is not True:
            errors.append({"path": path, "error": "MERGE requires same_intent=true"})
        if decision == "SPLIT" and boundary.get("same_intent") is not False:
            errors.append({"path": path, "error": "SPLIT requires same_intent=false"})
        if not str(boundary.get("reason") or "").strip():
            errors.append({"path": path + ".reason", "error": "must be non-empty"})
        if boundary.get("confidence_level") not in {"high", "medium", "low"}:
            errors.append({"path": path + ".confidence_level", "error": "invalid confidence"})
        evidence = boundary.get("evidence_event_ids")
        allowed_evidence = {
            str(event_id)
            for candidate_id in pair
            for event_id in candidate_by_id.get(candidate_id, {}).get("semantic_event_ids", [])
        }
        if not isinstance(evidence, list) or not evidence:
            errors.append({"path": path + ".evidence_event_ids", "error": "must be non-empty"})
        elif any(str(event_id) not in allowed_evidence for event_id in evidence):
            errors.append(
                {
                    "path": path + ".evidence_event_ids",
                    "error": "must reference only the adjacent candidates",
                }
            )
    if seen != expected_pairs:
        errors.append(
            {
                "path": "boundaries",
                "error": "must contain every adjacent pair exactly once and in order",
            }
        )
    return errors


def _reject_extra_keys(
    value: Mapping[str, Any],
    allowed: Set[str],
    path: str,
    errors: List[Dict[str, Any]],
) -> None:
    extras = sorted(set(str(key) for key in value) - allowed)
    if extras:
        errors.append({"path": path, "error": "unexpected properties", "properties": extras})


def _subagent_anchor_count(candidate: Mapping[str, Any]) -> int:
    return sum(
        str(anchor).startswith("subagent_result:")
        for anchor in candidate.get("semantic_anchors") or []
    )


def _effective_boundaries(
    candidates: List[Dict[str, Any]],
    value: Optional[Mapping[str, Any]],
    fallback_reason: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[List[str]]]:
    raw_by_pair: Dict[Tuple[str, str], Mapping[str, Any]] = {}
    for item in (value or {}).get("boundaries") or []:
        if isinstance(item, dict):
            raw_by_pair[
                (
                    str(item.get("left_candidate_id") or ""),
                    str(item.get("right_candidate_id") or ""),
                )
            ] = item
    if not candidates:
        return [], []
    decisions: List[Dict[str, Any]] = []
    groups: List[List[str]] = [[str(candidates[0]["candidate_episode_id"])]]
    group_subagents = _subagent_anchor_count(candidates[0])
    for left, right in zip(candidates, candidates[1:]):
        pair = (
            str(left["candidate_episode_id"]),
            str(right["candidate_episode_id"]),
        )
        raw = raw_by_pair.get(pair, {})
        model_decision = str(raw.get("decision") or "SPLIT")
        override_reason: Optional[str] = None
        if left.get("turn_id") != right.get("turn_id"):
            override_reason = "different_turns_must_split"
        elif "terminal_response" in {
            left.get("candidate_kind"),
            right.get("candidate_kind"),
        }:
            override_reason = "terminal_response_must_be_independent"
        elif len(groups[-1]) >= 3:
            override_reason = "maximum_candidates_per_episode"
        elif group_subagents + _subagent_anchor_count(right) > 1:
            override_reason = "maximum_subagent_results_per_episode"
        effective = (
            "SPLIT" if override_reason or fallback_reason or model_decision != "MERGE" else "MERGE"
        )
        origin = (
            "hard_constraint" if override_reason else "fallback" if fallback_reason else "model"
        )
        decision = {
            "left_candidate_id": pair[0],
            "right_candidate_id": pair[1],
            "model_decision": model_decision if raw else None,
            "effective_decision": effective,
            "decision_origin": origin,
            "reason": str(raw.get("reason") or fallback_reason or override_reason or ""),
            "override_reason": override_reason,
            "evidence_event_ids": [str(item) for item in raw.get("evidence_event_ids") or []],
            "model_confidence": raw.get("confidence_level"),
        }
        decisions.append(decision)
        if effective == "MERGE":
            groups[-1].append(pair[1])
            group_subagents += _subagent_anchor_count(right)
        else:
            groups.append([pair[1]])
            group_subagents = _subagent_anchor_count(right)
    return decisions, groups


def _materialize_episodes(
    session_id: str,
    candidates: List[Dict[str, Any]],
    groups: Sequence[Sequence[str]],
    decisions: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    by_id = {str(item["candidate_episode_id"]): item for item in candidates}
    episodes: List[Dict[str, Any]] = []
    for sequence, group in enumerate(groups, start=1):
        selected = [by_id[str(candidate_id)] for candidate_id in group]
        event_ids: List[str] = []
        for candidate in selected:
            event_ids.extend(
                event_id for event_id in candidate["event_ids"] if event_id not in event_ids
            )
        semantic_event_ids = _ordered_unique(
            event_id
            for candidate in selected
            for event_id in candidate.get("semantic_event_ids") or []
        )
        episodes.append(
            {
                "episode_id": stable_id("episode", session_id, list(group)),
                "sequence": sequence,
                "turn_id": selected[0].get("turn_id"),
                "candidate_episode_ids": list(group),
                "candidate_kinds": [candidate.get("candidate_kind") for candidate in selected],
                "semantic_anchors": _ordered_unique(
                    anchor
                    for candidate in selected
                    for anchor in candidate.get("semantic_anchors") or []
                ),
                "event_ids": event_ids,
                "semantic_event_ids": semantic_event_ids,
                "start_event_id": event_ids[0] if event_ids else None,
                "end_event_id": event_ids[-1] if event_ids else None,
                "boundary_basis": sorted(
                    {
                        reason
                        for candidate in selected
                        for reason in candidate.get("boundary_basis") or []
                    }
                ),
                "segmentation": {
                    "internal_boundaries": [
                        decision
                        for decision in decisions or []
                        if decision.get("left_candidate_id") in set(group)
                        and decision.get("right_candidate_id") in set(group)
                    ],
                    "origin": "model_constrained" if decisions else "derived",
                },
                "origin": "derived",
            }
        )
    return episodes


def _field(value: str, evidence: Iterable[str], origin: str = "inferred") -> Dict[str, Any]:
    return {
        "value": str(value or "").strip(),
        "origin": origin,
        "evidence_event_ids": sorted(set(str(item) for item in evidence if item)),
    }


def _event_map(trace: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(event.get("event_id")): event
        for event in trace.get("events") or []
        if isinstance(event, dict) and event.get("event_id")
    }


def _stable_text(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value or "")


def _bounded_value_with_meta(
    value: Any, string_limit: int = 2400, item_limit: int = 40
) -> Tuple[Any, Dict[str, Any]]:
    source_text = _stable_text(value)
    omitted_items = 0
    truncated = False

    def compact(child: Any) -> Any:
        nonlocal omitted_items, truncated
        if isinstance(child, str):
            if len(child) <= string_limit:
                return child
            truncated = True
            return child[: string_limit - 1] + "…"
        if isinstance(child, dict):
            items = list(child.items())
            if len(items) > item_limit:
                truncated = True
                omitted_items += len(items) - item_limit
            return {str(key): compact(value) for key, value in items[:item_limit]}
        if isinstance(child, list):
            if len(child) > item_limit:
                truncated = True
                omitted_items += len(child) - item_limit
            return [compact(value) for value in child[:item_limit]]
        return child

    bounded = compact(value)
    retained_text = _stable_text(bounded)
    return bounded, {
        "original_length": len(source_text),
        "retained_length": len(retained_text),
        "truncated": truncated,
        "omitted_item_count": omitted_items,
        "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }


def _bounded_value(value: Any, string_limit: int = 2400) -> Any:
    return _bounded_value_with_meta(value, string_limit)[0]


def _evidence_digest(value: Any, limit: int = 6000) -> Dict[str, Any]:
    text = _stable_text(value)
    if len(text) <= limit:
        return {
            "text": text,
            "original_length": len(text),
            "retained_length": len(text),
            "truncated": False,
            "omitted_item_count": 0,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headings = _ordered_unique(
        line[:300]
        for line in lines
        if line.startswith("#") or re.match(r"^[一二三四五六七八九十0-9]+[、.)）]", line)
    )[:30]
    key_lines = _ordered_unique(
        line[:500]
        for line in lines
        if re.search(r"\d", line)
        or any(
            keyword in line.lower()
            for keyword in (
                "结论",
                "结果",
                "风险",
                "限制",
                "warning",
                "error",
                "total",
                "count",
            )
        )
    )[:40]
    retained_length = sum(
        len(str(value)) for value in [text[:1800], *headings, *key_lines, text[-1800:]]
    )
    return {
        "opening_excerpt": text[:1800],
        "headings": headings,
        "key_lines": key_lines,
        "conclusion_excerpt": text[-1800:],
        "original_length": len(text),
        "retained_length": retained_length,
        "truncated": True,
        "omitted_item_count": max(0, len(lines) - len(headings) - len(key_lines)),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def _key_event_map(key_events: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        str(event.get("event_id")): dict(event)
        for event in key_events
        if isinstance(event, Mapping) and event.get("event_id")
    }


def _episode_observed_topic(
    episode: Mapping[str, Any], event_map: Mapping[str, Mapping[str, Any]]
) -> str:
    for event_id in episode.get("semantic_event_ids") or episode.get("event_ids") or []:
        event = event_map.get(str(event_id)) or {}
        if event.get("event_type") == "subagent_result":
            subagent = event.get("subagent") if isinstance(event.get("subagent"), dict) else {}
            if subagent.get("task_summary"):
                return str(subagent["task_summary"])
        if event.get("event_type") == "tool_execution" and event.get("summary"):
            return str(event["summary"])
        if event.get("event_type") in {"user_prompt", "assistant_message"}:
            return _preview(event.get("summary"), 240)
    return "未提取到明确主题"


def _episode_evidence_packet(
    trace: Mapping[str, Any],
    episodes: List[Dict[str, Any]],
    index: int,
    key_events: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    episode = episodes[index]
    event_map = _key_event_map(key_events or build_key_information_events(trace))
    turn = next(
        (
            item
            for item in trace.get("turns") or []
            if item.get("turn_id") == episode.get("turn_id")
        ),
        {},
    )
    task_context = {
        "original_user_prompt": _evidence_digest(turn.get("prompt"), 4000),
        "session_id": (trace.get("session") or {}).get("session_id"),
        "project_root": (trace.get("session") or {}).get("cwd"),
        "main_agent": "Claude Code",
        "turn_count": len(trace.get("turns") or []),
        "subagent_result_count": (trace.get("metrics") or {}).get("subagent_result_count", 0),
    }
    evidence: Dict[str, List[Dict[str, Any]]] = {
        "user_prompts": [],
        "tool_executions": [],
        "subagent_results": [],
        "assistant_messages": [],
    }
    allowed_event_ids = list(episode.get("semantic_event_ids") or episode.get("event_ids") or [])
    for event_id in allowed_event_ids:
        event = event_map.get(str(event_id)) or {}
        common = {
            "event_id": event_id,
            "status": event.get("status"),
            "source_lines": event.get("source_lines") or [],
            "summary": event.get("summary"),
        }
        if event.get("event_type") == "user_prompt":
            evidence["user_prompts"].append({**common, "text": event.get("text") or {}})
        elif event.get("event_type") == "tool_execution":
            tool = event.get("tool") if isinstance(event.get("tool"), dict) else {}
            evidence["tool_executions"].append(
                {
                    **common,
                    "tool_name": tool.get("name"),
                    "tool_input": tool.get("input"),
                    "tool_input_meta": tool.get("input_meta") or {},
                    "tool_output": tool.get("output") or {},
                    "is_error": bool(tool.get("is_error")),
                }
            )
        elif event.get("event_type") == "subagent_result":
            subagent = event.get("subagent") if isinstance(event.get("subagent"), dict) else {}
            evidence["subagent_results"].append(
                {
                    **common,
                    "task_id": subagent.get("task_id"),
                    "task_summary": subagent.get("task_summary"),
                    "result": subagent.get("result") or {},
                }
            )
        elif event.get("event_type") == "assistant_message":
            evidence["assistant_messages"].append({**common, "text": event.get("text") or {}})
    packet = {
        "evidence": evidence,
        "episode_id": episode.get("episode_id"),
        "position": {"index": index + 1, "total": len(episodes)},
        "candidate_episode_ids": episode.get("candidate_episode_ids") or [],
        "candidate_kinds": episode.get("candidate_kinds") or [],
        "semantic_anchors": episode.get("semantic_anchors") or [],
        "boundary_context": {
            "boundary_basis": episode.get("boundary_basis") or [],
            "segmentation": episode.get("segmentation") or {},
        },
        "allowed_event_ids": allowed_event_ids,
    }
    neighbor_context = {
        "previous_episode": (
            {
                "episode_id": episodes[index - 1]["episode_id"],
                "observed_topic": _episode_observed_topic(episodes[index - 1], event_map),
            }
            if index > 0
            else None
        ),
        "next_episode": (
            {
                "episode_id": episodes[index + 1]["episode_id"],
                "observed_topic": _episode_observed_topic(episodes[index + 1], event_map),
            }
            if index + 1 < len(episodes)
            else None
        ),
    }
    return task_context, packet, neighbor_context


def _rule_nodes(
    session_id: str, trace: Mapping[str, Any], episodes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    events = _event_map(trace)
    nodes: List[Dict[str, Any]] = []
    previous: Optional[Dict[str, Any]] = None
    for episode in episodes:
        event_ids = list(episode.get("event_ids") or [])
        semantic_event_ids = list(episode.get("semantic_event_ids") or event_ids)
        episode_events = [events[event_id] for event_id in semantic_event_ids if event_id in events]
        tools = [event for event in episode_events if event.get("event_type") == "tool_execution"]
        final_messages = [
            event for event in episode_events if event.get("event_type") == "assistant_message"
        ]
        activity, objective, summary, outcome, confidence = _rule_annotation(
            tools, final_messages, previous
        )
        node_id = stable_id("semantic", session_id, [episode["episode_id"]])
        node = {
            "node_id": node_id,
            "sequence": len(nodes) + 1,
            "episode_ids": [episode["episode_id"]],
            "event_ids": event_ids,
            "semantic_event_ids": semantic_event_ids,
            "title": _rule_title(activity, objective),
            "primary_activity": activity,
            "activity_tags": ["Error Recovery"]
            if any(event.get("status") == "error" for event in tools)
            else [],
            "objective": _field(objective, semantic_event_ids),
            "summary": _field(summary, semantic_event_ids),
            "outcome_claims": [
                {
                    "text": outcome,
                    "origin": "inferred",
                    "evidence_event_ids": semantic_event_ids,
                    "confidence_level": confidence,
                }
            ]
            if outcome
            else [],
            "confidence": {
                "level": confidence,
                "evidence_coverage": 1.0,
                "boundary_basis": episode.get("boundary_basis") or [],
                "uncertainty_reason": ("规则只能根据可观察工具与文本进行保守分类" if confidence != "high" else ""),
            },
            "abstained": activity == "Uncertain",
            "origin": "inferred",
            "inference_method": "rules",
            "review_status": "unreviewed",
        }
        _decorate_node(node, episode_events)
        nodes.append(node)
        previous = node
    return nodes


def _rule_annotation(
    tools: List[Dict[str, Any]],
    final_messages: List[Dict[str, Any]],
    previous: Optional[Mapping[str, Any]],
) -> Tuple[str, str, str, str, str]:
    if final_messages and not tools:
        return (
            "Communication",
            "整理并向用户呈现分析过程与结果",
            "将已获得的证据和结果组织为面向用户的回答。",
            "已形成最终可见回答。",
            "high",
        )
    names = [
        str((event.get("payload") or {}).get("name") or event.get("title") or "") for event in tools
    ]
    joined = " ".join(
        str(event.get("summary") or "")
        + " "
        + str(((event.get("payload") or {}).get("input") or {}).get("command") or "")
        for event in tools
    ).lower()
    target_text = " ".join(
        json.dumps((event.get("payload") or {}).get("input") or {}, ensure_ascii=False)
        for event in tools
    ).lower()
    if any(name in {"Glob", "Read", "Grep"} for name in names):
        task_material = any(
            word in target_text for word in ("question", "task", "readme", "description")
        )
        activity = "Task Understanding" if task_material else "Data Understanding"
        intent = "定位并读取任务描述与相关材料" if task_material else "检查并理解分析输入"
        outcome = (
            "相关材料已成功读取。" if any(event.get("status") == "success" for event in tools) else "材料读取未完成。"
        )
        return activity, intent, "通过文件检索和读取建立任务上下文。", outcome, "high"
    if any(name in {"Write", "Edit", "NotebookEdit"} for name in names):
        return "Data Preparation", "生成或修改分析材料", "通过结构化文件工具更新分析内容。", "工具报告文件操作已完成。", "medium"
    if any(name in {"Bash", "Python", "SQL"} for name in names):
        previous_activity = str((previous or {}).get("primary_activity") or "")
        similar = previous_activity in {"Analysis", "Validation"} and _analysis_similarity(
            joined, previous
        )
        counts = _extract_counts(tools)
        if similar or any(
            word in joined for word in ("verify", "validate", "recount", "question marks")
        ):
            outcome = _count_outcome(counts, validation=True)
            return "Validation", "复核前一步分析结果与统计口径", "使用新的计算方式检查已有结果。", outcome, "medium"
        outcome = _count_outcome(counts, validation=False)
        return "Analysis", _analysis_intent(joined), "执行计算或命令以获得任务所需结果。", outcome, "medium"
    return "Uncertain", "无法从现有证据可靠确定分析意图", "该阶段包含可观察行为，但语义目标证据不足。", "", "low"


def _rule_title(activity: str, objective: str) -> str:
    preferred = {
        "Task Understanding": "理解任务与材料",
        "Data Understanding": "理解分析数据",
        "Data Preparation": "准备分析材料",
        "Exploration": "探索数据特征",
        "Analysis": "执行数据分析",
        "Visualization": "生成可视化",
        "Validation": "核验分析结果",
        "Refinement": "修正分析结果",
        "Synthesis": "综合分析结论",
        "Communication": "交付分析结果",
        "Uncertain": "未确定行为阶段",
    }
    return preferred.get(activity) or _preview(objective, 36)


def _analysis_similarity(joined: str, previous: Optional[Mapping[str, Any]]) -> bool:
    previous_text = " ".join(
        str((previous or {}).get(field, {}).get("value") or "")
        for field in ("objective", "summary")
        if isinstance((previous or {}).get(field), dict)
    ).lower()
    current_tokens = set(re.findall(r"[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}", joined))
    previous_tokens = set(re.findall(r"[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}", previous_text))
    return bool(current_tokens & previous_tokens)


def _extract_counts(tools: List[Dict[str, Any]]) -> Dict[str, str]:
    text = "\n".join(str((event.get("payload") or {}).get("output") or "") for event in tools)
    return {
        key: value for key, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([0-9]+)", text)
    }


def _count_outcome(counts: Mapping[str, str], validation: bool) -> str:
    if not counts:
        return "已获得命令执行结果。"
    details = "、".join("{0}={1}".format(key, value) for key, value in counts.items())
    return ("复核结果：" if validation else "初步结果：") + details


def _analysis_intent(joined: str) -> str:
    if "count" in joined or "统计" in joined:
        return "统计任务和问题的数量"
    return "执行任务所需的数据分析与计算"


def _decorate_node(node: Dict[str, Any], episode_events: List[Dict[str, Any]]) -> None:
    actions: List[Dict[str, Any]] = []
    inputs: List[Dict[str, Any]] = []
    outputs: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    orchestration_tools = {"TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "Skill"}
    for event in episode_events:
        if event.get("event_type") != "tool_execution":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_id = str(event.get("event_id"))
        actions.append(
            {
                "event_id": event_id,
                "tool_name": payload.get("name") or event.get("title"),
                "summary": event.get("summary"),
                "status": event.get("status"),
                "semantic_relevance": (
                    "orchestration"
                    if str(payload.get("name") or event.get("title") or "")
                    in orchestration_tools
                    else "key_action"
                ),
            }
        )
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else {}
        for key in ("file_path", "path"):
            if tool_input.get(key):
                inputs.append(
                    {
                        "value": str(tool_input[key]),
                        "origin": "observed",
                        "evidence_event_ids": [event_id],
                    }
                )
        if payload.get("output") is not None:
            outputs.append(
                {
                    "summary": _preview(payload.get("output"), 500),
                    "origin": "observed",
                    "evidence_event_ids": [event_id],
                }
            )
        if event.get("status") == "error":
            errors.append(
                {
                    "event_id": event_id,
                    "summary": _preview(payload.get("output"), 500),
                    "recovered": False,
                }
            )
    if errors and any(action["status"] == "success" for action in actions):
        for error in errors:
            error["recovered"] = True
    node["actions"] = actions
    node["observed_inputs"] = _dedupe_objects(inputs)
    node["reported_outputs"] = _dedupe_objects(outputs)
    node["verified_artifacts"] = []
    node["errors"] = errors


def _dedupe_objects(values: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _model_nodes(
    session_id: str,
    trace: Mapping[str, Any],
    episodes: List[Dict[str, Any]],
    value: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    raw_nodes = value.get("nodes") or []
    episode_by_id = {str(item["episode_id"]): item for item in episodes}
    event_map = _event_map(trace)
    result: List[Dict[str, Any]] = []
    for raw, episode in zip(raw_nodes, episodes):
        episode_id = str(episode["episode_id"])
        episode_ids = [episode_id]
        event_ids = list(episode["event_ids"])
        activity = str(raw["primary_activity"])
        model_confidence = _confidence(raw.get("model_confidence"))
        node = {
            "node_id": stable_id("semantic", session_id, episode_ids),
            "sequence": len(result) + 1,
            "episode_ids": episode_ids,
            "event_ids": event_ids,
            "title": str(raw["title"]),
            "primary_activity": activity,
            "activity_tags": [str(item) for item in raw.get("activity_tags") or []][:8],
            "objective": _validated_model_field(raw.get("objective"), event_ids),
            "summary": _validated_model_field(raw.get("summary"), event_ids),
            "outcome_claims": _validated_claims(raw.get("outcome_claims"), event_ids),
            "confidence": {
                "level": model_confidence,
                "model_level": model_confidence,
                "validated_level": model_confidence,
                "evidence_coverage": 0.0,
                "boundary_basis": episode_by_id[episode_id].get("boundary_basis") or [],
                "uncertainty_reason": str(raw.get("uncertainty_reason") or ""),
            },
            "abstained": bool(raw.get("abstained")) or activity == "Uncertain",
            "origin": "inferred",
            "inference_method": "model",
            "review_status": "unreviewed",
        }
        _decorate_node(
            node, [event_map[event_id] for event_id in event_ids if event_id in event_map]
        )
        result.append(node)
    return result


def _annotation_validation_errors(
    episodes: List[Dict[str, Any]], value: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    _reject_extra_keys(
        value,
        {"schema_version", "nodes", "_semantic_provider_meta"},
        "$",
        errors,
    )
    if value.get("schema_version") != "semantic-annotation/0.2":
        errors.append({"path": "schema_version", "error": "must equal semantic-annotation/0.2"})
    raw_nodes = value.get("nodes")
    if not isinstance(raw_nodes, list):
        return errors + [{"path": "nodes", "error": "must be an array"}]
    if len(raw_nodes) != len(episodes):
        errors.append({"path": "nodes", "error": "must contain exactly one Node per Episode"})
    for index, episode in enumerate(episodes):
        path = "nodes[{0}]".format(index)
        if index >= len(raw_nodes) or not isinstance(raw_nodes[index], dict):
            errors.append({"path": path, "error": "missing or invalid Node"})
            continue
        raw = raw_nodes[index]
        _reject_extra_keys(
            raw,
            {
                "episode_ids",
                "title",
                "primary_activity",
                "activity_tags",
                "objective",
                "summary",
                "outcome_claims",
                "model_confidence",
                "uncertainty_reason",
                "abstained",
            },
            path,
            errors,
        )
        expected_episode = str(episode["episode_id"])
        if [str(item) for item in raw.get("episode_ids") or []] != [expected_episode]:
            errors.append(
                {
                    "path": path + ".episode_ids",
                    "error": "must contain only the corresponding Episode ID",
                }
            )
        activity = raw.get("primary_activity")
        if activity not in ACTIVITY_TYPES:
            errors.append({"path": path + ".primary_activity", "error": "unknown activity"})
        if not isinstance(raw.get("activity_tags"), list):
            errors.append({"path": path + ".activity_tags", "error": "must be an array"})
        title = str(raw.get("title") or "").strip()
        if len(title) < 2 or len(title) > 36:
            errors.append({"path": path + ".title", "error": "must be 2-36 characters"})
        allowed_events = set(
            str(item)
            for item in (episode.get("semantic_event_ids") or episode.get("event_ids") or [])
        )
        for field_name in ("objective", "summary"):
            field = raw.get(field_name)
            field_path = path + "." + field_name
            if not isinstance(field, dict) or not str(field.get("value") or "").strip():
                errors.append({"path": field_path, "error": "must contain a non-empty value"})
                continue
            _reject_extra_keys(
                field,
                {"value", "evidence_event_ids"},
                field_path,
                errors,
            )
            evidence = [str(item) for item in field.get("evidence_event_ids") or []]
            if not evidence or any(item not in allowed_events for item in evidence):
                errors.append(
                    {
                        "path": field_path + ".evidence_event_ids",
                        "error": "must be non-empty and contained in this Episode",
                    }
                )
        claims = raw.get("outcome_claims")
        if not isinstance(claims, list):
            errors.append({"path": path + ".outcome_claims", "error": "must be an array"})
        else:
            for claim_index, claim in enumerate(claims):
                claim_path = path + ".outcome_claims[{0}]".format(claim_index)
                if not isinstance(claim, dict) or not str(claim.get("text") or "").strip():
                    errors.append({"path": claim_path, "error": "must contain non-empty text"})
                    continue
                _reject_extra_keys(
                    claim,
                    {"text", "evidence_event_ids", "confidence_level"},
                    claim_path,
                    errors,
                )
                evidence = [str(item) for item in claim.get("evidence_event_ids") or []]
                if not evidence or any(item not in allowed_events for item in evidence):
                    errors.append(
                        {
                            "path": claim_path + ".evidence_event_ids",
                            "error": "must be contained in this Episode",
                        }
                    )
        if raw.get("model_confidence") not in {"high", "medium", "low"}:
            errors.append({"path": path + ".model_confidence", "error": "invalid confidence"})
        if not isinstance(raw.get("abstained"), bool):
            errors.append({"path": path + ".abstained", "error": "must be boolean"})
        if activity == "Uncertain" and (
            raw.get("abstained") is not True or not str(raw.get("uncertainty_reason") or "").strip()
        ):
            errors.append(
                {
                    "path": path,
                    "error": "Uncertain requires abstained=true and uncertainty_reason",
                }
            )
        if activity == "Uncertain" and raw.get("model_confidence") != "low":
            errors.append(
                {
                    "path": path + ".model_confidence",
                    "error": "Uncertain activity requires low confidence",
                }
            )
    return errors


def _abstained_nodes(
    session_id: str, trace: Mapping[str, Any], episodes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    event_map = _event_map(trace)
    nodes: List[Dict[str, Any]] = []
    for episode in episodes:
        event_ids = list(episode.get("event_ids") or [])
        semantic_event_ids = list(episode.get("semantic_event_ids") or event_ids)
        episode_events = [event_map[item] for item in event_ids if item in event_map]
        digest = "；".join(
            _preview(event.get("title") or event.get("summary"), 120) for event in episode_events
        )
        node = {
            "node_id": stable_id("semantic", session_id, [episode["episode_id"]]),
            "sequence": len(nodes) + 1,
            "episode_ids": [episode["episode_id"]],
            "event_ids": event_ids,
            "title": "等待人工解释",
            "primary_activity": "Uncertain",
            "activity_tags": [],
            "objective": _field("保留该行为阶段并等待人工校正", semantic_event_ids),
            "summary": _field(digest or "该阶段包含可观察行为。", semantic_event_ids),
            "outcome_claims": [],
            "confidence": {
                "level": "low",
                "model_level": "low",
                "validated_level": "low",
                "evidence_coverage": 1.0,
                "boundary_basis": episode.get("boundary_basis") or [],
                "uncertainty_reason": "模型语义输出在一次修复后仍未通过验证",
            },
            "abstained": True,
            "origin": "inferred",
            "inference_method": "model_abstained",
            "review_status": "unreviewed",
        }
        _decorate_node(node, episode_events)
        nodes.append(node)
    return nodes


def _validated_model_field(value: Any, allowed_events: Sequence[str]) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    evidence = [
        str(event_id)
        for event_id in data.get("evidence_event_ids") or []
        if str(event_id) in set(allowed_events)
    ]
    return _field(str(data.get("value") or ""), evidence, "inferred")


def _validated_claims(value: Any, allowed_events: Sequence[str]) -> List[Dict[str, Any]]:
    claims: List[Dict[str, Any]] = []
    allowed = set(allowed_events)
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        evidence = [
            str(event_id)
            for event_id in item.get("evidence_event_ids") or []
            if str(event_id) in allowed
        ]
        text = str(item.get("text") or "").strip()
        if text and evidence:
            claims.append(
                {
                    "text": text,
                    "origin": "inferred",
                    "evidence_event_ids": evidence,
                    "confidence_level": _confidence(item.get("confidence_level")),
                }
            )
    return claims


def _confidence(value: Any) -> str:
    text = str(value or "").lower()
    return text if text in {"high", "medium", "low"} else "low"


def _relation_validation_errors(
    nodes: List[Dict[str, Any]], value: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    _reject_extra_keys(
        value,
        {"schema_version", "relations", "_semantic_provider_meta"},
        "$",
        errors,
    )
    if value.get("schema_version") != "semantic-relations/0.1":
        errors.append({"path": "schema_version", "error": "must equal semantic-relations/0.1"})
    raw_relations = value.get("relations")
    if not isinstance(raw_relations, list):
        return errors + [{"path": "relations", "error": "must be an array"}]
    node_ids = {str(node["node_id"]) for node in nodes}
    evidence_ids = {str(event_id) for node in nodes for event_id in node.get("event_ids") or []}
    seen: Set[Tuple[str, str, str]] = set()
    for index, relation in enumerate(raw_relations):
        path = "relations[{0}]".format(index)
        if not isinstance(relation, dict):
            errors.append({"path": path, "error": "must be an object"})
            continue
        _reject_extra_keys(
            relation,
            {
                "from_node_id",
                "to_node_id",
                "type",
                "evidence_event_ids",
                "confidence_level",
            },
            path,
            errors,
        )
        source = str(relation.get("from_node_id") or "")
        target = str(relation.get("to_node_id") or "")
        relation_type = str(relation.get("type") or "")
        if source not in node_ids or target not in node_ids or source == target:
            errors.append({"path": path, "error": "invalid relation endpoints"})
        if relation_type not in ALLOWED_RELATIONS:
            errors.append({"path": path + ".type", "error": "invalid relation type"})
        key = (source, target, relation_type)
        if key in seen:
            errors.append({"path": path, "error": "duplicate relation"})
        seen.add(key)
        evidence = [str(item) for item in relation.get("evidence_event_ids") or []]
        if not evidence or any(item not in evidence_ids for item in evidence):
            errors.append({"path": path + ".evidence_event_ids", "error": "invalid evidence"})
        if relation.get("confidence_level") not in {"high", "medium", "low"}:
            errors.append({"path": path + ".confidence_level", "error": "invalid confidence"})
    return errors


def _relations(
    session_id: str,
    nodes: List[Dict[str, Any]],
    model_value: Optional[Mapping[str, Any]] = None,
) -> List[Dict[str, Any]]:
    relations: List[Dict[str, Any]] = []
    for left, right in zip(nodes, nodes[1:]):
        relations.append(
            {
                "relation_id": stable_id(
                    "semantic-rel", session_id, left["node_id"], right["node_id"], "NEXT"
                ),
                "from_node_id": left["node_id"],
                "to_node_id": right["node_id"],
                "type": "NEXT",
                "origin": "derived",
                "evidence_event_ids": [left["event_ids"][-1], right["event_ids"][0]],
                "confidence_level": "high",
            }
        )
    node_ids = {node["node_id"] for node in nodes}
    if model_value is not None and isinstance(model_value.get("relations"), list):
        for raw in model_value["relations"]:
            if not isinstance(raw, dict):
                continue
            source = str(raw.get("from_node_id") or "")
            target = str(raw.get("to_node_id") or "")
            relation_type = str(raw.get("type") or "")
            evidence = [str(item) for item in raw.get("evidence_event_ids") or []]
            if (
                source in node_ids
                and target in node_ids
                and source != target
                and relation_type in ALLOWED_RELATIONS
                and evidence
            ):
                relations.append(
                    {
                        "relation_id": stable_id(
                            "semantic-rel", session_id, source, target, relation_type
                        ),
                        "from_node_id": source,
                        "to_node_id": target,
                        "type": relation_type,
                        "origin": "inferred",
                        "evidence_event_ids": evidence,
                        "confidence_level": _confidence(raw.get("confidence_level")),
                    }
                )
    else:
        for index, node in enumerate(nodes):
            if node.get("primary_activity") == "Validation" and index > 0:
                target = nodes[index - 1]
                relations.append(
                    {
                        "relation_id": stable_id(
                            "semantic-rel",
                            session_id,
                            node["node_id"],
                            target["node_id"],
                            "VALIDATES",
                        ),
                        "from_node_id": node["node_id"],
                        "to_node_id": target["node_id"],
                        "type": "VALIDATES",
                        "origin": "inferred",
                        "evidence_event_ids": node["event_ids"],
                        "confidence_level": "medium",
                    }
                )
    return _dedupe_relations(relations)


def _dedupe_relations(relations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for relation in relations:
        key = str(relation.get("relation_id"))
        if key not in seen:
            seen.add(key)
            result.append(relation)
    return result


def validate_semantic_workflow(
    workflow: Mapping[str, Any], trace: Mapping[str, Any]
) -> Dict[str, Any]:
    event_map = _event_map(trace)
    event_ids = set(event_map)
    episodes = workflow.get("episodes") if isinstance(workflow.get("episodes"), list) else []
    nodes = (
        workflow.get("semantic_nodes") if isinstance(workflow.get("semantic_nodes"), list) else []
    )
    relations = workflow.get("relations") if isinstance(workflow.get("relations"), list) else []
    evidence_issues: List[Dict[str, Any]] = []
    granularity_issues: List[Dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        unknown_episode_events = [
            str(event_id)
            for event_id in episode.get("event_ids") or []
            if str(event_id) not in event_ids
        ]
        if unknown_episode_events:
            evidence_issues.append(
                {
                    "code": "unknown_episode_evidence",
                    "episode_id": episode.get("episode_id"),
                    "event_ids": unknown_episode_events,
                }
            )
        subagent_anchors = [
            anchor
            for anchor in episode.get("semantic_anchors") or []
            if str(anchor).startswith("subagent_result:")
        ]
        if len(subagent_anchors) > 1:
            granularity_issues.append(
                {
                    "code": "multiple_subagent_results_in_episode",
                    "episode_id": episode.get("episode_id"),
                    "anchors": subagent_anchors,
                }
            )
        if (
            "terminal_response" in (episode.get("candidate_kinds") or [])
            and len(episode.get("candidate_episode_ids") or []) != 1
        ):
            granularity_issues.append(
                {
                    "code": "terminal_response_not_independent",
                    "episode_id": episode.get("episode_id"),
                }
            )
    covered_episodes: List[str] = []
    node_ids: Set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            evidence_issues.append({"code": "invalid_node", "detail": "Node is not an object"})
            continue
        node_id = str(node.get("node_id") or "")
        node_ids.add(node_id)
        covered_episodes.extend(str(item) for item in node.get("episode_ids") or [])
        if len(node.get("episode_ids") or []) != 1 and node.get("origin") != "user_validated":
            granularity_issues.append({"code": "node_must_map_to_one_episode", "node_id": node_id})
        if node.get("primary_activity") not in ACTIVITY_TYPES:
            evidence_issues.append({"code": "unknown_activity", "node_id": node_id})
        if not str(node.get("title") or "").strip():
            evidence_issues.append({"code": "missing_title", "node_id": node_id})
        for field_name in ("objective", "summary"):
            field = node.get(field_name) if isinstance(node.get(field_name), dict) else {}
            evidence = [str(item) for item in field.get("evidence_event_ids") or []]
            if not str(field.get("value") or "").strip() or not evidence:
                evidence_issues.append(
                    {"code": "unsupported_field", "node_id": node_id, "field": field_name}
                )
            if any(item not in event_ids for item in evidence):
                evidence_issues.append(
                    {"code": "unknown_evidence", "node_id": node_id, "field": field_name}
                )
        for claim_index, claim in enumerate(node.get("outcome_claims") or []):
            if not isinstance(claim, dict):
                evidence_issues.append(
                    {"code": "invalid_claim", "node_id": node_id, "claim_index": claim_index}
                )
                continue
            claim_evidence = [str(item) for item in claim.get("evidence_event_ids") or []]
            if not str(claim.get("text") or "").strip() or not claim_evidence:
                evidence_issues.append(
                    {"code": "unsupported_claim", "node_id": node_id, "claim_index": claim_index}
                )
            if any(item not in event_ids for item in claim_evidence):
                evidence_issues.append(
                    {
                        "code": "unknown_claim_evidence",
                        "node_id": node_id,
                        "claim_index": claim_index,
                    }
                )
        evidence_union = {
            str(event_id)
            for field_name in ("objective", "summary")
            for event_id in (node.get(field_name) or {}).get("evidence_event_ids") or []
        }
        evidence_union.update(
            str(event_id)
            for claim in node.get("outcome_claims") or []
            if isinstance(claim, dict)
            for event_id in claim.get("evidence_event_ids") or []
        )
        node_events = set(str(item) for item in node.get("event_ids") or [])
        episode_id = next(iter(node.get("episode_ids") or []), None)
        episode = next((item for item in episodes if item.get("episode_id") == episode_id), {})
        terminal_episode = "terminal_response" in (episode.get("candidate_kinds") or [])
        administrative_tools = {"TaskUpdate", "TaskGet", "TaskList", "Skill"}
        relevant_events = {
            event_id
            for event_id in node_events
            if event_id in event_map
            and (
                event_map[event_id].get("event_type") in {"user_prompt", "subagent_result"}
                or (
                    event_map[event_id].get("event_type") == "assistant_message"
                    and terminal_episode
                )
                or (
                    event_map[event_id].get("event_type") == "tool_execution"
                    and str((event_map[event_id].get("payload") or {}).get("name"))
                    not in administrative_tools
                )
            )
        }
        if not relevant_events:
            relevant_events = {
                event_id
                for event_id in node_events
                if event_id in event_map
                and event_map[event_id].get("event_type") != "model_response"
            }
        coverage = len(evidence_union & relevant_events) / max(1, len(relevant_events))
        if isinstance(node.get("confidence"), dict):
            node["confidence"]["evidence_coverage"] = round(coverage, 4)
            model_level = _confidence(
                node["confidence"].get("model_level") or node["confidence"].get("level")
            )
            validated_level = (
                model_level
                if coverage >= 0.8
                else "medium"
                if coverage >= 0.5 and model_level in {"high", "medium"}
                else "low"
            )
            if node.get("primary_activity") == "Uncertain":
                validated_level = "low"
            node["confidence"]["model_level"] = model_level
            node["confidence"]["validated_level"] = validated_level
            node["confidence"]["level"] = validated_level
        node_event_types = [
            event_map[event_id].get("event_type")
            for event_id in node_events
            if event_id in event_map
        ]
        if node_event_types.count("subagent_result") > 1 and node.get("origin") != "user_validated":
            granularity_issues.append(
                {"code": "multiple_subagent_results_in_node", "node_id": node_id}
            )
        if "assistant_message" in node_event_types and "tool_execution" in node_event_types:
            episode_id = next(iter(node.get("episode_ids") or []), None)
            episode = next((item for item in episodes if item.get("episode_id") == episode_id), {})
            if "terminal_response" in (episode.get("candidate_kinds") or []):
                granularity_issues.append(
                    {"code": "terminal_communication_mixed_with_execution", "node_id": node_id}
                )
        if "terminal_response" in (episode.get("candidate_kinds") or []) and node.get(
            "primary_activity"
        ) not in {"Communication", "Synthesis"}:
            granularity_issues.append({"code": "terminal_activity_mismatch", "node_id": node_id})
    if covered_episodes != [str(item.get("episode_id")) for item in episodes]:
        evidence_issues.append(
            {"code": "episode_coverage", "detail": "Episodes are missing, duplicated, or reordered"}
        )
    candidate_count = int((workflow.get("inference_run") or {}).get("candidate_count") or 0)
    if candidate_count >= 3 and len(nodes) <= 1:
        granularity_issues.append(
            {
                "code": "whole_session_overmerged",
                "candidate_count": candidate_count,
                "node_count": len(nodes),
            }
        )
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        if (
            relation.get("from_node_id") not in node_ids
            or relation.get("to_node_id") not in node_ids
        ):
            evidence_issues.append(
                {"code": "invalid_relation_node", "relation_id": relation.get("relation_id")}
            )
        if relation.get("type") != "NEXT" and not relation.get("evidence_event_ids"):
            evidence_issues.append(
                {"code": "unsupported_relation", "relation_id": relation.get("relation_id")}
            )
        if any(
            str(event_id) not in event_ids for event_id in relation.get("evidence_event_ids") or []
        ):
            evidence_issues.append(
                {"code": "unknown_relation_evidence", "relation_id": relation.get("relation_id")}
            )
    issues = evidence_issues + granularity_issues
    return {
        "valid": not issues,
        "evidence_valid": not evidence_issues,
        "granularity_valid": not granularity_issues,
        "issue_count": len(issues),
        "issues": issues,
        "evidence_issues": evidence_issues,
        "granularity_issues": granularity_issues,
        "episode_count": len(episodes),
        "node_count": len(nodes),
        "relation_count": len(relations),
        "source_event_count": len(event_ids),
    }


def _provider_complete(
    provider: SemanticProvider,
    prompt: str,
    stage: str,
    schema: Dict[str, Any],
    retry_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    if isinstance(provider, SemanticProvider):
        return provider.complete(
            prompt,
            stage,
            json_schema=schema,
            retry_callback=retry_callback,
        )
    return provider.complete(prompt, stage, json_schema=schema)


def run_semantic_workflow(
    session_id: str,
    root: Optional[str] = None,
    rules_only: bool = False,
    force: bool = False,
    resume_inference: Optional[str] = None,
    provider: Optional[SemanticProvider] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    _emit_progress(progress_callback, "prepare", 2, "读取 Observer Trace")
    if force and resume_inference:
        raise SemanticWorkflowError("--force and --resume cannot be used together")
    directory = session_directory(session_id, root)
    trace_path = directory / "derived" / "observer_trace.json"
    if not trace_path.is_file():
        raise SemanticWorkflowError("observer_trace.json does not exist; run observe derive first")
    trace = load_observer_trace(session_id, root)
    trace_sha = _sha256(trace_path)
    config = SemanticConfig.from_env()
    method = "rules" if rules_only else "model"
    current_path = directory / "derived" / "semantic_workflow.json"
    if current_path.is_file() and not force and not resume_inference:
        try:
            current = json.loads(current_path.read_text(encoding="utf-8"))
            inference = current.get("inference_run") or {}
            if (
                (current.get("source_trace") or {}).get("sha256") == trace_sha
                and inference.get("method") == method
                and inference.get("processor_version") == SEMANTIC_PROCESSOR_VERSION
            ):
                _emit_progress(
                    progress_callback,
                    "complete",
                    100,
                    "使用现有 Semantic Workflow",
                )
                return current
        except (OSError, ValueError, TypeError):
            pass

    key_events = build_key_information_events(trace)
    _emit_progress(
        progress_callback,
        "key_information",
        6,
        "已从 {0} 个观察事件提取 {1} 个关键 Event".format(len(trace.get("events") or []), len(key_events)),
    )
    candidates = _build_candidate_blocks(trace, key_events)
    if not candidates:
        raise SemanticWorkflowError("observer trace contains no reconstructable Episodes")
    _emit_progress(
        progress_callback,
        "candidate_blocks",
        12,
        "已生成 {0} 个候选行为块".format(len(candidates)),
    )
    warnings: List[str] = []
    semantic_provider = provider
    if not rules_only and semantic_provider is None:
        if not config.configured():
            raise SemanticWorkflowError(
                "Semantic API is not configured; configure it or pass --rules-only"
            )
        semantic_provider = SemanticProvider(config)

    prompt_version = "semantic-prompts/0.4"
    stages_root = directory / "derived" / "semantic_stages"
    stages_root.mkdir(parents=True, exist_ok=True)
    compatibility = {
        "session_id": session_id,
        "source_trace_sha256": trace_sha,
        "method": method,
        "processor_version": SEMANTIC_PROCESSOR_VERSION,
        "prompt_version": prompt_version,
        "candidate_sha256": _value_sha256(candidates),
    }
    if resume_inference:
        stage_root, inference_state = _load_resumable_stage(
            stages_root, resume_inference, compatibility
        )
        inference_id = stage_root.name
        _write_inference_state(
            stage_root,
            inference_state,
            status="running",
            retryable=False,
            error=None,
        )
        _emit_progress(
            progress_callback,
            "resume",
            int(inference_state.get("percent") or 12),
            "恢复语义任务 {0}".format(inference_id),
            current=inference_state.get("completed_episode_count"),
            total=inference_state.get("episode_count"),
        )
    else:
        inference_id = "semantic-{0}".format(uuid.uuid4().hex[:12])
        stage_root = stages_root / inference_id
        stage_root.mkdir(parents=True, exist_ok=False)
        inference_state = {
            **compatibility,
            "inference_id": inference_id,
            "status": "running",
            "stage": "candidate_blocks",
            "percent": 12,
            "episode_count": None,
            "completed_episode_count": 0,
            "completed_episodes": [],
            "failed_episode": None,
            "retryable": False,
            "error": None,
            "created_at": _utc_now(),
        }
        _write_inference_state(stage_root, inference_state)
        _write_json(
            stage_root / "key_information_events.json",
            {
                "schema_version": "semantic-events/0.1",
                "source_trace_sha256": trace_sha,
                "compaction_version": "key-information-events/0.1",
                "source_event_count": len(trace.get("events") or []),
                "event_count": len(key_events),
                "events": key_events,
            },
        )
        _write_json(stage_root / "candidate_blocks.json", candidates)

    def retry_progress(event: Dict[str, Any]) -> None:
        delay = event.get("delay_seconds")
        attempt = event.get("attempt")
        max_attempts = event.get("max_attempts")
        message = "网络异常，{0} 秒后重试 {1}/{2}".format(delay, attempt, max_attempts)
        _write_inference_state(
            stage_root,
            inference_state,
            status="retrying",
            retryable=True,
            last_retry=event,
            response_mode=event.get("response_mode")
            or inference_state.get("response_mode"),
        )
        _emit_progress(
            progress_callback,
            "retrying",
            int(inference_state.get("percent") or 0),
            message,
            current=inference_state.get("current_episode"),
            total=inference_state.get("episode_count"),
        )

    if resume_inference and isinstance(semantic_provider, SemanticProvider):
        semantic_provider.restore_response_mode(inference_state.get("response_mode"))

    def remember_response_mode(value: Mapping[str, Any]) -> None:
        meta = value.get("_semantic_provider_meta")
        if not isinstance(meta, Mapping):
            return
        mode = meta.get("response_mode")
        if mode in {"json_schema", "json_object", "text"}:
            _write_inference_state(
                stage_root,
                inference_state,
                response_mode=mode,
            )

    _emit_progress(progress_callback, "boundaries", 16, "判断相邻候选块边界")
    boundary_candidates = [_boundary_candidate_view(candidate) for candidate in candidates]
    boundary_prompt = segmentation_prompt(boundary_candidates)
    _write_json(
        stage_root / "boundary_request.json",
        {
            "prompt_version": prompt_version,
            "candidate_count": len(candidates),
            "candidate_view": boundary_candidates,
            "prompt": boundary_prompt,
        },
    )
    boundary_output: Optional[Dict[str, Any]] = None
    boundary_errors: List[Dict[str, Any]] = []
    boundary_fallback: Optional[str] = None
    validated_boundaries_path = stage_root / "validated_boundaries.json"
    episodes_path = stage_root / "episodes.json"
    if resume_inference and validated_boundaries_path.is_file() and episodes_path.is_file():
        decisions = _read_json(validated_boundaries_path)
        episodes = _read_json(episodes_path)
        groups = []
        _emit_progress(
            progress_callback,
            "boundaries",
            30,
            "复用已冻结的 {0} 个 Episode".format(len(episodes)),
        )
    else:
        try:
            if semantic_provider is not None:
                boundary_output = _provider_complete(
                    semantic_provider,
                    boundary_prompt,
                    "episode_boundaries",
                    BOUNDARY_SCHEMA,
                    retry_progress,
                )
                remember_response_mode(boundary_output)
                _write_json(stage_root / "boundary_raw_response.json", boundary_output)
                boundary_errors = _boundary_validation_errors(candidates, boundary_output)
                if boundary_errors:
                    repaired = _provider_complete(
                        semantic_provider,
                        repair_prompt(
                            "BOUNDARY_CLASSIFICATION",
                            boundary_prompt,
                            boundary_output,
                            boundary_errors,
                            BOUNDARY_SCHEMA,
                        ),
                        "episode_boundaries_repair",
                        BOUNDARY_SCHEMA,
                        retry_progress,
                    )
                    remember_response_mode(repaired)
                    _write_json(stage_root / "boundary_repair_response.json", repaired)
                    repaired_errors = _boundary_validation_errors(candidates, repaired)
                    if repaired_errors:
                        boundary_errors.extend(repaired_errors)
                        boundary_fallback = "model_boundary_output_invalid_after_repair"
                        warnings.append(
                            "Model boundary output remained invalid; uncertain boundaries defaulted to SPLIT"
                        )
                    else:
                        boundary_output = repaired
                        boundary_errors = []
            else:
                boundary_fallback = "rules_only_candidate_boundaries"
        except SemanticProviderError as error:
            _write_inference_state(
                stage_root,
                inference_state,
                status="partial" if error.retryable else "failed",
                stage="boundaries",
                percent=16,
                retryable=error.retryable,
                error=str(error),
                error_type=error.error_type,
            )
            raise SemanticWorkflowPartialError(str(error), inference_state) from error
        decisions, groups = _effective_boundaries(
            candidates,
            boundary_output if not boundary_errors else None,
            fallback_reason=boundary_fallback,
        )
        episodes = _materialize_episodes(session_id, candidates, groups, decisions)
    _emit_progress(
        progress_callback,
        "boundaries",
        30,
        "边界冻结为 {0} 个 Episode".format(len(episodes)),
    )
    boundary_validation_path = stage_root / "boundary_validation.json"
    if not (resume_inference and boundary_validation_path.is_file()):
        _write_json(
            boundary_validation_path,
            {
                "valid": not boundary_errors,
                "errors": boundary_errors,
                "fallback": boundary_fallback,
            },
        )
    _write_json(stage_root / "validated_boundaries.json", decisions)
    _write_json(stage_root / "episodes.json", episodes)
    _write_inference_state(
        stage_root,
        inference_state,
        status="running",
        stage="semantic_annotation",
        percent=30,
        episode_count=len(episodes),
        retryable=False,
        error=None,
    )

    if semantic_provider is not None:
        annotation_root = stage_root / "annotations"
        annotation_root.mkdir(exist_ok=True)
        nodes = []
        annotation_results: List[Dict[str, Any]] = []
        all_annotation_errors: List[Dict[str, Any]] = []
        for index, episode in enumerate(episodes):
            annotation_percent = 34 + int(46 * index / max(1, len(episodes)))
            prefix = "annotation-{0:03d}".format(index + 1)
            validation_path = annotation_root / (prefix + "-validation.json")
            node_path = annotation_root / (prefix + "-node.json")
            if resume_inference and validation_path.is_file():
                try:
                    checkpoint_validation = _read_json(validation_path)
                    checkpoint_node = _read_json(node_path) if node_path.is_file() else None
                    if not isinstance(checkpoint_node, dict) and checkpoint_validation.get("valid"):
                        response_path = annotation_root / (prefix + "-repair-response.json")
                        if not response_path.is_file():
                            response_path = annotation_root / (prefix + "-raw-response.json")
                        checkpoint_output = _read_json(response_path)
                        if not _annotation_validation_errors([episode], checkpoint_output):
                            checkpoint_node = _model_nodes(
                                session_id, trace, [episode], checkpoint_output
                            )[0]
                    if isinstance(checkpoint_node, dict):
                        checkpoint_node["sequence"] = index + 1
                        nodes.append(checkpoint_node)
                        annotation_results.append(checkpoint_validation)
                        if not checkpoint_validation.get("valid"):
                            all_annotation_errors.extend(
                                {
                                    **error,
                                    "episode_id": episode["episode_id"],
                                }
                                for error in checkpoint_validation.get("errors") or []
                                if isinstance(error, dict)
                            )
                        completed = list(inference_state.get("completed_episodes") or [])
                        if episode["episode_id"] not in completed:
                            completed.append(episode["episode_id"])
                        _write_inference_state(
                            stage_root,
                            inference_state,
                            status="running",
                            stage="semantic_annotation",
                            percent=annotation_percent,
                            current_episode=index + 1,
                            completed_episode_count=len(completed),
                            completed_episodes=completed,
                            failed_episode=None,
                            retryable=False,
                            error=None,
                        )
                        _emit_progress(
                            progress_callback,
                            "semantic_annotation",
                            annotation_percent,
                            "复用 Episode {0}/{1} 的检查点".format(
                                index + 1, len(episodes)
                            ),
                            current=index + 1,
                            total=len(episodes),
                        )
                        continue
                except (OSError, ValueError, TypeError, KeyError):
                    pass
            _emit_progress(
                progress_callback,
                "semantic_annotation",
                annotation_percent,
                "分析 Episode {0}/{1}".format(index + 1, len(episodes)),
                current=index + 1,
                total=len(episodes),
            )
            _write_inference_state(
                stage_root,
                inference_state,
                status="running",
                stage="semantic_annotation",
                percent=annotation_percent,
                current_episode=index + 1,
                failed_episode=None,
                retryable=False,
                error=None,
            )
            task_context, evidence_packet, neighbor_context = _episode_evidence_packet(
                trace, episodes, index, key_events
            )
            semantic_prompt = annotation_prompt(task_context, evidence_packet, neighbor_context)
            _write_json(
                annotation_root / (prefix + "-request.json"),
                {
                    "prompt_version": prompt_version,
                    "episode_id": episode["episode_id"],
                    "task_context": task_context,
                    "episode_evidence": evidence_packet,
                    "neighbor_context": neighbor_context,
                    "prompt": semantic_prompt,
                },
            )
            try:
                annotation_output = _provider_complete(
                    semantic_provider,
                    semantic_prompt,
                    "semantic_annotation_{0:03d}".format(index + 1),
                    ANNOTATION_SCHEMA,
                    retry_progress,
                )
                remember_response_mode(annotation_output)
            except SemanticProviderError as error:
                partial_status = "partial" if error.retryable else "failed"
                _write_inference_state(
                    stage_root,
                    inference_state,
                    status=partial_status,
                    stage="semantic_annotation",
                    percent=annotation_percent,
                    current_episode=index + 1,
                    failed_episode=index + 1,
                    retryable=error.retryable,
                    error=str(error),
                    error_type=error.error_type,
                )
                raise SemanticWorkflowPartialError(str(error), inference_state) from error
            _write_json(
                annotation_root / (prefix + "-raw-response.json"),
                annotation_output,
            )
            annotation_errors = _annotation_validation_errors([episode], annotation_output)
            repaired = False
            if annotation_errors:
                try:
                    repaired_annotation = _provider_complete(
                        semantic_provider,
                        repair_prompt(
                            "SEMANTIC_ANNOTATION",
                            semantic_prompt,
                            annotation_output,
                            annotation_errors,
                            ANNOTATION_SCHEMA,
                        ),
                        "semantic_annotation_{0:03d}_repair".format(index + 1),
                        ANNOTATION_SCHEMA,
                        retry_progress,
                    )
                    remember_response_mode(repaired_annotation)
                except SemanticProviderError as error:
                    _write_inference_state(
                        stage_root,
                        inference_state,
                        status="partial" if error.retryable else "failed",
                        stage="semantic_annotation_repair",
                        percent=annotation_percent,
                        current_episode=index + 1,
                        failed_episode=index + 1,
                        retryable=error.retryable,
                        error=str(error),
                        error_type=error.error_type,
                    )
                    raise SemanticWorkflowPartialError(str(error), inference_state) from error
                _write_json(
                    annotation_root / (prefix + "-repair-response.json"),
                    repaired_annotation,
                )
                repaired_errors = _annotation_validation_errors([episode], repaired_annotation)
                if repaired_errors:
                    annotation_errors.extend(repaired_errors)
                else:
                    annotation_output = repaired_annotation
                    annotation_errors = []
                    repaired = True
            if annotation_errors:
                warnings.append(
                    "Episode {0} annotation remained invalid and was retained as an abstained Node".format(
                        episode["episode_id"]
                    )
                )
                episode_nodes = _abstained_nodes(session_id, trace, [episode])
                all_annotation_errors.extend(
                    {**error, "episode_id": episode["episode_id"]} for error in annotation_errors
                )
            else:
                episode_nodes = _model_nodes(session_id, trace, [episode], annotation_output)
            episode_nodes[0]["sequence"] = index + 1
            nodes.extend(episode_nodes)
            _write_json(node_path, episode_nodes[0])
            validation_record = {
                "episode_id": episode["episode_id"],
                "valid": not annotation_errors,
                "repaired": repaired,
                "errors": annotation_errors,
            }
            annotation_results.append(validation_record)
            _write_json(
                annotation_root / (prefix + "-validation.json"),
                validation_record,
            )
            completed = list(inference_state.get("completed_episodes") or [])
            if episode["episode_id"] not in completed:
                completed.append(episode["episode_id"])
            _write_inference_state(
                stage_root,
                inference_state,
                status="running",
                stage="semantic_annotation",
                percent=annotation_percent,
                completed_episode_count=len(completed),
                completed_episodes=completed,
                failed_episode=None,
                retryable=False,
                error=None,
            )
        _emit_progress(
            progress_callback,
            "semantic_annotation",
            82,
            "已完成 {0} 个 Episode 的语义提取".format(len(episodes)),
            current=len(episodes),
            total=len(episodes),
        )
        _write_json(
            stage_root / "annotation_validation.json",
            {
                "valid": not all_annotation_errors,
                "episode_count": len(episodes),
                "results": annotation_results,
                "errors": all_annotation_errors,
            },
        )
    else:
        nodes = _rule_nodes(session_id, trace, episodes)
        _write_json(
            stage_root / "annotation_validation.json",
            {"valid": True, "method": "rules"},
        )
        _emit_progress(
            progress_callback,
            "semantic_annotation",
            82,
            "规则模式语义节点已生成",
            current=len(episodes),
            total=len(episodes),
        )
    _write_json(stage_root / "semantic_nodes.json", nodes)
    _write_inference_state(
        stage_root,
        inference_state,
        status="running",
        stage="relations",
        percent=86,
        completed_episode_count=len(episodes),
        completed_episodes=[episode["episode_id"] for episode in episodes],
        current_episode=None,
        failed_episode=None,
        retryable=False,
        error=None,
    )

    model_relations: Optional[Mapping[str, Any]] = None
    relation_errors: List[Dict[str, Any]] = []
    _emit_progress(progress_callback, "relations", 86, "提取 Semantic Node 关系")
    if semantic_provider is not None and all(
        node.get("inference_method") == "model" for node in nodes
    ):
        semantic_relation_prompt = relation_prompt(nodes)
        _write_json(
            stage_root / "relation_request.json",
            {"prompt_version": prompt_version, "prompt": semantic_relation_prompt},
        )
        relation_response_path = stage_root / "relation_raw_response.json"
        if resume_inference and relation_response_path.is_file():
            relation_output = _read_json(relation_response_path)
        else:
            try:
                relation_output = _provider_complete(
                    semantic_provider,
                    semantic_relation_prompt,
                    "semantic_relations",
                    RELATION_SCHEMA,
                    retry_progress,
                )
                remember_response_mode(relation_output)
            except SemanticProviderError as error:
                _write_inference_state(
                    stage_root,
                    inference_state,
                    status="partial" if error.retryable else "failed",
                    stage="relations",
                    percent=86,
                    retryable=error.retryable,
                    error=str(error),
                    error_type=error.error_type,
                )
                raise SemanticWorkflowPartialError(str(error), inference_state) from error
            _write_json(relation_response_path, relation_output)
        relation_errors = _relation_validation_errors(nodes, relation_output)
        if relation_errors:
            try:
                repaired_relations = _provider_complete(
                    semantic_provider,
                    repair_prompt(
                        "SEMANTIC_RELATIONS",
                        semantic_relation_prompt,
                        relation_output,
                        relation_errors,
                        RELATION_SCHEMA,
                    ),
                    "semantic_relations_repair",
                    RELATION_SCHEMA,
                    retry_progress,
                )
                remember_response_mode(repaired_relations)
            except SemanticProviderError as error:
                _write_inference_state(
                    stage_root,
                    inference_state,
                    status="partial" if error.retryable else "failed",
                    stage="relation_repair",
                    percent=88,
                    retryable=error.retryable,
                    error=str(error),
                    error_type=error.error_type,
                )
                raise SemanticWorkflowPartialError(str(error), inference_state) from error
            _write_json(stage_root / "relation_repair_response.json", repaired_relations)
            repaired_errors = _relation_validation_errors(nodes, repaired_relations)
            if repaired_errors:
                relation_errors.extend(repaired_errors)
                warnings.append(
                    "Model relations remained invalid; only deterministic NEXT relations were retained"
                )
            else:
                relation_output = repaired_relations
                relation_errors = []
        if not relation_errors:
            model_relations = relation_output
    _write_json(
        stage_root / "relation_validation.json",
        {"valid": not relation_errors, "errors": relation_errors},
    )
    relations = _relations(session_id, nodes, model_relations)
    _write_json(stage_root / "relations.json", relations)

    configured_model = config.model
    if semantic_provider is not None and hasattr(semantic_provider, "config"):
        configured_model = str(
            getattr(getattr(semantic_provider, "config"), "model", configured_model)
            or configured_model
        )
    workflow: Dict[str, Any] = {
        "schema_version": SEMANTIC_SCHEMA_VERSION,
        "source_trace": {
            "session_id": session_id,
            "path": "derived/observer_trace.json",
            "sha256": trace_sha,
            "schema_version": trace.get("schema_version"),
        },
        "inference_run": {
            "inference_id": inference_id,
            "method": method,
            "model": configured_model if semantic_provider is not None else None,
            "processor_version": SEMANTIC_PROCESSOR_VERSION,
            "prompt_version": prompt_version,
            "generated_at": _utc_now(),
            "candidate_count": len(candidates),
            "stage_path": "derived/semantic_stages/{0}/".format(inference_id),
            "warnings": warnings,
        },
        "boundary_decisions": decisions,
        "episodes": episodes,
        "semantic_nodes": nodes,
        "relations": relations,
        "validation": {},
        "review": {"status": "unreviewed", "review_event_count": 0},
    }
    _emit_progress(progress_callback, "validation", 95, "执行 Evidence 与粒度验证")
    workflow["validation"] = validate_semantic_workflow(workflow, trace)
    _write_json(stage_root / "validation_report.json", workflow["validation"])
    if not workflow["validation"]["valid"]:
        warnings.append("Semantic workflow contains validation issues; inspect validation.issues")

    versions = directory / "derived" / "semantic_workflows"
    versions.mkdir(parents=True, exist_ok=True)
    existing = sorted(versions.glob("semantic-*.json"))
    existing_versions = [
        int(match.group(1))
        for path in existing
        for match in [re.fullmatch(r"semantic-([0-9]+)\.json", path.name)]
        if match
    ]
    version_path = versions / "semantic-{0:04d}.json".format(max(existing_versions, default=0) + 1)
    _write_json(version_path, workflow)
    _write_json(current_path, workflow)
    update_manifest(
        session_id,
        {
            "files": {
                "semantic_workflow": "derived/semantic_workflow.json",
                "semantic_workflow_versions": "derived/semantic_workflows/",
                "semantic_stages": "derived/semantic_stages/",
                "semantic_reviews": "derived/semantic_reviews.jsonl",
            }
        },
        root,
    )
    _write_inference_state(
        stage_root,
        inference_state,
        status="completed",
        stage="complete",
        percent=100,
        retryable=False,
        error=None,
        completed_at=_utc_now(),
    )
    _emit_progress(progress_callback, "complete", 100, "Semantic Workflow 已生成")
    return workflow


def load_semantic_workflow(
    session_id: str, root: Optional[str] = None, reviewed: bool = True
) -> Dict[str, Any]:
    directory = session_directory(session_id, root)
    reviewed_path = directory / "derived" / "semantic_workflow_reviewed.json"
    base_path = directory / "derived" / "semantic_workflow.json"
    if not base_path.is_file():
        raise FileNotFoundError(
            "semantic_workflow.json does not exist; run 'agentvast observe semantic {0}'".format(
                session_id
            )
        )
    value = json.loads(base_path.read_text(encoding="utf-8"))
    if reviewed and reviewed_path.is_file():
        try:
            reviewed_value = json.loads(reviewed_path.read_text(encoding="utf-8"))
            if (reviewed_value.get("inference_run") or {}).get("inference_id") == (
                value.get("inference_run") or {}
            ).get("inference_id"):
                value = reviewed_value
        except (OSError, ValueError, TypeError):
            pass
    if isinstance(value, dict) and value.get("schema_version") == "semantic-workflow/0.2":
        value = _upgrade_legacy_semantic_workflow(value)
    if not isinstance(value, dict) or value.get("schema_version") != SEMANTIC_SCHEMA_VERSION:
        raise SemanticWorkflowError("semantic workflow has an unsupported schema")
    return value


def _upgrade_legacy_semantic_workflow(value: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt a v0.2 workflow in memory without rewriting historical evidence."""
    upgraded = json.loads(json.dumps(value, ensure_ascii=False))
    upgraded["schema_version"] = SEMANTIC_SCHEMA_VERSION
    for node in upgraded.get("semantic_nodes") or []:
        if not isinstance(node, dict):
            continue
        legacy_intent = node.get("specific_intent")
        legacy_goal = node.get("goal")
        objective = legacy_intent if isinstance(legacy_intent, dict) else legacy_goal
        if not isinstance(objective, dict):
            objective = _field("未提取阶段目标", node.get("event_ids") or [])
        node["objective"] = objective
        title_source = str(
            node.get("title")
            or objective.get("value")
            or node.get("primary_activity")
            or "语义阶段"
        )
        node["title"] = re.split(r"[。！？]", title_source, maxsplit=1)[0][:36]
        node.pop("specific_intent", None)
        node.pop("goal", None)
        for action in node.get("actions") or []:
            if not isinstance(action, dict):
                continue
            action["semantic_relevance"] = (
                "orchestration"
                if action.get("tool_name")
                in {"TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "Skill"}
                else "key_action"
            )
    inference = upgraded.setdefault("inference_run", {})
    inference["loaded_with_schema_adapter"] = "semantic-workflow/0.2-to-0.3"
    return upgraded


def revalidate_semantic_workflow(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    """Recompute deterministic validation without another model request."""
    directory = session_directory(session_id, root)
    workflow = load_semantic_workflow(session_id, root, reviewed=False)
    trace = load_observer_trace(session_id, root)
    workflow["validation"] = validate_semantic_workflow(workflow, trace)
    inference = workflow.setdefault("inference_run", {})
    inference["processor_version"] = SEMANTIC_PROCESSOR_VERSION
    inference["revalidated_at"] = _utc_now()
    warning = "Semantic workflow contains validation issues; inspect validation.issues"
    warnings = [str(item) for item in inference.get("warnings") or [] if str(item) != warning]
    if not workflow["validation"]["valid"]:
        warnings.append(warning)
    inference["warnings"] = warnings
    _write_json(directory / "derived" / "semantic_workflow.json", workflow)
    stage_path = str(inference.get("stage_path") or "").strip("/\\")
    if stage_path:
        _write_json(directory / stage_path / "validation_report.json", workflow["validation"])
    return workflow
