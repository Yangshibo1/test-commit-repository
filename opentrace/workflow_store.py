"""SQLite-backed recorder for Claude Code data-analysis workflows.

This module deliberately contains no data-analysis logic.  Claude Code owns the
analysis; OpenTrace only stores declared semantic steps, observes file versions,
and enforces a small workflow state machine.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Union


OUTPUT_ROLES = {"step_output", "internal_intermediate", "temporary"}
INPUT_TYPES = {
    "conversation_only",
    "analysis_guidance",
    "planning_input",
    "challenge",
}


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
                    claude_session_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS plan_revisions (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    version INTEGER NOT NULL,
                    nodes_json TEXT NOT NULL,
                    reason TEXT,
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
                """
            )

    def start_run(
        self,
        task_description: str,
        project_root: Union[Path, str],
        input_files: Iterable[Union[Path, str]],
        claude_session_id: Optional[str] = None,
        original_request: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_description = task_description.strip()
        if not task_description:
            raise WorkflowError("task_description cannot be empty")

        project = Path(project_root).resolve()
        if not project.is_dir():
            raise WorkflowError(f"project_root does not exist: {project}")

        resolved_inputs = [self._resolve_file(path, project) for path in input_files]
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        session_id = claude_session_id or str(uuid.uuid4())
        now = utc_now()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runs(
                    run_id, task_description, original_request, project_root,
                    claude_session_id, status, started_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    run_id,
                    task_description,
                    original_request or task_description,
                    str(project),
                    session_id,
                    now,
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
            "initial_file_versions": initial_versions,
        }

    def set_plan(
        self, run_id: str, nodes: List[Dict[str, Any]], reason: str = "initial plan"
    ) -> Dict[str, Any]:
        if not nodes:
            raise WorkflowError("plan must contain at least one node")

        normalized: List[Dict[str, Any]] = []
        seen = set()
        for index, node in enumerate(nodes, start=1):
            node_id = str(node.get("node_id") or f"node_{index:02d}")
            objective = str(node.get("objective") or "").strip()
            if not objective:
                raise WorkflowError(f"plan node {node_id} has no objective")
            if node_id in seen:
                raise WorkflowError(f"duplicate plan node_id: {node_id}")
            seen.add(node_id)
            normalized.append(
                {
                    "node_id": node_id,
                    "objective": objective,
                    "step_type": node.get("step_type", "analyze"),
                    "depends_on": list(node.get("depends_on") or []),
                    "status": node.get("status", "pending"),
                }
            )
        for node in normalized:
            unknown = sorted(set(node["depends_on"]) - seen)
            if unknown:
                raise WorkflowError(
                    f"plan node {node['node_id']} has unknown dependencies: "
                    f"{', '.join(unknown)}"
                )
            if node["node_id"] in node["depends_on"]:
                raise WorkflowError(
                    f"plan node cannot depend on itself: {node['node_id']}"
                )

        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM plan_revisions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            version = int(row["version"]) + 1
            connection.execute(
                """
                INSERT INTO plan_revisions(run_id, version, nodes_json, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, version, _json(normalized), reason, utc_now()),
            )

        return {"run_id": run_id, "plan_version": version, "nodes": normalized}

    def start_step(
        self,
        run_id: str,
        node_id: str,
        objective: str,
        input_files: Iterable[Union[Path, str]],
        completion_condition: str,
        expected_output_roles: Optional[List[str]] = None,
        target_data: str = "",
    ) -> Dict[str, Any]:
        objective = objective.strip()
        completion_condition = completion_condition.strip()
        if not objective:
            raise WorkflowError("objective cannot be empty")
        if not completion_condition:
            raise WorkflowError("completion_condition cannot be empty")

        roles = (
            ["step_output"]
            if expected_output_roles is None
            else expected_output_roles
        )
        invalid_roles = sorted(set(roles) - OUTPUT_ROLES)
        if invalid_roles:
            raise WorkflowError(f"invalid output roles: {', '.join(invalid_roles)}")

        warnings = self._granularity_warnings(objective)
        with self._connection() as connection:
            run = self._require_active_run(connection, run_id)
            pending = connection.execute(
                """
                SELECT COUNT(*) AS count FROM input_events
                WHERE run_id = ? AND status IN ('pending', 'classified')
                """,
                (run_id,),
            ).fetchone()["count"]
            if pending:
                raise WorkflowError(
                    "classify and apply unresolved user input before starting a step"
                )

            plan = self._latest_plan(connection, run_id)
            if plan is None:
                raise WorkflowError("set a plan before starting a step")
            if node_id not in {node["node_id"] for node in plan["nodes"]}:
                raise WorkflowError(f"node_id is not present in current plan: {node_id}")

            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if active:
                raise WorkflowError(f"run already has active step: {active['step_id']}")

            sequence = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM steps WHERE run_id = ?", (run_id,)
                ).fetchone()["count"]
            ) + 1
            step_id = f"step_{sequence:03d}_{uuid.uuid4().hex[:6]}"
            connection.execute(
                """
                INSERT INTO steps(
                    step_id, run_id, node_id, sequence, objective, target_data,
                    completion_condition, expected_output_roles_json, warnings_json,
                    status, started_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    step_id,
                    run_id,
                    node_id,
                    sequence,
                    objective,
                    target_data,
                    completion_condition,
                    _json(roles),
                    _json(warnings),
                    utc_now(),
                ),
            )

            project = Path(run["project_root"])
            inputs = [self._resolve_file(path, project) for path in input_files]
            if not inputs:
                raise WorkflowError("a step must declare at least one input file")
            versions = []
            for path in inputs:
                version = self._observe_file(connection, path)
                versions.append(version)
                connection.execute(
                    """
                    UPDATE step_outputs SET role = 'step_output'
                    WHERE file_version_id = ? AND role != 'step_output'
                    """,
                    (version["file_version_id"],),
                )
                connection.execute(
                    "INSERT INTO step_inputs(step_id, file_version_id) VALUES (?, ?)",
                    (step_id, version["file_version_id"]),
                )

        return {
            "step_id": step_id,
            "status": "active",
            "input_file_versions": versions,
            "granularity_warnings": warnings,
        }

    def complete_step(
        self,
        step_id: str,
        operation_summary: str,
        output_files: Optional[List[Dict[str, str]]] = None,
        processing_result: Optional[Dict[str, Any]] = None,
        analysis_conclusion: Optional[Dict[str, Any]] = None,
        operation_types: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        algorithms: Optional[List[Dict[str, Any]]] = None,
        programs: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        operation_summary = operation_summary.strip()
        if not operation_summary:
            raise WorkflowError("operation_summary cannot be empty")
        if not output_files and not processing_result and not analysis_conclusion:
            raise WorkflowError(
                "a completed step needs output files, processing_result, or analysis_conclusion"
            )

        output_files = output_files or []
        with self._connection() as connection:
            step = connection.execute(
                "SELECT * FROM steps WHERE step_id = ?", (step_id,)
            ).fetchone()
            if step is None:
                raise WorkflowError(f"step does not exist: {step_id}")
            if step["status"] != "active":
                raise WorkflowError(f"step is not active: {step_id}")
            run = self._require_active_run(connection, step["run_id"])
            project = Path(run["project_root"])

            versions = []
            for output in output_files:
                role = output.get("role", "step_output")
                if role not in OUTPUT_ROLES:
                    raise WorkflowError(f"invalid output role: {role}")
                path = self._resolve_file(output.get("path", ""), project)
                version = self._observe_file(connection, path)
                versions.append({**version, "role": role})
                connection.execute(
                    """
                    INSERT INTO step_outputs(step_id, file_version_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (step_id, version["file_version_id"], role),
                )

            connection.execute(
                """
                UPDATE steps SET
                    operation_summary = ?,
                    operation_types_json = ?,
                    parameters_json = ?,
                    algorithms_json = ?,
                    programs_json = ?,
                    processing_result_json = ?,
                    analysis_conclusion_json = ?,
                    status = 'completed',
                    completed_at = ?
                WHERE step_id = ?
                """,
                (
                    operation_summary,
                    _json(operation_types or []),
                    _json(parameters or {}),
                    _json(algorithms or []),
                    _json(self._program_records(project, programs or [])),
                    _json(processing_result or {}),
                    _json(analysis_conclusion or {}),
                    utc_now(),
                    step_id,
                ),
            )

        return {
            "step_id": step_id,
            "status": "completed",
            "output_file_versions": versions,
        }

    def capture_user_input(
        self, run_id: str, original_text: str, claude_session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not original_text.strip():
            raise WorkflowError("user input cannot be empty")
        input_event_id = f"input_{uuid.uuid4().hex[:12]}"
        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            connection.execute(
                """
                INSERT INTO input_events(
                    input_event_id, run_id, claude_session_id, original_text,
                    status, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    input_event_id,
                    run_id,
                    claude_session_id,
                    original_text,
                    utc_now(),
                ),
            )
        return {"input_event_id": input_event_id, "status": "pending"}

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
            connection.execute(
                """
                UPDATE input_events SET
                    type = ?, target_step_id = ?, target_plan_version = ?,
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
                    "resolved" if input_type == "conversation_only" else "classified",
                    utc_now() if input_type == "conversation_only" else None,
                    input_event_id,
                ),
            )
        status = "resolved" if input_type == "conversation_only" else "classified"
        return {
            "input_event_id": input_event_id,
            "type": input_type,
            "status": status,
            "creates_human_contribution": input_type != "conversation_only",
            "requires_apply": input_type != "conversation_only",
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

    def finish_run(self, run_id: str) -> Dict[str, Any]:
        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if active:
                raise WorkflowError(f"complete active step first: {active['step_id']}")
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
                raise WorkflowError("cannot finish a run without completed steps")
            completed_at = utc_now()
            connection.execute(
                "UPDATE runs SET status = 'completed', completed_at = ? WHERE run_id = ?",
                (completed_at, run_id),
            )
        return {"run_id": run_id, "status": "completed", "completed_at": completed_at}

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
            step_values = [self._step_dict(connection, row) for row in steps]
            if plan:
                statuses = {
                    item["node_id"]: item["status"]
                    for item in step_values
                    if item["status"] in {"active", "completed"}
                }
                plan["nodes"] = [
                    {**node, "status": statuses.get(node["node_id"], node["status"])}
                    for node in plan["nodes"]
                ]
            return {
                "run": {**dict(run), "initial_file_versions": [dict(row) for row in initial_files]},
                "plan": plan,
                "steps": step_values,
                "pending_user_inputs": [dict(row) for row in pending_inputs],
            }

    def export_run(
        self, run_id: str, output_path: Optional[Union[Path, str]] = None
    ) -> Path:
        state = self.get_state(run_id)
        with self._connection() as connection:
            inputs = connection.execute(
                "SELECT * FROM input_events WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT * FROM hook_events WHERE run_id = ? ORDER BY created_at",
                (run_id,),
            ).fetchall()
            state["human_inputs"] = [dict(row) for row in inputs]
            state["execution_events"] = [
                {
                    **dict(row),
                    "payload": _from_json(row["payload_json"], {}),
                }
                for row in events
            ]

        if output_path is None:
            output_path = self.db_path.parent / "exports" / f"{run_id}.json"
        destination = Path(output_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(_json(state), encoding="utf-8")
        return destination

    def gate_reason(self, run_id: str) -> Optional[str]:
        """Return why a material Claude tool call should be blocked, if any."""
        with self._connection() as connection:
            run = self._require_run(connection, run_id)
            if run["status"] != "active":
                return f"OpenTrace run is {run['status']}"
            pending = connection.execute(
                "SELECT input_event_id, status FROM input_events "
                "WHERE run_id = ? AND status IN ('pending', 'classified') "
                "ORDER BY created_at LIMIT 1",
                (run_id,),
            ).fetchone()
            if pending:
                if pending["status"] == "classified":
                    return (
                        "Record how the classified human input affected the workflow "
                        "with opentrace_apply_user_input: "
                        f"{pending['input_event_id']}"
                    )
                return (
                    "Classify pending user input with "
                    f"opentrace_classify_user_input: {pending['input_event_id']}"
                )
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if not active:
                return "Start a semantic OpenTrace step before material analysis work"
        return None

    def _step_dict(self, connection: sqlite3.Connection, row: sqlite3.Row) -> Dict[str, Any]:
        value = dict(row)
        for key in (
            "expected_output_roles_json",
            "operation_types_json",
            "parameters_json",
            "algorithms_json",
            "programs_json",
            "processing_result_json",
            "analysis_conclusion_json",
            "warnings_json",
        ):
            output_key = key[:-5] if key.endswith("_json") else key
            value[output_key] = _from_json(
                value.pop(key), [] if key.endswith("s_json") else {}
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
            "reason": row["reason"],
            "created_at": row["created_at"],
        }

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
    def _resolve_file(path: Union[Path, str], project_root: Path) -> Path:
        if not str(path).strip():
            raise WorkflowError("file path cannot be empty")
        value = Path(path)
        if not value.is_absolute():
            value = project_root / value
        value = value.resolve()
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
