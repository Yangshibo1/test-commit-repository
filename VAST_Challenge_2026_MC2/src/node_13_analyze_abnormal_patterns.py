"""
MC2 Analysis - Node 13: Analyze John's Three Abnormal Posting Patterns
读取 node_12_john_all_posts_analysis.json 和 node_01_loaded.json，
分析 John Windward 三次异常发帖（HiddenOrca.txt, MellowOtter.txt, SwiftWren.txt）的共同模式。
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def compact_event(event):
    when = float(event.get("when", 0))
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
    print("Node 13: Analyze John's Three Abnormal Posting Patterns")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 读取输入文件
    john_analysis_input = work_dir / "node_12_john_all_posts_analysis.json"
    raw_input = work_dir / "node_01_loaded.json"

    with open(john_analysis_input, "r", encoding="utf-8") as f:
        john_analysis = json.load(f)
    with open(raw_input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    events = sorted(raw.get("events", []), key=lambda e: float(e.get("when", 0)))

    # 三次异常发帖的详细信息
    abnormal_posts = john_analysis["john_saidit_activity"]["abnormal_post_details"]

    # 对每次异常发帖，分析其前后 5 分钟的事件链
    patterns = []
    for post in abnormal_posts:
        post_when = float(post["when"])
        content_source = post["content_source"]

        # 前后 5 分钟窗口
        window_start = post_when - 300
        window_end = post_when + 300

        window_events = []
        for event in events:
            event_when = float(event.get("when", 0))
            if window_start <= event_when <= window_end:
                # 只保留与 John 或 content_source 相关的事件
                parties_text = " ".join(event.get("parties", []))
                details_text = json.dumps(event.get("details", {}), ensure_ascii=False)
                if "john" in parties_text.lower() or content_source in details_text:
                    window_events.append(compact_event(event))

        # 找出 content_source 文件的创建事件
        source_create_event = None
        for event in events:
            if event.get("short_name") == "create_file":
                details = event.get("details", {})
                filename = details.get("filename", "")
                if content_source in filename:
                    source_create_event = compact_event(event)
                    break

        # 找出 content_source 相关的指令传播链
        instruction_chain = []
        source_stem = content_source.replace(".txt", "")
        for event in events:
            event_text = json.dumps(event, ensure_ascii=False)
            if source_stem in event_text or content_source in event_text:
                if event.get("when", 0) <= post_when:
                    instruction_chain.append(compact_event(event))

        pattern = {
            "post": post,
            "content_source": content_source,
            "post_datetime": post["datetime"],
            "window_event_count": len(window_events),
            "window_events_summary": [
                {"id": e["id"], "short_name": e["short_name"], "datetime": e["datetime"]}
                for e in window_events
            ],
            "source_create_event": source_create_event,
            "instruction_chain_length": len(instruction_chain),
            "related_instruction_events": len([e for e in instruction_chain if e["short_name"] == "queue_subordinate_task"])
        }
        patterns.append(pattern)

    # 比较三次异常发帖的共同模式
    commonalities = []
    differences = []

    # 共同点
    all_have_source_create = all(p["source_create_event"] is not None for p in patterns)
    all_in_general_forum = all(p["post"]["forum"] == "general" for p in patterns)
    all_by_john = True  # 已知都是 John 发布的

    commonalities.append(f"所有异常帖子都发布在 general 论坛")
    if all_have_source_create:
        commonalities.append(f"所有 content_source 文件都有明确的创建事件")

    # 找出每次发帖的指令来源
    for pattern in patterns:
        content_source = pattern["content_source"]
        # 找出该文件的创建者
        creator = None
        if pattern["source_create_event"]:
            parties = pattern["source_create_event"].get("parties", [])
            for p in parties:
                if "person:" in p and "Agent/person:" not in p:
                    creator = p
                    break
        pattern["file_creator"] = creator

        # 找出传播链中的关键人物
        key_parties = set()
        for event in pattern.get("window_events_summary", []):
            # 从原始 events 中获取完整信息
            for e in events:
                if e.get("id") == event["id"]:
                    for party in e.get("parties", []):
                        if "person:" in party:
                            key_parties.add(party)
        pattern["key_parties_in_window"] = list(key_parties)

    # 对比三次发帖的文件创建者
    creators = [p.get("file_creator") for p in patterns]
    unique_creators = set(c for c in creators if c)

    output = {
        "node_id": "node_13",
        "operation": "analyze_three_abnormal_posting_patterns",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "three_abnormal_posts": [
            {
                "content_source": p["content_source"],
                "datetime": p["post_datetime"],
                "file_creator": p.get("file_creator"),
                "related_instruction_count": p["related_instruction_events"]
            }
            for p in patterns
        ],
        "pattern_analysis": {
            "commonalities": commonalities,
            "unique_creators": list(unique_creators),
            "all_in_general_forum": all_in_general_forum
        },
        "detailed_patterns": patterns,
        "observation": {
            "summary": "已分析 John Windward 三次异常发帖的模式和上下文",
            "next_decision": "需要进一步分析每次发帖的传播路径差异"
        }
    }

    output_file = work_dir / "node_13_abnormal_patterns_analysis.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Analyzed {len(patterns)} abnormal posts")
    print(f"Common creators: {unique_creators}")
    print(f"All in general forum: {all_in_general_forum}")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node13_input_john_analysis", "entity_type": "dataset", "location": str(john_analysis_input),
             "attributes": {"from_node": "node_12", "abnormal_posts": len(abnormal_posts)}},
            {"id": "node13_input_raw", "entity_type": "dataset", "location": str(raw_input),
             "attributes": {"from_node": "node_01", "usage": "分析每次发帖的前后事件窗口"}},
            {"id": "node13_output_patterns", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"patterns_analyzed": len(patterns), "unique_creators": len(unique_creators)}}
        ],
        activities=[
            {"id": "node13_analyze_patterns", "activity_type": "compare",
             "description": "分析 John Windward 三次异常发帖的共同模式和差异",
             "attributes": {"abnormal_posts": len(abnormal_posts), "window_seconds": 300}}
        ],
        agents=[
            {"id": "node13_agent", "agent_type": "python_code", "name": "node_13_analyze_abnormal_patterns",
             "attributes": {"script": "node_13_analyze_abnormal_patterns.py"}}
        ],
        relations=[
            ("node13_analyze_patterns", "node13_input_john_analysis", "used"),
            ("node13_analyze_patterns", "node13_input_raw", "used"),
            ("node13_output_patterns", "node13_analyze_patterns", "wasGeneratedBy"),
            ("node13_analyze_patterns", "node13_agent", "wasAssociatedWith"),
            ("node13_output_patterns", "node13_input_john_analysis", "wasDerivedFrom"),
            ("node13_output_patterns", "node13_input_raw", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_13",
        step_name="analyze_abnormal_patterns",
        description="分析 John Windward 三次异常发帖的共同模式、文件创建者和传播路径",
        code_generated=[
            "for each abnormal post: analyze ±5min window events",
            "find content_source file creation event",
            "trace instruction chain for each source file"
        ],
        code_files=["src/node_13_analyze_abnormal_patterns.py"],
        commands_run=["python src/node_13_analyze_abnormal_patterns.py"],
        input_files=[str(john_analysis_input), str(raw_input)],
        output_files=[str(output_file)],
        parameters={
            "abnormal_posts_count": len(abnormal_posts),
            "unique_creators": len(unique_creators),
            "all_in_general_forum": all_in_general_forum,
            "next_step_basis": "基于模式分析结果决定是否需要进一步追溯传播路径"
        }
    )

    print("[OK] Node 13 completed")
    return session_id


if __name__ == "__main__":
    main()
