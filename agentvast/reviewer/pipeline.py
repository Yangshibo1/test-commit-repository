"""Short-lived Reviewer task orchestration and asset materialization."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agentvast.reviewer.context import build_task_context, load_workflow
from agentvast.reviewer.extractors import (
    execute_analysis_requests,
    extract_code,
    extract_report,
    materialize_chart_data,
    profile_dataset,
)
from agentvast.reviewer.prompts import (
    answer_review_prompt,
    code_prompt,
    dataset_plan_prompt,
    dataset_review_prompt,
    report_prompt,
)
from agentvast.reviewer.provider import (
    OpenAICompatibleReviewerProvider,
    ReviewerConfig,
    ReviewerProviderError,
)
from agentvast.reviewer.schemas import (
    ASSET_SCHEMA_VERSION,
    PROCESSOR_VERSION,
    ReviewValidationError,
    validate_analysis_requests,
    validate_answer_review,
    validate_code_review,
    validate_dataset_review,
    validate_report_review,
)


SUPPORTED_CODE = {".py", ".ipynb", ".r", ".sql"}
SUPPORTED_DATA = {".csv", ".json", ".jsonl"}
SUPPORTED_REPORT = {".json", ".txt", ".md"}


class ReviewerPipelineError(RuntimeError):
    """Raised when a Run cannot be reviewed safely."""


def review_run(
    project_root: Path,
    workflow_path: Path,
    force: bool = False,
    provider: Optional[OpenAICompatibleReviewerProvider] = None,
) -> Dict[str, Any]:
    project = project_root.resolve()
    workflow_file = workflow_path.resolve()
    workflow = load_workflow(workflow_file)
    run = workflow["run"]
    if run.get("status") != "completed":
        raise ReviewerPipelineError("only a completed Run can be reviewed")
    result_root = _resolve_project_path(project, str(run.get("result_root") or ""))
    workflow_sha = _sha256(workflow_file)
    assets_root = result_root / "trace_assets"
    assets_root.mkdir(parents=True, exist_ok=True)

    current = _read_json(assets_root / "current.json")
    if not force and current:
        manifest_path = assets_root / str(current.get("manifest_path") or "")
        manifest = _read_json(manifest_path)
        if (
            manifest
            and manifest.get("source_workflow", {}).get("sha256") == workflow_sha
            and manifest.get("review", {}).get("processor_version") == PROCESSOR_VERSION
            and manifest.get("review", {}).get("status") == "ready"
        ):
            return manifest

    config = ReviewerConfig.from_env()
    reviewer = provider or OpenAICompatibleReviewerProvider(config)
    review_id = _next_review_id(assets_root)
    staging = assets_root / (".{0}-{1}.tmp".format(review_id, uuid.uuid4().hex[:8]))
    final_root = assets_root / review_id
    staging.mkdir(parents=True, exist_ok=False)
    (staging / "nodes").mkdir()
    (staging / "chart_data").mkdir()
    status_path = assets_root / "review_status.json"
    status = {
        "run_id": run.get("run_id"),
        "review_id": review_id,
        "status": "running",
        "processor_version": PROCESSOR_VERSION,
        "model": config.model,
        "started_at": _utc_now(),
        "completed_nodes": 0,
        "total_nodes": len(workflow.get("nodes", [])),
        "error": None,
    }
    _write_json(status_path, status)

    node_manifests: List[Dict[str, Any]] = []
    review_summaries: List[Dict[str, Any]] = []
    all_node_assets: List[Dict[str, Any]] = []
    try:
        for node in sorted(
            workflow.get("nodes", []), key=lambda item: int(item.get("sequence") or 0)
        ):
            node_asset, summary = _review_node(
                project,
                result_root,
                workflow,
                node,
                reviewer,
                staging,
                review_summaries,
            )
            node_path = staging / "nodes" / (str(node["node_id"]) + ".json")
            _write_json(node_path, node_asset)
            review_summaries.append(summary)
            all_node_assets.append(node_asset)
            node_manifests.append(
                {
                    "node_id": node["node_id"],
                    "status": "ready" if not _blocking_issues(node_asset) else "partial",
                    "asset_path": "nodes/{0}.json".format(node["node_id"]),
                    "code_review_count": len(node_asset["code_reviews"]),
                    "dataset_review_count": len(node_asset["dataset_reviews"]),
                    "report_review_count": len(node_asset["report_reviews"]),
                    "visualization_count": sum(
                        len(item.get("visualizations", []))
                        for item in node_asset["dataset_reviews"]
                    ),
                    "issue_count": len(node_asset["review_issues"]),
                }
            )
            status["completed_nodes"] += 1
            _write_json(status_path, status)

        answer_context = build_task_context(
            workflow, project, prior_reviews=review_summaries
        )
        synthesis_input = _synthesis_input(all_node_assets)
        raw_answer = reviewer.review(
            answer_review_prompt(answer_context, synthesis_input),
            "review_run_answer",
        )
        answer_review = validate_answer_review(raw_answer)
        _sanitize_answer_references(answer_review, all_node_assets)
        answer_review_document = {
            "schema_version": "answer-review/0.1",
            "run_id": run["run_id"],
            "source_workflow_sha256": workflow_sha,
            "review": answer_review,
            "generated_by": _generated_by(config, "review_run_answer"),
        }
        _write_json(staging / "answer_review.json", answer_review_document)

        manifest = {
            "schema_version": ASSET_SCHEMA_VERSION,
            "run_id": run["run_id"],
            "source_workflow": {
                "path": _relative(workflow_file, project),
                "sha256": workflow_sha,
            },
            "review": {
                "review_id": review_id,
                "status": "ready",
                "processor_version": PROCESSOR_VERSION,
                "prompt_version": "0.1",
                "model": config.model,
                "created_at": _utc_now(),
            },
            "answer_review_path": "answer_review.json",
            "nodes": node_manifests,
        }
        _write_json(staging / "manifest.json", manifest)
        staging.replace(final_root)
        _write_json(
            assets_root / "current.json",
            {
                "review_id": review_id,
                "manifest_path": "{0}/manifest.json".format(review_id),
                "updated_at": _utc_now(),
            },
        )
        status.update(
            {
                "status": "ready",
                "completed_at": _utc_now(),
                "manifest_path": str(final_root / "manifest.json"),
            }
        )
        _write_json(status_path, status)
        return manifest
    except Exception as error:
        status.update(
            {
                "status": "failed",
                "completed_at": _utc_now(),
                "error": str(error),
            }
        )
        _write_json(status_path, status)
        failed_root = assets_root / (review_id + "-failed")
        if staging.exists() and not failed_root.exists():
            staging.replace(failed_root)
        raise


def review_status(result_root: Path) -> Dict[str, Any]:
    assets_root = result_root.resolve() / "trace_assets"
    status = _read_json(assets_root / "review_status.json")
    if status:
        return status
    current = _read_json(assets_root / "current.json")
    if current:
        return {"status": "ready", **current}
    return {"status": "not_started"}


def load_review_bundle(result_root: Path) -> Dict[str, Any]:
    """Load the current derived assets for the Web record view."""

    assets_root = result_root.resolve() / "trace_assets"
    current = _read_json(assets_root / "current.json")
    if not current:
        raise ReviewerPipelineError("this Run has no ready Reviewer assets")
    manifest_path = _safe_asset_path(
        assets_root, str(current.get("manifest_path") or "")
    )
    manifest = _read_json(manifest_path)
    if not manifest or manifest.get("review", {}).get("status") != "ready":
        raise ReviewerPipelineError("the current Reviewer manifest is not ready")
    revision_root = manifest_path.parent
    answer_path = _safe_asset_path(
        revision_root, str(manifest.get("answer_review_path") or "")
    )
    node_documents = []
    for item in manifest.get("nodes", []):
        relative = item.get("asset_path")
        if isinstance(relative, str):
            document = _read_json(_safe_asset_path(revision_root, relative))
            if document:
                node_documents.append(document)
    return {
        "current": current,
        "manifest": manifest,
        "answer_review": _read_json(answer_path),
        "nodes": node_documents,
    }


def reviewer_is_configured() -> bool:
    return ReviewerConfig.from_env().configured()


def _review_node(
    project: Path,
    result_root: Path,
    workflow: Dict[str, Any],
    node: Dict[str, Any],
    reviewer: OpenAICompatibleReviewerProvider,
    staging: Path,
    prior_reviews: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    context = build_task_context(workflow, project, node, prior_reviews)
    document: Dict[str, Any] = {
        "schema_version": "node-reviews/0.1",
        "run_id": workflow["run"]["run_id"],
        "node_id": node["node_id"],
        "source_node_digest": _digest_json(node),
        "code_reviews": [],
        "dataset_reviews": [],
        "report_reviews": [],
        "review_issues": [],
    }
    for output in node.get("outputs", []):
        path_value = output.get("path")
        if not isinstance(path_value, str):
            continue
        try:
            source = _resolve_project_path(project, path_value)
        except ReviewerPipelineError as error:
            document["review_issues"].append(
                _issue("unsafe_path", str(error), path_value, blocking=True)
            )
            continue
        expected_sha = str(output.get("sha256") or "")
        if not source.is_file():
            document["review_issues"].append(
                _issue("missing_artifact", "记录的产物文件不存在", path_value, blocking=True)
            )
            continue
        actual_sha = _sha256(source)
        if expected_sha and actual_sha != expected_sha:
            document["review_issues"].append(
                _issue(
                    "hash_mismatch",
                    "文件当前SHA-256与Node完成时记录不一致，Reviewer没有处理该版本",
                    path_value,
                    blocking=True,
                )
            )
            continue
        source_ref = {"path": _relative(source, project), "sha256": actual_sha}
        category = _artifact_category(source, result_root)
        suffix = source.suffix.lower()
        try:
            if category == "code" and suffix in SUPPORTED_CODE:
                extracted = extract_code(source)
                raw = reviewer.review(code_prompt(context, extracted), "review_code")
                document["code_reviews"].append(
                    {
                        "asset_type": "code_review",
                        "source": source_ref,
                        "extracted": {key: value for key, value in extracted.items() if key != "source"},
                        "review": validate_code_review(raw),
                        "generated_by": _generated_by(reviewer.config, "review_code"),
                    }
                )
            elif category == "data" and suffix in SUPPORTED_DATA:
                profile, rows = profile_dataset(source)
                raw_plan = reviewer.review(
                    dataset_plan_prompt(context, profile), "review_dataset_plan"
                )
                requests = validate_analysis_requests(raw_plan)
                computed = execute_analysis_requests(rows, requests)
                raw_review = reviewer.review(
                    dataset_review_prompt(context, profile, computed), "review_dataset"
                )
                fields = [item["name"] for item in profile.get("columns", [])]
                review = validate_dataset_review(raw_review, fields)
                asset_index = len(document["dataset_reviews"]) + 1
                for chart_index, chart in enumerate(review["visualizations"], 1):
                    visualization_id = "{0}-data-{1:03d}-chart-{2:03d}".format(
                        node["node_id"], asset_index, chart_index
                    )
                    chart["visualization_id"] = visualization_id
                    chart_data = {
                        "schema_version": "chart-data/0.1",
                        "visualization_id": visualization_id,
                        "source": source_ref,
                        "data": materialize_chart_data(rows, chart),
                    }
                    chart_path = staging / "chart_data" / (visualization_id + ".json")
                    _write_json(chart_path, chart_data)
                    chart["data_path"] = "chart_data/{0}.json".format(visualization_id)
                    chart["data_sha256"] = _sha256(chart_path)
                visualizations = review.pop("visualizations")
                document["dataset_reviews"].append(
                    {
                        "asset_type": "dataset_review",
                        "source": source_ref,
                        "profile": profile,
                        "requested_computations": computed,
                        "review": review,
                        "visualizations": visualizations,
                        "generated_by": _generated_by(reviewer.config, "review_dataset"),
                    }
                )
            elif category == "report" and suffix in SUPPORTED_REPORT:
                extracted_report = extract_report(source)
                raw = reviewer.review(
                    report_prompt(context, extracted_report), "review_report"
                )
                document["report_reviews"].append(
                    {
                        "asset_type": "report_review",
                        "source": source_ref,
                        "review": validate_report_review(raw),
                        "generated_by": _generated_by(reviewer.config, "review_report"),
                    }
                )
        except (ValueError, ReviewValidationError, ReviewerProviderError) as error:
            document["review_issues"].append(
                _issue(
                    "review_failed",
                    "Reviewer处理失败：{0}".format(error),
                    path_value,
                    blocking=False,
                )
            )
    summary = {
        "node_id": node["node_id"],
        "code": [item["review"] for item in document["code_reviews"]],
        "datasets": [
            {
                "source": item["source"]["path"],
                "description": item["review"].get("dataset_description"),
                "patterns": item["review"].get("key_patterns", []),
                "anomalies": item["review"].get("anomalies", []),
            }
            for item in document["dataset_reviews"]
        ],
        "reports": [item["review"] for item in document["report_reviews"]],
        "issues": document["review_issues"],
    }
    return document, summary


def _synthesis_input(node_assets: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "node_reviews": [
            {
                "node_id": item["node_id"],
                "code_reviews": [review["review"] for review in item["code_reviews"]],
                "dataset_reviews": [
                    {
                        "source": review["source"],
                        "review": review["review"],
                        "visualizations": review["visualizations"],
                    }
                    for review in item["dataset_reviews"]
                ],
                "report_reviews": [review["review"] for review in item["report_reviews"]],
                "review_issues": item["review_issues"],
            }
            for item in node_assets
        ]
    }


def _sanitize_answer_references(
    answer_review: Dict[str, Any], node_assets: List[Dict[str, Any]]
) -> None:
    valid_nodes = {str(item.get("node_id")) for item in node_assets}
    valid_assets = set()
    for node in node_assets:
        for category in ("code_reviews", "dataset_reviews", "report_reviews"):
            for item in node.get(category, []):
                path = (item.get("source") or {}).get("path")
                if isinstance(path, str):
                    valid_assets.add(path)
    aspect_ids = {
        str(item.get("aspect_id"))
        for item in answer_review.get("question_aspects", [])
        if item.get("aspect_id")
    }
    for item in answer_review.get("answer_coverage", []):
        item["supporting_nodes"] = [
            value
            for value in item.get("supporting_nodes", [])
            if isinstance(value, str) and value in valid_nodes
        ]
        item["supporting_assets"] = [
            value
            for value in item.get("supporting_assets", [])
            if isinstance(value, str) and value in valid_assets
        ]
        if item.get("aspect_id") not in aspect_ids:
            item["aspect_id"] = None
    for item in answer_review.get("analysis_gaps", []):
        item["related_aspects"] = [
            value
            for value in item.get("related_aspects", [])
            if isinstance(value, str) and value in aspect_ids
        ]


def _artifact_category(path: Path, result_root: Path) -> Optional[str]:
    try:
        relative = path.resolve().relative_to(result_root.resolve())
    except ValueError:
        return None
    return relative.parts[0] if relative.parts and relative.parts[0] in {"code", "data", "report", "visualization"} else None


def _resolve_project_path(project: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project / path
    resolved = path.resolve()
    try:
        resolved.relative_to(project.resolve())
    except ValueError as error:
        raise ReviewerPipelineError(
            "Reviewer source is outside the project: {0}".format(raw_path)
        ) from error
    return resolved


def _safe_asset_path(root: Path, raw_path: str) -> Path:
    if not raw_path:
        raise ReviewerPipelineError("Reviewer asset path is empty")
    path = (root / raw_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ReviewerPipelineError(
            "Reviewer asset path escapes trace_assets: {0}".format(raw_path)
        ) from error
    return path


def _issue(
    issue_type: str, description: str, path: str, blocking: bool
) -> Dict[str, Any]:
    return {
        "type": issue_type,
        "description": description,
        "source_path": path,
        "blocks_asset_generation": blocking,
    }


def _blocking_issues(document: Dict[str, Any]) -> bool:
    return any(item.get("blocks_asset_generation") for item in document["review_issues"])


def _generated_by(config: ReviewerConfig, task_mode: str) -> Dict[str, Any]:
    return {
        "processor": "agentvast-reviewer",
        "processor_version": PROCESSOR_VERSION,
        "prompt_version": "0.1",
        "task_mode": task_mode,
        "model": config.model,
        "generated_at": _utc_now(),
    }


def _next_review_id(assets_root: Path) -> str:
    numbers: List[int] = []
    for path in assets_root.glob("review-*"):
        name = path.name.split("-failed", 1)[0]
        try:
            numbers.append(int(name.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return "review-{0:03d}".format((max(numbers) if numbers else 0) + 1)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _relative(path: Path, project: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
