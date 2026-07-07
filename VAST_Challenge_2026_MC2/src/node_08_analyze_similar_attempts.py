"""
MC2 Analysis - Node 08: Analyze Similar Abnormal Posting Attempts
基于 node_04_source_trace.json 的发现，按需回读 node_01_loaded.json，找出所有与 SwiftWren 指令相关的历史/并发实例，
比较哪些人收到类似任务、哪些人尝试/检查 SaidIT、为什么只有 John Windward 发出了异常帖子。
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

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


def normalize_person(value):
    if not value:
        return None
    return str(value).replace("Agent/", "").replace("agent:", "").replace("Agent:", "")


def extract_target_agent(event):
    details = event.get("details", {})
    target = details.get("target_agent")
    if target:
        return normalize_person(target)
    nested = details.get("details", {}) if isinstance(details, dict) else {}
    if isinstance(nested, dict) and nested.get("person"):
        return normalize_person(nested.get("person"))
    parties = event.get("parties", [])
    if len(parties) >= 2:
        return normalize_person(parties[1])
    return None


def event_mentions_person(event, person):
    text = json.dumps(event, ensure_ascii=False).lower()
    return person.replace("person:", "").lower() in text


def main():
    print("=" * 60)
    print("Node 08: Analyze Similar Abnormal Posting Attempts")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    trace_input_file = work_dir / "node_04_source_trace.json"
    raw_input_file = work_dir / "node_01_loaded.json"

    with open(trace_input_file, "r", encoding="utf-8") as f:
        trace = json.load(f)
    with open(raw_input_file, "r", encoding="utf-8") as f:
        raw = json.load(f)

    events = raw.get("events", [])
    target_post = trace["target_post"]
    target_when = float(target_post["when"])
    content_source = trace["content_source"]
    instruction_file = content_source.replace(".txt", "_further_instructions.md")

    # 1. 找出所有包含 SwiftWren 指令/源文件的事件。
    related_events = []
    for event in events:
        text = json.dumps(event, ensure_ascii=False)
        if content_source in text or instruction_file in text:
            related_events.append(event)
    related_events.sort(key=lambda e: float(e.get("when", 0)))

    # 2. 找出所有被要求读取 SwiftWren_further_instructions.md 的目标人员。
    instruction_tasks = []
    for event in related_events:
        if event.get("short_name") != "queue_subordinate_task":
            continue
        details = event.get("details", {})
        args = details.get("args", {}) if isinstance(details, dict) else {}
        nested = details.get("details", {}) if isinstance(details, dict) else {}
        path = args.get("path") or (nested.get("details", {}) if isinstance(nested, dict) else {}).get("path")
        if path == instruction_file or instruction_file in json.dumps(details, ensure_ascii=False):
            target = extract_target_agent(event)
            source = normalize_person(event.get("parties", [None])[0]) if event.get("parties") else None
            instruction_tasks.append({
                "event": compact_event(event),
                "source_agent": source,
                "target_agent": target,
                "seconds_before_target_post": float(event.get("when", 0)) - target_when
            })

    targets = sorted(set(t["target_agent"] for t in instruction_tasks if t.get("target_agent")))

    # 3. 对每个收到类似指令的人，分析后续行为：是否检查SaidIT、是否发帖、是否删除源文件。
    per_target = {}
    for target in targets:
        first_task_time = min(t["event"]["when"] for t in instruction_tasks if t["target_agent"] == target)
        # 看收到指令后 2 小时内行为；也保留全局 SwiftWren 相关行为。
        window_end = first_task_time + 7200
        target_events_after = [
            compact_event(e) for e in events
            if first_task_time <= float(e.get("when", 0)) <= window_end and event_mentions_person(e, target)
        ]
        target_related = [
            compact_event(e) for e in related_events
            if event_mentions_person(e, target)
        ]
        saidit_checks = [e for e in target_events_after if e["short_name"] == "saidit_post_check"]
        saidit_posts = [e for e in target_events_after if e["short_name"] in ["saidit_post", "post_saidit"]]
        swiftwren_posts = [
            e for e in saidit_posts
            if content_source in json.dumps(e.get("details", {}), ensure_ascii=False)
        ]
        deletes = [
            e for e in target_events_after
            if e["short_name"] == "delete_file" and (content_source in json.dumps(e.get("details", {}), ensure_ascii=False) or instruction_file in json.dumps(e.get("details", {}), ensure_ascii=False))
        ]
        reads = [
            e for e in target_events_after
            if e["short_name"] == "read_file" and instruction_file in json.dumps(e.get("details", {}), ensure_ascii=False)
        ]
        per_target[target] = {
            "first_instruction_time": str(datetime.fromtimestamp(first_task_time)),
            "instruction_count": sum(1 for t in instruction_tasks if t["target_agent"] == target),
            "source_agents": sorted(set(t["source_agent"] for t in instruction_tasks if t["target_agent"] == target and t.get("source_agent"))),
            "read_instruction_events": reads,
            "saidit_post_check_events": saidit_checks,
            "saidit_post_events_after_instruction": saidit_posts,
            "swiftwren_saidit_posts": swiftwren_posts,
            "delete_source_events": deletes,
            "all_swiftwren_related_events_for_target": target_related[:20],
            "outcome": "posted_swiftwren_to_saidit" if swiftwren_posts else "no_swiftwren_saidit_post_found"
        }

    # 4. 分析直接任务链中的“为什么只有 John 发出来”：直接上游是 Chloe->John，John 后续连续出现 check/post/delete。
    posters = [target for target, info in per_target.items() if info["swiftwren_saidit_posts"]]
    non_posters = [target for target, info in per_target.items() if not info["swiftwren_saidit_posts"]]

    # 5. 另外统计所有 SwiftWren 相关 queue_subordinate_task 的来源/目标分布，发现是否存在广泛传播但未发帖。
    source_counter = Counter(t["source_agent"] for t in instruction_tasks if t.get("source_agent"))
    target_counter = Counter(t["target_agent"] for t in instruction_tasks if t.get("target_agent"))

    output = {
        "node_id": "node_08",
        "operation": "analyze_similar_abnormal_posting_attempts",
        "input_trace_file": str(trace_input_file),
        "input_raw_file": str(raw_input_file),
        "target_post": target_post,
        "content_source": content_source,
        "instruction_file": instruction_file,
        "summary": {
            "related_events_total": len(related_events),
            "instruction_task_events": len(instruction_tasks),
            "unique_instruction_targets": len(targets),
            "targets_with_swiftwren_saidit_post": posters,
            "targets_without_swiftwren_saidit_post_count": len(non_posters),
            "source_agent_counts": dict(source_counter.most_common()),
            "target_agent_counts": dict(target_counter.most_common())
        },
        "instruction_tasks": instruction_tasks,
        "per_target_outcomes": per_target,
        "analysis": {
            "similar_instances_found": len(instruction_tasks) > 1,
            "why_only_john_posted_preliminary": [
                "John Windward 是唯一出现 content_source=SwiftWren.txt 的 saidit_post 事件的目标人员。",
                "John 在收到 Chloe Ballast 的 read_file 指令后，1秒后进行 saidit_post_check，2秒后发布 saidit_post，随后连续删除指令文件和源文件。",
                "其他收到 SwiftWren_further_instructions.md 相关任务的人员，在其后续窗口内未出现 content_source=SwiftWren.txt 的 SaidIT 发布事件。"
            ],
            "next_decision": "需要进一步检查 John 与其他目标人员在任务后的 SaidIT check / access / permission / post pipeline 差异。"
        }
    }

    output_file = work_dir / "node_08_similar_attempts.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Instruction tasks: {len(instruction_tasks)}")
    print(f"Unique targets: {len(targets)}")
    print(f"Posters: {posters}")
    print(f"Output: {output_file}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node08_input_trace", "entity_type": "dataset", "location": str(trace_input_file),
             "attributes": {"from_node": "node_04", "content_source": content_source}},
            {"id": "node08_input_raw", "entity_type": "dataset", "location": str(raw_input_file),
             "attributes": {"from_node": "node_01", "usage": "查找所有类似SwiftWren指令实例"}},
            {"id": "node08_output_similar", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"instruction_tasks": len(instruction_tasks), "unique_targets": len(targets), "posters": posters}}
        ],
        activities=[
            {"id": "node08_analyze_similar", "activity_type": "analyze",
             "description": "分析John Windward类似异常发帖行为及其他未发帖实例",
             "attributes": {"instruction_file": instruction_file, "content_source": content_source, "targets": len(targets)}}
        ],
        agents=[
            {"id": "node08_agent", "agent_type": "python_code", "name": "node_08_analyze_similar_attempts",
             "attributes": {"script": "node_08_analyze_similar_attempts.py"}}
        ],
        relations=[
            ("node08_analyze_similar", "node08_input_trace", "used"),
            ("node08_analyze_similar", "node08_input_raw", "used"),
            ("node08_output_similar", "node08_analyze_similar", "wasGeneratedBy"),
            ("node08_analyze_similar", "node08_agent", "wasAssociatedWith"),
            ("node08_output_similar", "node08_input_trace", "wasDerivedFrom"),
            ("node08_output_similar", "node08_input_raw", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_08",
        step_name="analyze_similar_abnormal_posting_attempts",
        description="读取node_04证据链并按需回读node_01，查找所有SwiftWren指令相关实例，比较John与其他目标人员的后续行为",
        code_generated=[
            "instruction_tasks = [queue_subordinate_task events with SwiftWren_further_instructions.md]",
            "for target in targets: analyze post-check/post/delete outcomes after instruction",
            "posters = [target for target if swiftwren_saidit_posts]"
        ],
        code_files=["src/node_08_analyze_similar_attempts.py"],
        commands_run=["python src/node_08_analyze_similar_attempts.py"],
        input_files=[str(trace_input_file), str(raw_input_file)],
        output_files=[str(output_file)],
        parameters={
            "instruction_tasks": len(instruction_tasks),
            "unique_targets": len(targets),
            "posters": posters,
            "next_step_basis": "node_09 将读取 node_08_similar_attempts.json，并按需回读node_01检查SaidIT check/permission/post pipeline差异"
        }
    )

    print("[OK] Node 08 completed")
    return session_id


if __name__ == "__main__":
    main()
