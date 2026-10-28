"""Construct an explicitly synthetic analysis log; optionally analyze it via API."""

import argparse
import json
from pathlib import Path

from agentvast.observer.store import create_session
from agentvast.observer.trace_builder import build_observer_trace
from agentvast.observer.transcript_reader import snapshot_transcript
from agentvast.semantic.event_workflow import run_event_workflow


def create_demo(base: Path):
    project = base / "project"
    project.mkdir(parents=True, exist_ok=True)
    csv = "date,value\n2026-01-01,10\ninvalid,20\n2026-01-03,30\n,40\n2026-01-05,50\n"
    (project / "sales.csv").write_text(csv)
    (project / "analyze.py").write_text(
        "# Synthetic demo artifact; transcript commands are not executed.\n"
    )
    report_text = (
        "5 行数据中 2 行日期无效，占 40%；3 行有效日期对应的均值为 30。样本不足以判断趋势。"
    )
    (project / "report.md").write_text(report_text)
    records = []

    def add(kind, message=None, **extra):
        index = len(records) + 1
        record = {
            "type": kind,
            "uuid": "demo-%02d" % index,
            "timestamp": "2026-10-09T09:00:%02dZ" % index,
            "sessionId": "demo-event-workflow",
            **extra,
        }
        if records:
            record["parentUuid"] = records[-1]["uuid"]
        if message is not None:
            record["message"] = message
        records.append(record)

    def response(name, tools, text=""):
        content = ([{"type": "text", "text": text}] if text else []) + [
            {"type": "tool_use", "id": tool_id, "name": tool_name, "input": values}
            for tool_id, tool_name, values in tools
        ]
        add("assistant", {"id": name, "model": "claude-demo", "content": content})

    def result(tool_id, output, error=False, **structured):
        add(
            "user",
            {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": output,
                        "is_error": error,
                    }
                ]
            },
            toolUseResult=structured,
        )

    add(
        "user",
        {
            "content": "这是人工构造的演示记录。检查 sales.csv 的日期质量，计算有效日期行的 value 均值，生成简短报告并说明限制。"
        },
        origin={"kind": "human"},
        promptSource="typed",
    )
    response("inspect", [("glob", "Glob", {"pattern": "*.csv"})])
    result("glob", "sales.csv")
    response("read-data", [("read", "Read", {"file_path": "sales.csv"})])
    result("read", csv)
    response("first-run", [("bad-run", "Bash", {"command": "python analyze.py sales.csv"})])
    result(
        "bad-run",
        "ValueError: time data 'invalid' does not match date format",
        True,
        exitCode=1,
        stderr="ValueError: invalid date",
    )
    response(
        "correct",
        [
            (
                "edit",
                "Edit",
                {
                    "file_path": "analyze.py",
                    "old_string": "pd.to_datetime(df['date'])",
                    "new_string": "pd.to_datetime(df['date'], errors='coerce')",
                },
            )
        ],
        "首次执行遇到无效日期，改为标记异常日期并单独统计，避免把无效日期计入有效样本。",
    )
    result("edit", "Updated analyze.py")
    response(
        "rerun",
        [
            ("good-run", "Bash", {"command": "python analyze.py sales.csv"}),
            ("notes", "Read", {"file_path": "analysis-notes.md"}),
        ],
    )
    result(
        "good-run",
        '{"rows":5,"invalid_dates":2,"invalid_rate":0.4,"valid_rows":3,"valid_mean":30}',
        exitCode=0,
    )
    result("notes", "报告需要说明有效样本与无效日期比例；样本较少时不判断趋势。")
    response(
        "validate",
        [
            (
                "agent",
                "Agent",
                {
                    "description": "复核计算结果",
                    "prompt": "请复核 5 行中 2 行无效日期，占 40%；有效日期行的值为 10、30、50，均值为 30。",
                },
            ),
            ("task-update", "TaskUpdate", {"taskId": "analysis", "status": "completed"}),
        ],
    )
    result("agent", "Background validation agent started")
    result("task-update", "Task status updated")
    add(
        "user",
        {
            "content": "<task-notification><task-id>validation</task-id><tool-use-id>agent</tool-use-id><status>completed</status><summary>复核结果</summary><result>复核通过：无效日期 2/5=40%；有效值 10、30、50 的均值为 30。样本只有 3 行，不足以判断趋势。</result></task-notification>"
        },
        origin={"kind": "task-notification"},
    )
    response(
        "write-report",
        [("write", "Write", {"file_path": "report.md", "content": report_text})],
        "子任务复核通过，将计算结果与样本限制写入报告。",
    )
    result("write", "Created report.md")
    add(
        "assistant",
        {
            "id": "final",
            "model": "claude-demo",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": report_text + "报告已写入 report.md。"}],
        },
    )
    add("system", subtype="context_compacted", content="Conversation context compacted")
    source = base / "synthetic-transcript.jsonl"
    root = base / "observations"
    if source.is_file() and (root / "demo-event-workflow/derived/observer_trace.json").is_file():
        trace = json.loads((root / "demo-event-workflow/derived/observer_trace.json").read_text())
        print(
            json.dumps(
                {"synthetic": True, "storage_root": str(root), "event_count": len(trace["events"])},
                ensure_ascii=False,
            ),
            flush=True,
        )
        return root
    source.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))
    create_session("demo-event-workflow", project, root)
    snapshot_transcript("demo-event-workflow", source, root, attempts=1, delay=0)
    trace = build_observer_trace("demo-event-workflow", str(root))
    print(
        json.dumps(
            {
                "synthetic": True,
                "storage_root": str(root.resolve()),
                "event_count": len(trace["events"]),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="scratch/event-workflow-demo")
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    root = create_demo(Path(args.base).resolve())
    if args.generate:
        last_stage = [None]

        def progress(value):
            if value["stage"] != last_stage[0]:
                print(
                    json.dumps(
                        {
                            "stage": value["stage"],
                            "message": value["message"],
                            "status": value["status"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                last_stage[0] = value["stage"]

        workflow = run_event_workflow("demo-event-workflow", str(root), progress_callback=progress)
        print(
            json.dumps(
                {
                    "model": workflow["inference_run"]["model"],
                    "reasoning_effort": workflow["inference_run"]["reasoning_effort"],
                    "events": len(workflow["event_summaries"]),
                    "relations": len(workflow["logical_relations"]),
                    "levels": {
                        level: sum(item["level"] == level for item in workflow["event_importance"])
                        for level in ["key_decision", "normal_execution", "key_turning_point", "key_result"]
                    },
                    "metrics": workflow["inference_run"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
