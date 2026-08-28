"""Silent Claude Code hook handler for passive observation."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

from agentvast.observer.store import (
    append_raw_event,
    record_observer_error,
    registered_session_root,
    update_manifest,
)


def _record_internal_error(error: BaseException, raw_text: str = "") -> None:
    registered_root = None
    try:
        payload = json.loads(raw_text) if raw_text else {}
        session_id = payload.get("session_id") if isinstance(payload, dict) else None
        if session_id:
            registered_root = registered_session_root(str(session_id))
    except (ValueError, TypeError):
        pass
    record_observer_error(
        error,
        os.environ.get("AGENTVAST_OBSERVER_ROOT") or registered_root or None,
        {"collector": "hook", "raw_stdin": raw_text},
    )


def collect_event(payload: Any, raw_text: str = "") -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        payload = {"_observer_unparsed_payload": payload, "_raw_stdin": raw_text}
    session_id = str(
        payload.get("session_id")
        or os.environ.get("AGENTVAST_OBSERVER_SESSION_ID")
        or ""
    ).strip()
    if not session_id:
        raise ValueError("Claude hook payload has no session_id")
    root = (
        os.environ.get("AGENTVAST_OBSERVER_ROOT")
        or registered_session_root(session_id)
        or None
    )
    event = append_raw_event(
        session_id,
        "hook",
        payload,
        root,
        metadata={
            "collector": "agentvast.observer.hook_collector",
            "collector_pid": os.getpid(),
            "hook_event_name": payload.get("hook_event_name"),
        },
    )
    transcript_path = payload.get("transcript_path")
    manifest_update: Dict[str, Any] = {
        key: value
        for key, value in {
            "cwd": payload.get("cwd"),
            "transcript_source_path": transcript_path,
        }.items()
        if value is not None
    }
    event_name = str(payload.get("hook_event_name") or "")
    if event_name == "SessionStart":
        manifest_update["started_at"] = event["observer_received_at"]
        if payload.get("model"):
            manifest_update["model_at_start"] = payload.get("model")
    if event_name == "SessionEnd":
        manifest_update["ended_at"] = event["observer_received_at"]
        manifest_update["session_end_reason"] = payload.get("reason")
    update_manifest(session_id, manifest_update, root)
    return event


def main() -> int:
    raw_text = ""
    try:
        raw_text = sys.stdin.read()
        try:
            payload = json.loads(raw_text)
        except ValueError:
            payload = {"_observer_parse_error": True, "_raw_stdin": raw_text}
        collect_event(payload, raw_text)
    except BaseException as error:
        _record_internal_error(error, raw_text)
    # Passive contract: never emit output and never affect Claude Code.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
