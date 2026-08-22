"""Canonical and legacy filesystem locations used by AgentVAST."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


STATE_DIRECTORY_NAME = ".agentvast"
# Read-only naming compatibility for Runs created before the AgentVAST rename.
LEGACY_STATE_DIRECTORY_NAME = ".opentrace"
WORKFLOW_DATABASE_NAME = "workflow.sqlite3"


def resolve_user_path(value: Union[Path, str]) -> Path:
    """Resolve a path copied from a shell or browser input field.

    Windows users commonly paste paths with surrounding quotes or environment
    variables. ``Path`` treats those quotes as literal filename characters, so
    normalize them before resolving the path.
    """

    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    if not text:
        raise ValueError("path cannot be empty")
    return Path(os.path.expandvars(text)).expanduser().resolve()


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
