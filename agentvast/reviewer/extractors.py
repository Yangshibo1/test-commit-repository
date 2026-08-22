"""Deterministic code, dataset, and report extraction for Reviewer prompts."""

from __future__ import annotations

import ast
import csv
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MAX_CODE_CHARS = 40_000
MAX_REPORT_CHARS = 30_000
MAX_PROFILE_ROWS = 50_000
MAX_UNIQUE_VALUES = 5_000


def extract_code(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".ipynb":
        try:
            notebook = json.loads(text)
            text = "\n\n".join(
                "".join(cell.get("source", []))
                for cell in notebook.get("cells", [])
                if isinstance(cell, dict) and cell.get("cell_type") == "code"
            )
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    result: Dict[str, Any] = {
        "language": _code_language(path),
        "line_count": len(text.splitlines()),
        "source": text[:MAX_CODE_CHARS],
        "source_truncated": len(text) > MAX_CODE_CHARS,
        "imports": [],
        "functions": [],
        "classes": [],
        "constants": {},
    }
    if path.suffix.lower() != ".py":
        return result
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        result["parse_error"] = str(error)
        return result
    imports: List[str] = []
    functions: List[Dict[str, Any]] = []
    classes: List[Dict[str, Any]] = []
    constants: Dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(
                {
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "parameters": [item.arg for item in node.args.args],
                    "docstring": (ast.get_docstring(node) or "")[:500],
                }
            )
        elif isinstance(node, ast.ClassDef):
            classes.append(
                {
                    "name": node.name,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                }
            )
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id.isupper()
        ):
            value = _literal_value(node.value)
            if value is not None:
                constants[node.targets[0].id] = value
    result.update(
        {
            "imports": sorted(set(filter(None, imports))),
            "functions": sorted(functions, key=lambda item: item["line_start"]),
            "classes": sorted(classes, key=lambda item: item["line_start"]),
            "constants": constants,
        }
    )
    return result


def profile_dataset(path: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    rows, metadata = _load_rows(path)
    fields = _field_order(rows)
    columns: List[Dict[str, Any]] = []
    for field in fields:
        values = [row.get(field) for row in rows]
        present = [value for value in values if value not in (None, "")]
        inferred = _infer_type(present)
        column: Dict[str, Any] = {
            "name": field,
            "inferred_type": inferred,
            "missing_count": len(values) - len(present),
            "unique_count": _unique_count(present),
        }
        numbers = [_as_number(value) for value in present]
        numeric = [value for value in numbers if value is not None]
        if inferred == "number" and numeric:
            column["numeric_summary"] = {
                "min": min(numeric),
                "max": max(numeric),
                "mean": mean(numeric),
            }
        if inferred in {"string", "boolean"} and present:
            column["top_values"] = [
                {"value": key[:500], "count": count}
                for key, count in Counter(str(value) for value in present).most_common(10)
            ]
        if inferred == "datetime" and present:
            ordered = sorted(str(value) for value in present)
            column["time_range"] = {"min": ordered[0], "max": ordered[-1]}
        columns.append(column)
    profile = {
        **metadata,
        "row_count_profiled": len(rows),
        "column_count": len(fields),
        "columns": columns,
        "sample": _representative_sample(rows),
    }
    return profile, rows


def extract_report(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    parsed: Any = None
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    content: Any = parsed if parsed is not None else text[:MAX_REPORT_CHARS]
    content_truncated = parsed is None and len(text) > MAX_REPORT_CHARS
    if parsed is not None and len(text) > MAX_REPORT_CHARS:
        content = _safe_value(parsed)
        content_truncated = True
    return {
        "format": path.suffix.lower().lstrip("."),
        "content": content,
        "content_truncated": content_truncated,
    }


def execute_analysis_requests(
    rows: Sequence[Dict[str, Any]], requests: Iterable[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    fields = set(_field_order(rows))
    results: List[Dict[str, Any]] = []
    for request in requests:
        operation = request["operation"]
        field = request["field"]
        limit = int(request.get("limit") or 20)
        if field not in fields:
            results.append({"request": request, "error": "field does not exist"})
            continue
        values = [row.get(field) for row in rows if row.get(field) not in (None, "")]
        if operation in {"count_by", "top_n"}:
            data = [
                {"value": key[:500], "count": count}
                for key, count in Counter(str(value) for value in values).most_common(limit)
            ]
        elif operation == "numeric_summary":
            numeric = [value for value in (_as_number(item) for item in values) if value is not None]
            data = (
                {
                    "count": len(numeric),
                    "min": min(numeric),
                    "max": max(numeric),
                    "mean": mean(numeric),
                }
                if numeric
                else {"count": 0}
            )
        elif operation == "time_range":
            ordered = sorted(str(value) for value in values)
            data = {"min": ordered[0], "max": ordered[-1]} if ordered else {}
        elif operation == "timeline_events":
            selected_fields = [field] + [
                value for value in request.get("fields", []) if value in fields and value != field
            ]
            data = sorted(
                ({key: row.get(key) for key in selected_fields} for row in rows),
                key=lambda row: str(row.get(field) or ""),
            )[:limit]
        else:
            data = None
        results.append({"request": request, "result": data})
    return results


def materialize_chart_data(
    rows: Sequence[Dict[str, Any]], visualization: Dict[str, Any]
) -> Dict[str, Any]:
    chart_type = visualization["chart_type"]
    encoding = visualization.get("encoding", {})
    if chart_type == "table":
        return {"rows": [_safe_value(dict(row)) for row in rows[:100]]}
    if chart_type in {"bar", "distribution"}:
        field = encoding.get("x") or encoding.get("category") or encoding.get("y")
        counts = Counter(str(row.get(field)) for row in rows if row.get(field) not in (None, ""))
        return {
            "field": field,
            "items": [
                {"value": key, "count": count} for key, count in counts.most_common(30)
            ],
        }
    if chart_type in {"line", "scatter"}:
        keys = [encoding.get("x"), encoding.get("y"), encoding.get("category")]
        keys = [key for key in keys if key]
        return {
            "rows": [
                {key: _safe_value(row.get(key)) for key in keys}
                for row in rows[:1000]
            ]
        }
    if chart_type == "timeline":
        keys = [
            encoding.get("time"),
            encoding.get("category"),
            encoding.get("event"),
            encoding.get("detail"),
        ]
        keys = [key for key in keys if key]
        time_key = encoding.get("time")
        selected = [
            {key: _safe_value(row.get(key)) for key in keys} for row in rows
        ]
        if time_key:
            selected.sort(key=lambda row: str(row.get(time_key) or ""))
        return {"rows": selected[:1000]}
    if chart_type == "network":
        source = encoding.get("source")
        target = encoding.get("target")
        counts = Counter(
            (str(row.get(source)), str(row.get(target)))
            for row in rows
            if row.get(source) not in (None, "") and row.get(target) not in (None, "")
        )
        return {
            "edges": [
                {"source": pair[0], "target": pair[1], "count": count}
                for pair, count in counts.most_common(500)
            ]
        }
    return {"rows": [_safe_value(dict(row)) for row in rows[:100]]}


def _load_rows(path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        rows: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                if index >= MAX_PROFILE_ROWS:
                    break
                rows.append(dict(row))
        return rows, {"format": "csv", "profile_truncated": len(rows) >= MAX_PROFILE_ROWS}
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            rows = []
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    if index >= MAX_PROFILE_ROWS:
                        break
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rows.append(value if isinstance(value, dict) else {"value": value})
            return rows, {"format": "jsonl", "profile_truncated": len(rows) >= MAX_PROFILE_ROWS}
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        rows, location = _rows_from_json(data)
        return rows[:MAX_PROFILE_ROWS], {
            "format": "json",
            "record_path": location,
            "profile_truncated": len(rows) > MAX_PROFILE_ROWS,
            "top_level_type": type(data).__name__,
        }
    raise ValueError("unsupported dataset format: {0}".format(suffix))


def _rows_from_json(data: Any) -> Tuple[List[Dict[str, Any]], str]:
    if isinstance(data, list):
        return [item if isinstance(item, dict) else {"value": item} for item in data], "$"
    if isinstance(data, dict):
        candidates = [
            (key, value)
            for key, value in data.items()
            if isinstance(value, list) and value
        ]
        if candidates:
            key, values = max(candidates, key=lambda item: len(item[1]))
            return [item if isinstance(item, dict) else {"value": item} for item in values], "$.{0}".format(key)
        return [data], "$"
    return [{"value": data}], "$"


def _field_order(rows: Sequence[Dict[str, Any]]) -> List[str]:
    result: List[str] = []
    seen = set()
    for row in rows[:1000]:
        for key in row:
            if key not in seen:
                seen.add(key)
                result.append(str(key))
    return result


def _representative_sample(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    indexes = sorted(set([0, len(rows) // 2, len(rows) - 1]))
    return [_safe_value(dict(rows[index])) for index in indexes]


def _infer_type(values: Sequence[Any]) -> str:
    if not values:
        return "unknown"
    if all(isinstance(value, bool) or str(value).lower() in {"true", "false"} for value in values[:100]):
        return "boolean"
    if all(_as_number(value) is not None for value in values[:100]):
        return "number"
    if sum(1 for value in values[:100] if _is_datetime(value)) >= max(1, int(len(values[:100]) * 0.8)):
        return "datetime"
    if any(isinstance(value, (dict, list)) for value in values[:100]):
        return "object"
    return "string"


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _is_datetime(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 8:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _unique_count(values: Sequence[Any]) -> int:
    unique = set()
    for value in values:
        try:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            key = str(value)
        unique.add(key)
        if len(unique) >= MAX_UNIQUE_VALUES:
            return MAX_UNIQUE_VALUES
    return len(unique)


def _literal_value(node: ast.AST) -> Any:
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _code_language(path: Path) -> str:
    return {
        ".py": "python",
        ".r": "r",
        ".sql": "sql",
        ".ipynb": "notebook",
    }.get(path.suffix.lower(), path.suffix.lower().lstrip(".") or "unknown")


def _safe_value(value: Any, depth: int = 0) -> Any:
    if depth >= 4:
        return "<nested value omitted>"
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, dict):
        return {
            str(key)[:200]: _safe_value(item, depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, list):
        return [_safe_value(item, depth + 1) for item in value[:30]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1000]
