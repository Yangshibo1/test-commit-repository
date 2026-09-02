"""Semantic workflow reconstruction and deterministic evidence validation."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

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
from agentvast.semantic.provider import SemanticConfig, SemanticProvider


ALLOWED_RELATIONS = {"VALIDATES", "REFINES", "USES_RESULT_FROM", "RETRY_OF"}


class SemanticWorkflowError(RuntimeError):
    """Raised when a semantic workflow cannot be safely generated or loaded."""


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


def _event_payload_for_model(event: Mapping[str, Any]) -> Dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    result = {
        "event_id": event.get("event_id"),
        "event_type": event.get("event_type"),
        "title": event.get("title"),
        "summary": event.get("summary"),
        "status": event.get("status"),
        "origin": event.get("origin"),
        "source_lines": event.get("source_lines") or [],
    }
    if event.get("event_type") == "tool_execution":
        result["tool"] = {
            "name": payload.get("name"),
            "input": payload.get("input"),
            "output_preview": _preview(payload.get("output"), 1600),
            "is_error": payload.get("is_error"),
        }
    elif event.get("event_type") in {
        "user_prompt",
        "assistant_message",
        "subagent_result",
    }:
        result["text_preview"] = _preview(
            payload.get("result") or payload.get("content") or payload.get("text"),
            2400,
        )
        if event.get("event_type") == "subagent_result":
            result["subagent"] = {
                "task_id": payload.get("task_id"),
                "task_summary": payload.get("task_summary"),
                "status": payload.get("status"),
            }
    return result


def build_candidate_episodes(trace: Mapping[str, Any]) -> List[Dict[str, Any]]:
    events = trace.get("events") if isinstance(trace.get("events"), list) else []
    relations = trace.get("relations") if isinstance(trace.get("relations"), list) else []
    event_by_id = {
        str(event.get("event_id")): event
        for event in events
        if isinstance(event, dict) and event.get("event_id")
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
                    "events": [_event_payload_for_model(event) for event in candidate_events],
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
                    "events": [_event_payload_for_model(subagent)],
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
        if atomic and prompt_id in event_by_id:
            atomic[0]["event_ids"] = [prompt_id] + atomic[0]["event_ids"]
            atomic[0]["events"] = [_event_payload_for_model(event_by_id[prompt_id])] + atomic[0][
                "events"
            ]
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
            for event_id in candidate_by_id.get(candidate_id, {}).get("event_ids", [])
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


def _rule_nodes(
    session_id: str, trace: Mapping[str, Any], episodes: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    events = _event_map(trace)
    nodes: List[Dict[str, Any]] = []
    previous: Optional[Dict[str, Any]] = None
    for episode in episodes:
        episode_events = [
            events[event_id] for event_id in episode["event_ids"] if event_id in events
        ]
        tools = [event for event in episode_events if event.get("event_type") == "tool_execution"]
        final_messages = [
            event for event in episode_events if event.get("event_type") == "assistant_message"
        ]
        activity, intent, summary, outcome, confidence = _rule_annotation(
            tools, final_messages, previous
        )
        node_id = stable_id("semantic", session_id, [episode["episode_id"]])
        evidence = list(episode["event_ids"])
        node = {
            "node_id": node_id,
            "sequence": len(nodes) + 1,
            "episode_ids": [episode["episode_id"]],
            "event_ids": evidence,
            "primary_activity": activity,
            "activity_tags": ["Error Recovery"]
            if any(event.get("status") == "error" for event in tools)
            else [],
            "specific_intent": _field(intent, evidence),
            "goal": _field(intent, evidence),
            "summary": _field(summary, evidence),
            "outcome_claims": [
                {
                    "text": outcome,
                    "origin": "inferred",
                    "evidence_event_ids": evidence,
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


def _analysis_similarity(joined: str, previous: Optional[Mapping[str, Any]]) -> bool:
    previous_text = " ".join(
        str((previous or {}).get(field, {}).get("value") or "")
        for field in ("specific_intent", "summary")
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
            "primary_activity": activity,
            "activity_tags": [str(item) for item in raw.get("activity_tags") or []][:8],
            "specific_intent": _validated_model_field(raw.get("specific_intent"), event_ids),
            "goal": _validated_model_field(raw.get("goal"), event_ids),
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
    if value.get("schema_version") != "semantic-annotation/0.1":
        errors.append({"path": "schema_version", "error": "must equal semantic-annotation/0.1"})
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
                "primary_activity",
                "activity_tags",
                "specific_intent",
                "goal",
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
        allowed_events = set(str(item) for item in episode.get("event_ids") or [])
        for field_name in ("specific_intent", "goal", "summary"):
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
        episode_events = [event_map[item] for item in event_ids if item in event_map]
        digest = "；".join(
            _preview(event.get("title") or event.get("summary"), 120) for event in episode_events
        )
        node = {
            "node_id": stable_id("semantic", session_id, [episode["episode_id"]]),
            "sequence": len(nodes) + 1,
            "episode_ids": [episode["episode_id"]],
            "event_ids": event_ids,
            "primary_activity": "Uncertain",
            "activity_tags": [],
            "specific_intent": _field("语义标注未通过验证", event_ids),
            "goal": _field("保留该行为阶段并等待人工校正", event_ids),
            "summary": _field(digest or "该阶段包含可观察行为。", event_ids),
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
        for field_name in ("specific_intent", "goal", "summary"):
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
            for field_name in ("specific_intent", "goal", "summary")
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
) -> Dict[str, Any]:
    return provider.complete(prompt, stage, json_schema=schema)


def run_semantic_workflow(
    session_id: str,
    root: Optional[str] = None,
    rules_only: bool = False,
    force: bool = False,
    provider: Optional[SemanticProvider] = None,
) -> Dict[str, Any]:
    directory = session_directory(session_id, root)
    trace_path = directory / "derived" / "observer_trace.json"
    if not trace_path.is_file():
        raise SemanticWorkflowError("observer_trace.json does not exist; run observe derive first")
    trace = load_observer_trace(session_id, root)
    trace_sha = _sha256(trace_path)
    config = SemanticConfig.from_env()
    method = "rules" if rules_only else "model"
    current_path = directory / "derived" / "semantic_workflow.json"
    if current_path.is_file() and not force:
        try:
            current = json.loads(current_path.read_text(encoding="utf-8"))
            inference = current.get("inference_run") or {}
            if (
                (current.get("source_trace") or {}).get("sha256") == trace_sha
                and inference.get("method") == method
                and inference.get("processor_version") == SEMANTIC_PROCESSOR_VERSION
            ):
                return current
        except (OSError, ValueError, TypeError):
            pass

    candidates = build_candidate_episodes(trace)
    if not candidates:
        raise SemanticWorkflowError("observer trace contains no reconstructable Episodes")
    warnings: List[str] = []
    semantic_provider = provider
    if not rules_only and semantic_provider is None:
        if not config.configured():
            raise SemanticWorkflowError(
                "Semantic API is not configured; configure it or pass --rules-only"
            )
        semantic_provider = SemanticProvider(config)

    inference_id = "semantic-{0}".format(uuid.uuid4().hex[:12])
    stage_root = directory / "derived" / "semantic_stages" / inference_id
    stage_root.mkdir(parents=True, exist_ok=False)
    _write_json(stage_root / "candidate_blocks.json", candidates)

    boundary_prompt = segmentation_prompt(candidates)
    _write_json(
        stage_root / "boundary_request.json",
        {
            "prompt_version": "semantic-prompts/0.2",
            "candidate_count": len(candidates),
            "prompt": boundary_prompt,
        },
    )
    boundary_output: Optional[Dict[str, Any]] = None
    boundary_errors: List[Dict[str, Any]] = []
    boundary_fallback: Optional[str] = None
    if semantic_provider is not None:
        boundary_output = _provider_complete(
            semantic_provider,
            boundary_prompt,
            "episode_boundaries",
            BOUNDARY_SCHEMA,
        )
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
            )
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
    decisions, groups = _effective_boundaries(
        candidates,
        boundary_output if not boundary_errors else None,
        fallback_reason=boundary_fallback,
    )
    _write_json(
        stage_root / "boundary_validation.json",
        {
            "valid": not boundary_errors,
            "errors": boundary_errors,
            "fallback": boundary_fallback,
        },
    )
    _write_json(stage_root / "validated_boundaries.json", decisions)
    episodes = _materialize_episodes(session_id, candidates, groups, decisions)
    _write_json(stage_root / "episodes.json", episodes)

    if semantic_provider is not None:
        event_map = _event_map(trace)
        episode_payloads = [
            {
                **episode,
                "allowed_event_ids": episode["event_ids"],
                "events": [
                    _event_payload_for_model(event_map[event_id])
                    for event_id in episode["event_ids"]
                    if event_id in event_map
                ],
            }
            for episode in episodes
        ]
        semantic_prompt = annotation_prompt(episode_payloads)
        _write_json(
            stage_root / "annotation_request.json",
            {
                "prompt_version": "semantic-prompts/0.2",
                "episode_count": len(episodes),
                "prompt": semantic_prompt,
            },
        )
        annotation_output = _provider_complete(
            semantic_provider,
            semantic_prompt,
            "semantic_annotation",
            ANNOTATION_SCHEMA,
        )
        _write_json(stage_root / "annotation_raw_response.json", annotation_output)
        annotation_errors = _annotation_validation_errors(episodes, annotation_output)
        if annotation_errors:
            repaired_annotation = _provider_complete(
                semantic_provider,
                repair_prompt(
                    "SEMANTIC_ANNOTATION",
                    semantic_prompt,
                    annotation_output,
                    annotation_errors,
                    ANNOTATION_SCHEMA,
                ),
                "semantic_annotation_repair",
                ANNOTATION_SCHEMA,
            )
            _write_json(stage_root / "annotation_repair_response.json", repaired_annotation)
            repaired_errors = _annotation_validation_errors(episodes, repaired_annotation)
            if repaired_errors:
                annotation_errors.extend(repaired_errors)
                warnings.append(
                    "Model annotations remained invalid; Episodes were retained as abstained Nodes"
                )
                nodes = _abstained_nodes(session_id, trace, episodes)
            else:
                annotation_output = repaired_annotation
                annotation_errors = []
                nodes = _model_nodes(session_id, trace, episodes, annotation_output)
        else:
            nodes = _model_nodes(session_id, trace, episodes, annotation_output)
        _write_json(
            stage_root / "annotation_validation.json",
            {"valid": not annotation_errors, "errors": annotation_errors},
        )
    else:
        nodes = _rule_nodes(session_id, trace, episodes)
        _write_json(
            stage_root / "annotation_validation.json",
            {"valid": True, "method": "rules"},
        )
    _write_json(stage_root / "semantic_nodes.json", nodes)

    model_relations: Optional[Mapping[str, Any]] = None
    relation_errors: List[Dict[str, Any]] = []
    if semantic_provider is not None and all(
        node.get("inference_method") == "model" for node in nodes
    ):
        semantic_relation_prompt = relation_prompt(nodes)
        _write_json(
            stage_root / "relation_request.json",
            {"prompt_version": "semantic-prompts/0.2", "prompt": semantic_relation_prompt},
        )
        relation_output = _provider_complete(
            semantic_provider,
            semantic_relation_prompt,
            "semantic_relations",
            RELATION_SCHEMA,
        )
        _write_json(stage_root / "relation_raw_response.json", relation_output)
        relation_errors = _relation_validation_errors(nodes, relation_output)
        if relation_errors:
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
            )
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
            "prompt_version": "semantic-prompts/0.2",
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
    if not isinstance(value, dict) or value.get("schema_version") != SEMANTIC_SCHEMA_VERSION:
        raise SemanticWorkflowError("semantic workflow has an unsupported schema")
    return value


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
