import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentvast.paths import REPOSITORY_ROOT, expose_repository_to_python, resolve_user_path


def test_resolve_user_path_accepts_quoted_windows_style_input(tmp_path: Path):
    expected = tmp_path.resolve()

    assert resolve_user_path(f'"{tmp_path}"') == expected
    assert resolve_user_path(f"'{tmp_path}'") == expected


def test_resolve_user_path_expands_environment_variables(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTVAST_TEST_PROJECT", str(tmp_path))

    assert resolve_user_path("%AGENTVAST_TEST_PROJECT%") == tmp_path.resolve()


def test_resolve_user_path_rejects_empty_values():
    with pytest.raises(ValueError, match="empty"):
        resolve_user_path("  ")


def test_repository_is_importable_from_external_project(tmp_path: Path):
    environment = os.environ.copy()
    environment.pop("AGENTVAST_RUN_ID", None)
    expose_repository_to_python(environment)

    result = subprocess.run(
        [sys.executable, "-c", "import agentvast; print(agentvast.__file__)"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert str(REPOSITORY_ROOT) in result.stdout
