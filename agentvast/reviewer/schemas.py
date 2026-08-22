"""Small validation helpers for Reviewer model outputs."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


PROCESSOR_VERSION = "0.1.0"
ASSET_SCHEMA_VERSION = "trace-assets/0.1"
ALLOWED_ANALYSIS_OPERATIONS = {
    "count_by",
    "numeric_summary",
    "time_range",
    "top_n",
    "timeline_events",
}
ALLOWED_CHART_TYPES = {
    "table",
    "bar",
    "line",
    "scatter",
    "timeline",
    "network",
    "distribution",
}
ANSWER_STATUSES = {"answered", "partial", "unanswered", "not_applicable"}
DEPTH_STATUSES = {"sufficient", "partial", "insufficient", "not_applicable"}


class ReviewValidationError(ValueError):
    """Raised when a Reviewer result cannot be safely materialized."""


def require_object(value: Any, label: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ReviewValidationError("{0} must be a JSON object".format(label))
    return value


def list_of_objects(value: Any, label: str) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ReviewValidationError("{0} must be an array of objects".format(label))
    return value


def string_list(value: Any, label: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReviewValidationError("{0} must be an array of strings".format(label))
    return value


def keep_allowed(value: Any, allowed: Iterable[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in set(allowed) else default


def validate_code_review(value: Any) -> Dict[str, Any]:
    data = require_object(value, "code review")
    return {
        "summary": str(data.get("summary") or "").strip(),
        "logic_steps": list_of_objects(data.get("logic_steps"), "logic_steps"),
        "data_flow": require_object(data.get("data_flow") or {}, "data_flow"),
        "critical_logic": string_list(data.get("critical_logic"), "critical_logic"),
        "implementation_notes": string_list(
            data.get("implementation_notes"), "implementation_notes"
        ),
        "potential_issues": list_of_objects(
            data.get("potential_issues"), "potential_issues"
        ),
    }


def validate_analysis_requests(value: Any) -> List[Dict[str, Any]]:
    data = require_object(value, "dataset analysis plan")
    requests: List[Dict[str, Any]] = []
    for item in list_of_objects(data.get("analysis_requests"), "analysis_requests")[:8]:
        operation = str(item.get("operation") or "")
        field = str(item.get("field") or "").strip()
        if operation not in ALLOWED_ANALYSIS_OPERATIONS or not field:
            continue
        requests.append(
            {
                "operation": operation,
                "field": field,
                "limit": max(1, min(int(item.get("limit") or 20), 100)),
                "fields": [
                    str(value)
                    for value in item.get("fields", [])
                    if isinstance(value, str)
                ][:8],
            }
        )
    return requests


def validate_dataset_review(value: Any, available_fields: Iterable[str]) -> Dict[str, Any]:
    data = require_object(value, "dataset review")
    fields = set(available_fields)
    visualizations: List[Dict[str, Any]] = []
    for index, item in enumerate(
        list_of_objects(data.get("visualizations"), "visualizations")[:4], 1
    ):
        chart_type = keep_allowed(item.get("chart_type"), ALLOWED_CHART_TYPES, "table")
        encoding = require_object(item.get("encoding") or {}, "visualization.encoding")
        clean_encoding = {
            key: str(value)
            for key, value in encoding.items()
            if key in {"x", "y", "category", "time", "event", "detail", "source", "target"}
            and isinstance(value, str)
            and value in fields
        }
        if chart_type != "table" and not clean_encoding:
            continue
        visualizations.append(
            {
                "visualization_id": "chart-{0:03d}".format(index),
                "chart_type": chart_type,
                "title": str(item.get("title") or "Data view").strip(),
                "purpose": str(item.get("purpose") or "").strip(),
                "encoding": clean_encoding,
            }
        )
    return {
        "dataset_description": str(data.get("dataset_description") or "").strip(),
        "role_in_analysis": str(data.get("role_in_analysis") or "").strip(),
        "key_patterns": list_of_objects(data.get("key_patterns"), "key_patterns"),
        "anomalies": list_of_objects(data.get("anomalies"), "anomalies"),
        "quality_notes": string_list(data.get("quality_notes"), "quality_notes"),
        "visualizations": visualizations,
    }


def validate_report_review(value: Any) -> Dict[str, Any]:
    data = require_object(value, "report review")
    return {
        "core_findings": list_of_objects(data.get("core_findings"), "core_findings"),
        "conclusions": string_list(data.get("conclusions"), "conclusions"),
        "limitations": string_list(data.get("limitations"), "limitations"),
        "unresolved_questions": string_list(
            data.get("unresolved_questions"), "unresolved_questions"
        ),
        "relevant_question_aspects": string_list(
            data.get("relevant_question_aspects"), "relevant_question_aspects"
        ),
    }


def validate_answer_review(value: Any) -> Dict[str, Any]:
    data = require_object(value, "Run answer review")
    aspects = list_of_objects(data.get("question_aspects"), "question_aspects")
    coverage = list_of_objects(data.get("answer_coverage"), "answer_coverage")
    for item in coverage:
        item["status"] = keep_allowed(item.get("status"), ANSWER_STATUSES, "unanswered")
    depth = list_of_objects(data.get("analysis_depth"), "analysis_depth")
    for item in depth:
        item["status"] = keep_allowed(item.get("status"), DEPTH_STATUSES, "insufficient")
    return {
        "question_aspects": aspects,
        "answer_coverage": coverage,
        "analysis_depth": depth,
        "analysis_gaps": list_of_objects(data.get("analysis_gaps"), "analysis_gaps"),
        "next_analysis_directions": list_of_objects(
            data.get("next_analysis_directions"), "next_analysis_directions"
        ),
    }
