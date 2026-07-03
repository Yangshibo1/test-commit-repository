"""
MC2 Analysis - Node 02: Filter SaidIT Events
基于 node_01_loaded.json，筛选 SaidIT 相关事件并保存为可继续处理的中间数据集。
"""
import json
import sys
from pathlib import Path
from collections import Counter
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def event_to_record(event):
    when = event.get("when", 0)
    return {
        "id": event.get("id"),
        "short_name": event.get("short_name"),
        "when": when,
        "datetime": str(datetime.fromtimestamp(when)),
        "parties": event.get("parties", []),
        "details": event.get("details", {}),
        "source_event": event,
    }


def main():
    print("=" * 60)
    print("Node 02: Filter SaidIT Events")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    input_file = work_dir / "node_01_loaded.json"
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("events", [])
    event_type_counts = Counter(e.get("short_name") for e in events)

    # 最小处理节点：过滤 SaidIT 相关事件。
    # 下游节点将只读取本节点输出，而不是重新扫描完整原始数据。
    saidit_events = []
    for event in events:
        short_name = str(event.get("short_name", "")).lower()
        details_text = json.dumps(event.get("details", {}), ensure_ascii=False).lower()
        parties_text = " ".join(event.get("parties", [])).lower()
        if "saidit" in short_name or "saidit" in details_text or "system:saidit" in parties_text:
            saidit_events.append(event_to_record(event))

    saidit_type_counts = Counter(e["short_name"] for e in saidit_events)
    poster_counts = Counter()
    for record in saidit_events:
        details = record.get("details", {})
        poster = details.get("poster_id") or details.get("person")
        if not poster:
            for party in record.get("parties", []):
                if "person:" in party:
                    poster = party.replace("Agent/", "")
                    break
        if poster:
            poster_counts[poster] += 1

    output = {
        "node_id": "node_02",
        "input_file": str(input_file),
        "operation": "filter_saidit_events",
        "total_input_events": len(events),
        "total_saidit_events": len(saidit_events),
        "event_type_counts": dict(event_type_counts.most_common()),
        "saidit_type_counts": dict(saidit_type_counts.most_common()),
        "poster_counts": dict(poster_counts.most_common()),
        "records": saidit_events,
        "observation": {
            "summary": "发现 SaidIT 相关事件，可在下一节点基于这些事件查找目标时间的异常帖子。",
            "next_decision": "在 SaidIT 子集内按日期 2046-05-17 和时间 19:21:15 定位异常发布事件。"
        }
    }

    output_file = work_dir / "node_02_saidit_events.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Input events: {len(events):,}")
    print(f"SaidIT events: {len(saidit_events):,}")
    print(f"Output: {output_file}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node02_input_loaded", "entity_type": "dataset", "location": str(input_file),
             "attributes": {"events": len(events), "from_node": "node_01"}},
            {"id": "node02_output_saidit", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"events": len(saidit_events), "filter": "saidit", "from_node": "node_02"}}
        ],
        activities=[
            {"id": "node02_filter_saidit", "activity_type": "filter",
             "description": "从node_01_loaded.json中过滤SaidIT相关事件",
             "attributes": {"input_events": len(events), "output_events": len(saidit_events), "predicate": "saidit in short_name/details/parties"}}
        ],
        agents=[
            {"id": "node02_agent", "agent_type": "python_code", "name": "node_02_filter_saidit_events",
             "attributes": {"script": "node_02_filter_saidit_events.py"}}
        ],
        relations=[
            ("node02_filter_saidit", "node02_input_loaded", "used"),
            ("node02_output_saidit", "node02_filter_saidit", "wasGeneratedBy"),
            ("node02_filter_saidit", "node02_agent", "wasAssociatedWith"),
            ("node02_output_saidit", "node02_input_loaded", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_02",
        step_name="filter_saidit_events",
        description="读取node_01产物，过滤SaidIT相关事件，形成下游查找异常帖子的中间数据集",
        code_generated=[
            "saidit_events = []",
            "if 'saidit' in short_name or 'saidit' in details_text or 'system:saidit' in parties_text:",
            "    saidit_events.append(event_to_record(event))"
        ],
        code_files=["src/node_02_filter_saidit_events.py"],
        commands_run=["python src/node_02_filter_saidit_events.py"],
        input_files=[str(input_file)],
        output_files=[str(output_file)],
        parameters={
            "input_events": len(events),
            "output_events": len(saidit_events),
            "saidit_type_counts": dict(saidit_type_counts.most_common()),
            "top_posters": dict(poster_counts.most_common(10)),
            "next_step_basis": "node_03 将读取 node_02_saidit_events.json，而不是直接读取完整原始数据"
        }
    )

    print("[OK] Node 02 completed")
    return session_id


if __name__ == "__main__":
    main()
