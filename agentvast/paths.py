"""Canonical and legacy filesystem locations used by AgentVAST."""

from __future__ import annotations

from pathlib import Path


STATE_DIRECTORY_NAME = ".agentvast"
# Read-only naming compatibility for Runs created before the AgentVAST rename.
LEGACY_STATE_DIRECTORY_NAME = ".opentrace"
WORKFLOW_DATABASE_NAME = "workflow.sqlite3"


def state_directory(project_root: Path) -> Path:
    """Return the current state directory, falling back to an existing legacy one."""

    project = Path(project_root).resolve()
    current = project / STATE_DIRECTORY_NAME
    legacy = project / LEGACY_STATE_DIRECTORY_NAME
    if current.exists() or not legacy.exists():
        return current
    return legacy


def workflow_database(project_root: Path) -> Path:
    """Resolve the workflow database without invalidating historical Runs."""

    return state_directory(project_root) / WORKFLOW_DATABASE_NAME
