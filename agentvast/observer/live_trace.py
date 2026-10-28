"""Resumable transcript tailing and immutable, per-Turn semantic analysis.

Hooks remain passive. A web background task owns collection and a separate
worker owns analysis; neither blocks the Claude terminal or its hook process.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .locking import InterProcessFileLock
from .store import (
    session_directory,
    default_observations_root,
    read_manifest,
    update_manifest,
    iter_jsonl,
    write_jsonl,
    _write_json_atomic,
    utc_now,
)
from .trace_builder import build_observer_trace, load_observer_trace
from .event_schema import compact_event


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return copy.deepcopy(default)


def live_state(session_id, root=None):
    return _read(
        session_directory(session_id, root) / "live/state.json",
        {
            "enabled": False,
            "session_id": session_id,
            "trace_revision": 0,
            "turns": [],
        },
    )


def enable_live_trace(session_id, root=None):
    manifest = read_manifest(session_id, root)
    update_manifest(
        session_id,
        {
            "live_trace_enabled": True,
            "ended_at": None,
            "live_activated_at": manifest.get("live_activated_at") or utc_now(),
        },
        root,
    )


@contextmanager
def _connect(directory):
    path = directory / "live"
    path.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path / "capture.sqlite3"), timeout=5)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS cursors (source TEXT PRIMARY KEY, identity TEXT,
          generation TEXT, offset INTEGER, line INTEGER, anchor TEXT);
        CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY AUTOINCREMENT,
          dedup TEXT UNIQUE, generation TEXT, source_line INTEGER, raw TEXT, parsed INTEGER);
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def capture_append(session_id, source, root=None):
    """Commit complete lines and their cursor in one transaction, before projection.

    An unfinished UTF-8/JSON line is re-read next tick. UUID+content dedup keeps
    rotations/replays idempotent while retaining changed records with one UUID.
    """
    directory = session_directory(session_id, root)
    source = Path(source).expanduser().resolve()
    with source.open("rb") as stream, _connect(directory) as db:
        stat = os.fstat(stream.fileno())
        identity = f"{stat.st_dev}:{stat.st_ino}"
        cursor = db.execute(
            "SELECT identity,generation,offset,line,anchor FROM cursors WHERE source=?",
            (str(source),),
        ).fetchone()
        generation, offset, line = os.urandom(12).hex(), 0, 0
        if cursor and cursor[0] == identity and stat.st_size >= cursor[2]:
            stream.seek(max(0, cursor[2] - 256))
            anchor = hashlib.sha256(stream.read(min(256, cursor[2]))).hexdigest()
            if anchor == cursor[4]:
                generation, offset, line = cursor[1:4]
        stream.seek(offset)
        # Bounded batches; readline completes a record larger than the batch.
        data = stream.read(4 * 1024 * 1024)
        if data and not data.endswith(b"\n") and len(data) == 4 * 1024 * 1024:
            data += stream.readline()
        boundary = data.rfind(b"\n") + 1
        complete = data[:boundary]
        for raw in complete.splitlines():
            line += 1
            text = raw.decode("utf-8", errors="replace")
            try:
                record = json.loads(text)
                parsed = isinstance(record, dict)
            except ValueError:
                record, parsed = {}, False
            uuid = record.get("uuid") if parsed else None
            key = digest([uuid, text]) if uuid else digest([generation, line, text])
            db.execute(
                "INSERT OR IGNORE INTO records(dedup,generation,source_line,raw,parsed) VALUES(?,?,?,?,?)",
                (key, generation, line, text, int(parsed)),
            )
        offset += len(complete)
        stream.seek(max(0, offset - 256))
        anchor = hashlib.sha256(stream.read(min(256, offset))).hexdigest()
        db.execute(
            "INSERT OR REPLACE INTO cursors VALUES(?,?,?,?,?,?)",
            (str(source), identity, generation, offset, line, anchor),
        )
        count = db.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    return {
        "record_count": count,
        "offset": offset,
        "pending_bytes": max(0, stat.st_size - offset),
        "generation": generation,
        "source_path": str(source),
    }


def _project_capture(session_id, root):
    directory = session_directory(session_id, root)
    with _connect(directory) as db:
        rows = db.execute(
            "SELECT id,generation,source_line,raw,parsed FROM records ORDER BY id"
        ).fetchall()
    envelopes = []
    for number, (capture_id, generation, source_line, raw, parsed) in enumerate(rows, start=1):
        item = {
            "line_number": number,
            "parsed": bool(parsed),
            "raw_line": raw,
            "source_generation": generation,
            "source_line_number": source_line,
            "capture_record_id": capture_id,
        }
        if parsed:
            item["record"] = json.loads(raw)
        envelopes.append(item)
    write_jsonl(directory / "raw/transcript.jsonl", envelopes)
    target = directory / "transcript/transcript.jsonl"
    temp = target.with_suffix(".tmp")
    temp.write_text("".join(row[3] + "\n" for row in rows), encoding="utf-8")
    temp.replace(target)
    return build_observer_trace(session_id, str(root) if root else None)


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _turn_boundaries(trace, hooks, records=()):
    """Pair boundary hooks with human prompts, never with tool results/subagents."""
    turns = trace["turns"]
    by_id = {t["turn_id"]: t for t in turns}
    event_map = {e["event_id"]: e for e in trace["events"]}
    human_uuids = {
        event_map[t["prompt_event_id"]].get("message_uuid"): t["turn_id"]
        for t in turns
        if event_map[t["prompt_event_id"]].get("message_uuid")
    }
    # Claude can re-submit a prompt id for injected context, and can start
    # automatic notification loops with a new prompt id. Map those loops to
    # the human Turn owning their transcript position, without creating tasks.
    prompt_owners = {}
    owner = None
    for envelope in records:
        record = envelope.get("record") or {}
        if record.get("uuid") in human_uuids:
            owner = human_uuids[record["uuid"]]
        prompt_id = record.get("promptId") or record.get("prompt_id")
        if prompt_id and owner:
            prompt_owners.setdefault(prompt_id, owner)
    boundaries = {}
    active = None
    used_prompts = set()
    fallback_allowed = True
    for envelope in hooks:
        payload = envelope.get("raw_payload") or {}
        if not isinstance(payload, dict) or payload.get("agent_id"):
            continue
        name = payload.get("hook_event_name")
        received = _timestamp(envelope.get("observer_received_at"))
        prompt_id = payload.get("prompt_id") or payload.get("promptId")
        mapped = prompt_owners.get(prompt_id)
        if name == "UserPromptSubmit" and mapped:
            active = mapped
            used_prompts.add(active)
            fallback_allowed = True
            continue
        if name == "UserPromptSubmit":
            candidates = [
                t
                for t in turns
                if t["turn_id"] not in used_prompts
                and str(t.get("prompt", "")).strip() == str(payload.get("prompt", "")).strip()
            ]
            if candidates:
                match = min(
                    candidates,
                    key=lambda t: abs(
                        (_timestamp(t.get("started_at")) or received or 0) - (received or 0)
                    ),
                )
                active = match["turn_id"]
                used_prompts.add(active)
                if prompt_id:
                    prompt_owners.setdefault(prompt_id, active)
                fallback_allowed = True
            else:
                active = None  # An unpersisted prompt must not close the preceding turn.
                fallback_allowed = False
        elif name in {"Stop", "StopFailure", "SessionEnd"}:
            if mapped:
                active = mapped
            elif prompt_id:
                # A stop whose prompt has not been captured cannot close an
                # unrelated preceding task based on a timestamp alone.
                continue
            if active is None and fallback_allowed and received is not None:
                candidates = [
                    t
                    for t in turns
                    if _timestamp(t.get("started_at")) is not None
                    and _timestamp(t["started_at"]) <= received
                ]
                if candidates:
                    active = max(candidates, key=lambda t: _timestamp(t["started_at"]))["turn_id"]
            if name == "SessionEnd" and active in boundaries:
                continue
            if active in by_id:
                boundaries[active] = {
                    "kind": name,
                    "received_at": envelope.get("observer_received_at"),
                    "last_assistant_message": payload.get("last_assistant_message"),
                    "pending_background_tasks": sum(
                        t.get("status") in {"running", "pending"}
                        for t in payload.get("background_tasks", [])
                        if isinstance(t, dict)
                    ),
                }
    return boundaries


def _snapshot(trace, turn):
    ids = set(turn["event_ids"])
    events = [e for e in trace["events"] if e["event_id"] in ids]
    relations = [r for r in trace["relations"] if r["from"] in ids and r["to"] in ids]
    return {
        **trace,
        "session": {**trace["session"], "source": "live_turn_snapshot"},
        "events": events,
        "relations": relations,
        "turns": [turn],
        "telemetry": [],
        "artifacts": [a for a in trace["artifacts"] if ids.intersection(a["evidence_event_ids"])],
    }


def _fact_hash(snapshot):
    # Full-session counters, current file existence and derivation timestamps do
    # not invalidate an otherwise unchanged completed Turn.
    return digest(
        {
            "events": [compact_event(e) for e in snapshot["events"]],
            "relations": snapshot["relations"],
        }
    )


def sync_live_trace(session_id, root=None, settle_seconds=1.0, now=None):
    directory = session_directory(session_id, root)
    manifest = read_manifest(session_id, root)
    if not manifest.get("live_trace_enabled"):
        return live_state(session_id, root)
    now = time.time() if now is None else now
    (directory / "live").mkdir(parents=True, exist_ok=True)
    with InterProcessFileLock(directory / "live/capture.lock"):
        state = live_state(session_id, root)
        state.update(enabled=True, session_id=session_id, analysis_mode="manual")
        if state.get("ended_at") != manifest.get("ended_at"):
            state["trace_revision"] = state.get("trace_revision", 0) + 1
        state["ended_at"] = manifest.get("ended_at")
        source = manifest.get("transcript_source_path")
        if not source or not Path(source).expanduser().is_file():
            state.update(message="等待 transcript 路径", updated_at=utc_now())
            _write_json_atomic(directory / "live/state.json", state)
            return state
        capture = capture_append(session_id, source, root)
        changed = capture["record_count"] != state.get("capture", {}).get("record_count")
        if changed or not (directory / "derived/observer_trace.json").is_file():
            trace = _project_capture(session_id, root)
            state["trace_revision"] = state.get("trace_revision", 0) + 1
        else:
            trace = load_observer_trace(session_id, root)
        hooks = list(iter_jsonl(directory / "raw/hooks.jsonl"))
        boundaries = _turn_boundaries(trace, hooks, iter_jsonl(directory / "raw/transcript.jsonl"))
        previous = {t["turn_id"]: t for t in state.get("turns", [])}
        current = []
        for index, turn in enumerate(trace["turns"]):
            snapshot = _snapshot(trace, turn)
            if not snapshot["events"]:
                continue
            content_hash = _fact_hash(snapshot)
            old = previous.get(turn["turn_id"], {})
            item = {
                **old,
                "turn_id": turn["turn_id"],
                "ordinal": index + 1,
                "prompt": turn["prompt"],
                "event_count": len(snapshot["events"]),
                "content_hash": content_hash,
            }
            if content_hash != old.get("content_hash"):
                item["last_change"] = now
            boundary = boundaries.get(turn["turn_id"])
            execution = "running"
            if boundary:
                kind = boundary["kind"]
                if kind == "StopFailure":
                    execution = "failed"
                elif kind == "SessionEnd":
                    execution = "interrupted"
                else:
                    finals = [
                        e
                        for e in snapshot["events"]
                        if e["event_type"] == "model_response"
                        and (
                            e["payload"].get("stop_reason") == "end_turn"
                            or boundary.get("last_assistant_message")
                            and not e["payload"].get("tool_use_ids")
                            and e["payload"].get("text", "").strip()
                            == str(boundary["last_assistant_message"]).strip()
                        )
                    ]
                    last_event = max(
                        (
                            e
                            for e in snapshot["events"]
                            if e["event_type"] not in {"subagent_result", "control_event"}
                        ),
                        key=lambda e: e["sequence"],
                    )
                    if (
                        finals
                        and max(e["sequence"] for e in finals) >= last_event["sequence"]
                        and (
                            not boundary.get("last_assistant_message")
                            or any(
                                e["payload"].get("text", "").strip()
                                == str(boundary["last_assistant_message"]).strip()
                                for e in finals
                            )
                        )
                    ):
                        execution = "completed"
                    else:
                        execution = "settling"
                if now - item.get("last_change", now) < settle_seconds or (
                    index == len(trace["turns"]) - 1 and capture["pending_bytes"]
                ):
                    execution = "settling"
            elif any(
                e["event_type"] == "control_event"
                and e["payload"].get("control_kind")
                in {"execution_cancelled", "execution_interrupted", "session_terminated"}
                for e in snapshot["events"]
            ):
                execution = "interrupted"
            elif index < len(trace["turns"]) - 1 or manifest.get("ended_at"):
                execution = "interrupted"  # Never infer successful completion from silence.
            item["execution_state"] = execution
            if boundary:
                item["boundary"] = boundary
            if execution in {"completed", "interrupted", "failed"}:
                # Historical turns from before activation stay available for manual
                # full-session analysis; do not silently send an old session to AI.
                ended = _timestamp((boundary or {}).get("received_at") or turn.get("ended_at"))
                activated = _timestamp(manifest.get("live_activated_at"))
                historical = ended is not None and activated is not None and ended < activated
                if historical and not old.get("revision"):
                    item["analysis_state"] = "historical"
                elif content_hash != old.get("snapshot_hash") or execution != old.get(
                    "snapshot_execution"
                ):
                    revision = old.get("revision", 0) + 1
                    revision_dir = directory / "live/turns" / turn["turn_id"] / f"v{revision:04d}"
                    snapshot["history_context"] = {
                        "recent_user_tasks": [
                            t["prompt"][:1600] for t in trace["turns"][max(0, index - 3) : index]
                        ],
                        "recent_reported_results": [
                            {
                                "turn_id": prior["turn_id"],
                                "reported_text": next(
                                    (
                                        e["payload"].get("text", "")[:1800]
                                        for e in reversed(trace["events"])
                                        if e.get("turn_id") == prior["turn_id"]
                                        and e["event_type"] == "model_response"
                                        and e["payload"].get("is_final")
                                    ),
                                    "",
                                ),
                            }
                            for prior in trace["turns"][max(0, index - 3) : index]
                        ],
                        "instruction": "历史任务仅帮助理解本轮要求，不是可引用的 Event 证据；只分析本轮 Event，不生成跨轮关系。",
                    }
                    snapshot["turns"] = [{**turn, "status": execution}]
                    snapshot["analysis_scope"] = {
                        "type": "turn",
                        "execution_state": execution,
                        "cross_turn_inference": False,
                    }
                    snapshot_dir = revision_dir / session_id / "derived"
                    snapshot_dir.mkdir(parents=True, exist_ok=True)
                    _write_json_atomic(snapshot_dir / "observer_trace.json", snapshot)
                    write_jsonl(
                        snapshot_dir / "events.jsonl",
                        [compact_event(e) for e in snapshot["events"]],
                    )
                    update_manifest(session_id, {"cwd": trace["session"].get("cwd")}, revision_dir)
                    # Retain the content fingerprint separately from the version's
                    # immutable source files. Late records create a new version.
                    item.update(
                        revision=revision,
                        snapshot_hash=content_hash,
                        snapshot_execution=execution,
                        snapshot_root=str(revision_dir),
                        analysis_state="idle",
                        analysis_requested=False,
                        percent=0,
                        error=None,
                    )
            else:
                if content_hash != old.get("snapshot_hash"):
                    item.update(analysis_state="waiting", percent=0, error=None)
                else:
                    item.setdefault("analysis_state", "waiting")
            if not item.get("analysis_requested") and item.get("analysis_state") in {
                "queued",
                "running",
                "waiting_config",
            }:
                item.update(analysis_state="idle", percent=0)
            current.append(item)
        active = state.get("active_analysis") or {}
        if active.get("status") == "running" and not any(
            t["turn_id"] == active.get("turn_id") and t.get("analysis_requested") for t in current
        ):
            state["active_analysis"] = {
                **active,
                "status": "stopped",
                "message": "已切换为手动分析",
            }
        state.update(turns=current, capture=capture, message="动态采集中", updated_at=utc_now())
        _write_json_atomic(directory / "live/state.json", state)
        return state


class SupersededTurnAnalysis(RuntimeError):
    """The current snapshot has moved on; retain checkpoints and release the queue."""


def _update_turn(session_id, root, turn_id, revision, **updates):
    directory = session_directory(session_id, root)
    with InterProcessFileLock(directory / "live/capture.lock"):
        state = live_state(session_id, root)
        previous_active = state.get("active_analysis") or {}
        state["active_analysis"] = {
            "turn_id": turn_id,
            "revision": revision,
            "status": updates.get("analysis_state", "running"),
            "percent": updates.get("percent", previous_active.get("percent", 0)),
            "message": updates.get("message", previous_active.get("message")),
            "error": updates.get("error"),
            "updated_at": utc_now(),
        }
        for item in state.get("turns", []):
            if (
                item["turn_id"] == turn_id
                and updates.get("analysis_state") != "superseded"
                and item.get("revision") == revision
                and item.get("snapshot_hash") == item.get("content_hash")
                and item.get("snapshot_execution") == item.get("execution_state")
            ):
                item.update(updates)
        state["updated_at"] = utc_now()
        _write_json_atomic(directory / "live/state.json", state)


def analyze_next_turn(session_id, root=None, runner=None):
    """One durable job at a time. A process lock also prevents duplicate web workers."""
    from agentvast.semantic.event_workflow import run_event_workflow
    from agentvast.semantic.provider import SemanticConfig

    directory = session_directory(session_id, root)
    try:
        with InterProcessFileLock(directory / "live/analysis.lock", timeout=0.02):
            state = live_state(session_id, root)
            jobs = [
                t
                for t in state.get("turns", [])
                if t.get("analysis_requested")
                and t.get("analysis_state") in {"queued", "running", "waiting_config"}
                and t.get("snapshot_hash") == t.get("content_hash")
                and t.get("snapshot_execution") == t.get("execution_state")
            ]
            if not jobs:
                return False
            job = jobs[0]
            turn_id, revision = job["turn_id"], job["revision"]
            if runner is None and not SemanticConfig.from_env().configured():
                _update_turn(
                    session_id,
                    root,
                    turn_id,
                    revision,
                    analysis_state="waiting_config",
                    error="请配置语义 API 后自动继续",
                )
                return False
            _update_turn(
                session_id, root, turn_id, revision, analysis_state="running", percent=0, error=None
            )

            def check_current():
                latest = next(
                    (
                        t
                        for t in live_state(session_id, root).get("turns", [])
                        if t["turn_id"] == turn_id
                    ),
                    {},
                )
                if (
                    not latest.get("analysis_requested")
                    or latest.get("revision") != revision
                    or latest.get("snapshot_hash") != latest.get("content_hash")
                    or latest.get("snapshot_execution") != latest.get("execution_state")
                ):
                    raise SupersededTurnAnalysis("已有更新的 Turn 版本，保留摘要检查点并切换")

            def report(progress):
                check_current()
                _update_turn(
                    session_id,
                    root,
                    turn_id,
                    revision,
                    percent=progress.get("percent", 0),
                    message=progress.get("message"),
                    analysis_state="running",
                )

            try:
                snapshot_root = Path(job["snapshot_root"])
                cache_roots = [
                    str(p)
                    for p in snapshot_root.parent.glob("v*")
                    if p.is_dir() and p.name < snapshot_root.name
                ]
                (runner or run_event_workflow)(
                    session_id,
                    root=job["snapshot_root"],
                    resume=True,
                    progress_callback=report,
                    annotation_cache_roots=cache_roots,
                    cancel_check=check_current,
                )
                check_current()
                _update_turn(
                    session_id,
                    root,
                    turn_id,
                    revision,
                    analysis_state="ready",
                    percent=100,
                    error=None,
                )
            except SupersededTurnAnalysis:
                _update_turn(
                    session_id,
                    root,
                    turn_id,
                    revision,
                    analysis_state="superseded",
                    message="旧版本已让位于更新版本",
                )
            except Exception as error:
                _update_turn(
                    session_id, root, turn_id, revision, analysis_state="partial", error=str(error)
                )
            return True
    except TimeoutError:
        return False


def request_turn_analysis(session_id, turn_ids, root=None, force=False):
    """Explicit user selection is the only source of model jobs, including history."""
    trace = load_observer_trace(session_id, root)
    selected = set(turn_ids)
    known = {turn["turn_id"] for turn in trace["turns"]}
    if not selected or not selected.issubset(known):
        raise ValueError("请选择当前会话中有效的 Turn")
    directory = session_directory(session_id, root)
    (directory / "live").mkdir(parents=True, exist_ok=True)
    with InterProcessFileLock(directory / "live/capture.lock"):
        state = live_state(session_id, root)
        previous = {t["turn_id"]: t for t in state.get("turns", [])}
        items = []
        for index, turn in enumerate(trace["turns"]):
            old = previous.get(turn["turn_id"], {})
            execution = old.get("execution_state") or (
                "completed" if turn.get("status") == "complete" else "interrupted"
            )
            snapshot = _snapshot(trace, turn)
            content_hash = _fact_hash(snapshot)
            item = {
                **old,
                "turn_id": turn["turn_id"],
                "ordinal": index + 1,
                "prompt": turn["prompt"],
                "event_count": len(snapshot["events"]),
                "execution_state": execution,
                "content_hash": content_hash,
            }
            if item["turn_id"] not in selected:
                item.setdefault("analysis_state", "idle")
                items.append(item)
                continue
            same = (
                old.get("snapshot_hash") == content_hash
                and old.get("snapshot_execution") == execution
            )
            if same and not force and old.get("analysis_state") in {"running", "ready"}:
                items.append(item)
                continue
            if force or not same or not old.get("snapshot_root"):
                revision = old.get("revision", 0) + 1
                revision_dir = directory / "live/turns" / turn["turn_id"] / f"v{revision:04d}"
                output = revision_dir / session_id / "derived"
                output.mkdir(parents=True, exist_ok=True)
                snapshot["turns"] = [{**turn, "status": execution}]
                snapshot["analysis_scope"] = {
                    "type": "turn",
                    "execution_state": execution,
                    "cross_turn_inference": False,
                }
                snapshot["history_context"] = {
                    "recent_user_tasks": [
                        t["prompt"][:1600] for t in trace["turns"][max(0, index - 3) : index]
                    ],
                    "instruction": "历史仅为理解上下文，不作为本轮证据；不生成跨轮关系。",
                }
                if same and old.get("snapshot_root"):
                    previous_snapshot = _read(
                        Path(old["snapshot_root"]) / session_id / "derived/observer_trace.json", {}
                    )
                    if previous_snapshot.get("history_context"):
                        snapshot["history_context"] = previous_snapshot["history_context"]
                _write_json_atomic(output / "observer_trace.json", snapshot)
                write_jsonl(output / "events.jsonl", [compact_event(e) for e in snapshot["events"]])
                update_manifest(session_id, {"cwd": trace["session"].get("cwd")}, revision_dir)
                item.update(
                    revision=revision,
                    snapshot_root=str(revision_dir),
                    snapshot_hash=content_hash,
                    snapshot_execution=execution,
                )
            item.update(analysis_requested=True, analysis_state="queued", percent=0, error=None)
            items.append(item)
        state.update(
            analysis_mode="manual",
            turns=items,
            updated_at=utc_now(),
            trace_revision=state.get("trace_revision", 0) + 1,
        )
        _write_json_atomic(directory / "live/state.json", state)
        return state


def retry_live_turns(session_id, root=None):
    directory = session_directory(session_id, root)
    if not live_state(session_id, root).get("enabled"):
        raise ValueError("当前会话尚未启用动态采集")
    with InterProcessFileLock(directory / "live/capture.lock"):
        state = live_state(session_id, root)
        for item in state.get("turns", []):
            if item.get("analysis_state") == "partial":
                item.update(analysis_state="queued", analysis_requested=True, error=None)
        _write_json_atomic(directory / "live/state.json", state)
    return state


def live_event_workflow(session_id, root=None):
    """Compose only current, successfully analyzed Turn versions; never synthesize AI facts."""
    from agentvast.semantic.event_workflow import load_event_workflow

    state = live_state(session_id, root)
    workflows = []
    published_turns = []
    for turn in state.get("turns", []):
        if (
            turn.get("analysis_state") == "ready"
            and turn.get("snapshot_hash") == turn.get("content_hash")
            and turn.get("snapshot_execution") == turn.get("execution_state")
        ):
            workflows.append(load_event_workflow(session_id, turn["snapshot_root"]))
            published_turns.append(turn)
    if not workflows:
        return None
    merged = copy.deepcopy(workflows[-1])
    for name in (
        "event_summaries",
        "event_importance",
        "logical_relations",
        "relation_assessments",
    ):
        merged[name] = [item for workflow in workflows for item in workflow.get(name, [])]
    merged["scope"] = {
        "type": "completed_turns",
        "cross_turn_inference": False,
        "turns": [{"turn_id": t["turn_id"], "revision": t["revision"]} for t in published_turns],
    }
    merged["validation"].update(
        event_count=len(merged["event_summaries"]),
        relation_count=len(merged["logical_relations"]),
        candidate_relation_count=sum(
            w["validation"].get("candidate_relation_count", 0) for w in workflows
        ),
        rejected_relation_count=sum(
            w["validation"].get("rejected_relation_count", 0) for w in workflows
        ),
        note="逐 Turn 分析；跨 Turn 仅保留规则关系",
    )
    merged["inference_run"]["inference_id"] = digest(merged["scope"])
    for field in ("call_count", "elapsed_seconds"):
        merged["inference_run"][field] = sum(w["inference_run"].get(field, 0) for w in workflows)
    return merged


class LiveTraceService:
    def __init__(self, root=None, interval=1.0):
        self.root = Path(root or default_observations_root())
        self.interval = interval
        self.tasks = []

    def sessions(self, capture_only=False):
        if not self.root.is_dir():
            return []
        sessions = []
        for path in self.root.glob("*/manifest.json"):
            try:
                if _read(path, {}).get("live_trace_enabled") or (
                    not capture_only
                    and live_state(path.parent.name, self.root).get("analysis_mode") == "manual"
                ):
                    sessions.append(path.parent.name)
            except (OSError, ValueError, TypeError):
                continue
        return sessions

    def start(self):
        self.tasks = [asyncio.create_task(self.collect()), asyncio.create_task(self.analyze())]

    async def collect(self):
        while True:
            for session_id in self.sessions(capture_only=True):
                try:
                    await asyncio.to_thread(sync_live_trace, session_id, self.root)
                except Exception as error:
                    from .store import record_observer_error

                    record_observer_error(
                        error, self.root, {"collector": "live", "session_id": session_id}
                    )
            await asyncio.sleep(self.interval)

    async def analyze(self):
        while True:
            for session_id in self.sessions():
                try:
                    await asyncio.to_thread(analyze_next_turn, session_id, self.root)
                except Exception as error:
                    from .store import record_observer_error

                    record_observer_error(
                        error, self.root, {"collector": "live-analysis", "session_id": session_id}
                    )
            await asyncio.sleep(self.interval)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
