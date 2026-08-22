import asyncio
import json

from agentvast.mcp_stdio import mcp


def test_tool_schemas_avoid_gateway_incompatible_constructs():
    tools = asyncio.run(mcp.list_tools())
    encoded = json.dumps(
        [tool.inputSchema for tool in tools],
        ensure_ascii=False,
        sort_keys=True,
    )

    assert "anyOf" not in encoded
    assert "additionalProperties" not in encoded


def test_set_plan_accepts_serialized_nodes(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    data = project / "data.csv"
    data.write_text("x\n1\n", encoding="utf-8")

    from agentvast.workflow_store import WorkflowStore

    database = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(database)
    run = store.start_run("分析数据", project, [data])
    monkeypatch.setenv("AGENTVAST_DB", str(database))
    monkeypatch.setenv("AGENTVAST_RUN_ID", run["run_id"])

    asyncio.run(
        mcp.call_tool(
            "agentvast_set_plan",
            {
                "nodes_json": json.dumps(
                    [{"node_id": "profile", "objective": "检查数据质量"}],
                    ensure_ascii=False,
                )
            },
        )
    )

    assert store.get_state(run["run_id"])["plan"]["nodes"][0]["node_id"] == "profile"
