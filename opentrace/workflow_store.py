"""SQLite-backed recorder for Claude Code data-analysis workflows.

This module deliberately contains no data-analysis logic.  Claude Code owns the
analysis; OpenTrace only stores declared semantic nodes, observes file versions,
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
            self._ensure_column(
                connection, "plan_revisions", "trigger_kind", "TEXT"
            )
            self._ensure_column(connection, "steps", "plan_version", "INTEGER")
            self._ensure_column(connection, "steps", "commands_json", "TEXT")
            self._ensure_column(connection, "steps", "result_summary", "TEXT")
            self._ensure_column(
                connection, "steps", "analysis_conclusion", "TEXT"
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
        self,
        run_id: str,
        nodes: List[Dict[str, Any]],
        trigger: Optional[str] = None,
        change_reason: Optional[str] = None,
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
            implementation_reason = self._implementation_only_reason(objective)
            if implementation_reason:
                raise WorkflowError(
                    f"plan node {node_id} is an implementation action rather than "
                    f"a semantic analysis objective ({implementation_reason}). "
                    "Keep it inside the analysis node that produces or consumes "
                    "the file."
                )
            if node_id in seen:
                raise WorkflowError(f"duplicate plan node_id: {node_id}")
            seen.add(node_id)
            normalized.append(
                {
                    "node_id": node_id,
                    "objective": objective,
                    "depends_on": list(node.get("depends_on") or []),
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
        self._validate_plan_is_acyclic(normalized)

        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM plan_revisions WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            version = int(row["version"]) + 1
            effective_trigger = trigger or (
                "initial" if version == 1 else "agent_replan"
            )
            if effective_trigger not in PLAN_TRIGGERS:
                raise WorkflowError(f"invalid plan trigger: {effective_trigger}")
            if version == 1 and effective_trigger != "initial":
                raise WorkflowError("the first plan revision must use trigger 'initial'")
            if version > 1 and effective_trigger == "initial":
                raise WorkflowError(
                    "only the first plan revision may use trigger 'initial'"
                )

            completed_nodes = {
                row["node_id"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT node_id FROM steps
                    WHERE run_id = ? AND status IN ('active', 'completed')
                    """,
                    (run_id,),
                ).fetchall()
            }
            missing = sorted(completed_nodes - seen)
            if missing:
                raise WorkflowError(
                    "a plan revision cannot remove nodes already started: "
                    + ", ".join(missing)
                )
            previous = self._latest_plan(connection, run_id)
            if previous is not None:
                previous_nodes = {
                    node["node_id"]: node for node in previous["nodes"]
                }
                current_nodes = {node["node_id"]: node for node in normalized}
                changed_started = [
                    node_id
                    for node_id in completed_nodes
                    if (
                        current_nodes[node_id]["objective"]
                        != previous_nodes[node_id]["objective"]
                        or set(current_nodes[node_id]["depends_on"])
                        != set(previous_nodes[node_id].get("depends_on") or [])
                    )
                ]
                if changed_started:
                    raise WorkflowError(
                        "a plan revision cannot rewrite objectives or dependencies "
                        "of nodes already started; add a new node instead: "
                        + ", ".join(sorted(changed_started))
                    )
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
                    (change_reason or "").strip() or None,
                    effective_trigger,
                    utc_now(),
                ),
            )

        return {
            "run_id": run_id,
            "plan_version": version,
            "trigger": effective_trigger,
            "change_reason": (change_reason or "").strip() or None,
            "nodes": normalized,
        }

    def start_step(
        self,
        run_id: str,
        node_id: str,
        input_files: Iterable[Union[Path, str]],
        objective: str = "",
    ) -> Dict[str, Any]:
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
            plan_nodes = {node["node_id"]: node for node in plan["nodes"]}
            if node_id not in plan_nodes:
                raise WorkflowError(f"node_id is not present in current plan: {node_id}")
            plan_node = plan_nodes[node_id]
            supplied_objective = objective.strip()
            if supplied_objective and supplied_objective != plan_node["objective"]:
                raise WorkflowError(
                    "step objective must exactly match the current plan node objective"
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
                    f"current plan node already has a completed step: {node_id}"
                )
            missing_dependencies = sorted(
                set(plan_node["depends_on"]) - completed_nodes
            )
            if missing_dependencies:
                raise WorkflowError(
                    "complete plan dependencies before starting this step: "
                    + ", ".join(missing_dependencies)
                )

            project = Path(run["project_root"])
            inputs = [self._resolve_file(path, project) for path in input_files]
            if not inputs:
                raise WorkflowError("a step must declare at least one input file")
            versions = [self._observe_file(connection, path) for path in inputs]
            allowed_version_ids = {
                row["file_version_id"]
                for row in connection.execute(
                    """
                    SELECT file_version_id FROM run_inputs WHERE run_id = ?
                    UNION
                    SELECT o.file_version_id
                    FROM step_outputs o
                    JOIN steps s ON s.step_id = o.step_id
                    WHERE s.run_id = ? AND s.status = 'completed'
                    """,
                    (run_id, run_id),
                ).fetchall()
            }
            untracked = [
                version["path"]
                for version in versions
                if version["file_version_id"] not in allowed_version_ids
            ]
            if untracked:
                raise WorkflowError(
                    "node inputs must be declared Run inputs or outputs of completed "
                    "nodes: " + ", ".join(untracked)
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

            for version in versions:
                connection.execute(
                    "INSERT INTO step_inputs(step_id, file_version_id) VALUES (?, ?)",
                    (step_id, version["file_version_id"]),
                )

        return {
            "step_id": step_id,
            "status": "active",
            "plan_version": plan["version"],
            "node_id": node_id,
            "objective": objective,
            "input_file_versions": versions,
            "granularity_warnings": warnings,
        }

    def complete_step(
        self,
        step_id: str,
        operation_summary: str,
        result_summary: str,
        output_files: Optional[List[Union[Path, str, Dict[str, str]]]] = None,
        analysis_conclusion: Optional[str] = None,
    ) -> Dict[str, Any]:
        operation_summary = operation_summary.strip()
        result_summary = result_summary.strip()
        if not operation_summary:
            raise WorkflowError("operation_summary cannot be empty")
        if not result_summary:
            raise WorkflowError("result_summary cannot be empty")
        if analysis_conclusion is not None:
            analysis_conclusion = analysis_conclusion.strip() or None

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
            input_version_ids = {
                row["file_version_id"]
                for row in connection.execute(
                    """
                    SELECT file_version_id FROM step_inputs
                    WHERE step_id = ?
                    """,
                    (step_id,),
                ).fetchall()
            }

            versions = []
            for output in output_files:
                raw_path = output.get("path", "") if isinstance(output, dict) else output
                path = self._resolve_file(raw_path, project)
                version = self._observe_file(connection, path)
                if version["file_version_id"] in input_version_ids:
                    raise WorkflowError(
                        "an unchanged input file cannot also be recorded as this "
                        f"step's output: {version['path']}"
                    )
                versions.append(version)
                connection.execute(
                    """
                    INSERT INTO step_outputs(step_id, file_version_id, role)
                    VALUES (?, ?, 'step_output')
                    """,
                    (step_id, version["file_version_id"]),
                )

            commands, programs = self._observed_operation(
                connection, step_id, project
            )
            connection.execute(
                """
                UPDATE steps SET
                    operation_summary = ?,
                    programs_json = ?,
                    commands_json = ?,
                    result_summary = ?,
                    analysis_conclusion = ?,
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
                    utc_now(),
                    step_id,
                ),
            )

        return {
            "step_id": step_id,
            "node_id": step["node_id"],
            "status": "completed",
            "output_file_versions": versions,
            "observed_commands": commands,
            "observed_programs": programs,
        }

    def complete_node(
        self,
        run_id: str,
        node_id: str,
        operation_summary: str,
        result_summary: str,
        output_files: Optional[List[Union[Path, str, Dict[str, str]]]] = None,
        analysis_conclusion: Optional[str] = None,
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
            operation_summary=operation_summary,
            result_summary=result_summary,
            output_files=output_files,
            analysis_conclusion=analysis_conclusion,
        )

    def capture_user_input(
        self, run_id: str, original_text: str, claude_session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if not original_text.strip():
            raise WorkflowError("user input cannot be empty")
        input_event_id = f"input_{uuid.uuid4().hex[:12]}"
        with self._connection() as connection:
            self._require_active_run(connection, run_id)
            active = connection.execute(
                """
                SELECT step_id FROM steps
                WHERE run_id = ? AND status = 'active'
                """,
                (run_id,),
            ).fetchone()
            plan = self._latest_plan(connection, run_id)
            connection.execute(
                """
                INSERT INTO input_events(
                    input_event_id, run_id, claude_session_id, original_text,
                    target_step_id, target_plan_version, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    input_event_id,
                    run_id,
                    claude_session_id,
                    original_text,
                    active["step_id"] if active else None,
                    plan["version"] if plan else None,
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
            completed_at = utc_now()
            connection.execute(
                "UPDATE runs SET status = 'completed', completed_at = ? WHERE run_id = ?",
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
            return {
                "run": {**dict(run), "initial_file_versions": [dict(row) for row in initial_files]},
                "plan": plan,
                "nodes": node_values,
                "pending_user_inputs": [dict(row) for row in pending_inputs],
            }

    def export_run(
        self, run_id: str, output_path: Optional[Union[Path, str]] = None
    ) -> Path:
        with self._connection() as connection:
            exported = self._normalized_export(connection, run_id)

        if output_path is None:
            output_path = self.db_path.parent / "exports" / f"{run_id}.json"
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
              AND type != 'conversation_only'
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
            "schema_version": "1.1",
            "run": {
                "run_id": run["run_id"],
                "task": run["task_description"],
                "project_root": run["project_root"],
                "agent": "claude-code",
                "session_id": run["claude_session_id"],
                "status": run["status"],
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
                        "with python -m opentrace.agent_cli apply-user-input: "
                        f"{pending['input_event_id']}"
                    )
                return (
                    "Classify pending user input with python -m "
                    "opentrace.agent_cli classify-user-input: "
                    f"{pending['input_event_id']}"
                )
            plan = self._latest_plan(connection, run_id)
            if plan is None:
                return "Set an OpenTrace plan before material analysis work"
            active = connection.execute(
                "SELECT step_id FROM steps WHERE run_id = ? AND status = 'active'",
                (run_id,),
            ).fetchone()
            if not active:
                return "Start a semantic OpenTrace node before material analysis work"
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

    def _observed_operation(
        self,
        connection: sqlite3.Connection,
        step_id: str,
        project: Path,
    ) -> Tuple[List[str], List[str]]:
        rows = connection.execute(
            """
            SELECT tool_name, payload_json FROM hook_events
            WHERE step_id = ? AND hook_event_name = 'PostToolUse'
            ORDER BY created_at
            """,
            (step_id,),
        ).fetchall()
        commands: List[str] = []
        program_paths: List[str] = []
        for row in rows:
            payload = _from_json(row["payload_json"], {})
            tool_input = payload.get("tool_input") or {}
            tool_name = str(row["tool_name"] or payload.get("tool_name") or "")
            if tool_name in {"Bash", "PowerShell"}:
                command = str(tool_input.get("command") or "").strip()
                if command and "opentrace.agent_cli" not in command:
                    commands.append(command)
                    for match in re.findall(
                        r"""(?:"([^"]+\.py)"|'([^']+\.py)'|([^\s"';&|]+\.py))""",
                        command,
                        re.IGNORECASE,
                    ):
                        program_paths.append(next(value for value in match if value))
            elif tool_name in {"Write", "Edit", "NotebookEdit"}:
                raw_path = str(
                    tool_input.get("file_path")
                    or tool_input.get("notebook_path")
                    or ""
                ).strip()
                if raw_path.lower().endswith((".py", ".ipynb")):
                    program_paths.append(raw_path)

        normalized_programs = []
        seen = set()
        for raw_path in program_paths:
            path = Path(raw_path)
            if not path.is_absolute():
                path = project / path
            normalized = str(path.resolve())
            key = os.path.normcase(normalized)
            if key not in seen:
                normalized_programs.append(normalized)
                seen.add(key)
        return list(dict.fromkeys(commands)), normalized_programs

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
