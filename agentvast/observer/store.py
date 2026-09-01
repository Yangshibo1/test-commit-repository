"""Raw-first storage for Claude Code observer sessions."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Union

from agentvast.observer.locking import InterProcessFileLock


OBSERVER_VERSION = "0.1.0"
RAW_FILES = {
    "hook": "raw/hooks.jsonl",
    "otel": "raw/otel.jsonl",
}
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_observations_root() -> Path:
    configured = os.environ.get("AGENTVAST_OBSERVER_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".agentvast" / "observations").resolve()


def observer_registry_directory() -> Path:
    configured = os.environ.get("AGENTVAST_OBSERVER_REGISTRY", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".agentvast" / "observer-registry").resolve()


def register_session_root(session_id: str, root: Union[Path, str]) -> Path:
    registry = observer_registry_directory()
    registry.mkdir(parents=True, exist_ok=True)
    target = registry / (validate_session_id(session_id) + ".json")
    with InterProcessFileLock(registry / ".registry.lock"):
        _write_json_atomic(
            target,
            {
                "session_id": validate_session_id(session_id),
                "storage_root": str(Path(root).expanduser().resolve()),
                "registered_at": utc_now(),
            },
        )
    return target


def registered_session_root(session_id: str) -> Optional[Path]:
    target = observer_registry_directory() / (validate_session_id(session_id) + ".json")
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        root = value.get("storage_root")
        return Path(root).expanduser().resolve() if root else None
    except (OSError, ValueError, TypeError):
        return None


def validate_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value or not SESSION_ID_PATTERN.fullmatch(value):
        raise ValueError("observer session_id contains unsupported characters")
    return value


def session_directory(session_id: str, root: Optional[Union[Path, str]] = None) -> Path:
    return Path(root or default_observations_root()) / validate_session_id(session_id)


def ensure_session_layout(session_id: str, root: Optional[Union[Path, str]] = None) -> Path:
    directory = session_directory(session_id, root)
    for relative in (
        "raw/api",
        "derived",
        "diagnostics",
        "transcript",
    ):
        (directory / relative).mkdir(parents=True, exist_ok=True)
    return directory


def _manifest_template(session_id: str) -> Dict[str, Any]:
    return {
        "observer_version": OBSERVER_VERSION,
        "schema_version": "1.0",
        "session_id": session_id,
        "started_at": None,
        "ended_at": None,
        "claude_code_version": None,
        "cwd": None,
        "transcript_source_path": None,
        "sources": {
            "hooks": False,
            "otel": False,
            "transcript": False,
            "raw_api": False,
        },
        "files": {
            "hooks": "raw/hooks.jsonl",
            "otel": "raw/otel.jsonl",
            "transcript": "raw/transcript.jsonl",
            "transcript_snapshot": "transcript/transcript.jsonl",
            "api": "raw/api/",
            "canonical_events": "derived/canonical_events.jsonl",
            "observer_trace": "derived/observer_trace.json",
            "semantic_workflow": "derived/semantic_workflow.json",
            "semantic_workflow_versions": "derived/semantic_workflows/",
            "semantic_stages": "derived/semantic_stages/",
            "semantic_reviews": "derived/semantic_reviews.jsonl",
        },
        "collector": {
            "otel_decode_available": None,
            "otel_endpoint": None,
        },
    }


def _merge(target: Dict[str, Any], update: Mapping[str, Any]) -> Dict[str, Any]:
    for key, value in update.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
    return target


def read_manifest(session_id: str, root: Optional[Union[Path, str]] = None) -> Dict[str, Any]:
    directory = ensure_session_layout(session_id, root)
    path = directory / "manifest.json"
    if not path.exists():
        return _manifest_template(validate_session_id(session_id))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    return _merge(_manifest_template(validate_session_id(session_id)), value)


def _write_json_atomic(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(str(temporary), str(path))


def update_manifest(
    session_id: str,
    update: Mapping[str, Any],
    root: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    directory = ensure_session_layout(session_id, root)
    with InterProcessFileLock(directory / ".observer.lock"):
        value = read_manifest(session_id, root)
        _merge(value, update)
        _write_json_atomic(directory / "manifest.json", value)
    return value


def create_session(
    session_id: str,
    cwd: Union[Path, str],
    root: Optional[Union[Path, str]] = None,
    claude_code_version: Optional[str] = None,
    raw_api: bool = False,
) -> Dict[str, Any]:
    ensure_session_layout(session_id, root)
    return update_manifest(
        session_id,
        {
            "started_at": utc_now(),
            "cwd": str(Path(cwd).resolve()),
            "claude_code_version": claude_code_version,
            "sources": {"raw_api": bool(raw_api)},
        },
        root,
    )


def append_raw_event(
    session_id: str,
    source: str,
    raw_payload: Any,
    root: Optional[Union[Path, str]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    if source not in RAW_FILES:
        raise ValueError("unsupported observer source: {0}".format(source))
    directory = ensure_session_layout(session_id, root)
    sequence_path = directory / "diagnostics" / "observer_sequence.txt"
    with InterProcessFileLock(directory / ".observer.lock"):
        try:
            previous = int(sequence_path.read_text(encoding="ascii").strip() or "0")
        except (OSError, ValueError):
            previous = 0
        sequence = previous + 1
        event = {
            "observer_event_id": str(uuid.uuid4()),
            "observer_received_at": utc_now(),
            "observer_monotonic_ns": time.monotonic_ns(),
            "observer_sequence": sequence,
            "source": source,
            "schema_version": "1.0",
            "observer_metadata": dict(metadata or {}),
            "raw_payload": raw_payload,
        }
        target = directory / RAW_FILES[source]
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        sequence_path.write_text(str(sequence), encoding="ascii")
    update_manifest(
        session_id,
        {"sources": {"hooks" if source == "hook" else "otel": True}},
        root,
    )
    return event


def iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            text = raw_line.rstrip("\r\n")
            if not text:
                continue
            try:
                value = json.loads(text)
            except ValueError:
                value = {
                    "line_number": line_number,
                    "parsed": False,
                    "raw_line": text,
                }
            yield value


def write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex[:8])
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")
    os.replace(str(temporary), str(path))


def record_observer_error(
    error: BaseException,
    root: Optional[Union[Path, str]] = None,
    context: Optional[Mapping[str, Any]] = None,
) -> None:
    """Best-effort diagnostics that never escape into Claude's execution."""

    try:
        directory = Path(root or default_observations_root())
        directory.mkdir(parents=True, exist_ok=True)
        with InterProcessFileLock(directory / ".observer-errors.lock", timeout=0.5):
            with (directory / "observer_errors.jsonl").open(
                "a", encoding="utf-8", newline="\n"
            ) as stream:
                stream.write(
                    json.dumps(
                        {
                            "observed_at": utc_now(),
                            "pid": os.getpid(),
                            "error_type": type(error).__name__,
                            "error": str(error),
                            "context": dict(context or {}),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except BaseException:
        pass
