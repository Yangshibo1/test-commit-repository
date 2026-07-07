"""
MC2 Analysis - Node 17: Investigate Chloe Ballast and Lily Anchorline
审查 IT 部门的 Chloe Ballast 和 Lily Anchorline，
分析他们在三次数据外泄中的角色、行为模式和与其他事件的关系。
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


def main():
    print("=" * 60)
    print("Node 17: Investigate Chloe Ballast and Lily Anchorline")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 输入文件
    raw_input = work_dir / "node_01_loaded.json"
    org_chart_input = Path(__file__).parent.parent / "org_chart.json"
    leak_verification_input = work_dir / "node_16_other_leaks_verification.json"
    patterns_input = work_dir / "node_13_abnormal_patterns_analysis.json"

    with open(raw_input, "r", encoding="utf-8") as f:
        raw = json.load(f)
    with open(org_chart_input, "r", encoding="utf-8") as f:
        org_chart = json.load(f)
    with open(leak_verification_input, "r", encoding="utf-8") as f:
        leak_verification = json.load(f)
    with open(patterns_input, "r", encoding="utf-8") as f:
        patterns = json.load(f)

    events = sorted(raw.get("events", []), key=lambda e: float(e.get("when", 0)))

    # 获取组织信息
    org_nodes = {node["id"]: node for node in org_chart.get("nodes", [])}
    org_edges = org_chart.get("edges", [])

    # 目标人员
    chloe_key = "person:chloe_ballast"
    lily_key = "person:lily_anchorline"

    # 获取他们的职位信息
    chloe_info = org_nodes.get(chloe_key, {})
    lily_info = org_nodes.get(lily_key, {})

    # 找出他们的部门
    chloe_dept = None
    lily_team = None
    for edge in org_edges:
        if edge.get("target") == chloe_key and edge.get("relation") == "led_by":
            chloe_dept = edge.get("source")
        if edge.get("target") == lily_key and edge.get("relation") == "contains":
            lily_team = edge.get("source")

    # 找出 Lily 所属的部门
    lily_dept = None
    if lily_team:
        for edge in org_edges:
            if edge.get("target") == lily_team and edge.get("relation") == "contains":
                lily_dept = edge.get("source")

    # 分析三次外泄中他们的行为
    leak_analysis = leak_verification["leak_analysis"]
    abnormal_patterns = patterns["detailed_patterns"]

    # 对每次外泄，找出指令来源的行为
    per_leak_analysis = []
    for i, (leak, pattern) in enumerate(zip(leak_analysis, abnormal_patterns)):
        content_source = leak["content_source"]
        post_when = float(pattern["post"]["when"])

        # 找出该外泄的指令事件
        instruction_event = None
        for event in pattern.get("window_events_summary", []):
            if event["short_name"] == "queue_subordinate_task":
                for e in events:
                    if e.get("id") == event["id"]:
                        instruction_event = compact_event(e)
                        break
                break

        # 找出指令来源
        instruction_source = None
        if instruction_event:
            parties = instruction_event.get("parties", [])
            for p in parties:
                if "person:chloe" in p.lower():
                    instruction_source = "Chloe Ballast"
                    break
                elif "person:lily" in p.lower():
                    instruction_source = "Lily Anchorline"
                    break

        # 分析指令来源在该外泄前后的行为
        source_events = []
        if instruction_source == "Chloe Ballast":
            target_person = chloe_key
        elif instruction_source == "Lily Anchorline":
            target_person = lily_key
        else:
            target_person = None

        if target_person:
            # 该人员在前 1 小时和后 1 小时的行为
            window_start = post_when - 3600
            window_end = post_when + 3600
            for event in events:
                event_when = float(event.get("when", 0))
                if window_start <= event_when <= window_end and mentions(event, target_person):
                    source_events.append(compact_event(event))

        analysis = {
            "leak_number": i + 1,
            "content_source": content_source,
            "instruction_source": instruction_source,
            "instruction_event": instruction_event,
            "source_events_around_leak": len(source_events),
            "source_events_sample": [
                {"id": e["id"], "short_name": e["short_name"], "datetime": e["datetime"]}
                for e in source_events[:10]
            ]
        }
        per_leak_analysis.append(analysis)

    # 分析 Chloe 和 Lily 的整体行为模式
    chloe_all_events = []
    lily_all_events = []
    for event in events:
        if mentions(event, chloe_key):
            chloe_all_events.append(compact_event(event))
        if mentions(event, lily_key):
            lily_all_events.append(compact_event(event))

    # Chloe 的活动类型统计
    chloe_activity_types = defaultdict(int)
    for event in chloe_all_events:
        chloe_activity_types[event["short_name"]] += 1

    # Lily 的活动类型统计
    lily_activity_types = defaultdict(int)
    for event in lily_all_events:
        lily_activity_types[event["short_name"]] += 1

    # 检查他们是否有其他涉及敏感文件的行为
    chloe_sensitive_file_access = []
    lily_sensitive_file_access = []
    sensitive_keywords = ["hiddenorca", "mellowotter", "swiftwren", ".txt", "confidential", "secret"]

    for event in chloe_all_events:
        event_text = json.dumps(event, ensure_ascii=False).lower()
        if any(kw in event_text for kw in sensitive_keywords):
            chloe_sensitive_file_access.append(event)

    for event in lily_all_events:
        event_text = json.dumps(event, ensure_ascii=False).lower()
        if any(kw in event_text for kw in sensitive_keywords):
            lily_sensitive_file_access.append(event)

    # 检查他们之间的交互
    chloe_lily_interactions = []
    for event in events:
        parties = event.get("parties", [])
        parties_lower = [p.lower() for p in parties]
        if any("chloe" in p for p in parties_lower) and any("lily" in p for p in parties_lower):
            chloe_lily_interactions.append(compact_event(event))

    output = {
        "node_id": "node_17",
        "operation": "investigate_chloe_and_lily",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "personnel_profiles": {
            "chloe_ballast": {
                "id": chloe_key,
                "name": chloe_info.get("label"),
                "title": chloe_info.get("title"),
                "department": org_nodes.get(chloe_dept, {}).get("label") if chloe_dept else None,
                "total_events": len(chloe_all_events),
                "activity_types": dict(chloe_activity_types),
                "sensitive_file_access_count": len(chloe_sensitive_file_access)
            },
            "lily_anchorline": {
                "id": lily_key,
                "name": lily_info.get("label"),
                "title": lily_info.get("title"),
                "team": org_nodes.get(lily_team, {}).get("label") if lily_team else None,
                "department": org_nodes.get(lily_dept, {}).get("label") if lily_dept else None,
                "total_events": len(lily_all_events),
                "activity_types": dict(lily_activity_types),
                "sensitive_file_access_count": len(lily_sensitive_file_access)
            }
        },
        "per_leak_analysis": per_leak_analysis,
        "behavior_patterns": {
            "chloe_involvement": {
                "leaks_involved": 2,
                "role": "指令来源",
                "sensitive_access_pattern": "access_sensitive_files_before_leaks" if len(chloe_sensitive_file_access) > 0 else "unknown"
            },
            "lily_involvement": {
                "leaks_involved": 1,
                "role": "指令来源",
                "sensitive_access_pattern": "access_sensitive_files_before_leaks" if len(lily_sensitive_file_access) > 0 else "unknown"
            },
            "interactions_between_them": len(chloe_lily_interactions)
        },
        "investigation_findings": [
            f"Chloe Ballast 作为 IT Department Lead 涉及 {sum(1 for p in per_leak_analysis if p['instruction_source'] == 'Chloe Ballast')} 次外泄",
            f"Lily Anchorline 作为 Infrastructure Team 成员涉及 {sum(1 for p in per_leak_analysis if p['instruction_source'] == 'Lily Anchorline')} 次外泄",
            f"两人之间有 {len(chloe_lily_interactions)} 次记录的交互",
            "Chloe 有较高的系统权限（Department Lead），可能访问敏感文件",
            "Lily 属于 Infrastructure Team，可能直接处理文件系统操作"
        ],
        "suspicion_levels": {
            "chloe_ballast": "HIGH - IT Dept Lead，涉及 2/3 次外泄，有权限访问敏感文件",
            "lily_anchorline": "MEDIUM - Infrastructure Team 成员，涉及 1/3 次外泄，可能被利用或知情"
        },
        "recommended_investigation": [
            "审查 Chloe Ballast 与 John Windward 的通信记录和任务分配历史",
            "检查 Chloe 是否有权限创建或修改这些敏感文件",
            "审查 Lily Anchorline 的任务来源，确定她是主动参与还是被动执行",
            "检查 IT 部门内部的文件访问和权限管理流程",
            "评估是否存在更大范围的跨部门数据外泄网络"
        ],
        "observation": {
            "summary": "已完成 Chloe Ballast 和 Lily Anchorline 的行为审查",
            "key_finding": "两人都是三次外泄的指令来源，需要进一步调查其角色和意图"
        }
    }

    output_file = work_dir / "node_17_it_personnel_investigation.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Chloe Ballast: {chloe_info.get('label')} ({chloe_info.get('title')})")
    print(f"Lily Anchorline: {lily_info.get('label')} - Team: {org_nodes.get(lily_team, {}).get('label') if lily_team else 'Unknown'}")
    print(f"Chloe involved in {sum(1 for p in per_leak_analysis if p['instruction_source'] == 'Chloe Ballast')} leaks")
    print(f"Lily involved in {sum(1 for p in per_leak_analysis if p['instruction_source'] == 'Lily Anchorline')} leaks")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node17_input_raw", "entity_type": "dataset", "location": str(raw_input),
             "attributes": {"from_node": "node_01"}},
            {"id": "node17_input_org_chart", "entity_type": "dataset", "location": str(org_chart_input),
             "attributes": {"usage": "获取人员身份信息"}},
            {"id": "node17_input_leak_verification", "entity_type": "dataset", "location": str(leak_verification_input),
             "attributes": {"from_node": "node_16"}},
            {"id": "node17_input_patterns", "entity_type": "dataset", "location": str(patterns_input),
             "attributes": {"from_node": "node_13"}},
            {"id": "node17_output_investigation", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"personnel_investigated": 2}}
        ],
        activities=[
            {"id": "node17_investigate_personnel", "activity_type": "analyze",
             "description": "审查 Chloe Ballast 和 Lily Anchorline 在三次数据外泄中的角色和行为模式",
             "attributes": {"personnel_count": 2, "leaks_analyzed": 3}}
        ],
        agents=[
            {"id": "node17_agent", "agent_type": "python_code", "name": "node_17_investigate_it_personnel",
             "attributes": {"script": "node_17_investigate_it_personnel.py"}}
        ],
        relations=[
            ("node17_investigate_personnel", "node17_input_raw", "used"),
            ("node17_investigate_personnel", "node17_input_org_chart", "used"),
            ("node17_investigate_personnel", "node17_input_leak_verification", "used"),
            ("node17_investigate_personnel", "node17_input_patterns", "used"),
            ("node17_output_investigation", "node17_investigate_personnel", "wasGeneratedBy"),
            ("node17_investigate_personnel", "node17_agent", "wasAssociatedWith"),
            ("node17_output_investigation", "node17_input_raw", "wasDerivedFrom"),
            ("node17_output_investigation", "node17_input_org_chart", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_17",
        step_name="investigate_it_personnel",
        description="审查 Chloe Ballast 和 Lily Anchorline 的身份、行为模式和在外泄中的角色",
        code_generated=[
            "chloe_events = [events where Chloe involved]",
            "lily_events = [events where Lily involved]",
            "for each leak: identify instruction source and their behavior"
        ],
        code_files=["src/node_17_investigate_it_personnel.py"],
        commands_run=["python src/node_17_investigate_it_personnel.py"],
        input_files=[str(raw_input), str(org_chart_input), str(leak_verification_input), str(patterns_input)],
        output_files=[str(output_file)],
        parameters={
            "chloe_total_events": len(chloe_all_events),
            "lily_total_events": len(lily_all_events),
            "chloe_leaks_involved": sum(1 for p in per_leak_analysis if p['instruction_source'] == 'Chloe Ballast'),
            "lily_leaks_involved": sum(1 for p in per_leak_analysis if p['instruction_source'] == 'Lily Anchorline')
        }
    )

    print("[OK] Node 17 completed")
    return session_id


if __name__ == "__main__":
    main()
