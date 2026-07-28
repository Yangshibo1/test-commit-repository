import json
from pathlib import Path

from opentrace import plugin_hook
from opentrace.workflow_store import WorkflowStore


def configured_run(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")
    database = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(database)
    run = store.start_run("分析数据", project, [data], claude_session_id="session-1")
    monkeypatch.setenv("OPENTRACE_DB", str(database))
    monkeypatch.setenv("OPENTRACE_RUN_ID", run["run_id"])
    return project, store, run


def test_user_prompt_is_captured_and_material_tool_is_gated(tmp_path, monkeypatch):
    project, store, run = configured_run(tmp_path, monkeypatch)

    context = plugin_hook.user_prompt_submit(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "prompt": "先检查异常值，再决定是否删除",
        }
    )
    assert "input_" in json.dumps(context)

    denied = plugin_hook.pre_tool_use(
        {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    input_event_id = store.get_state(run["run_id"])["pending_user_inputs"][0][
        "input_event_id"
    ]
    store.classify_user_input(input_event_id, "planning_input")
    denied_unapplied = plugin_hook.pre_tool_use(
        {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
    )
    assert "apply_user_input" in denied_unapplied["hookSpecificOutput"][
        "permissionDecisionReason"
    ]
    store.apply_user_input(
        input_event_id,
        workflow_effect="在当前计划中先检查异常值",
    )
    denied_without_step = plugin_hook.pre_tool_use(
        {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
    )
    assert "Set an OpenTrace plan" in denied_without_step["hookSpecificOutput"][
        "permissionDecisionReason"
    ]

    store.set_plan(run["run_id"], [{"node_id": "n1", "objective": "检查异常值"}])
    store.start_step(run["run_id"], "n1", [project / "data.csv"])
    assert (
        plugin_hook.pre_tool_use(
            {"hook_event_name": "PreToolUse", "tool_name": "Bash"}
        )
        == {}
    )


def test_initial_launcher_prompt_is_not_human_intervention(tmp_path, monkeypatch):
    _, store, run = configured_run(tmp_path, monkeypatch)
    result = plugin_hook.user_prompt_submit(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "prompt": f"[OPENTRACE_INITIAL_TASK run_id={run['run_id']}]\n分析数据",
        }
    )
    assert result == {}
    assert store.get_state(run["run_id"])["pending_user_inputs"] == []


def test_recording_bash_command_bypasses_step_gate_but_chaining_does_not(
    tmp_path, monkeypatch
):
    project, _, _ = configured_run(tmp_path, monkeypatch)
    monkeypatch.setenv("OPENTRACE_PROJECT_ROOT", str(project))
    allowed = plugin_hook.pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "opentrace-agent set-plan --payload "
                    """'{"nodes":[{"node_id":"n1","objective":"Inspect"}]}'"""
                )
            },
        }
    )
    assert allowed == {}

    allowed_with_cd_and_multiline_payload = plugin_hook.pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'cd "{project}" && python -m opentrace.agent_cli '
                    "set-plan --payload '{\n"
                    '  "nodes": [{"node_id": "n1", "objective": "Inspect"}]\n'
                    "}'"
                )
            },
        }
    )
    assert allowed_with_cd_and_multiline_payload == {}

    denied = plugin_hook.pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "opentrace-agent state && python analyze.py"
            },
        }
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    denied_after_payload = plugin_hook.pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    "python -m opentrace.agent_cli set-plan "
                    """--payload '{"nodes":[{"node_id":"n1","objective":"Inspect"}]}' """
                    "&& python analyze.py"
                )
            },
        }
    )
    assert denied_after_payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    other_project = tmp_path / "other"
    other_project.mkdir()
    denied_other_directory = plugin_hook.pre_tool_use(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    f'cd "{other_project}" && python -m opentrace.agent_cli '
                    """state"""
                )
            },
        }
    )
    assert denied_other_directory["hookSpecificOutput"][
        "permissionDecision"
    ] == "deny"


def test_powershell_and_unknown_tools_are_gated(tmp_path, monkeypatch):
    _, _, _ = configured_run(tmp_path, monkeypatch)

    for tool_name in ("PowerShell", "WebFetch", "Agent", "FutureDataTool", ""):
        denied = plugin_hook.pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": {},
            }
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    assert (
        plugin_hook.pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "tool_input": {},
            }
        )
        == {}
    )


def test_stop_requires_plan_steps_and_finished_run(tmp_path, monkeypatch):
    project, store, run = configured_run(tmp_path, monkeypatch)
    assert plugin_hook.stop({})["decision"] == "block"

    store.set_plan(run["run_id"], [{"node_id": "n1", "objective": "检查数据"}])
    assert "Complete every node" in plugin_hook.stop({})["reason"]

    step = store.start_step(run["run_id"], "n1", [project / "data.csv"])
    assert step["step_id"] in plugin_hook.stop({})["reason"]
    store.complete_step(step["step_id"], "检查数据", "检查完成")
    assert "finish-run" in plugin_hook.stop({})["reason"]

    store.finish_run(run["run_id"])
    assert plugin_hook.stop({}) == {}


def test_plugin_json_files_are_valid():
    root = Path(__file__).resolve().parents[1] / "claude-plugin"
    json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert hooks["hooks"]["PreToolUse"][0]["matcher"] == "*"
    assert hooks["hooks"]["PostToolUse"][0]["matcher"] == "*"
    assert not (root / ".mcp.json").exists()
    skill = (root / "skills" / "data-analysis" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "python -m opentrace.agent_cli set-plan" in skill
