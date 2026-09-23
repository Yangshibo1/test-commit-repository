"""Append-only human validation sidecar for semantic workflows."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

from agentvast.observer.locking import InterProcessFileLock
from agentvast.observer.store import iter_jsonl, session_directory
from agentvast.observer.trace_builder import load_observer_trace, stable_id
from agentvast.semantic.pipeline import (
    SemanticWorkflowError,
    load_semantic_workflow,
    validate_semantic_workflow,
)
from agentvast.semantic.prompts import ACTIVITY_TYPES


REVIEW_ACTIONS = {"accept", "update", "merge", "split"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def record_semantic_review(
    session_id: str,
    action: str,
    payload: Mapping[str, Any],
    root: Optional[str] = None,
) -> Dict[str, Any]:
    if action not in REVIEW_ACTIONS:
        raise SemanticWorkflowError(
            "semantic review action must be accept, update, merge, or split"
        )
    directory = session_directory(session_id, root)
    base = load_semantic_workflow(session_id, root, reviewed=False)
    review_event = {
        "review_id": "review-{0}".format(uuid.uuid4().hex[:12]),
        "session_id": session_id,
        "inference_id": (base.get("inference_run") or {}).get("inference_id"),
        "action": action,
        "payload": dict(payload),
        "created_at": _utc_now(),
        "origin": "user_validated",
    }
    preview = json.loads(
        json.dumps(load_semantic_workflow(session_id, root, reviewed=True), ensure_ascii=False)
    )
    _apply_review(preview, review_event)
    path = directory / "derived" / "semantic_reviews.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with InterProcessFileLock(directory / ".semantic-review.lock"):
        with path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(json.dumps(review_event, ensure_ascii=False) + "\n")
        reviewed = materialize_reviewed_workflow(session_id, root)
    return {"review_event": review_event, "workflow": reviewed}


def materialize_reviewed_workflow(session_id: str, root: Optional[str] = None) -> Dict[str, Any]:
    directory = session_directory(session_id, root)
    workflow = json.loads(
        json.dumps(load_semantic_workflow(session_id, root, reviewed=False), ensure_ascii=False)
    )
    inference_id = (workflow.get("inference_run") or {}).get("inference_id")
    reviews = [
        item
        for item in iter_jsonl(directory / "derived" / "semantic_reviews.jsonl")
        if item.get("inference_id") == inference_id
    ]
    applied: List[str] = []
    warnings: List[str] = []
    for review in reviews:
        try:
            _apply_review(workflow, review)
            applied.append(str(review.get("review_id")))
        except SemanticWorkflowError as error:
            warnings.append("{0}: {1}".format(review.get("review_id"), error))
    trace = load_observer_trace(session_id, root)
    workflow["validation"] = validate_semantic_workflow(workflow, trace)
    workflow["review"] = {
        "status": "reviewed" if applied else "unreviewed",
        "review_event_count": len(applied),
        "applied_review_ids": applied,
        "warnings": warnings,
    }
    output = directory / "derived" / "semantic_workflow_reviewed.json"
    _write_json(output, workflow)
    return workflow


def _apply_review(workflow: Dict[str, Any], review: Mapping[str, Any]) -> None:
    action = str(review.get("action") or "")
    payload = review.get("payload") if isinstance(review.get("payload"), dict) else {}
    if action == "accept":
        node = _node(workflow, str(payload.get("node_id") or ""))
        node["review_status"] = "accepted"
        node.setdefault("review_history", []).append(str(review.get("review_id")))
    elif action == "update":
        node = _node(workflow, str(payload.get("node_id") or ""))
        _update_node(node, payload, str(review.get("review_id")))
    elif action == "merge":
        _merge_nodes(workflow, payload, str(review.get("review_id")))
    elif action == "split":
        _split_node(workflow, payload, str(review.get("review_id")))
    else:
        raise SemanticWorkflowError("unsupported semantic review action")


def _node(workflow: Mapping[str, Any], node_id: str) -> Dict[str, Any]:
    for node in workflow.get("semantic_nodes") or []:
        if isinstance(node, dict) and node.get("node_id") == node_id:
            return node
    raise SemanticWorkflowError("semantic node does not exist: {0}".format(node_id))


def _update_node(node: Dict[str, Any], payload: Mapping[str, Any], review_id: str) -> None:
    activity = payload.get("primary_activity")
    if activity is not None:
        if str(activity) not in ACTIVITY_TYPES:
            raise SemanticWorkflowError("unknown primary_activity")
        node["primary_activity"] = str(activity)
    if isinstance(payload.get("activity_tags"), list):
        node["activity_tags"] = [str(item) for item in payload["activity_tags"]][:8]
    if payload.get("title") is not None:
        title = str(payload["title"]).strip()
        if not title or len(title) > 36:
            raise SemanticWorkflowError("title must be 1-36 characters")
        node["title"] = title
    for field_name in ("objective", "summary"):
        if payload.get(field_name) is None:
            continue
        current = node.get(field_name) if isinstance(node.get(field_name), dict) else {}
        node[field_name] = {
            "value": str(payload[field_name]).strip(),
            "origin": "user_validated",
            "evidence_event_ids": list(
                current.get("evidence_event_ids") or node.get("event_ids") or []
            ),
            "review_id": review_id,
        }
    node["review_status"] = "corrected"
    node.setdefault("review_history", []).append(review_id)


def _merge_nodes(workflow: Dict[str, Any], payload: Mapping[str, Any], review_id: str) -> None:
    node_ids = [str(item) for item in payload.get("node_ids") or []]
    if len(node_ids) < 2:
        raise SemanticWorkflowError("merge requires at least two node_ids")
    nodes = workflow.get("semantic_nodes") or []
    selected = [
        node for node in nodes if isinstance(node, dict) and node.get("node_id") in node_ids
    ]
    if len(selected) != len(set(node_ids)):
        raise SemanticWorkflowError("one or more merge nodes do not exist")
    selected.sort(key=lambda node: int(node.get("sequence") or 0))
    positions = [int(node.get("sequence") or 0) for node in selected]
    if positions != list(range(min(positions), max(positions) + 1)):
        raise SemanticWorkflowError("only consecutive semantic nodes can be merged")
    episode_ids = _ordered_unique(
        episode_id for node in selected for episode_id in node.get("episode_ids") or []
    )
    event_ids = _ordered_unique(
        event_id for node in selected for event_id in node.get("event_ids") or []
    )
    merged = _combined_node(selected, episode_ids, event_ids, payload, review_id)
    replacement_index = min(positions) - 1
    remaining = [node for node in nodes if node not in selected]
    remaining.insert(replacement_index, merged)
    workflow["semantic_nodes"] = remaining
    _renumber_and_rebuild_relations(workflow, {node_id: merged["node_id"] for node_id in node_ids})


def _combined_node(
    selected: List[Dict[str, Any]],
    episode_ids: List[str],
    event_ids: List[str],
    payload: Mapping[str, Any],
    review_id: str,
) -> Dict[str, Any]:
    activity = str(
        payload.get("primary_activity") or selected[0].get("primary_activity") or "Uncertain"
    )
    if activity not in ACTIVITY_TYPES:
        raise SemanticWorkflowError("unknown primary_activity")
    objective = str(
        payload.get("objective")
        or "；".join(
            str((node.get("objective") or {}).get("value") or "") for node in selected
        )
    ).strip()
    title = str(
        payload.get("title")
        or " / ".join(str(node.get("title") or "") for node in selected)
    ).strip()[:36]
    summary = str(
        payload.get("summary")
        or "；".join(str((node.get("summary") or {}).get("value") or "") for node in selected)
    ).strip()
    return {
        "node_id": stable_id("semantic-user", review_id, episode_ids),
        "sequence": min(int(node.get("sequence") or 0) for node in selected),
        "episode_ids": episode_ids,
        "event_ids": event_ids,
        "title": title or "合并行为阶段",
        "primary_activity": activity,
        "activity_tags": _ordered_unique(
            str(tag) for node in selected for tag in node.get("activity_tags") or []
        ),
        "objective": _reviewed_field(objective, event_ids, review_id),
        "summary": _reviewed_field(summary, event_ids, review_id),
        "outcome_claims": [
            claim for node in selected for claim in node.get("outcome_claims") or []
        ],
        "confidence": {
            "level": "high",
            "evidence_coverage": 1.0,
            "boundary_basis": ["user_merge"],
            "uncertainty_reason": "",
        },
        "abstained": False,
        "origin": "user_validated",
        "inference_method": "human_review",
        "review_status": "corrected",
        "review_history": [review_id],
        "actions": [action for node in selected for action in node.get("actions") or []],
        "observed_inputs": _unique_dicts(
            item for node in selected for item in node.get("observed_inputs") or []
        ),
        "reported_outputs": _unique_dicts(
            item for node in selected for item in node.get("reported_outputs") or []
        ),
        "verified_artifacts": _unique_dicts(
            item for node in selected for item in node.get("verified_artifacts") or []
        ),
        "errors": [error for node in selected for error in node.get("errors") or []],
    }


def _split_node(workflow: Dict[str, Any], payload: Mapping[str, Any], review_id: str) -> None:
    original = _node(workflow, str(payload.get("node_id") or ""))
    groups = payload.get("groups")
    if not isinstance(groups, list) or len(groups) < 2:
        raise SemanticWorkflowError("split requires at least two groups")
    expected = list(original.get("episode_ids") or [])
    flattened = [
        str(item)
        for group in groups
        if isinstance(group, dict)
        for item in group.get("episode_ids") or []
    ]
    if flattened != expected:
        raise SemanticWorkflowError("split groups must partition episode_ids in order")
    episode_map = {
        str(episode.get("episode_id")): episode
        for episode in workflow.get("episodes") or []
        if isinstance(episode, dict)
    }
    replacements: List[Dict[str, Any]] = []
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise SemanticWorkflowError("split group must be an object")
        episode_ids = [str(item) for item in group.get("episode_ids") or []]
        event_ids = _ordered_unique(
            event_id
            for episode_id in episode_ids
            for event_id in (episode_map.get(episode_id) or {}).get("event_ids") or []
        )
        selected = [{**original, "episode_ids": episode_ids, "event_ids": event_ids}]
        node = _combined_node(
            selected, episode_ids, event_ids, group, "{0}-{1}".format(review_id, index)
        )
        node["actions"] = [
            item for item in original.get("actions") or [] if item.get("event_id") in set(event_ids)
        ]
        node["errors"] = [
            item for item in original.get("errors") or [] if item.get("event_id") in set(event_ids)
        ]
        node["verified_artifacts"] = [
            item
            for item in original.get("verified_artifacts") or []
            if set(item.get("evidence_event_ids") or []) & set(event_ids)
        ]
        replacements.append(node)
    nodes = workflow.get("semantic_nodes") or []
    position = nodes.index(original)
    workflow["semantic_nodes"] = nodes[:position] + replacements + nodes[position + 1 :]
    _renumber_and_rebuild_relations(workflow, {original["node_id"]: replacements[0]["node_id"]})


def _reviewed_field(value: str, evidence: Iterable[str], review_id: str) -> Dict[str, Any]:
    return {
        "value": value,
        "origin": "user_validated",
        "evidence_event_ids": list(evidence),
        "review_id": review_id,
    }


def _renumber_and_rebuild_relations(workflow: Dict[str, Any], remap: Mapping[str, str]) -> None:
    nodes = workflow.get("semantic_nodes") or []
    for index, node in enumerate(nodes, start=1):
        node["sequence"] = index
    semantic_relations: List[Dict[str, Any]] = []
    node_ids = {node["node_id"] for node in nodes}
    for relation in workflow.get("relations") or []:
        if relation.get("type") == "NEXT":
            continue
        source = remap.get(str(relation.get("from_node_id")), str(relation.get("from_node_id")))
        target = remap.get(str(relation.get("to_node_id")), str(relation.get("to_node_id")))
        if source in node_ids and target in node_ids and source != target:
            semantic_relations.append({**relation, "from_node_id": source, "to_node_id": target})
    next_relations = []
    session_id = (workflow.get("source_trace") or {}).get("session_id")
    for left, right in zip(nodes, nodes[1:]):
        next_relations.append(
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
    workflow["relations"] = _unique_dicts(next_relations + semantic_relations, key="relation_id")


def _ordered_unique(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen: Set[str] = set()
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _unique_dicts(
    values: Iterable[Dict[str, Any]], key: Optional[str] = None
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for value in values:
        identity = (
            str(value.get(key)) if key else json.dumps(value, ensure_ascii=False, sort_keys=True)
        )
        if identity not in seen:
            seen.add(identity)
            result.append(value)
    return result
