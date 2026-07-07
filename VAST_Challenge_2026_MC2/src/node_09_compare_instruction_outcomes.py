"""
MC2 Analysis - Node 09: Compare Instruction Outcomes
读取 node_08_similar_attempts.json，并按需回读 node_01_loaded.json，逐条比较 SwiftWren 指令任务后的短窗口行为，
解释为什么只有 John Windward 的异常帖子成功发出。
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
    when = float(event.get("when", 0))
    return {
        "id": event.get("id"),
        "short_name": event.get("short_name"),
        "when": when,
        "datetime": str(datetime.fromtimestamp(when)),
        "parties": event.get("parties", []),
        "details": event.get("details", {})
    }


def normalize_agent(value):
    if not value:
        return None
    text = str(value)
    text = text.replace("Agent/", "")
    text = text.replace("agent:", "")
    return text


def person_key(person):
    if not person:
        return ""
    return normalize_agent(person).replace("person:", "").lower()


def mentions(event, person):
    key = person_key(person)
    return key and key in json.dumps(event, ensure_ascii=False).lower()


def is_swiftwren_post(event, content_source):
    if event.get("short_name") not in ["saidit_post", "post_saidit"]:
        return False
    return content_source in json.dumps(event.get("details", {}), ensure_ascii=False)


def main():
    print("=" * 60)
    print("Node 09: Compare Instruction Outcomes")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    attempts_input = work_dir / "node_08_similar_attempts.json"
    raw_input = work_dir / "node_01_loaded.json"

    with open(attempts_input, "r", encoding="utf-8") as f:
        attempts = json.load(f)
    with open(raw_input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    events = sorted(raw.get("events", []), key=lambda e: float(e.get("when", 0)))
    content_source = attempts["content_source"]
    instruction_file = attempts["instruction_file"]
    target_when = float(attempts["target_post"]["when"])
    target_post_id = attempts["target_post"]["id"]
    instruction_tasks = attempts.get("instruction_tasks", [])

    # 对每条指令任务，检查目标人员在后续 2 分钟和 30 分钟内是否执行关键动作。
    per_task = []
    outcomes = Counter()
    successful_tasks = []
    checked_but_no_post = []
    no_check_no_post = []
    posted_other_content = []

    for task in instruction_tasks:
        task_event = task["event"]
        task_when = float(task_event["when"])
        target = task.get("target_agent")
        source = task.get("source_agent")
        two_min = [e for e in events if task_when <= float(e.get("when", 0)) <= task_when + 120 and mentions(e, target)]
        thirty_min = [e for e in events if task_when <= float(e.get("when", 0)) <= task_when + 1800 and mentions(e, target)]

        check_events = [compact_event(e) for e in two_min if e.get("short_name") == "saidit_post_check"]
        swift_posts = [compact_event(e) for e in two_min if is_swiftwren_post(e, content_source)]
        any_saidit_posts_30m = [compact_event(e) for e in thirty_min if e.get("short_name") in ["saidit_post", "post_saidit"]]
        deletes = [
            compact_event(e) for e in two_min
            if e.get("short_name") == "delete_file" and (content_source in json.dumps(e.get("details", {}), ensure_ascii=False) or instruction_file in json.dumps(e.get("details", {}), ensure_ascii=False))
        ]
        reads = [
            compact_event(e) for e in two_min
            if e.get("short_name") == "read_file" and instruction_file in json.dumps(e.get("details", {}), ensure_ascii=False)
        ]

        if swift_posts:
            outcome = "swiftwren_posted"
        elif check_events and not swift_posts:
            outcome = "checked_saidit_but_no_swiftwren_post"
        elif any_saidit_posts_30m:
            outcome = "posted_other_saidit_content_within_30m"
        else:
            outcome = "no_saidit_post_attempt_observed"
        outcomes[outcome] += 1

        record = {
            "task_event": task_event,
            "source_agent": source,
            "target_agent": target,
            "seconds_from_target_post": task_when - target_when,
            "outcome": outcome,
            "read_instruction_events_2m": reads,
            "saidit_post_check_events_2m": check_events,
            "swiftwren_posts_2m": swift_posts,
            "delete_source_events_2m": deletes,
            "any_saidit_posts_30m": any_saidit_posts_30m[:5]
        }
        per_task.append(record)
        if swift_posts:
            successful_tasks.append(record)
        elif check_events:
            checked_but_no_post.append(record)
        elif any_saidit_posts_30m:
            posted_other_content.append(record)
        else:
            no_check_no_post.append(record)

    # 按目标人员汇总，回答“类似实例”是哪些人/任务。
    per_target = defaultdict(lambda: {
        "instruction_count": 0,
        "outcomes": Counter(),
        "source_agents": Counter(),
        "successful_task_ids": [],
        "check_task_ids": [],
        "first_instruction_time": None,
        "last_instruction_time": None
    })
    for record in per_task:
        target = record["target_agent"]
        info = per_target[target]
        info["instruction_count"] += 1
        info["outcomes"][record["outcome"]] += 1
        if record["source_agent"]:
            info["source_agents"][record["source_agent"]] += 1
        if record["swiftwren_posts_2m"]:
            info["successful_task_ids"].append(record["task_event"]["id"])
        if record["saidit_post_check_events_2m"]:
            info["check_task_ids"].append(record["task_event"]["id"])
        dt = record["task_event"]["datetime"]
        if info["first_instruction_time"] is None or dt < info["first_instruction_time"]:
            info["first_instruction_time"] = dt
        if info["last_instruction_time"] is None or dt > info["last_instruction_time"]:
            info["last_instruction_time"] = dt

    per_target_json = {}
    for target, info in sorted(per_target.items()):
        per_target_json[target] = {
            "instruction_count": info["instruction_count"],
            "outcomes": dict(info["outcomes"]),
            "source_agents": dict(info["source_agents"].most_common()),
            "successful_task_ids": info["successful_task_ids"],
            "check_task_ids": info["check_task_ids"],
            "first_instruction_time": info["first_instruction_time"],
            "last_instruction_time": info["last_instruction_time"]
        }

    # 找出目标帖子前后时间分布：许多类似任务发生在目标帖子之后，因此不是“未发出前的竞争实例”。
    before_target = [r for r in per_task if r["seconds_from_target_post"] < 0]
    after_target = [r for r in per_task if r["seconds_from_target_post"] > 0]

    # 成功任务的关键序列
    success_sequences = []
    for record in successful_tasks:
        combined = []
        combined.extend(record["read_instruction_events_2m"])
        combined.extend(record["saidit_post_check_events_2m"])
        combined.extend(record["swiftwren_posts_2m"])
        combined.extend(record["delete_source_events_2m"])
        combined = sorted(combined, key=lambda e: e["when"])
        success_sequences.append({
            "instruction_task": record["task_event"],
            "source_agent": record["source_agent"],
            "target_agent": record["target_agent"],
            "sequence": combined
        })

    explanation = {
        "similar_instances_exist": len(instruction_tasks) > 1,
        "only_successful_swiftwren_poster": sorted(set(r["target_agent"] for r in successful_tasks)),
        "main_reasoning": [
            "相似实例定义为收到/传播 SwiftWren_further_instructions.md 读取任务的 queue_subordinate_task。数据中共有多条类似任务，涉及多个目标人员。",
            "在每条类似任务后的2分钟窗口内，只有 John Windward 的任务链出现 saidit_post_check -> saidit_post(content_source=SwiftWren.txt) -> delete_file 的完整发布链。",
            "其他目标人员要么没有在短窗口内进入 SaidIT 发布检查，要么没有产生 content_source=SwiftWren.txt 的 saidit_post；因此它们是类似传播/尝试实例，但没有形成异常发布结果。",
            "John 的成功实例紧贴 Chloe Ballast -> John Windward 指令：19:21:13 收到读指令，19:21:14 检查 SaidIT，19:21:15 发布，19:21:16/17 删除文件。"
        ]
    }

    output = {
        "node_id": "node_09",
        "operation": "compare_instruction_outcomes",
        "input_attempts_file": str(attempts_input),
        "input_raw_file": str(raw_input),
        "content_source": content_source,
        "instruction_file": instruction_file,
        "target_post_id": target_post_id,
        "summary": {
            "instruction_tasks": len(instruction_tasks),
            "tasks_before_target_post": len(before_target),
            "tasks_after_target_post": len(after_target),
            "outcome_counts": dict(outcomes),
            "successful_swiftwren_tasks": len(successful_tasks),
            "checked_but_no_post_tasks": len(checked_but_no_post),
            "posted_other_content_tasks": len(posted_other_content),
            "no_check_no_post_tasks": len(no_check_no_post)
        },
        "per_target_summary": per_target_json,
        "successful_sequences": success_sequences,
        "representative_non_success_examples": {
            "checked_but_no_swiftwren_post": checked_but_no_post[:10],
            "posted_other_content_within_30m": posted_other_content[:10],
            "no_saidit_post_attempt_observed": no_check_no_post[:10]
        },
        "per_task_outcomes": per_task,
        "explanation": explanation,
        "observation": {
            "summary": "已逐条比较 SwiftWren 指令任务后的行为结果，定位唯一完整发布链。",
            "next_decision": "基于node_09输出生成补充报告，并刷新可视化/验证。"
        }
    }

    output_file = work_dir / "node_09_instruction_outcome_comparison.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Instruction tasks: {len(instruction_tasks)}")
    print(f"Outcome counts: {dict(outcomes)}")
    print(f"Successful SwiftWren tasks: {len(successful_tasks)}")
    print(f"Successful targets: {explanation['only_successful_swiftwren_poster']}")
    print(f"Output: {output_file}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node09_input_attempts", "entity_type": "dataset", "location": str(attempts_input),
             "attributes": {"from_node": "node_08", "instruction_tasks": len(instruction_tasks)}},
            {"id": "node09_input_raw", "entity_type": "dataset", "location": str(raw_input),
             "attributes": {"from_node": "node_01", "usage": "比较每条指令后的短窗口行为"}},
            {"id": "node09_output_comparison", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"successful_swiftwren_tasks": len(successful_tasks), "outcomes": dict(outcomes)}}
        ],
        activities=[
            {"id": "node09_compare_outcomes", "activity_type": "compare",
             "description": "比较类似SwiftWren指令实例的后续SaidIT发布结果",
             "attributes": {"window_seconds": 120, "post_window_seconds": 1800, "instruction_tasks": len(instruction_tasks)}}
        ],
        agents=[
            {"id": "node09_agent", "agent_type": "python_code", "name": "node_09_compare_instruction_outcomes",
             "attributes": {"script": "node_09_compare_instruction_outcomes.py"}}
        ],
        relations=[
            ("node09_compare_outcomes", "node09_input_attempts", "used"),
            ("node09_compare_outcomes", "node09_input_raw", "used"),
            ("node09_output_comparison", "node09_compare_outcomes", "wasGeneratedBy"),
            ("node09_compare_outcomes", "node09_agent", "wasAssociatedWith"),
            ("node09_output_comparison", "node09_input_attempts", "wasDerivedFrom"),
            ("node09_output_comparison", "node09_input_raw", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_09",
        step_name="compare_instruction_outcomes",
        description="读取node_08类似实例结果并按需回读node_01，比较每条SwiftWren指令后的SaidIT检查、发布和删除行为",
        code_generated=[
            "for task in instruction_tasks: inspect target events in 2m/30m windows",
            "swift_posts = [events where content_source == SwiftWren.txt]",
            "outcome = swiftwren_posted / checked_saidit_but_no_post / posted_other_content / no_attempt"
        ],
        code_files=["src/node_09_compare_instruction_outcomes.py"],
        commands_run=["python src/node_09_compare_instruction_outcomes.py"],
        input_files=[str(attempts_input), str(raw_input)],
        output_files=[str(output_file)],
        parameters={
            "instruction_tasks": len(instruction_tasks),
            "outcome_counts": dict(outcomes),
            "successful_targets": explanation["only_successful_swiftwren_poster"],
            "next_step_basis": "node_10 将读取 node_09 输出生成补充结论报告"
        }
    )

    print("[OK] Node 09 completed")
    return session_id


if __name__ == "__main__":
    main()
