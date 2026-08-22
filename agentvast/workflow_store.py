"""SQLite-backed recorder for Claude Code data-analysis workflows.

This module deliberately contains no data-analysis logic.  Claude Code owns the
analysis; AgentVAST only stores declared semantic nodes, observes file versions,
and enforces a small workflow state machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union


PLAN_TRIGGERS = {"initial", "agent_replan", "human_intervention"}
CHECKPOINT_MODES = {"plan", "node", "none"}
ANALYSIS_OUTCOMES = {
    "answered",
    "partial",
    "insufficient_data",
    "blocked",
    "failed",
    "not_assessed",
}
INPUT_TYPES = {
    "conversation_only",
    "checkpoint_continue",
    "analysis_guidance",
    "planning_input",
    "challenge",
}
NON_CONTRIBUTION_INPUT_TYPES = {"conversation_only", "checkpoint_continue"}
ARTIFACT_CATEGORIES = ("code", "data", "report", "visualization")
ARTIFACT_EXTENSIONS = {
    "code": {".py", ".ipynb"},
    "data": {".csv", ".json", ".jsonl", ".parquet", ".feather", ".arrow"},
    "report": {".json"},
    "visualization": {".html", ".svg", ".png", ".jpg", ".jpeg", ".pdf"},
}
NODE_ID_PATTERN = re.compile(r"^node-(\d+)$")


class WorkflowError(ValueError):
    """Raised when an attempted workflow transition is invalid."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _from_json(value: Optional[str], default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


class WorkflowStore:
    """Single-writer-friendly SQLite store for the prototype workflow model."""

    def __init__(self, db_path: Union[Path, str]):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.db_path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    task_description TEXT NOT NULL,
                    original_request TEXT NOT NULL,
                    project_root TEXT NOT NULL,
                    result_root TEXT,
                    claude_session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    checkpoint_mode TEXT DEFAULT 'plan',
                    awaiting_user INTEGER DEFAULT 0,
                    checkpoint_kind TEXT,
                    checkpoint_step_id TEXT,
                    checkpoint_created_at TEXT,
                    final_approved_plan_version INTEGER,
                    plan_approved_version INTEGER,
                    plan_approved_at TEXT,
                    checkpoint_approved_step_id TEXT,
                    analysis_outcome TEXT
                );

                CREATE TABLE IF NOT EXISTS plan_revisions (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    version INTEGER NOT NULL,
                    nodes_json TEXT NOT NULL,
                    reason TEXT,
                    trigger_kind TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, version)
                );

                CREATE TABLE IF NOT EXISTS run_inputs (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    file_version_id TEXT NOT NULL REFERENCES file_versions(file_version_id),
                    PRIMARY KEY(run_id, file_version_id)
                );

                CREATE TABLE IF NOT EXISTS steps (
                    step_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    node_id TEXT NOT NULL,
                    plan_version INTEGER,
                    sequence INTEGER NOT NULL,
                    objective TEXT NOT NULL,
                    target_data TEXT,
                    completion_condition TEXT NOT NULL,
                    expected_output_roles_json TEXT NOT NULL,
                    operation_summary TEXT,
                    operation_types_json TEXT,
                    parameters_json TEXT,
                    algorithms_json TEXT,
                    programs_json TEXT,
                    commands_json TEXT,
                    result_summary TEXT,
                    analysis_conclusion TEXT,
                    analysis_outcome TEXT,
                    processing_result_json TEXT,
                    analysis_conclusion_json TEXT,
                    warnings_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_active_step_per_run
                ON steps(run_id) WHERE status = 'active';

                CREATE TABLE IF NOT EXISTS file_versions (
                    file_version_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    UNIQUE(path, sha256)
                );

                CREATE TABLE IF NOT EXISTS step_inputs (
                    step_id TEXT NOT NULL REFERENCES steps(step_id),
                    file_version_id TEXT NOT NULL REFERENCES file_versions(file_version_id),
                    PRIMARY KEY(step_id, file_version_id)
                );

                CREATE TABLE IF NOT EXISTS step_outputs (
                    step_id TEXT NOT NULL REFERENCES steps(step_id),
                    file_version_id TEXT NOT NULL REFERENCES file_versions(file_version_id),
                    role TEXT NOT NULL,
                    PRIMARY KEY(step_id, file_version_id)
                );

                CREATE TABLE IF NOT EXISTS input_events (
                    input_event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    claude_session_id TEXT,
                    original_text TEXT NOT NULL,
                    type TEXT,
                    target_step_id TEXT,
                    target_plan_version INTEGER,
                    structured_summary TEXT,
                    workflow_effect TEXT,
                    checkpoint_kind TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS hook_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    step_id TEXT,
                    hook_event_name TEXT NOT NULL,
                    tool_name TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS session_bindings (
                    binding_id TEXT PRIMARY KEY,
                    claude_session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    terminal_session_id TEXT,
                    status TEXT NOT NULL,
                    bound_at TEXT NOT NULL,
                    released_at TEXT,
                    release_reason TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_active_run_per_claude_session
                ON session_bindings(claude_session_id) WHERE status = 'active';

                CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_run
                ON session_bindings(run_id) WHERE status = 'active';

                CREATE TABLE IF NOT EXISTS control_messages (
                    control_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    claude_session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    consumed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS artifact_baselines (
                    step_id TEXT NOT NULL REFERENCES steps(step_id),
                    path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    PRIMARY KEY(step_id, path)
                );

                CREATE TABLE IF NOT EXISTS input_baselines (
                    step_id TEXT NOT NULL REFERENCES steps(step_id),
                    path TEXT NOT NULL,
                    file_version_id TEXT NOT NULL REFERENCES file_versions(file_version_id),
                    PRIMARY KEY(step_id, path)
                );
                """
            )
            self._ensure_column(connection, "runs", "result_root", "TEXT")
            self._ensure_column(
                connection, "runs", "checkpoint_mode", "TEXT DEFAULT 'plan'"
            )
            self._ensure_column(
                connection, "runs", "awaiting_user", "INTEGER DEFAULT 0"
            )
            self._ensure_column(connection, "runs", "checkpoint_kind", "TEXT")
            self._ensure_column(
                connection, "runs", "checkpoint_step_id", "TEXT"
            )
            self._ensure_column(
                connection, "runs", "checkpoint_created_at", "TEXT"
            )
            self._ensure_column(
                connection, "runs", "final_approved_plan_version", "INTEGER"
            )
            self._ensure_column(
                connection, "runs", "plan_approved_version", "INTEGER"
            )
            self._ensure_column(connection, "runs", "plan_approved_at", "TEXT")
            self._ensure_column(
                connection, "runs", "checkpoint_approved_step_id", "TEXT"
            )
            self._ensure_column(
                connection, "plan_revisions", "trigger_kind", "TEXT"
            )
            self._ensure_column(connection, "steps", "plan_version", "INTEGER")
            self._ensure_column(connection, "steps", "commands_json", "TEXT")
            self._ensure_column(connection, "steps", "result_summary", "TEXT")
            self._ensure_column(
                connection, "steps", "analysis_conclusion", "TEXT"
            )
            self._ensure_column(
                connection, "steps", "analysis_outcome", "TEXT"
            )
            self._ensure_column(
                connection, "runs", "analysis_outcome", "TEXT"
            )
            self._ensure_column(
                connection, "input_events", "checkpoint_kind", "TEXT"
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        declaration: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
            )

    def start_run(
        self,
        task_description: str,
        project_root: Union[Path, str],
        input_files: Iterable[Union[Path, str]],
        claude_session_id: Optional[str] = None,
        original_request: Optional[str] = None,
        checkpoint_mode: str = "plan",
    ) -> Dict[str, Any]:
        task_description = task_description.strip()
        if not task_description:
            raise WorkflowError("task_description cannot be empty")
        if checkpoint_mode not in CHECKPOINT_MODES:
            raise WorkflowError(f"invalid checkpoint mode: {checkpoint_mode}")

        project = Path(project_root).resolve()
        if not project.is_dir():
            raise WorkflowError(f"project_root does not exist: {project}")

        resolved_inputs = [self._resolve_file(path, project) for path in input_files]
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        result_root = project / "result" / run_id
        for category in ARTIFACT_CATEGORIES:
            (result_root / category).mkdir(parents=True, exist_ok=True)
        session_id = claude_session_id or str(uuid.uuid4())
        now = utc_now()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    run_id, task_description, original_request, project_root, result_root,
                    claude_session_id, status, started_at, checkpoint_mode,
                    awaiting_user
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, 0)
                """,
                (
                    run_id,
                    task_description,
                    original_request or task_description,
                    str(project),
                    str(result_root),
                    session_id,
                    now,
                    checkpoint_mode,
                ),
            )
            initial_versions = [
                self._observe_file(connection, path) for path in resolved_inputs
            ]
            for version in initial_versions:
                connection.execute(
                    "INSERT INTO run_inputs(run_id, file_version_id) VALUES (?, ?)",
                    (run_id, version["file_version_id"]),
                )

        return {
            "run_id": run_id,
            "claude_session_id": session_id,
            "status": "active",
            "project_root": str(project),
            "result_root": str(result_root),
            "workflow_path": str(result_root / "workflow.json"),
            "checkpoint_mode": checkpoint_mode,
            "initial_file_versions": initial_versions,
        }

    def bind_session(
        self,
        run_id: str,
        claude_session_id: str,
        terminal_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bind one active Run to a Claude session used by dormant Hooks."""

        claude_session_id = claude_session_id.strip()
        if not claude_session_id:
            raise WorkflowError("claude_session_id cannot be empty")
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            if run["claude_session_id"] != claude_session_id:
                raise WorkflowError(
                    "Run Claude session does not match the requested binding"
                )
            existing = connection.execute(
                """
                SELECT * FROM session_bindings
                WHERE claude_session_id = ? AND status = 'active'
                """,
                (claude_session_id,),
            ).fetchone()
            if existing:
                if existing["run_id"] != run_id:
                    raise WorkflowError(
                        "Claude session is already bound to another active Run: "
                        f"{existing['run_id']}"
                    )
                connection.execute(
                    """
                    UPDATE session_bindings SET terminal_session_id = COALESCE(?, terminal_session_id)
                    WHERE binding_id = ?
                    """,
                    (terminal_session_id, existing["binding_id"]),
                )
                return {
                    "binding_id": existing["binding_id"],
                    "run_id": run_id,
                    "claude_session_id": claude_session_id,
                    "terminal_session_id": terminal_session_id
                    or existing["terminal_session_id"],
                    "status": "active",
                }
            binding_id = f"binding_{uuid.uuid4().hex[:12]}"
            bound_at = utc_now()
            connection.execute(
                """
                INSERT INTO session_bindings(
                    binding_id, claude_session_id, run_id, terminal_session_id,
                    status, bound_at
                ) VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (
                    binding_id,
                    claude_session_id,
                    run_id,
                    terminal_session_id,
                    bound_at,
                ),
            )
        return {
            "binding_id": binding_id,
            "run_id": run_id,
            "claude_session_id": claude_session_id,
            "terminal_session_id": terminal_session_id,
            "status": "active",
            "bound_at": bound_at,
        }

    def can_discover_inputs(self, run_id: str) -> bool:
        """Return whether Claude may perform read-only external-input discovery."""

        with self._connection() as connection:
            run = self._require_run(connection, run_id)
            if run["status"] != "active" or run["awaiting_user"]:
                return False
            active = connection.execute(
                "SELECT 1 FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            unresolved = connection.execute(
                """
                SELECT 1 FROM input_events
                WHERE run_id = ? AND status IN ('pending', 'classified')
                """,
                (run_id,),
            ).fetchone()
            if active is not None or unresolved is not None:
                return False
            plan = self._latest_plan(connection, run_id)
            input_count = connection.execute(
                "SELECT COUNT(*) AS count FROM run_inputs WHERE run_id = ?",
                (run_id,),
            ).fetchone()["count"]
            if plan is None:
                return input_count == 0
            completed = {
                row["node_id"]
                for row in connection.execute(
                    """
                    SELECT node_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    """,
                    (run_id,),
                ).fetchall()
            }
            return all(node["node_id"] in completed for node in plan["nodes"])

    def declare_run_inputs(
        self,
        run_id: str,
        input_files: Iterable[Union[Path, str]],
    ) -> Dict[str, Any]:
        """Optionally register files; completion-time discovery is also supported."""

        submitted = list(input_files)
        if not submitted:
            raise WorkflowError("input_files must contain at least one file")
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            project = Path(run["project_root"])
            result_root = self._result_root(run)
            paths: List[Path] = []
            seen = set()
            for raw_path in submitted:
                path = self._resolve_file(raw_path, project)
                try:
                    path.relative_to(result_root)
                except ValueError:
                    pass
                else:
                    raise WorkflowError(
                        "Run artifacts are Node outputs, not external Run inputs: "
                        + str(path)
                    )
                normalized = os.path.normcase(str(path))
                if normalized not in seen:
                    seen.add(normalized)
                    paths.append(path)

            existing_ids = {
                row["file_version_id"]
                for row in connection.execute(
                    "SELECT file_version_id FROM run_inputs WHERE run_id = ?",
                    (run_id,),
                ).fetchall()
            }
            added: List[Dict[str, Any]] = []
            for path in paths:
                version = self._observe_file(connection, path)
                if version["file_version_id"] in existing_ids:
                    continue
                connection.execute(
                    "INSERT INTO run_inputs(run_id, file_version_id) VALUES (?, ?)",
                    (run_id, version["file_version_id"]),
                )
                existing_ids.add(version["file_version_id"])
                added.append(version)
        return {
            "run_id": run_id,
            "added_file_versions": added,
            "added_count": len(added),
        }

    def active_run_for_session(
        self, claude_session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return the active Run bound to a Claude session, if one exists."""

        claude_session_id = claude_session_id.strip()
        if not claude_session_id:
            return None
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT b.binding_id, b.terminal_session_id, b.bound_at,
                       r.run_id, r.status, r.project_root, r.result_root,
                       r.task_description, r.claude_session_id
                FROM session_bindings b
                JOIN runs r ON r.run_id = b.run_id
                WHERE b.claude_session_id = ? AND b.status = 'active'
                  AND r.status = 'active'
                ORDER BY b.bound_at DESC LIMIT 1
                """,
                (claude_session_id,),
            ).fetchone()
        return dict(row) if row else None

    def latest_active_bound_run(self) -> Optional[Dict[str, Any]]:
        """Return the most recently bound active Run for local recovery."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT b.binding_id, b.terminal_session_id, b.bound_at,
                       r.run_id, r.status, r.project_root, r.result_root,
                       r.task_description, r.claude_session_id
                FROM session_bindings b
                JOIN runs r ON r.run_id = b.run_id
                WHERE b.status = 'active' AND r.status = 'active'
                ORDER BY b.bound_at DESC LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def latest_run_for_session(
        self, claude_session_id: str
    ) -> Optional[Dict[str, Any]]:
        claude_session_id = claude_session_id.strip()
        if not claude_session_id:
            return None
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT run_id, status, project_root, result_root, task_description,
                       claude_session_id, started_at, completed_at
                FROM runs WHERE claude_session_id = ?
                ORDER BY started_at DESC LIMIT 1
                """,
                (claude_session_id,),
            ).fetchone()
        return dict(row) if row else None

    def release_session_binding(self, run_id: str, reason: str) -> None:
        reason = reason.strip() or "released"
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE session_bindings SET status = 'released', released_at = ?,
                    release_reason = ?
                WHERE run_id = ? AND status = 'active'
                """,
                (utc_now(), reason, run_id),
            )

    def create_control_message(
        self,
        run_id: str,
        claude_session_id: str,
        kind: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Persist internal Web-to-Claude control data outside terminal text."""

        claude_session_id = claude_session_id.strip()
        kind = kind.strip()
        if not claude_session_id:
            raise WorkflowError("control message Claude session cannot be empty")
        if not kind:
            raise WorkflowError("control message kind cannot be empty")
        if not isinstance(payload, dict):
            raise WorkflowError("control message payload must be an object")
        control_id = f"control_{uuid.uuid4().hex[:12]}"
        created_at = utc_now()
        with self._connection() as connection:
            run = self._require_run(connection, run_id)
            if run["claude_session_id"] != claude_session_id:
                raise WorkflowError(
                    "control message Claude session does not match the Run"
                )
            connection.execute(
                """
                INSERT INTO control_messages(
                    control_id, run_id, claude_session_id, kind, payload_json,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    control_id,
                    run_id,
                    claude_session_id,
                    kind,
                    _json(payload),
                    created_at,
                ),
            )
        return {
            "control_id": control_id,
            "run_id": run_id,
            "claude_session_id": claude_session_id,
            "kind": kind,
            "status": "pending",
            "created_at": created_at,
        }

    def consume_control_message(
        self,
        control_id: str,
        claude_session_id: str,
    ) -> Dict[str, Any]:
        """Return an internal control payload and mark its first delivery."""

        claude_session_id = claude_session_id.strip()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM control_messages WHERE control_id = ?",
                (control_id,),
            ).fetchone()
            if row is None:
                raise WorkflowError(f"control message does not exist: {control_id}")
            if row["claude_session_id"] != claude_session_id:
                raise WorkflowError(
                    "control message does not belong to this Claude session"
                )
            consumed_at = row["consumed_at"] or utc_now()
            if row["status"] == "pending":
                connection.execute(
                    """
                    UPDATE control_messages SET status = 'consumed', consumed_at = ?
                    WHERE control_id = ?
                    """,
                    (consumed_at, control_id),
                )
        return {
            "control_id": row["control_id"],
            "run_id": row["run_id"],
            "claude_session_id": row["claude_session_id"],
            "kind": row["kind"],
            "payload": _from_json(row["payload_json"], {}),
            "status": "consumed",
            "created_at": row["created_at"],
            "consumed_at": consumed_at,
        }

    def rotate_claude_session(
        self,
        run_id: str,
        new_session_id: str,
        reason: str,
        terminal_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bind an active Run to a fresh Claude session without losing workflow state."""

        new_session_id = new_session_id.strip()
        reason = reason.strip()
        if not new_session_id:
            raise WorkflowError("new_session_id cannot be empty")
        if not reason:
            raise WorkflowError("session rotation reason cannot be empty")
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            previous_session_id = run["claude_session_id"]
            if previous_session_id == new_session_id:
                raise WorkflowError("new Claude session must use a different ID")
            now = utc_now()
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            connection.execute(
                "UPDATE runs SET claude_session_id = ? WHERE run_id = ?",
                (new_session_id, run_id),
            )
            connection.execute(
                """
                UPDATE session_bindings SET status = 'released', released_at = ?,
                    release_reason = ?
                WHERE run_id = ? AND status = 'active'
                """,
                (now, reason, run_id),
            )
            connection.execute(
                """
                INSERT INTO session_bindings(
                    binding_id, claude_session_id, run_id, terminal_session_id,
                    status, bound_at
                ) VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (
                    f"binding_{uuid.uuid4().hex[:12]}",
                    new_session_id,
                    run_id,
                    terminal_session_id,
                    now,
                ),
            )
            event_id = f"event_{uuid.uuid4().hex[:12]}"
            connection.execute(
                """
                INSERT INTO hook_events(
                    event_id, run_id, step_id, hook_event_name, tool_name,
                    payload_json, created_at
                ) VALUES (?, ?, ?, 'ClaudeSessionRotated', NULL, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    active["step_id"] if active else None,
                    _json(
                        {
                            "previous_session_id": previous_session_id,
                            "new_session_id": new_session_id,
                            "reason": reason,
                        }
                    ),
                    now,
                ),
            )
        return {
            "run_id": run_id,
            "previous_session_id": previous_session_id,
            "claude_session_id": new_session_id,
            "reason": reason,
            "terminal_session_id": terminal_session_id,
            "rotated_at": now,
        }

    def set_plan(
        self,
        run_id: str,
        nodes: List[Dict[str, Any]],
        trigger: Optional[str] = None,
        change_reason: Optional[str] = None,
        replace_plan_checkpoint: bool = False,
    ) -> Dict[str, Any]:
        if not nodes:
            raise WorkflowError("plan must contain at least one node")

        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            replacing_plan_checkpoint = bool(
                replace_plan_checkpoint
                and run["awaiting_user"]
                and run["checkpoint_kind"] == "plan"
                and trigger == "human_intervention"
            )
            if run["awaiting_user"] and not replacing_plan_checkpoint:
                raise WorkflowError(
                    "record the checkpoint user response before revising the Plan"
                )
            if replacing_plan_checkpoint:
                connection.execute(
                    """
                    UPDATE runs SET awaiting_user = 0, checkpoint_kind = NULL,
                        checkpoint_step_id = NULL, checkpoint_created_at = NULL
                    WHERE run_id = ?
                    """,
                    (run_id,),
                )
            if (run["checkpoint_mode"] or "plan") == "node":
                latest_completed = connection.execute(
                    """
                    SELECT step_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    ORDER BY sequence DESC LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                if (
                    latest_completed
                    and run["checkpoint_step_id"] != latest_completed["step_id"]
                ):
                    raise WorkflowError(
                        "pause for user review after the completed Node before "
                        "revising the Plan"
                    )
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM plan_revisions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            version = int(row["version"]) + 1
            previous = self._latest_plan(connection, run_id)
            previous_ids = {
                node["node_id"] for node in previous["nodes"]
            } if previous else set()
            started_definitions: Dict[str, Dict[str, Any]] = {}
            started_rows = connection.execute(
                """
                SELECT node_id, plan_version FROM steps
                WHERE run_id = ? AND status IN ('active', 'completed')
                """,
                (run_id,),
            ).fetchall()
            for started_row in started_rows:
                started_plan = self._plan_revision(
                    connection, run_id, int(started_row["plan_version"])
                )
                started_node = next(
                    (
                        node
                        for node in started_plan["nodes"]
                        if node["node_id"] == started_row["node_id"]
                    ),
                    None,
                )
                if started_node is None:
                    raise WorkflowError(
                        "started Node is missing from its original Plan Revision: "
                        f"{started_row['node_id']}"
                    )
                started_definitions[started_row["node_id"]] = started_node
            retained_ids = previous_ids | set(started_definitions)
            used_numbers: List[int] = []
            revision_rows = connection.execute(
                "SELECT nodes_json FROM plan_revisions WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            for revision_row in revision_rows:
                for stored_node in _from_json(revision_row["nodes_json"], []):
                    match = NODE_ID_PATTERN.fullmatch(
                        str(stored_node.get("node_id") or "")
                    )
                    if match:
                        used_numbers.append(int(match.group(1)))
            next_number = max(used_numbers, default=0) + 1

            aliases: List[str] = []
            alias_to_node_id: Dict[str, str] = {}
            for index, node in enumerate(nodes, start=1):
                alias = str(node.get("node_id") or f"submitted-node-{index}")
                if alias in alias_to_node_id:
                    raise WorkflowError(f"duplicate submitted node_id: {alias}")
                aliases.append(alias)
                if alias in retained_ids:
                    assigned = alias
                else:
                    assigned = f"node-{next_number:03d}"
                    next_number += 1
                alias_to_node_id[alias] = assigned

            normalized: List[Dict[str, Any]] = []
            for alias, node in zip(aliases, nodes):
                node_id = alias_to_node_id[alias]
                objective = str(node.get("objective") or "").strip()
                if not objective:
                    raise WorkflowError(f"plan node {alias} has no objective")
                if (
                    alias not in previous_ids
                    and not re.search(r"[\u3400-\u9fff]", objective)
                ):
                    raise WorkflowError(
                        f"plan node {alias} objective must be written in Chinese"
                    )
                implementation_reason = self._implementation_only_reason(objective)
                if implementation_reason:
                    raise WorkflowError(
                        f"plan node {alias} is an implementation action rather than "
                        f"a semantic analysis objective ({implementation_reason}). "
                        "Keep it inside the analysis node that produces or consumes "
                        "the file."
                    )
                raw_dependencies = [
                    str(value) for value in (node.get("depends_on") or [])
                ]
                unknown = sorted(
                    dependency
                    for dependency in set(raw_dependencies)
                    if dependency not in alias_to_node_id
                )
                if unknown:
                    raise WorkflowError(
                        f"plan node {alias} has unknown dependencies: "
                        f"{', '.join(unknown)}"
                    )
                dependencies = [
                    alias_to_node_id[dependency] for dependency in raw_dependencies
                ]
                if node_id in dependencies:
                    raise WorkflowError(
                        f"plan node cannot depend on itself: {alias}"
                    )
                raw_artifacts = node.get("required_artifacts", [])
                if not isinstance(raw_artifacts, list):
                    raise WorkflowError(
                        f"plan node {alias} required_artifacts must be an array"
                    )
                required_artifacts = list(
                    dict.fromkeys(str(value).strip() for value in raw_artifacts)
                )
                invalid_artifacts = sorted(
                    set(required_artifacts) - set(ARTIFACT_CATEGORIES)
                )
                if invalid_artifacts:
                    raise WorkflowError(
                        f"plan node {alias} has invalid required_artifacts: "
                        + ", ".join(invalid_artifacts)
                    )
                normalized.append(
                    {
                        "node_id": node_id,
                        "objective": objective,
                        "depends_on": dependencies,
                        "required_artifacts": required_artifacts,
                    }
                )

            if started_definitions:
                normalized_by_id = {
                    node["node_id"]: node for node in normalized
                }
                missing_started = sorted(
                    set(started_definitions) - set(normalized_by_id)
                )
                if missing_started:
                    raise WorkflowError(
                        "active/completed Nodes cannot be removed from a Plan "
                        "Revision: " + ", ".join(missing_started)
                    )
                for node_id, original_node in started_definitions.items():
                    revised_node = normalized_by_id[node_id]
                    if (
                        revised_node["objective"] != original_node["objective"]
                        or set(revised_node["depends_on"])
                        != set(original_node.get("depends_on") or [])
                        or set(revised_node["required_artifacts"])
                        != set(original_node.get("required_artifacts") or [])
                    ):
                        raise WorkflowError(
                            "active/completed Node definitions are immutable; only "
                            f"pending Nodes may be revised: {node_id}"
                        )

            self._validate_plan_is_acyclic(normalized)

            # Trigger is recorder metadata, not an analysis decision Claude should
            # need to memorize. Web edits remain human_intervention; every agent
            # alias (for example finding/analysis_finding) becomes agent_replan.
            if version == 1:
                effective_trigger = "initial"
            elif trigger == "human_intervention":
                effective_trigger = "human_intervention"
            else:
                effective_trigger = "agent_replan"
            normalized_reason = (change_reason or "").strip() or None
            if version > 1 and normalized_reason is None:
                raise WorkflowError(
                    "a revised plan must explain the real change with change_reason"
                )
            if previous is not None:
                previous_by_id = {
                    node["node_id"]: node for node in previous["nodes"]
                }
                current_by_id = {node["node_id"]: node for node in normalized}
                materially_changed = (
                    set(previous_by_id) != set(current_by_id)
                    or any(
                        current_by_id[node_id]["objective"]
                        != previous_by_id[node_id]["objective"]
                        or set(current_by_id[node_id]["depends_on"])
                        != set(
                            previous_by_id[node_id].get("depends_on") or []
                        )
                        or set(current_by_id[node_id]["required_artifacts"])
                        != set(
                            previous_by_id[node_id].get("required_artifacts") or []
                        )
                        for node_id in set(previous_by_id) & set(current_by_id)
                    )
                )
                if not materially_changed:
                    raise WorkflowError(
                        "do not create a Plan Revision when no Node changed"
                    )

            created_at = utc_now()
            connection.execute(
                """
                INSERT INTO plan_revisions(
                    run_id, version, nodes_json, reason, trigger_kind, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    version,
                    _json(normalized),
                    normalized_reason,
                    effective_trigger,
                    created_at,
                ),
            )

            checkpoint_opened = False
            checkpoint_mode = run["checkpoint_mode"] or "plan"
            # Only the initial Plan is a mandatory approval boundary. Later
            # Revisions are recorded and may be edited by the user, but they do not
            # interrupt Claude's analysis by default.
            if version == 1 and checkpoint_mode in {"plan", "node"}:
                checkpoint_opened = True
                connection.execute(
                    """
                    UPDATE runs SET
                        awaiting_user = 1,
                        checkpoint_kind = 'plan',
                        checkpoint_step_id = NULL,
                        checkpoint_created_at = ?
                    WHERE run_id = ?
                    """,
                    (created_at, run_id),
                )

        return {
            "run_id": run_id,
            "plan_version": version,
            "trigger": effective_trigger,
            "change_reason": normalized_reason,
            "nodes": normalized,
            "node_mapping": alias_to_node_id,
            "next_action": (
                "present-plan-and-wait-for-user"
                if checkpoint_opened
                else "start-node"
            ),
            "checkpoint": (
                {
                    "kind": "plan",
                    "plan_version": version,
                    "created_at": created_at,
                }
                if checkpoint_opened
                else None
            ),
        }

    def start_step(
        self,
        run_id: str,
        node_id: str,
        objective: str = "",
    ) -> Dict[str, Any]:
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            if run["awaiting_user"]:
                raise WorkflowError(
                    "AgentVAST is waiting for the user at a checkpoint"
                )
            pending = connection.execute(
                """
                SELECT COUNT(*) AS count FROM input_events
                WHERE run_id = ? AND status IN ('pending', 'classified')
                """,
                (run_id,),
            ).fetchone()["count"]
            if pending:
                raise WorkflowError(
                    "classify and apply unresolved user input before starting a node"
                )

            plan = self._latest_plan(connection, run_id)
            if plan is None:
                raise WorkflowError("set a plan before starting a node")
            checkpoint_mode = run["checkpoint_mode"] or "plan"
            if (
                checkpoint_mode in {"plan", "node"}
                and run["plan_approved_version"] != plan["version"]
            ):
                raise WorkflowError(
                    "obtain user approval for the current Plan Revision before "
                    "starting a Node"
                )
            if run["checkpoint_mode"] == "node":
                latest_completed = connection.execute(
                    """
                    SELECT step_id, node_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    ORDER BY sequence DESC LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                if (
                    latest_completed
                    and run["checkpoint_approved_step_id"]
                    != latest_completed["step_id"]
                ):
                    raise WorkflowError(
                        "pause for user review after the completed Node before "
                        "starting another Node"
                    )
            plan_nodes = {node["node_id"]: node for node in plan["nodes"]}
            if node_id not in plan_nodes:
                raise WorkflowError(f"node_id is not present in current plan: {node_id}")
            plan_node = plan_nodes[node_id]
            supplied_objective = objective.strip()
            if supplied_objective and supplied_objective != plan_node["objective"]:
                raise WorkflowError(
                    "node objective must exactly match the current plan node objective"
                )
            objective = plan_node["objective"]
            warnings = self._granularity_warnings(objective)

            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if active:
                active_node = connection.execute(
                    "SELECT node_id FROM steps WHERE step_id = ?",
                    (active["step_id"],),
                ).fetchone()["node_id"]
                raise WorkflowError(f"run already has active node: {active_node}")

            completed_nodes = {
                row["node_id"]
                for row in connection.execute(
                    """
                    SELECT node_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    """,
                    (run_id,),
                ).fetchall()
            }
            if node_id in completed_nodes:
                raise WorkflowError(
                    f"current Plan Node is already completed: {node_id}"
                )
            missing_dependencies = sorted(
                set(plan_node["depends_on"]) - completed_nodes
            )
            if missing_dependencies:
                raise WorkflowError(
                    "complete Plan dependencies before starting this Node: "
                    + ", ".join(missing_dependencies)
                )

            sequence = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM steps WHERE run_id = ?", (run_id,)
                ).fetchone()["count"]
            ) + 1
            step_id = f"step_{sequence:03d}_{uuid.uuid4().hex[:6]}"
            connection.execute(
                """
                INSERT INTO steps(
                    step_id, run_id, node_id, plan_version, sequence, objective, target_data,
                    completion_condition, expected_output_roles_json, warnings_json,
                    status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, 'active', ?)
                """,
                (
                    step_id,
                    run_id,
                    node_id,
                    plan["version"],
                    sequence,
                    objective,
                    f"Record a truthful result for plan node {node_id}",
                    _json(["step_output"]),
                    _json(warnings),
                    utc_now(),
                ),
            )

            known_inputs = self._snapshot_eligible_inputs(
                connection, run_id, step_id
            )
            result_root = self._result_root(run)
            for artifact in self._scan_artifacts(result_root).values():
                connection.execute(
                    """
                    INSERT INTO artifact_baselines(step_id, path, sha256)
                    VALUES (?, ?, ?)
                    """,
                    (step_id, artifact["path"], artifact["sha256"]),
                )

        return {
            "step_id": step_id,
            "status": "active",
            "plan_version": plan["version"],
            "node_id": node_id,
            "objective": objective,
            "required_artifacts": list(
                plan_node.get("required_artifacts") or []
            ),
            "result_root": str(result_root),
            "artifact_filename_prefix": f"{node_id}_",
            "known_input_files": [
                {
                    "path": version["path"],
                    "sha256": version["sha256"],
                }
                for version in known_inputs
            ],
            "granularity_warnings": warnings,
        }

    def complete_step(
        self,
        step_id: str,
        input_files: Iterable[Union[Path, str]],
        operation_summary: str,
        result_summary: str,
        output_files: Optional[List[Union[Path, str, Dict[str, str]]]] = None,
        analysis_conclusion: Optional[str] = None,
        analysis_outcome: str = "not_assessed",
    ) -> Dict[str, Any]:
        operation_summary = operation_summary.strip()
        result_summary = result_summary.strip()
        if not operation_summary:
            raise WorkflowError("operation_summary cannot be empty")
        if not result_summary:
            raise WorkflowError("result_summary cannot be empty")
        if analysis_conclusion is not None:
            analysis_conclusion = analysis_conclusion.strip() or None
        analysis_outcome = (analysis_outcome or "not_assessed").strip().lower()
        if analysis_outcome not in ANALYSIS_OUTCOMES:
            analysis_outcome = "not_assessed"

        output_files = output_files or []
        with self._connection() as connection:
            step = connection.execute(
                "SELECT * FROM steps WHERE step_id = ?", (step_id,)
            ).fetchone()
            if step is None:
                raise WorkflowError(f"internal node execution does not exist: {step_id}")
            if step["status"] != "active":
                raise WorkflowError(f"node is not active: {step['node_id']}")
            run = self._require_active_run(connection, step["run_id"])
            project = Path(run["project_root"])
            plan = self._plan_revision(
                connection, step["run_id"], int(step["plan_version"])
            )
            plan_node = next(
                (
                    node
                    for node in plan["nodes"]
                    if node["node_id"] == step["node_id"]
                ),
                None,
            )
            if plan_node is None:
                raise WorkflowError(
                    f"node is missing from its plan revision: {step['node_id']}"
                )
            input_versions, dependency_warnings = self._record_actual_inputs(
                connection,
                step,
                plan_node,
                input_files,
                project,
            )
            input_version_ids = {
                version["file_version_id"] for version in input_versions
            }

            commands = self._observed_commands(connection, step_id)
            artifact_warnings: List[str] = []
            required_artifacts = list(
                plan_node.get("required_artifacts") or []
            )
            result_root = self._result_root(run)
            baseline = {
                row["path"]: row["sha256"]
                for row in connection.execute(
                    "SELECT path, sha256 FROM artifact_baselines WHERE step_id = ?",
                    (step_id,),
                ).fetchall()
            }
            current = self._scan_artifacts(result_root)
            changed = {
                path: artifact for path, artifact in current.items()
                if baseline.get(path) != artifact["sha256"]
            }
            created_paths = set(changed) - set(baseline)
            prefix = f"{step['node_id']}_"
            invalid_names = sorted(
                artifact["relative_path"] for path, artifact in changed.items()
                if path in created_paths
                and not Path(artifact["path"]).name.startswith(prefix)
            )
            if invalid_names:
                artifact_warnings.append(
                    "new artifacts do not use the recommended Node prefix: "
                    + ", ".join(invalid_names)
                )
            empty_files = sorted(
                artifact["relative_path"] for artifact in changed.values()
                if artifact["size"] == 0
            )
            if empty_files:
                artifact_warnings.append(
                    "empty artifacts were recorded: " + ", ".join(empty_files)
                )
            qualifying_categories = {
                artifact["category"] for artifact in changed.values()
                if Path(artifact["path"]).suffix.lower()
                in ARTIFACT_EXTENSIONS[artifact["category"]]
            }
            missing_categories = sorted(
                set(required_artifacts) - qualifying_categories
            )
            if missing_categories:
                artifact_warnings.append(
                    "planned artifact suggestions not produced: "
                    + ", ".join(missing_categories)
                )
            if not changed:
                artifact_warnings.append("node produced no new or changed artifacts")

            versions = []
            for artifact in sorted(changed.values(), key=lambda value: value["path"]):
                version = self._observe_file(connection, Path(artifact["path"]))
                if version["file_version_id"] in input_version_ids:
                    artifact_warnings.append(
                        "the same file version appeared as both input and output: "
                        + version["path"]
                    )
                    continue
                versions.append(version)
                connection.execute(
                    "INSERT OR IGNORE INTO step_outputs(step_id, file_version_id, role) "
                    "VALUES (?, ?, ?)",
                    (step_id, version["file_version_id"], artifact["category"]),
                )

            code_candidates = [
                Path(artifact["path"]) for artifact in changed.values()
                if artifact["category"] == "code"
            ] + [
                Path(version["path"]) for version in input_versions
                if Path(version["path"]).suffix.lower() in ARTIFACT_EXTENSIONS["code"]
            ]
            programs = self._canonical_programs(commands, code_candidates, project)
            connection.execute(
                """
                UPDATE steps SET
                    operation_summary = ?,
                    programs_json = ?,
                    commands_json = ?,
                    result_summary = ?,
                    analysis_conclusion = ?,
                    analysis_outcome = ?,
                    status = 'completed',
                    completed_at = ?
                WHERE step_id = ?
                """,
                (
                    operation_summary,
                    _json(programs),
                    _json(commands),
                    result_summary,
                    analysis_conclusion,
                    analysis_outcome,
                    utc_now(),
                    step_id,
                ),
            )
            all_warnings = [*dependency_warnings, *artifact_warnings]
            if all_warnings:
                existing_warnings = _from_json(step["warnings_json"], [])
                connection.execute(
                    "UPDATE steps SET warnings_json = ? WHERE step_id = ?",
                    (
                        _json(
                            list(
                                dict.fromkeys(
                                    [*existing_warnings, *all_warnings]
                                )
                            )
                        ),
                        step_id,
                    ),
                )
            latest_plan = self._latest_plan(connection, step["run_id"])
            completed_nodes = {
                row["node_id"]
                for row in connection.execute(
                    """
                    SELECT node_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    """,
                    (step["run_id"],),
                ).fetchall()
            }
            plan_is_complete = bool(latest_plan) and all(
                node["node_id"] in completed_nodes
                for node in latest_plan["nodes"]
            )
            checkpoint_mode = run["checkpoint_mode"] or "plan"
            if checkpoint_mode == "node" or (
                checkpoint_mode == "final" and plan_is_complete
            ):
                next_action = "pause-for-user"
            elif plan_is_complete:
                next_action = "wait-for-follow-up-or-new-task-trace"
            else:
                next_action = "review-plan-or-start-next-node"

        return {
            "step_id": step_id,
            "node_id": step["node_id"],
            "status": "completed",
            "input_file_versions": input_versions,
            "output_file_versions": versions,
            "observed_commands": commands,
            "observed_programs": programs,
            "analysis_outcome": analysis_outcome,
            "recording_warnings": all_warnings,
            "next_action": next_action,
        }

    def complete_node(
        self,
        run_id: str,
        node_id: str,
        input_files: Iterable[Union[Path, str]],
        operation_summary: str,
        result_summary: str,
        output_files: Optional[List[Union[Path, str, Dict[str, str]]]] = None,
        analysis_conclusion: Optional[str] = None,
        analysis_outcome: str = "not_assessed",
    ) -> Dict[str, Any]:
        """Complete the active execution of a public workflow Node."""

        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            row = connection.execute(
                """
                SELECT step_id FROM steps
                WHERE run_id = ? AND node_id = ? AND status = 'active'
                """,
                (run_id, node_id),
            ).fetchone()
            if row is None:
                raise WorkflowError(f"node is not active: {node_id}")
            step_id = row["step_id"]
        return self.complete_step(
            step_id=step_id,
            input_files=input_files,
            operation_summary=operation_summary,
            result_summary=result_summary,
            output_files=output_files,
            analysis_conclusion=analysis_conclusion,
            analysis_outcome=analysis_outcome,
        )

    def pause_for_user(self, run_id: str) -> Dict[str, Any]:
        """Open a human checkpoint without completing the Run."""

        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            checkpoint_mode = run["checkpoint_mode"] or "plan"
            if checkpoint_mode == "none":
                raise WorkflowError(
                    "this Run uses checkpoint mode 'none' and cannot pause"
                )
            if checkpoint_mode == "plan":
                raise WorkflowError(
                    "checkpoint mode 'plan' pauses automatically after the initial "
                    "Plan; analysis then runs without later checkpoints"
                )
            if run["awaiting_user"]:
                raise WorkflowError("the Run is already waiting for user input")
            active = connection.execute(
                "SELECT node_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if active:
                raise WorkflowError(
                    f"complete the active Node before pausing: {active['node_id']}"
                )
            unresolved = connection.execute(
                """
                SELECT COUNT(*) AS count FROM input_events
                WHERE run_id = ? AND status IN ('pending', 'classified')
                """,
                (run_id,),
            ).fetchone()["count"]
            if unresolved:
                raise WorkflowError(
                    "resolve existing user input before opening a checkpoint"
                )
            plan = self._latest_plan(connection, run_id)
            if plan is None:
                raise WorkflowError("set a Plan before opening a checkpoint")
            latest_completed = connection.execute(
                """
                SELECT step_id, node_id FROM steps
                WHERE run_id = ? AND status = 'completed'
                ORDER BY sequence DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            if latest_completed is None:
                raise WorkflowError(
                    "complete at least one Node before opening a checkpoint"
                )
            completed_nodes = {
                row["node_id"]
                for row in connection.execute(
                    """
                    SELECT node_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    """,
                    (run_id,),
                ).fetchall()
            }
            unfinished = [
                node["node_id"]
                for node in plan["nodes"]
                if node["node_id"] not in completed_nodes
            ]
            checkpoint_kind = (
                "node"
                if checkpoint_mode == "node"
                else "final" if not unfinished else "node"
            )
            if checkpoint_mode == "final" and checkpoint_kind != "final":
                raise WorkflowError(
                    "checkpoint mode 'final' pauses only after all current Plan "
                    "Nodes are complete"
                )
            if (
                checkpoint_mode == "node"
                and checkpoint_kind == "node"
                and run["checkpoint_approved_step_id"]
                == latest_completed["step_id"]
            ):
                raise WorkflowError(
                    "this completed Node checkpoint was already acknowledged"
                )
            now = utc_now()
            connection.execute(
                """
                UPDATE runs SET
                    awaiting_user = 1,
                    checkpoint_kind = ?,
                    checkpoint_step_id = ?,
                    checkpoint_created_at = ?,
                    final_approved_plan_version =
                        CASE WHEN ? = 'final' THEN NULL
                             ELSE final_approved_plan_version END
                WHERE run_id = ?
                """,
                (
                    checkpoint_kind,
                    latest_completed["step_id"],
                    now,
                    checkpoint_kind,
                    run_id,
                ),
            )
        return {
            "run_id": run_id,
            "status": "awaiting_user",
            "checkpoint": {
                "kind": checkpoint_kind,
                "node_id": latest_completed["node_id"],
                "plan_version": plan["version"],
                "created_at": now,
            },
            "instruction": (
                "End this Claude turn after presenting the completed work. "
                "The next user message will be recorded against this checkpoint."
            ),
        }

    def capture_user_input(
        self, run_id: str, original_text: str, claude_session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not original_text.strip():
            raise WorkflowError("user input cannot be empty")
        input_event_id = f"input_{uuid.uuid4().hex[:12]}"
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            active = connection.execute(
                """
                SELECT step_id FROM steps
                WHERE run_id = ? AND status = 'active'
                """,
                (run_id,),
            ).fetchone()
            plan = self._latest_plan(connection, run_id)
            checkpoint_kind = (
                run["checkpoint_kind"] if run["awaiting_user"] else None
            )
            target_step_id = (
                active["step_id"]
                if active
                else run["checkpoint_step_id"] if run["awaiting_user"] else None
            )
            connection.execute(
                """
                INSERT INTO input_events(
                    input_event_id, run_id, claude_session_id, original_text,
                    target_step_id, target_plan_version, checkpoint_kind,
                    status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    input_event_id,
                    run_id,
                    claude_session_id,
                    original_text,
                    target_step_id,
                    plan["version"] if plan else None,
                    checkpoint_kind,
                    utc_now(),
                ),
            )
            if run["awaiting_user"]:
                connection.execute(
                    "UPDATE runs SET awaiting_user = 0 WHERE run_id = ?",
                    (run_id,),
                )
        return {
            "input_event_id": input_event_id,
            "status": "pending",
            "checkpoint_kind": checkpoint_kind,
        }

    def classify_user_input(
        self,
        input_event_id: str,
        input_type: str,
        structured_summary: str = "",
        target_step_id: Optional[str] = None,
        target_plan_version: Optional[int] = None,
        workflow_effect: str = "",
    ) -> Dict[str, Any]:
        if input_type not in INPUT_TYPES:
            raise WorkflowError(f"invalid input type: {input_type}")
        with self._connection() as connection:
            event = connection.execute(
                "SELECT * FROM input_events WHERE input_event_id = ?",
                (input_event_id,),
            ).fetchone()
            if event is None:
                raise WorkflowError(f"input event does not exist: {input_event_id}")
            if event["status"] != "pending":
                raise WorkflowError(f"input event is already classified: {input_event_id}")
            if (
                input_type == "checkpoint_continue"
                and event["checkpoint_kind"] is None
            ):
                raise WorkflowError(
                    "checkpoint_continue is valid only for a checkpoint response"
                )
            if (
                input_type == "checkpoint_continue"
                and target_plan_version is not None
                and target_plan_version != event["target_plan_version"]
            ):
                raise WorkflowError(
                    "checkpoint confirmation must remain bound to the Plan version "
                    "shown to the user"
                )
            resolved_immediately = input_type in NON_CONTRIBUTION_INPUT_TYPES
            connection.execute(
                """
                UPDATE input_events SET
                    type = ?, target_step_id = COALESCE(?, target_step_id),
                    target_plan_version = COALESCE(?, target_plan_version),
                    structured_summary = ?, workflow_effect = ?,
                    status = ?, resolved_at = ?
                WHERE input_event_id = ?
                """,
                (
                    input_type,
                    target_step_id,
                    target_plan_version,
                    structured_summary,
                    workflow_effect,
                    "resolved" if resolved_immediately else "classified",
                    utc_now() if resolved_immediately else None,
                    input_event_id,
                ),
            )
            effective_plan_version = event["target_plan_version"]
            if target_plan_version is not None:
                effective_plan_version = target_plan_version
            if (
                input_type == "checkpoint_continue"
                and event["checkpoint_kind"] == "final"
            ):
                if effective_plan_version is None:
                    raise WorkflowError(
                        "a final checkpoint confirmation must target a Plan version"
                    )
                connection.execute(
                    """
                    UPDATE runs SET final_approved_plan_version = ?,
                        checkpoint_kind = NULL, checkpoint_step_id = NULL,
                        checkpoint_created_at = NULL
                    WHERE run_id = ?
                    """,
                    (effective_plan_version, event["run_id"]),
                )
            if (
                input_type == "checkpoint_continue"
                and event["checkpoint_kind"] == "plan"
            ):
                if effective_plan_version is None:
                    raise WorkflowError(
                        "a Plan checkpoint confirmation must target a Plan version"
                    )
                connection.execute(
                    """
                    UPDATE runs SET plan_approved_version = ?, plan_approved_at = ?,
                        checkpoint_kind = NULL, checkpoint_step_id = NULL,
                        checkpoint_created_at = NULL
                    WHERE run_id = ?
                    """,
                    (effective_plan_version, utc_now(), event["run_id"]),
                )
            if (
                input_type == "checkpoint_continue"
                and event["checkpoint_kind"] == "node"
            ):
                connection.execute(
                    """
                    UPDATE runs SET checkpoint_approved_step_id = ?,
                        checkpoint_kind = NULL, checkpoint_step_id = NULL,
                        checkpoint_created_at = NULL
                    WHERE run_id = ?
                    """,
                    (event["target_step_id"], event["run_id"]),
                )
        status = "resolved" if resolved_immediately else "classified"
        return {
            "input_event_id": input_event_id,
            "type": input_type,
            "status": status,
            "creates_human_contribution": (
                input_type not in NON_CONTRIBUTION_INPUT_TYPES
            ),
            "requires_apply": not resolved_immediately,
        }

    def apply_user_input(
        self,
        input_event_id: str,
        workflow_effect: str,
        target_step_id: Optional[str] = None,
        target_plan_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        workflow_effect = workflow_effect.strip()
        if not workflow_effect:
            raise WorkflowError("workflow_effect cannot be empty")
        with self._connection() as connection:
            event = connection.execute(
                "SELECT * FROM input_events WHERE input_event_id = ?",
                (input_event_id,),
            ).fetchone()
            if event is None:
                raise WorkflowError(f"input event does not exist: {input_event_id}")
            if event["status"] != "classified":
                raise WorkflowError(
                    f"input event must be classified before apply: {input_event_id}"
                )
            connection.execute(
                """
                UPDATE input_events SET
                    target_step_id = COALESCE(?, target_step_id),
                    target_plan_version = COALESCE(?, target_plan_version),
                    workflow_effect = ?, status = 'applied', resolved_at = ?
                WHERE input_event_id = ?
                """,
                (
                    target_step_id,
                    target_plan_version,
                    workflow_effect,
                    utc_now(),
                    input_event_id,
                ),
            )
        return {
            "input_event_id": input_event_id,
            "status": "applied",
            "workflow_effect": workflow_effect,
        }

    def record_applied_user_input(
        self,
        run_id: str,
        original_text: str,
        input_type: str,
        workflow_effect: str,
        claude_session_id: Optional[str] = None,
        target_plan_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record a structured Web intervention that is already fully applied."""

        original_text = original_text.strip()
        workflow_effect = workflow_effect.strip()
        if not original_text:
            raise WorkflowError("user input cannot be empty")
        if not workflow_effect:
            raise WorkflowError("workflow_effect cannot be empty")
        if input_type not in {
            "analysis_guidance",
            "planning_input",
            "challenge",
        }:
            raise WorkflowError(f"invalid applied input type: {input_type}")

        input_event_id = f"input_{uuid.uuid4().hex[:12]}"
        now = utc_now()
        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            active = connection.execute(
                """
                SELECT step_id FROM steps
                WHERE run_id = ? AND status = 'active'
                """,
                (run_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO input_events(
                    input_event_id, run_id, claude_session_id, original_text,
                    type, target_step_id, target_plan_version,
                    structured_summary, workflow_effect, status,
                    created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied', ?, ?)
                """,
                (
                    input_event_id,
                    run_id,
                    claude_session_id,
                    original_text,
                    input_type,
                    active["step_id"] if active else None,
                    target_plan_version,
                    original_text,
                    workflow_effect,
                    now,
                    now,
                ),
            )
        return {
            "input_event_id": input_event_id,
            "type": input_type,
            "status": "applied",
            "workflow_effect": workflow_effect,
        }

    def record_hook_event(
        self, run_id: str, hook_event_name: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        event_id = f"event_{uuid.uuid4().hex[:12]}"
        tool_name = payload.get("tool_name")
        with self._connection() as connection:
            self._require_run(connection, run_id)
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hook_events(
                    event_id, run_id, step_id, hook_event_name, tool_name,
                    payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    active["step_id"] if active else None,
                    hook_event_name,
                    tool_name,
                    _json(payload),
                    utc_now(),
                ),
            )
        return {"event_id": event_id, "step_id": active["step_id"] if active else None}

    def freeze_active_input(self, run_id: str, raw_path: Union[Path, str]) -> None:
        """Freeze a file version immediately before a material file tool uses it."""

        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if active is None:
                return
            path = self._resolve_path(raw_path, Path(run["project_root"]))
            if not path.is_file():
                return
            result_root = self._result_root(run)
            try:
                path.relative_to(result_root)
            except ValueError:
                existed_at_start = True
            else:
                existed_at_start = connection.execute(
                    """
                    SELECT 1 FROM artifact_baselines
                    WHERE step_id = ? AND path = ?
                    """,
                    (active["step_id"], str(path)),
                ).fetchone() is not None
            if not existed_at_start:
                # A file created by the current Node remains an output even when
                # the same Node reads it again as an intermediate artifact.
                return
            version = self._observe_file(connection, path)
            connection.execute(
                """
                INSERT OR REPLACE INTO input_baselines(step_id, path, file_version_id)
                VALUES (?, ?, ?)
                """,
                (active["step_id"], str(path), version["file_version_id"]),
            )
            try:
                path.relative_to(self._result_root(run))
            except ValueError:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO run_inputs(run_id, file_version_id)
                    VALUES (?, ?)
                    """,
                    (run_id, version["file_version_id"]),
                )

    def finish_run(self, run_id: str) -> Dict[str, Any]:
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            if run["awaiting_user"]:
                raise WorkflowError(
                    "the Run is waiting for user input at a checkpoint"
                )
            plan = self._latest_plan(connection, run_id)
            if plan is None:
                raise WorkflowError("cannot finish a run without a plan")
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if active:
                node = connection.execute(
                    "SELECT node_id FROM steps WHERE step_id = ?",
                    (active["step_id"],),
                ).fetchone()
                raise WorkflowError(f"complete active node first: {node['node_id']}")
            pending = connection.execute(
                "SELECT COUNT(*) AS count FROM input_events "
                "WHERE run_id = ? AND status IN ('pending', 'classified')",
                (run_id,),
            ).fetchone()["count"]
            if pending:
                raise WorkflowError("classify pending user input before finishing the run")
            step_count = connection.execute(
                "SELECT COUNT(*) AS count FROM steps "
                "WHERE run_id = ? AND status = 'completed'",
                (run_id,),
            ).fetchone()["count"]
            if not step_count:
                raise WorkflowError("cannot finish a run without completed nodes")
            completed_nodes = {
                row["node_id"]
                for row in connection.execute(
                    """
                    SELECT node_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    """,
                    (run_id,),
                ).fetchall()
            }
            unfinished = [
                node["node_id"]
                for node in plan["nodes"]
                if node["node_id"] not in completed_nodes
            ]
            if unfinished:
                raise WorkflowError(
                    "complete every node in the current plan before finishing: "
                    + ", ".join(unfinished)
                )
            checkpoint_mode = run["checkpoint_mode"] or "plan"
            if (
                checkpoint_mode in {"plan", "node"}
                and run["plan_approved_version"] != plan["version"]
            ):
                raise WorkflowError(
                    "obtain user approval for the current Plan Revision before "
                    "finishing"
                )
            if checkpoint_mode == "node":
                latest_completed = connection.execute(
                    """
                    SELECT step_id FROM steps
                    WHERE run_id = ? AND status = 'completed'
                    ORDER BY sequence DESC LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()
                if (
                    latest_completed
                    and run["checkpoint_approved_step_id"]
                    != latest_completed["step_id"]
                ):
                    raise WorkflowError(
                        "obtain user confirmation for the last completed Node "
                        "before finishing"
                    )
            if (
                checkpoint_mode == "final"
                and run["final_approved_plan_version"] != plan["version"]
            ):
                raise WorkflowError(
                    "open a final checkpoint with pause-for-user and obtain an "
                    "explicit user confirmation before finishing the Run"
                )
            invalid_steps = connection.execute(
                """
                SELECT COUNT(*) AS count FROM steps
                WHERE run_id = ? AND status != 'completed'
                """,
                (run_id,),
            ).fetchone()["count"]
            if invalid_steps:
                raise WorkflowError(
                    "a successful run cannot contain interrupted or failed steps"
                )
            artifact_rows = connection.execute(
                """
                SELECT f.path, f.sha256, o.role, s.sequence
                FROM step_outputs o
                JOIN steps s ON s.step_id = o.step_id
                JOIN file_versions f ON f.file_version_id = o.file_version_id
                WHERE s.run_id = ? AND s.status = 'completed'
                ORDER BY s.sequence DESC
                """,
                (run_id,),
            ).fetchall()
            stale_artifacts = []
            checked_paths = set()
            for artifact_row in artifact_rows:
                path = Path(artifact_row["path"])
                normalized = os.path.normcase(str(path.resolve()))
                if normalized in checked_paths:
                    continue
                checked_paths.add(normalized)
                if (
                    not path.is_file()
                    or self._sha256(path) != artifact_row["sha256"]
                ):
                    stale_artifacts.append(str(path))
            if stale_artifacts:
                raise WorkflowError(
                    "the latest recorded versions of artifacts were removed or "
                    "changed outside a later completed Node: "
                    + ", ".join(sorted(stale_artifacts))
                )
            completed_at = utc_now()
            connection.execute(
                "UPDATE runs SET status = 'completed', completed_at = ? WHERE run_id = ?",
                (completed_at, run_id),
            )
            connection.execute(
                """
                UPDATE session_bindings SET status = 'released', released_at = ?,
                    release_reason = 'run_completed'
                WHERE run_id = ? AND status = 'active'
                """,
                (completed_at, run_id),
            )
        return {"run_id": run_id, "status": "completed", "completed_at": completed_at}

    def abort_run(self, run_id: str, reason: str) -> Dict[str, Any]:
        """Abort an unusable Run without deleting its truthful history."""

        reason = reason.strip()
        if not reason:
            raise WorkflowError("abort reason cannot be empty")
        completed_at = utc_now()
        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            connection.execute(
                """
                UPDATE steps SET status = 'interrupted', completed_at = ?
                WHERE run_id = ? AND status = 'active'
                """,
                (completed_at, run_id),
            )
            connection.execute(
                """
                UPDATE runs SET status = 'aborted', completed_at = ?
                WHERE run_id = ?
                """,
                (completed_at, run_id),
            )
            connection.execute(
                """
                UPDATE session_bindings SET status = 'released', released_at = ?,
                    release_reason = 'run_aborted'
                WHERE run_id = ? AND status = 'active'
                """,
                (completed_at, run_id),
            )
            event_id = f"event_{uuid.uuid4().hex[:12]}"
            connection.execute(
                """
                INSERT INTO hook_events(
                    event_id, run_id, step_id, hook_event_name, tool_name,
                    payload_json, created_at
                ) VALUES (?, ?, NULL, 'RunAborted', NULL, ?, ?)
                """,
                (event_id, run_id, _json({"reason": reason}), completed_at),
            )
        return {
            "run_id": run_id,
            "status": "aborted",
            "reason": reason,
            "completed_at": completed_at,
        }

    def get_state(self, run_id: str) -> Dict[str, Any]:
        with self._connection() as connection:
            run = self._require_run(connection, run_id)
            plan = self._latest_plan(connection, run_id)
            steps = connection.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
            pending_inputs = connection.execute(
                """
                SELECT input_event_id, original_text, type, status, created_at
                FROM input_events
                WHERE run_id = ? AND status IN ('pending', 'classified')
                ORDER BY created_at
                """,
                (run_id,),
            ).fetchall()
            initial_files = connection.execute(
                """
                SELECT f.* FROM file_versions f
                JOIN run_inputs i ON i.file_version_id = f.file_version_id
                WHERE i.run_id = ?
                """,
                (run_id,),
            ).fetchall()
            node_values = [self._state_node_dict(connection, row) for row in steps]
            if plan:
                statuses = {
                    item["node_id"]: item["status"]
                    for item in node_values
                    if item["status"] in {"active", "completed"}
                }
                plan["nodes"] = [
                    {**node, "status": statuses.get(node["node_id"], "pending")}
                    for node in plan["nodes"]
                ]
            run_value = dict(run)
            if run["status"] != "active":
                phase = str(run["status"])
            elif run["awaiting_user"]:
                checkpoint_kind = str(run["checkpoint_kind"] or "checkpoint")
                phase = (
                    "plan_review"
                    if checkpoint_kind == "plan"
                    else "node_review"
                    if checkpoint_kind == "node"
                    else "checkpoint"
                )
            elif pending_inputs:
                phase = "handling_input"
            elif plan is None:
                phase = "planning"
            elif any(node["status"] == "active" for node in node_values):
                phase = "executing"
            elif plan["nodes"] and all(
                node["status"] == "completed" for node in plan["nodes"]
            ):
                phase = "idle"
            else:
                phase = "ready"
            run_value["phase"] = phase
            run_value["result_root"] = str(self._result_root(run))
            run_value["workflow_path"] = str(
                self._result_root(run) / "workflow.json"
            )
            run_value["checkpoint_node_id"] = self._node_id_for_step(
                connection, run["checkpoint_step_id"]
            )
            run_value["checkpoint_approved_node_id"] = self._node_id_for_step(
                connection, run["checkpoint_approved_step_id"]
            )
            return {
                "run": {
                    **run_value,
                    "initial_file_versions": [dict(row) for row in initial_files],
                },
                "plan": plan,
                "nodes": node_values,
                "pending_user_inputs": [dict(row) for row in pending_inputs],
            }

    def export_run(
        self, run_id: str, output_path: Optional[Union[Path, str]] = None
    ) -> Path:
        with self._connection() as connection:
            exported = self._normalized_export(connection, run_id)
            run = self._require_run(connection, run_id)

        if output_path is None:
            output_path = self._result_root(run) / "workflow.json"
        destination = Path(output_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(_json(exported), encoding="utf-8")
        return destination

    def _normalized_export(
        self, connection: sqlite3.Connection, run_id: str
    ) -> Dict[str, Any]:
        run = self._require_run(connection, run_id)
        project = Path(run["project_root"])
        initial_files = connection.execute(
            """
            SELECT f.* FROM file_versions f
            JOIN run_inputs i ON i.file_version_id = f.file_version_id
            WHERE i.run_id = ? ORDER BY f.path
            """,
            (run_id,),
        ).fetchall()
        plans = connection.execute(
            """
            SELECT * FROM plan_revisions
            WHERE run_id = ? ORDER BY version
            """,
            (run_id,),
        ).fetchall()
        step_rows = connection.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall()
        interventions = connection.execute(
            """
            SELECT * FROM input_events
            WHERE run_id = ? AND type IS NOT NULL
              AND type NOT IN ('conversation_only', 'checkpoint_continue')
            ORDER BY created_at
            """,
            (run_id,),
        ).fetchall()

        nodes: List[Dict[str, Any]] = []
        lineage: List[Dict[str, Any]] = []
        for row in step_rows:
            inputs = self._step_file_refs(connection, row["step_id"], "input", project)
            outputs = self._step_file_refs(
                connection, row["step_id"], "output", project
            )
            commands = _from_json(row["commands_json"], [])
            programs = [
                self._public_path(Path(path), project)
                for path in _from_json(row["programs_json"], [])
            ]
            result_summary = row["result_summary"]
            if not result_summary:
                legacy_result = _from_json(row["processing_result_json"], {})
                result_summary = self._legacy_summary(legacy_result)
            conclusion = row["analysis_conclusion"]
            if conclusion is None:
                legacy_conclusion = _from_json(
                    row["analysis_conclusion_json"], {}
                )
                conclusion = self._legacy_summary(legacy_conclusion) or None
            nodes.append(
                {
                    "node_id": row["node_id"],
                    "sequence": row["sequence"],
                    "plan_version": row["plan_version"],
                    "objective": row["objective"],
                    "inputs": inputs,
                    "operation": {
                        "summary": row["operation_summary"],
                        "commands": commands,
                        "programs": programs,
                    },
                    "outputs": outputs,
                    "result_summary": result_summary,
                    "analysis_conclusion": conclusion,
                    "analysis_outcome": row["analysis_outcome"] or "not_assessed",
                    "recording_warnings": _from_json(row["warnings_json"], []),
                    "status": row["status"],
                    "started_at": row["started_at"],
                    "completed_at": row["completed_at"],
                }
            )
            if outputs:
                lineage.append(
                    {
                        "node_id": row["node_id"],
                        "inputs": inputs,
                        "outputs": outputs,
                    }
                )

        return {
            "schema_version": "1.3",
            "run": {
                "run_id": run["run_id"],
                "task": run["task_description"],
                "project_root": run["project_root"],
                "result_root": self._public_path(
                    self._result_root(run), project
                ),
                "agent": "claude-code",
                "session_id": run["claude_session_id"],
                "status": run["status"],
                "analysis_outcome": run["analysis_outcome"] or self._run_outcome(
                    [node["analysis_outcome"] for node in nodes]
                ),
                "started_at": run["started_at"],
                "completed_at": run["completed_at"],
                "declared_inputs": [
                    self._public_file_ref(dict(item), project)
                    for item in initial_files
                ],
            },
            "plan_revisions": [
                {
                    "version": row["version"],
                    "created_at": row["created_at"],
                    "trigger": row["trigger_kind"]
                    or ("initial" if row["version"] == 1 else "agent_replan"),
                    "change_reason": row["reason"],
                    "nodes": [
                        {
                            "node_id": node["node_id"],
                            "objective": node["objective"],
                            "depends_on": list(node.get("depends_on") or []),
                            "required_artifacts": list(
                                node.get("required_artifacts") or []
                            ),
                        }
                        for node in _from_json(row["nodes_json"], [])
                    ],
                }
                for row in plans
            ],
            "nodes": nodes,
            "human_interventions": [
                {
                    "intervention_id": row["input_event_id"],
                    "original_text": row["original_text"],
                    "type": row["type"],
                    "active_node_id": self._node_id_for_step(
                        connection, row["target_step_id"]
                    ),
                    "plan_version": row["target_plan_version"],
                    "workflow_effect": row["workflow_effect"],
                    "created_at": row["created_at"],
                    "applied_at": row["resolved_at"],
                }
                for row in interventions
            ],
            "file_lineage": lineage,
        }

    @staticmethod
    def _run_outcome(node_outcomes: Iterable[str]) -> str:
        values = [value for value in node_outcomes if value and value != "not_assessed"]
        if not values:
            return "not_assessed"
        for outcome in ("failed", "blocked", "insufficient_data", "partial"):
            if outcome in values:
                return outcome
        return "answered" if all(value == "answered" for value in values) else values[-1]

    def _step_file_refs(
        self,
        connection: sqlite3.Connection,
        step_id: str,
        direction: str,
        project: Path,
    ) -> List[Dict[str, str]]:
        if direction == "input":
            rows = connection.execute(
                """
                SELECT f.* FROM file_versions f
                JOIN step_inputs i ON i.file_version_id = f.file_version_id
                WHERE i.step_id = ? ORDER BY f.path
                """,
                (step_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT f.* FROM file_versions f
                JOIN step_outputs o ON o.file_version_id = f.file_version_id
                WHERE o.step_id = ? ORDER BY f.path
                """,
                (step_id,),
            ).fetchall()
        return [self._public_file_ref(dict(row), project) for row in rows]

    def gate_reason(self, run_id: str) -> Optional[str]:
        """Return why a material Claude tool call should be blocked, if any."""
        with self._connection() as connection:
            run = self._require_run(connection, run_id)
            if run["status"] != "active":
                return f"AgentVAST run is {run['status']}"
            if run["awaiting_user"]:
                return "AgentVAST is waiting for user input at a checkpoint"
            pending = connection.execute(
                "SELECT input_event_id, status FROM input_events "
                "WHERE run_id = ? AND status IN ('pending', 'classified') "
                "ORDER BY created_at LIMIT 1",
                (run_id,),
            ).fetchone()
            if pending:
                if pending["status"] == "classified":
                    return (
                        "Run: python -m agentvast.agent_cli apply-user-input "
                        f"{pending['input_event_id']} "
                        "\"REAL_WORKFLOW_EFFECT\""
                    )
                return (
                    "Run: python -m agentvast.agent_cli classify-user-input "
                    f"{pending['input_event_id']} INPUT_TYPE; replace INPUT_TYPE "
                    "with conversation_only, checkpoint_continue, "
                    "analysis_guidance, planning_input, or challenge"
                )
            plan = self._latest_plan(connection, run_id)
            if plan is None:
                return "Set an AgentVAST plan before material analysis work"
            checkpoint_mode = run["checkpoint_mode"] or "plan"
            if (
                checkpoint_mode in {"plan", "node"}
                and run["plan_approved_version"] != plan["version"]
            ):
                return (
                    "Present the current Plan Revision and wait for explicit user "
                    "approval before material analysis"
                )
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if not active:
                if checkpoint_mode == "node":
                    latest_completed = connection.execute(
                        """
                        SELECT step_id FROM steps
                        WHERE run_id = ? AND status = 'completed'
                        ORDER BY sequence DESC LIMIT 1
                        """,
                        (run_id,),
                    ).fetchone()
                    if (
                        latest_completed
                        and run["checkpoint_approved_step_id"]
                        != latest_completed["step_id"]
                    ):
                        return (
                            "Open a user checkpoint with python -m "
                            "agentvast.agent_cli pause-for-user before the next Node"
                        )
                return "Start a semantic AgentVAST node before material analysis work"
        return None

    def _step_dict(self, connection: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
        value = dict(row)
        json_fields = {
            "expected_output_roles_json": ("expected_output_roles", []),
            "operation_types_json": ("operation_types", []),
            "parameters_json": ("parameters", {}),
            "algorithms_json": ("algorithms", []),
            "programs_json": ("programs", []),
            "commands_json": ("commands", []),
            "processing_result_json": ("processing_result", {}),
            "warnings_json": ("warnings", []),
        }
        for key, (output_key, default) in json_fields.items():
            value[output_key] = _from_json(value.pop(key), default)
        legacy_conclusion = _from_json(
            value.pop("analysis_conclusion_json"), {}
        )
        if value.get("analysis_conclusion") is None:
            value["analysis_conclusion"] = (
                self._legacy_summary(legacy_conclusion) or None
            )

        inputs = connection.execute(
            """
            SELECT f.* FROM file_versions f
            JOIN step_inputs i ON i.file_version_id = f.file_version_id
            WHERE i.step_id = ?
            """,
            (row["step_id"],),
        ).fetchall()
        outputs = connection.execute(
            """
            SELECT f.*, o.role FROM file_versions f
            JOIN step_outputs o ON o.file_version_id = f.file_version_id
            WHERE o.step_id = ?
            """,
            (row["step_id"],),
        ).fetchall()
        value["input_files"] = [dict(item) for item in inputs]
        value["output_files"] = [dict(item) for item in outputs]
        return value

    def _state_node_dict(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> Dict[str, Any]:
        value = self._step_dict(connection, row)
        value.pop("step_id", None)
        return value

    @staticmethod
    def _node_id_for_step(
        connection: sqlite3.Connection, step_id: Optional[str]
    ) -> Optional[str]:
        if not step_id:
            return None
        row = connection.execute(
            "SELECT node_id FROM steps WHERE step_id = ?",
            (step_id,),
        ).fetchone()
        return row["node_id"] if row else None

    def _latest_plan(
        self, connection: sqlite3.Connection, run_id: str
    ) -> Optional[Dict[str, Any]]:
        row = connection.execute(
            """
            SELECT * FROM plan_revisions
            WHERE run_id = ? ORDER BY version DESC LIMIT 1
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "version": row["version"],
            "nodes": _from_json(row["nodes_json"], []),
            "trigger": row["trigger_kind"]
            or ("initial" if row["version"] == 1 else "agent_replan"),
            "change_reason": row["reason"],
            "created_at": row["created_at"],
        }

    def _plan_revision(
        self, connection: sqlite3.Connection, run_id: str, version: int
    ) -> Dict[str, Any]:
        row = connection.execute(
            """
            SELECT * FROM plan_revisions
            WHERE run_id = ? AND version = ?
            """,
            (run_id, version),
        ).fetchone()
        if row is None:
            raise WorkflowError(
                f"plan revision does not exist: run={run_id}, version={version}"
            )
        return {
            "version": row["version"],
            "nodes": _from_json(row["nodes_json"], []),
            "trigger": row["trigger_kind"],
            "change_reason": row["reason"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _result_root(run: sqlite3.Row) -> Path:
        raw_path = run["result_root"] if "result_root" in run.keys() else None
        if raw_path:
            return Path(raw_path).resolve()
        return (Path(run["project_root"]) / "result" / run["run_id"]).resolve()

    @classmethod
    def _scan_artifacts(cls, result_root: Path) -> Dict[str, Dict[str, Any]]:
        artifacts: Dict[str, Dict[str, Any]] = {}
        for category in ARTIFACT_CATEGORIES:
            category_root = result_root / category
            if not category_root.is_dir():
                continue
            for path in category_root.rglob("*"):
                if not path.is_file():
                    continue
                relative_source = path.relative_to(category_root)
                if (
                    "__pycache__" in path.parts
                    or path.suffix.lower() in {".pyc", ".pyo"}
                    or any(
                        part.startswith(".") for part in relative_source.parts
                    )
                ):
                    continue
                resolved = path.resolve()
                try:
                    relative_path = resolved.relative_to(result_root.resolve())
                except ValueError:
                    continue
                artifacts[str(resolved)] = {
                    "path": str(resolved),
                    "relative_path": relative_path.as_posix(),
                    "category": category,
                    "sha256": cls._sha256(resolved),
                    "size": resolved.stat().st_size,
                }
        return artifacts

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_plan_is_acyclic(nodes: List[Dict[str, Any]]) -> None:
        dependencies = {
            node["node_id"]: set(node["depends_on"]) for node in nodes
        }
        visiting = set()
        visited = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise WorkflowError("plan dependencies must form an acyclic graph")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in dependencies[node_id]:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in dependencies:
            visit(node_id)

    def _snapshot_eligible_inputs(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        step_id: str,
    ) -> List[Dict[str, Any]]:
        """Freeze file versions that may truthfully be claimed at completion."""

        rows = connection.execute(
            """
            SELECT f.*
            FROM file_versions f
            JOIN (
                SELECT file_version_id FROM run_inputs WHERE run_id = ?
                UNION
                SELECT o.file_version_id
                FROM step_outputs o
                JOIN steps s ON s.step_id = o.step_id
                WHERE s.run_id = ? AND s.status = 'completed'
            ) allowed ON allowed.file_version_id = f.file_version_id
            ORDER BY f.observed_at DESC
            """,
            (run_id, run_id),
        ).fetchall()
        rows_by_path: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            normalized = str(Path(row["path"]).resolve())
            rows_by_path.setdefault(normalized, []).append(row)

        snapshots: List[Dict[str, Any]] = []
        for normalized, versions in rows_by_path.items():
            path = Path(normalized)
            if not path.is_file():
                continue
            current_sha256 = self._sha256(path)
            matching = next(
                (row for row in versions if row["sha256"] == current_sha256),
                None,
            )
            if matching is None:
                continue
            connection.execute(
                """
                INSERT INTO input_baselines(step_id, path, file_version_id)
                VALUES (?, ?, ?)
                """,
                (step_id, normalized, matching["file_version_id"]),
            )
            snapshots.append(dict(matching))
        return sorted(snapshots, key=lambda value: value["path"])

    def _record_actual_inputs(
        self,
        connection: sqlite3.Connection,
        step: sqlite3.Row,
        plan_node: Dict[str, Any],
        input_files: Iterable[Union[Path, str]],
        project: Path,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Record files actually used, without requiring advance registration.

        For a known file we preserve the version frozen at Node start. A newly
        discovered external file is observed at completion and becomes a Run
        input. New artifacts created by the current Node are outputs, not inputs.
        """

        submitted_paths = list(input_files)
        submitted_paths.extend(
            self._observed_file_inputs(connection, step["step_id"], project)
        )
        input_warnings: List[str] = []
        if not submitted_paths:
            input_warnings.append(
                "no file input was reported or observed for this Node"
            )

        baseline_rows = connection.execute(
            """
            SELECT b.path AS baseline_path, f.*
            FROM input_baselines b
            JOIN file_versions f ON f.file_version_id = b.file_version_id
            WHERE b.step_id = ?
            """,
            (step["step_id"],),
        ).fetchall()
        if not baseline_rows:
            # Compatibility for a Node started before input_baselines was introduced.
            baseline_rows = connection.execute(
                """
                SELECT f.path AS baseline_path, f.*
                FROM step_inputs i
                JOIN file_versions f ON f.file_version_id = i.file_version_id
                WHERE i.step_id = ?
                """,
                (step["step_id"],),
            ).fetchall()

        baselines = {
            os.path.normcase(str(Path(row["baseline_path"]).resolve())): dict(row)
            for row in baseline_rows
        }
        result_root = self._result_root(
            self._require_run(connection, step["run_id"])
        )
        selected: List[Dict[str, Any]] = []
        seen_paths = set()
        for submitted in submitted_paths:
            try:
                path = self._resolve_file(submitted, project)
            except (OSError, WorkflowError) as error:
                input_warnings.append(
                    f"input could not be versioned and was omitted: {submitted} ({error})"
                )
                continue
            normalized = os.path.normcase(str(path))
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            version = baselines.get(normalized)
            if version is not None:
                version = dict(version)
            else:
                try:
                    path.relative_to(result_root)
                except ValueError:
                    version = self._observe_file(connection, path)
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO run_inputs(run_id, file_version_id)
                        VALUES (?, ?)
                        """,
                        (step["run_id"], version["file_version_id"]),
                    )
                else:
                    input_warnings.append(
                        "a newly created Run artifact was reported as an input and "
                        "was retained only as an output: " + str(path)
                    )
                    continue
            version.pop("baseline_path", None)
            selected.append(version)

        connection.execute(
            "DELETE FROM step_inputs WHERE step_id = ?", (step["step_id"],)
        )
        for version in selected:
            connection.execute(
                "INSERT INTO step_inputs(step_id, file_version_id) VALUES (?, ?)",
                (step["step_id"], version["file_version_id"]),
            )

        selected_version_ids = {
            version["file_version_id"] for version in selected
        }
        dependency_rows = connection.execute(
            """
            SELECT s.node_id, o.file_version_id
            FROM step_outputs o
            JOIN steps s ON s.step_id = o.step_id
            WHERE s.run_id = ? AND s.status = 'completed'
            """,
            (step["run_id"],),
        ).fetchall()
        contributed_by = {
            row["node_id"]
            for row in dependency_rows
            if row["file_version_id"] in selected_version_ids
        }
        dependency_warnings = [
            (
                f"Plan dependency {dependency} supplied no actual file input to "
                f"{step['node_id']}; this is allowed as a semantic dependency."
            )
            for dependency in plan_node.get("depends_on") or []
            if dependency not in contributed_by
        ]
        return selected, [*input_warnings, *dependency_warnings]

    @staticmethod
    def _observed_file_inputs(
        connection: sqlite3.Connection, step_id: str, project: Path
    ) -> List[str]:
        rows = connection.execute(
            """
            SELECT tool_name, payload_json FROM hook_events
            WHERE step_id = ? AND hook_event_name = 'PostToolUse'
            ORDER BY created_at
            """,
            (step_id,),
        ).fetchall()
        baseline_paths = {
            os.path.normcase(str(Path(row["path"]).resolve()))
            for row in connection.execute(
                "SELECT path FROM input_baselines WHERE step_id = ?",
                (step_id,),
            ).fetchall()
        }
        paths: List[str] = []
        fields = {
            "Read": "file_path",
            "Edit": "file_path",
            "MultiEdit": "file_path",
            "NotebookEdit": "notebook_path",
        }
        for row in rows:
            payload = _from_json(row["payload_json"], {})
            tool_name = str(row["tool_name"] or payload.get("tool_name") or "")
            field = fields.get(tool_name)
            if field:
                value = (payload.get("tool_input") or {}).get(field)
                if isinstance(value, str) and value.strip():
                    path = WorkflowStore._resolve_path(value, project)
                    if path.is_file():
                        paths.append(str(path))
        return list(dict.fromkeys(paths))

    @staticmethod
    def _observed_commands(
        connection: sqlite3.Connection,
        step_id: str,
    ) -> List[str]:
        rows = connection.execute(
            """
            SELECT tool_name, payload_json FROM hook_events
            WHERE step_id = ? AND hook_event_name = 'PostToolUse'
            ORDER BY created_at
            """,
            (step_id,),
        ).fetchall()
        commands: List[str] = []
        for row in rows:
            payload = _from_json(row["payload_json"], {})
            tool_input = payload.get("tool_input") or {}
            tool_name = str(row["tool_name"] or payload.get("tool_name") or "")
            if tool_name in {"Bash", "PowerShell"}:
                command = str(tool_input.get("command") or "").strip()
                if command:
                    commands.append(command)
        return list(dict.fromkeys(commands))

    @staticmethod
    def _canonical_programs(
        commands: Iterable[str],
        candidates: Iterable[Path],
        project: Path,
    ) -> List[str]:
        """Match successful commands to real code files without guessing cwd."""

        normalized_candidates: List[Path] = []
        seen = set()
        for candidate in candidates:
            path = candidate.resolve()
            key = os.path.normcase(str(path))
            if key not in seen:
                normalized_candidates.append(path)
                seen.add(key)

        basename_counts: Dict[str, int] = {}
        for path in normalized_candidates:
            basename = path.name.lower()
            basename_counts[basename] = basename_counts.get(basename, 0) + 1

        execution_pattern = re.compile(
            r"(?:^|[;&|]\s*)(?:&\s*)?"
            r"(?:(?:uv|poetry)\s+run\s+)?"
            r"(?:python(?:3(?:\.\d+)*)?(?:\.exe)?|py|ipython|jupyter)\b",
            re.IGNORECASE,
        )
        normalized_commands = [
            str(command).replace("\\", "/").lower()
            for command in commands
            if execution_pattern.search(str(command))
        ]
        matched: List[str] = []
        for path in normalized_candidates:
            aliases = {str(path).replace("\\", "/").lower()}
            try:
                aliases.add(path.relative_to(project).as_posix().lower())
            except ValueError:
                pass
            if basename_counts[path.name.lower()] == 1:
                aliases.add(path.name.lower())
            if any(
                alias and alias in command
                for alias in aliases
                for command in normalized_commands
            ):
                matched.append(str(path))
        return matched

    @staticmethod
    def _legacy_summary(value: Any) -> str:
        if value in (None, {}, []):
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("summary"), str):
            return value["summary"]
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _public_file_ref(value: Dict[str, Any], project: Path) -> Dict[str, str]:
        return {
            "path": WorkflowStore._public_path(Path(value["path"]), project),
            "sha256": value["sha256"],
        }

    @staticmethod
    def _public_path(path: Path, project: Path) -> str:
        try:
            return path.relative_to(project).as_posix()
        except ValueError:
            return str(path)

    def _require_run(self, connection: sqlite3.Connection, run_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise WorkflowError(f"run does not exist: {run_id}")
        return row

    def _require_active_run(
        self, connection: sqlite3.Connection, run_id: str
    ) -> sqlite3.Row:
        row = self._require_run(connection, run_id)
        if row["status"] != "active":
            raise WorkflowError(f"run is not active: {run_id}")
        return row

    def _observe_file(
        self, connection: sqlite3.Connection, path: Path
    ) -> Dict[str, Any]:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
        existing = connection.execute(
            "SELECT * FROM file_versions WHERE path = ? AND sha256 = ?",
            (str(path), sha256),
        ).fetchone()
        if existing:
            return dict(existing)
        value = {
            "file_version_id": f"file_{uuid.uuid4().hex[:12]}",
            "path": str(path),
            "sha256": sha256,
            "size": path.stat().st_size,
            "observed_at": utc_now(),
        }
        connection.execute(
            """
            INSERT INTO file_versions(
                file_version_id, path, sha256, size, observed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            tuple(value.values()),
        )
        return value

    @staticmethod
    def _resolve_path(
        path: Union[Path, str], project_root: Path
    ) -> Path:
        if not str(path).strip():
            raise WorkflowError("file path cannot be empty")
        value = Path(path)
        if not value.is_absolute():
            value = project_root / value
        return value.resolve()

    @staticmethod
    def _resolve_file(path: Union[Path, str], project_root: Path) -> Path:
        value = WorkflowStore._resolve_path(path, project_root)
        if not value.is_file():
            raise WorkflowError(f"file does not exist: {value}")
        return value

    @staticmethod
    def _program_records(
        project_root: Path, programs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        records = []
        for program in programs:
            record = dict(program)
            raw_path = str(record.get("path") or "").strip()
            if raw_path:
                path = Path(raw_path)
                if not path.is_absolute():
                    path = project_root / path
                path = path.resolve()
                record["path"] = str(path)
                if path.is_file():
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    record["sha256"] = digest.hexdigest()
            records.append(record)
        return records

    @staticmethod
    def _granularity_warnings(objective: str) -> List[str]:
        lowered = objective.lower()
        warnings = []
        implementation_phrases = (
            "运行脚本",
            "执行python",
            "执行 python",
            "写代码",
            "run script",
            "run python",
            "write code",
        )
        if any(phrase in lowered for phrase in implementation_phrases):
            warnings.append(
                "Objective appears implementation-oriented; describe the data-analysis goal."
            )
        broad_markers = ("然后", "并且", "同时", " and then ", " as well as ")
        if sum(marker in lowered for marker in broad_markers) >= 2:
            warnings.append(
                "Objective may contain multiple semantic goals; consider splitting it."
            )
        return warnings

    @staticmethod
    def _implementation_only_reason(objective: str) -> Optional[str]:
        """Reject narrow, unambiguous implementation-only Plan objectives."""

        normalized = objective.strip().lower()
        always_implementation = (
            "save ",
            "write ",
            "export ",
            "persist ",
            "copy ",
            "move ",
            "rename ",
            "run script",
            "run python",
            "execute command",
            "install ",
            "retry ",
            "保存",
            "写入",
            "导出",
            "持久化",
            "复制",
            "移动",
            "重命名",
            "运行脚本",
            "执行命令",
            "安装",
            "重试",
        )
        for prefix in always_implementation:
            if normalized.startswith(prefix):
                return f"starts with '{prefix.strip()}'"

        read_prefixes = ("read ", "load ", "open ", "读取", "加载", "打开")
        semantic_markers = (
            "understand",
            "inspect",
            "analyze",
            "validate",
            "verify",
            "assess",
            "identify",
            "compare",
            "summarize",
            "explain",
            "check",
            "理解",
            "检查",
            "分析",
            "验证",
            "评估",
            "识别",
            "比较",
            "总结",
            "解释",
        )
        if normalized.startswith(read_prefixes) and not any(
            marker in normalized for marker in semantic_markers
        ):
            return "only reads or opens a file"
        return None
