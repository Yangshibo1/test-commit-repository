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
    annotation_prompt,
    relation_prompt,
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
    elif event.get("event_type") in {"user_prompt", "assistant_message"}:
        result["text_preview"] = _preview(payload.get("content") or payload.get("text"), 2000)
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
        for index, response in enumerate(responses):
            response_id = str(response.get("event_id"))
            event_ids: List[str] = []
            if index == 0 and prompt_id in event_by_id:
                event_ids.append(prompt_id)
            event_ids.append(response_id)
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
            candidates.append(
                {
                    "candidate_episode_id": candidate_id,
                    "turn_id": turn_id,
                    "event_ids": event_ids,
                    "events": [_event_payload_for_model(event) for event in candidate_events],
                    "boundary_basis": [
                        "model_response_boundary",
                        "human_prompt_boundary" if index == 0 else "response_transition",
                    ],
                }
            )

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


def _episode_groups_from_model(
    candidates: List[Dict[str, Any]], value: Mapping[str, Any]
) -> Optional[List[List[str]]]:
    raw_groups = value.get("episode_groups")
    if not isinstance(raw_groups, list):
        return None
    expected = [str(item["candidate_episode_id"]) for item in candidates]
    flattened: List[str] = []
    groups: List[List[str]] = []
    for item in raw_groups:
        if not isinstance(item, dict) or not isinstance(item.get("candidate_episode_ids"), list):
            return None
        ids = [str(candidate_id) for candidate_id in item["candidate_episode_ids"]]
        if not ids:
            return None
        groups.append(ids)
        flattened.extend(ids)
    if flattened != expected:
        return None
    return groups


def _materialize_episodes(
    session_id: str,
    candidates: List[Dict[str, Any]],
    groups: Sequence[Sequence[str]],
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
) -> Optional[List[Dict[str, Any]]]:
    raw_nodes = value.get("nodes")
    if not isinstance(raw_nodes, list):
        return None
    episode_by_id = {str(item["episode_id"]): item for item in episodes}
    expected = [str(item["episode_id"]) for item in episodes]
    covered: List[str] = []
    event_map = _event_map(trace)
    result: List[Dict[str, Any]] = []
    for raw in raw_nodes:
        if not isinstance(raw, dict) or not isinstance(raw.get("episode_ids"), list):
            return None
        episode_ids = [str(item) for item in raw["episode_ids"]]
        if not episode_ids or any(item not in episode_by_id for item in episode_ids):
            return None
        covered.extend(episode_ids)
        event_ids: List[str] = []
        for episode_id in episode_ids:
            event_ids.extend(
                event_id
                for event_id in episode_by_id[episode_id]["event_ids"]
                if event_id not in event_ids
            )
        activity = str(raw.get("primary_activity") or "Uncertain")
        if activity not in ACTIVITY_TYPES:
            activity = "Uncertain"
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
                "level": _confidence((raw.get("confidence") or {}).get("level")),
                "evidence_coverage": 0.0,
                "boundary_basis": sorted(
                    {
                        reason
                        for episode_id in episode_ids
                        for reason in episode_by_id[episode_id].get("boundary_basis") or []
                    }
                ),
                "uncertainty_reason": str(
                    (raw.get("confidence") or {}).get("uncertainty_reason") or ""
                ),
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
    if covered != expected:
        return None
    return result


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
    event_ids = {
        str(event.get("event_id")) for event in trace.get("events") or [] if isinstance(event, dict)
    }
    episodes = workflow.get("episodes") if isinstance(workflow.get("episodes"), list) else []
    nodes = (
        workflow.get("semantic_nodes") if isinstance(workflow.get("semantic_nodes"), list) else []
    )
    relations = workflow.get("relations") if isinstance(workflow.get("relations"), list) else []
    issues: List[Dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        unknown_episode_events = [
            str(event_id)
            for event_id in episode.get("event_ids") or []
            if str(event_id) not in event_ids
        ]
        if unknown_episode_events:
            issues.append(
                {
                    "code": "unknown_episode_evidence",
                    "episode_id": episode.get("episode_id"),
                    "event_ids": unknown_episode_events,
                }
            )
    covered_episodes: List[str] = []
    node_ids: Set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            issues.append({"code": "invalid_node", "detail": "Node is not an object"})
            continue
        node_id = str(node.get("node_id") or "")
        node_ids.add(node_id)
        covered_episodes.extend(str(item) for item in node.get("episode_ids") or [])
        if node.get("primary_activity") not in ACTIVITY_TYPES:
            issues.append({"code": "unknown_activity", "node_id": node_id})
        for field_name in ("specific_intent", "goal", "summary"):
            field = node.get(field_name) if isinstance(node.get(field_name), dict) else {}
            evidence = [str(item) for item in field.get("evidence_event_ids") or []]
            if not str(field.get("value") or "").strip() or not evidence:
                issues.append(
                    {"code": "unsupported_field", "node_id": node_id, "field": field_name}
                )
            if any(item not in event_ids for item in evidence):
                issues.append({"code": "unknown_evidence", "node_id": node_id, "field": field_name})
        for claim_index, claim in enumerate(node.get("outcome_claims") or []):
            if not isinstance(claim, dict):
                issues.append(
                    {"code": "invalid_claim", "node_id": node_id, "claim_index": claim_index}
                )
                continue
            claim_evidence = [str(item) for item in claim.get("evidence_event_ids") or []]
            if not str(claim.get("text") or "").strip() or not claim_evidence:
                issues.append(
                    {"code": "unsupported_claim", "node_id": node_id, "claim_index": claim_index}
                )
            if any(item not in event_ids for item in claim_evidence):
                issues.append(
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
        coverage = len(evidence_union & node_events) / max(1, len(node_events))
        if isinstance(node.get("confidence"), dict):
            node["confidence"]["evidence_coverage"] = round(coverage, 4)
    if covered_episodes != [str(item.get("episode_id")) for item in episodes]:
        issues.append(
            {"code": "episode_coverage", "detail": "Episodes are missing, duplicated, or reordered"}
        )
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        if (
            relation.get("from_node_id") not in node_ids
            or relation.get("to_node_id") not in node_ids
        ):
            issues.append(
                {"code": "invalid_relation_node", "relation_id": relation.get("relation_id")}
            )
        if relation.get("type") != "NEXT" and not relation.get("evidence_event_ids"):
            issues.append(
                {"code": "unsupported_relation", "relation_id": relation.get("relation_id")}
            )
        if any(
            str(event_id) not in event_ids for event_id in relation.get("evidence_event_ids") or []
        ):
            issues.append(
                {"code": "unknown_relation_evidence", "relation_id": relation.get("relation_id")}
            )
    return {
        "valid": not issues,
        "issue_count": len(issues),
        "issues": issues,
        "episode_count": len(episodes),
        "node_count": len(nodes),
        "relation_count": len(relations),
        "source_event_count": len(event_ids),
    }


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

    groups: List[List[str]] = [[str(item["candidate_episode_id"])] for item in candidates]
    if semantic_provider is not None:
        segmentation = semantic_provider.complete(
            segmentation_prompt(candidates), "episode_segmentation"
        )
        model_groups = _episode_groups_from_model(candidates, segmentation)
        if model_groups is None:
            warnings.append(
                "Model segmentation failed validation; candidate boundaries were retained"
            )
        else:
            groups = model_groups
    episodes = _materialize_episodes(session_id, candidates, groups)

    nodes: Optional[List[Dict[str, Any]]] = None
    if semantic_provider is not None:
        episode_payloads = []
        event_map = _event_map(trace)
        for episode in episodes:
            episode_payloads.append(
                {
                    **episode,
                    "events": [
                        _event_payload_for_model(event_map[event_id])
                        for event_id in episode["event_ids"]
                        if event_id in event_map
                    ],
                }
            )
        annotation = semantic_provider.complete(
            annotation_prompt(episode_payloads), "semantic_annotation"
        )
        nodes = _model_nodes(session_id, trace, episodes, annotation)
        if nodes is None:
            warnings.append(
                "Model annotations failed validation; conservative rule annotations were used"
            )
    if nodes is None:
        nodes = _rule_nodes(session_id, trace, episodes)

    model_relations: Optional[Mapping[str, Any]] = None
    if semantic_provider is not None and all(
        node.get("inference_method") == "model" for node in nodes
    ):
        model_relations = semantic_provider.complete(relation_prompt(nodes), "semantic_relations")
    relations = _relations(session_id, nodes, model_relations)
    inference_id = "semantic-{0}".format(uuid.uuid4().hex[:12])
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
            "model": config.model if semantic_provider is not None else None,
            "processor_version": SEMANTIC_PROCESSOR_VERSION,
            "prompt_version": "semantic-prompts/0.1",
            "generated_at": _utc_now(),
            "warnings": warnings,
        },
        "episodes": episodes,
        "semantic_nodes": nodes,
        "relations": relations,
        "validation": {},
        "review": {"status": "unreviewed", "review_event_count": 0},
    }
    workflow["validation"] = validate_semantic_workflow(workflow, trace)
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
