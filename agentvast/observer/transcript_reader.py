"""Immutable best-effort snapshots of Claude Code transcript JSONL files."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from agentvast.observer.store import (
    ensure_session_layout,
    read_manifest,
    update_manifest,
    utc_now,
    write_jsonl,
)


def _wait_for_stable_file(path: Path, attempts: int, delay: float) -> bool:
    previous: Optional[int] = None
    stable = 0
    for _ in range(max(1, attempts)):
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        if size is not None and size == previous:
            stable += 1
            if stable >= 1:
                return True
        else:
            stable = 0
        previous = size
        time.sleep(max(0.0, delay))
    return path.is_file()


def snapshot_transcript(
    session_id: str,
    transcript_path: Union[Path, str],
    root: Optional[Union[Path, str]] = None,
    attempts: int = 10,
    delay: float = 0.1,
) -> Dict[str, Any]:
    source = Path(transcript_path).expanduser().resolve()
    directory = ensure_session_layout(session_id, root)
    if not _wait_for_stable_file(source, attempts, delay):
        raise FileNotFoundError("Claude transcript does not exist: {0}".format(source))

    snapshot = directory / "transcript" / "transcript.jsonl"
    temporary = snapshot.with_name(snapshot.name + ".tmp")
    shutil.copyfile(str(source), str(temporary))
    temporary.replace(snapshot)
    (directory / "transcript" / "source_path.txt").write_text(
        str(source) + "\n", encoding="utf-8"
    )

    envelopes: List[Dict[str, Any]] = []
    with snapshot.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            raw_line = line.rstrip("\r\n")
            try:
                record = json.loads(raw_line)
                envelopes.append(
                    {
                        "line_number": line_number,
                        "parsed": True,
                        "record": record,
                        "raw_line": raw_line,
                    }
                )
            except ValueError:
                envelopes.append(
                    {
                        "line_number": line_number,
                        "parsed": False,
                        "raw_line": raw_line,
                    }
                )
    write_jsonl(directory / "raw" / "transcript.jsonl", envelopes)
    update_manifest(
        session_id,
        {
            "transcript_source_path": str(source),
            "sources": {"transcript": True},
        },
        root,
    )
    return {
        "session_id": session_id,
        "source_path": str(source),
        "snapshot_path": str(snapshot),
        "record_count": len(envelopes),
        "invalid_record_count": sum(not item["parsed"] for item in envelopes),
    }


def finalize_session(
    session_id: str,
    root: Optional[Union[Path, str]] = None,
    transcript_path: Optional[Union[Path, str]] = None,
) -> Dict[str, Any]:
    manifest = read_manifest(session_id, root)
    source = transcript_path or manifest.get("transcript_source_path")
    result: Dict[str, Any] = {
        "session_id": session_id,
        "transcript": None,
        "warnings": [],
    }
    if source:
        try:
            result["transcript"] = snapshot_transcript(session_id, source, root)
        except (OSError, ValueError) as error:
            result["warnings"].append(str(error))
    else:
        result["warnings"].append("no transcript_path was observed")
    update_manifest(session_id, {"ended_at": utc_now()}, root)
    return result
