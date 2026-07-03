"""
MC2 Analysis - Node 04: Trace Target Post Source
基于 node_03_target_post.json 中的异常帖子，按需读取 node_01_loaded.json 追溯 content_source、任务链和删除行为。
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def compact_event(event):
    when = event.get("when", 0)
    return {
        "id": event.get("id"),
        "short_name": event.get("short_name"),
        "when": when,
        "datetime": str(datetime.fromtimestamp(when)),
        "parties": event.get("parties", []),
        "details": event.get("details", {})
    }


def main():
    print("=" * 60)
    print("Node 04: Trace Target Post Source")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    target_input_file = work_dir / "node_03_target_post.json"
    source_input_file = work_dir / "node_01_loaded.json"

    with open(target_input_file, "r", encoding="utf-8") as f:
        target_data = json.load(f)

    target_matches = target_data.get("target_matches", [])
    if not target_matches:
        raise RuntimeError("node_03_target_post.json 中没有 target_matches，无法追溯来源")

    target_post = target_matches[0]
    target_when = float(target_post["when"])
    content_source = target_post.get("details", {}).get("content_source")
    if not content_source:
        raise RuntimeError("目标帖子没有 content_source 字段")

    with open(source_input_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    events = raw_data.get("events", [])

    # 最小处理节点：围绕 node_03 的目标帖子，按 content_source 回原始数据追溯文件生命周期和任务链。
    source_stem = content_source.replace(".txt", "")
    source_related_events = []
    for event in events:
        event_text = json.dumps(event, ensure_ascii=False)
        if content_source in event_text or source_stem in event_text:
            source_related_events.append(event)

    create_events = [compact_event(e) for e in source_related_events if e.get("short_name") == "create_file"]
    read_events = [compact_event(e) for e in source_related_events if e.get("short_name") == "read_file"]
    delete_events = [compact_event(e) for e in source_related_events if e.get("short_name") == "delete_file"]
    saidit_events = [compact_event(e) for e in source_related_events if "saidit" in str(e.get("short_name", "")).lower()]

    # 异常帖前后 10 分钟内与关键人员/目标文件相关的事件
    key_people = ["daniel_gangway", "chloe_ballast", "john_windward", "emma_harbor"]
    window_start = target_when - 600
    window_end = target_when + 120
    nearby_key_events = []
    for event in events:
        when = float(event.get("when", 0))
        if not (window_start <= when <= window_end):
            continue
        event_text = json.dumps(event, ensure_ascii=False).lower()
        if any(person in event_text for person in key_people) or source_stem.lower() in event_text:
            nearby_key_events.append(compact_event(event))

    task_chain_events = [
        e for e in nearby_key_events
        if e.get("short_name") in ["queue_subordinate_task", "saidit_post_check", "saidit_post", "delete_file", "read_file"]
    ]

    # 检查 Daniel 在异常前一小时是否收到上游任务（基于事件 details/parties）。
    daniel_prior_tasks = []
    prior_start = target_when - 3600
    for event in events:
        when = float(event.get("when", 0))
        if not (prior_start <= when < target_when):
            continue
        if event.get("short_name") != "queue_subordinate_task":
            continue
        text = json.dumps(event, ensure_ascii=False).lower()
        if "daniel_gangway" in text:
            daniel_prior_tasks.append(compact_event(event))

    source_type_counts = Counter(e.get("short_name") for e in source_related_events)

    output = {
        "node_id": "node_04",
        "operation": "trace_target_post_source",
        "input_target_file": str(target_input_file),
        "input_source_file": str(source_input_file),
        "target_post": target_post,
        "content_source": content_source,
        "source_related_summary": {
            "total": len(source_related_events),
            "type_counts": dict(source_type_counts.most_common()),
            "create_events": len(create_events),
            "read_events": len(read_events),
            "delete_events": len(delete_events),
            "saidit_events": len(saidit_events)
        },
        "file_lifecycle": {
            "created": create_events,
            "read": read_events,
            "deleted": delete_events
        },
        "task_chain_near_post": task_chain_events,
        "daniel_prior_tasks_1h": daniel_prior_tasks,
        "observation": {
            "summary": "已基于node_03确定的content_source追溯到文件生命周期、任务传递链和删除行为。",
            "next_decision": "汇总node_04的链条证据，生成最终报告；报告不再重新扫描原始数据。"
        }
    }

    output_file = work_dir / "node_04_source_trace.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Target post id: {target_post.get('id')}")
    print(f"Content source: {content_source}")
    print(f"Source related events: {len(source_related_events)}")
    print(f"Task chain events near post: {len(task_chain_events)}")
    print(f"Daniel prior tasks in 1h: {len(daniel_prior_tasks)}")
    print(f"Output: {output_file}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node04_input_target", "entity_type": "dataset", "location": str(target_input_file),
             "attributes": {"target_matches": len(target_matches), "from_node": "node_03"}},
            {"id": "node04_input_raw", "entity_type": "dataset", "location": str(source_input_file),
             "attributes": {"events": len(events), "from_node": "node_01", "usage": "按content_source追溯"}},
            {"id": "node04_output_trace", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"source_related_events": len(source_related_events), "content_source": content_source, "from_node": "node_04"}}
        ],
        activities=[
            {"id": "node04_trace_source", "activity_type": "trace",
             "description": "基于目标帖子content_source追溯文件生命周期和任务链",
             "attributes": {"content_source": content_source, "target_post_id": target_post.get("id"), "window_seconds_before": 600, "window_seconds_after": 120}}
        ],
        agents=[
            {"id": "node04_agent", "agent_type": "python_code", "name": "node_04_trace_target_source",
             "attributes": {"script": "node_04_trace_target_source.py"}}
        ],
        relations=[
            ("node04_trace_source", "node04_input_target", "used"),
            ("node04_trace_source", "node04_input_raw", "used"),
            ("node04_output_trace", "node04_trace_source", "wasGeneratedBy"),
            ("node04_trace_source", "node04_agent", "wasAssociatedWith"),
            ("node04_output_trace", "node04_input_target", "wasDerivedFrom"),
            ("node04_output_trace", "node04_input_raw", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_04",
        step_name="trace_target_post_source",
        description="读取node_03异常帖子产物，按content_source从node_01原始数据产物中追溯文件生命周期、传播链和删除行为",
        code_generated=[
            "content_source = target_post['details']['content_source']",
            "source_related_events = [event for event in events if content_source in json.dumps(event)]",
            "task_chain_events = [e for e in nearby_key_events if e['short_name'] in [...]]"
        ],
        code_files=["src/node_04_trace_target_source.py"],
        commands_run=["python src/node_04_trace_target_source.py"],
        input_files=[str(target_input_file), str(source_input_file)],
        output_files=[str(output_file)],
        parameters={
            "target_post_id": target_post.get("id"),
            "content_source": content_source,
            "source_related_events": len(source_related_events),
            "task_chain_events_near_post": len(task_chain_events),
            "daniel_prior_tasks_1h": len(daniel_prior_tasks),
            "next_step_basis": "node_05 将只读取 node_04_source_trace.json 生成最终报告"
        }
    )

    print("[OK] Node 04 completed")
    return session_id


if __name__ == "__main__":
    main()
