"""Bounded context construction for Reviewer tasks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


MAX_TASK_TEXT_CHARS = 12_000
MAX_CONTEXT_CHARS = 30_000
TASK_TEXT_SUFFIXES = {".txt", ".md", ".rst"}


def load_workflow(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("run"), dict):
        raise ValueError("workflow.json is not an AgentVAST workflow document")
    return data


def workflow_summary(workflow: Dict[str, Any]) -> Dict[str, Any]:
    run = workflow["run"]
    return {
        "run_id": run.get("run_id"),
        "task": run.get("task"),
        "status": run.get("status"),
        "plan_revisions": [
            {
                "version": item.get("version"),
                "trigger": item.get("trigger"),
                "change_reason": item.get("change_reason"),
                "nodes": [
                    {
                        "node_id": node.get("node_id"),
                        "objective": node.get("objective"),
                        "depends_on": node.get("depends_on", []),
                    }
                    for node in item.get("nodes", [])
                ],
            }
            for item in workflow.get("plan_revisions", [])
        ],
        "human_interventions": [
            {
                "intervention_id": item.get("intervention_id"),
                "original_text": item.get("original_text"),
                "workflow_effect": item.get("workflow_effect"),
                "plan_version": item.get("plan_version"),
            }
            for item in workflow.get("human_interventions", [])
        ],
        "completed_nodes": [node_summary(node) for node in workflow.get("nodes", [])],
    }


def node_summary(node: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "node_id": node.get("node_id"),
        "sequence": node.get("sequence"),
        "plan_version": node.get("plan_version"),
        "objective": node.get("objective"),
        "operation_summary": (node.get("operation") or {}).get("summary"),
        "result_summary": node.get("result_summary"),
        "analysis_conclusion": node.get("analysis_conclusion"),
        "inputs": [item.get("path") for item in node.get("inputs", [])],
        "outputs": [item.get("path") for item in node.get("outputs", [])],
    }


def previous_node_context(
    workflow: Dict[str, Any], current: Dict[str, Any]
) -> List[Dict[str, Any]]:
    current_sequence = int(current.get("sequence") or 0)
    previous = [
        node_summary(node)
        for node in workflow.get("nodes", [])
        if int(node.get("sequence") or 0) < current_sequence
    ]
    return previous[-6:]


def task_text_context(workflow: Dict[str, Any], project_root: Path) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in workflow.get("run", {}).get("declared_inputs", []):
        raw_path = item.get("path")
        if not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = project_root / path
        try:
            resolved = path.resolve()
            resolved.relative_to(project_root.resolve())
        except (OSError, ValueError):
            continue
        if resolved.suffix.lower() not in TASK_TEXT_SUFFIXES or not resolved.is_file():
            continue
        recorded_sha = str(item.get("sha256") or "")
        current_sha = _sha256(resolved)
        if recorded_sha and recorded_sha != current_sha:
            result.append(
                {
                    "path": _relative(resolved, project_root),
                    "recorded_sha256": recorded_sha,
                    "current_sha256": current_sha,
                    "content_unavailable": "文件已不同于Run声明时的版本，未注入其当前内容",
                }
            )
            continue
        text = resolved.read_text(encoding="utf-8", errors="replace")
        result.append(
            {
                "path": _relative(resolved, project_root),
                "content": text[:MAX_TASK_TEXT_CHARS],
                "truncated": str(len(text) > MAX_TASK_TEXT_CHARS).lower(),
            }
        )
    return result[:6]


def build_task_context(
    workflow: Dict[str, Any],
    project_root: Path,
    current_node: Optional[Dict[str, Any]] = None,
    prior_reviews: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "original_task": workflow.get("run", {}).get("task"),
        "declared_task_texts": task_text_context(workflow, project_root),
    }
    if current_node is not None:
        context["current_node"] = node_summary(current_node)
        context["previous_nodes"] = previous_node_context(workflow, current_node)
    else:
        context["workflow_summary"] = workflow_summary(workflow)
    if prior_reviews:
        context["prior_review_summaries"] = [
            _compact_review_summary(item) for item in list(prior_reviews)[-12:]
        ]
    return trim_json_context(context, MAX_CONTEXT_CHARS)


def trim_json_context(value: Dict[str, Any], max_chars: int) -> Dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) <= max_chars:
        return value
    copy = dict(value)
    if "declared_task_texts" in copy:
        copy["declared_task_texts"] = [
            {
                "path": item.get("path"),
                "content": str(item.get("content") or "")[:3000],
                "truncated": "true",
            }
            for item in copy["declared_task_texts"][:3]
        ]
    if "workflow_summary" in copy:
        summary = dict(copy["workflow_summary"])
        summary["completed_nodes"] = summary.get("completed_nodes", [])[-12:]
        summary["plan_revisions"] = summary.get("plan_revisions", [])[-6:]
        summary["human_interventions"] = summary.get("human_interventions", [])[-12:]
        copy["workflow_summary"] = summary
    if "prior_review_summaries" in copy:
        copy["prior_review_summaries"] = copy["prior_review_summaries"][-6:]
    if len(json.dumps(copy, ensure_ascii=False)) <= max_chars:
        return copy
    if "previous_nodes" in copy:
        copy["previous_nodes"] = copy["previous_nodes"][-3:]
    if "prior_review_summaries" in copy:
        copy["prior_review_summaries"] = copy["prior_review_summaries"][-3:]
    if "workflow_summary" in copy:
        summary = dict(copy["workflow_summary"])
        summary["completed_nodes"] = summary.get("completed_nodes", [])[-6:]
        summary["plan_revisions"] = summary.get("plan_revisions", [])[-3:]
        summary["human_interventions"] = summary.get("human_interventions", [])[-6:]
        copy["workflow_summary"] = summary
    while len(json.dumps(copy, ensure_ascii=False)) > max_chars:
        reduced = False
        for key in ("prior_review_summaries", "previous_nodes"):
            values = copy.get(key)
            if isinstance(values, list) and len(values) > 1:
                copy[key] = values[1:]
                reduced = True
                break
        if reduced:
            continue
        summary = copy.get("workflow_summary")
        if isinstance(summary, dict):
            for key in ("completed_nodes", "human_interventions", "plan_revisions"):
                values = summary.get(key)
                if isinstance(values, list) and len(values) > 1:
                    summary[key] = values[1:]
                    reduced = True
                    break
        if reduced:
            continue
        texts = copy.get("declared_task_texts")
        if isinstance(texts, list) and texts:
            longest = max(
                texts,
                key=lambda item: len(str(item.get("content") or "")),
            )
            content = str(longest.get("content") or "")
            if len(content) > 500:
                longest["content"] = content[: max(500, len(content) // 2)]
                longest["truncated"] = "true"
                continue
        break
    return copy


def _compact_review_summary(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "node_id": item.get("node_id"),
        "code": [
            {
                "summary": review.get("summary"),
                "critical_logic": review.get("critical_logic", [])[:5],
                "potential_issues": review.get("potential_issues", [])[:3],
            }
            for review in item.get("code", [])[:4]
        ],
        "datasets": [
            {
                "source": review.get("source"),
                "description": review.get("description"),
                "patterns": review.get("patterns", [])[:5],
                "anomalies": review.get("anomalies", [])[:5],
            }
            for review in item.get("datasets", [])[:4]
        ],
        "reports": [
            {
                "core_findings": review.get("core_findings", [])[:5],
                "conclusions": review.get("conclusions", [])[:5],
                "limitations": review.get("limitations", [])[:3],
            }
            for review in item.get("reports", [])[:4]
        ],
        "issues": item.get("issues", [])[:5],
    }


def _relative(path: Path, project_root: Path) -> str:
    try:
        return path.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
