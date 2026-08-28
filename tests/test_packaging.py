from pathlib import Path


def test_mcp_is_optional_and_pinned_before_breaking_v2():
    pyproject = (
        Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    project_section, optional_section = pyproject.split(
        "[project.optional-dependencies]", 1
    )

    assert 'dependencies = []' in project_section
    assert '"mcp>=' not in project_section
    assert 'mcp = [' in optional_section
    assert 'mcp>=1.28,<2.0' in optional_section
