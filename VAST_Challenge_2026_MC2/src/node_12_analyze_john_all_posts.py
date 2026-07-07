"""
MC2 Analysis - Node 12: Analyze John Windward's All Posting Behavior
读取 node_01_loaded.json 和 org_chart.json，分析 John Windward 的所有发帖行为，
并找出所有使用 content_source 的异常发帖人，进行身份和行为模式对比。
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

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


def main():
    print("=" * 60)
    print("Node 12: Analyze John Windward's All Posting Behavior")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 读取输入文件
    raw_input = work_dir / "node_01_loaded.json"
    org_chart_input = Path(__file__).parent.parent / "org_chart.json"

    with open(raw_input, "r", encoding="utf-8") as f:
        raw = json.load(f)
    with open(org_chart_input, "r", encoding="utf-8") as f:
        org_chart = json.load(f)

    events = sorted(raw.get("events", []), key=lambda e: float(e.get("when", 0)))

    # 解析组织结构
    org_nodes = {node["id"]: node for node in org_chart.get("nodes", [])}
    org_edges = org_chart.get("edges", [])

    # 找出 John Windward 的信息
    john_key = "person:john_windward"
    john_info = org_nodes.get(john_key, {})
    john_title = john_info.get("title", "Unknown")
    john_dept = None
    john_team = None

    for edge in org_edges:
        if edge.get("target") == john_key:
            if edge.get("relation") == "led_by":
                # John 是 department lead
                john_dept = edge.get("source")
            elif edge.get("relation") == "contains":
                # John 在某个 team 中
                john_team = edge.get("source")

    # 找出 John 的下属团队
    john_teams = []
    if john_dept:
        for edge in org_edges:
            if edge.get("source") == john_dept and edge.get("relation") == "contains":
                john_teams.append(edge.get("target"))

    # 找出 John 的直接下属
    john_subordinates = []
    for team in john_teams:
        for edge in org_edges:
            if edge.get("source") == team and edge.get("relation") == "contains":
                subordinate_id = edge.get("target")
                if subordinate_id.startswith("person:"):
                    subordinate_info = org_nodes.get(subordinate_id, {})
                    john_subordinates.append({
                        "id": subordinate_id,
                        "name": subordinate_info.get("label", "Unknown"),
                        "team": org_nodes.get(team, {}).get("label", "Unknown")
                    })

    # 分析 John 的所有 SaidIT 相关行为
    john_events = []
    for event in events:
        parties = event.get("parties", [])
        if john_key in parties or john_key.replace("person:", "Agent/person:") in parties:
            short_name = event.get("short_name", "").lower()
            if "saidit" in short_name or short_name in ["ask_agent", "give_advice"]:
                john_events.append(compact_event(event))

    # John 的所有 SaidIT 帖子
    john_posts = [e for e in john_events if e["short_name"] in ["saidit_post", "post_saidit"]]

    # John 的异常帖子（有 content_source）
    john_abnormal_posts = []
    for post in john_posts:
        details = post.get("details", {})
        content_source = details.get("content_source")
        if content_source:
            john_abnormal_posts.append({
                **post,
                "content_source": content_source,
                "forum": details.get("forum"),
                "is_abnormal": bool(content_source)
            })

    # 找出所有使用 content_source 的异常帖子
    all_abnormal_posts = []
    for event in events:
        if event.get("short_name") in ["saidit_post", "post_saidit"]:
            details = event.get("details", {})
            content_source = details.get("content_source")
            if content_source:
                parties = event.get("parties", [])
                poster = None
                for p in parties:
                    if "person:" in p:
                        poster = p
                        break
                if poster:
                    poster_info = org_nodes.get(poster, {})
                    all_abnormal_posts.append({
                        "event_id": event.get("id"),
                        "poster": poster,
                        "poster_name": poster_info.get("label", "Unknown"),
                        "poster_title": poster_info.get("title", "Unknown"),
                        "when": float(event.get("when", 0)),
                        "datetime": str(datetime.fromtimestamp(float(event.get("when", 0)))),
                        "content_source": content_source,
                        "forum": details.get("forum")
                    })

    # 按发帖人汇总异常行为
    poster_summary = defaultdict(lambda: {
        "abnormal_post_count": 0,
        "posts": [],
        "title": None,
        "department": None
    })
    for post in all_abnormal_posts:
        poster = post["poster"]
        poster_summary[poster]["abnormal_post_count"] += 1
        poster_summary[poster]["posts"].append(post)
        poster_summary[poster]["title"] = post["poster_title"]

        # 找出部门
        for edge in org_edges:
            if edge.get("target") == poster and edge.get("relation") == "contains":
                dept_or_team = edge.get("source")
                if dept_or_team.startswith("department:"):
                    poster_summary[poster]["department"] = org_nodes.get(dept_or_team, {}).get("label", "Unknown")
                    break
                elif dept_or_team.startswith("team:"):
                    # 找到 team 所属的 department
                    for edge2 in org_edges:
                        if edge2.get("target") == dept_or_team and edge2.get("relation") == "contains":
                            dept = edge2.get("source")
                            poster_summary[poster]["department"] = org_nodes.get(dept, {}).get("label", "Unknown")
                            break

    # 找出所有发帖人（包括正常帖子）
    all_posters = defaultdict(lambda: {"post_count": 0, "abnormal_count": 0})
    for event in events:
        if event.get("short_name") in ["saidit_post", "post_saidit"]:
            parties = event.get("parties", [])
            poster = None
            for p in parties:
                if "person:" in p:
                    poster = p
                    break
            if poster:
                all_posters[poster]["post_count"] += 1
                details = event.get("details", {})
                if details.get("content_source"):
                    all_posters[poster]["abnormal_count"] += 1

    # 对比分析：John vs 其他异常发帖人
    comparison = {
        "john_windward": {
            "identity": {
                "id": john_key,
                "name": john_info.get("label"),
                "title": john_title,
                "department": john_dept,
                "teams_led": john_teams,
                "direct_subordinates": john_subordinates
            },
            "saidit_activity": {
                "total_saidit_events": len(john_events),
                "total_posts": len(john_posts),
                "abnormal_posts": len(john_abnormal_posts),
                "abnormal_post_details": john_abnormal_posts
            }
        },
        "all_abnormal_posters": dict(poster_summary),
        "all_posters_summary": dict(all_posters)
    }

    # 关键发现
    findings = []
    findings.append(f"John Windward 是 Customer Support 部门的 Department Lead，直接下属 {len(john_subordinates)} 人")
    findings.append(f"John 共有 {len(john_posts)} 条 SaidIT 帖子，其中 {len(john_abnormal_posts)} 条使用了 content_source（异常帖子）")
    findings.append(f"系统中使用 content_source 的异常帖子共 {len(all_abnormal_posts)} 条，涉及 {len(poster_summary)} 个不同发帖人")

    # 找出其他异常发帖人
    other_abnormal_posters = []
    for poster_id, summary in poster_summary.items():
        if poster_id != john_key:
            other_abnormal_posters.append({
                "id": poster_id,
                "name": org_nodes.get(poster_id, {}).get("label", "Unknown"),
                "title": summary["title"],
                "department": summary["department"],
                "abnormal_post_count": summary["abnormal_post_count"]
            })
    findings.append(f"其他异常发帖人：{len(other_abnormal_posters)} 人")

    output = {
        "node_id": "node_12",
        "operation": "analyze_john_all_posts_and_compare",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "input_files": [str(raw_input), str(org_chart_input)],
        "john_windward_identity": {
            "id": john_key,
            "name": john_info.get("label"),
            "title": john_title,
            "department": org_nodes.get(john_dept, {}).get("label") if john_dept else None,
            "teams_led": [org_nodes.get(t, {}).get("label") for t in john_teams],
            "direct_subordinates": john_subordinates
        },
        "john_saidit_activity": {
            "total_saidit_events": len(john_events),
            "total_posts": len(john_posts),
            "abnormal_posts": len(john_abnormal_posts),
            "abnormal_post_details": john_abnormal_posts
        },
        "all_abnormal_posts_summary": {
            "total_abnormal_posts": len(all_abnormal_posts),
            "unique_posters": len(poster_summary),
            "posters": dict(poster_summary)
        },
        "all_posters_summary": {
            "total_unique_posters": len(all_posters),
            "top_posters": sorted(
                [(pid, data) for pid, data in all_posters.items()],
                key=lambda x: x[1]["post_count"],
                reverse=True
            )[:10]
        },
        "other_abnormal_posters": other_abnormal_posters,
        "comparison_findings": findings,
        "observation": {
            "summary": "已完成 John Windward 全部发帖行为分析，并与组织结构和其他异常发帖人对比",
            "next_decision": "基于发现决定是否需要进一步分析 John 与其他异常发帖人的关系模式"
        }
    }

    output_file = work_dir / "node_12_john_all_posts_analysis.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"John Windward: {john_info.get('label')} ({john_title})")
    print(f"John's SaidIT posts: {len(john_posts)} (abnormal: {len(john_abnormal_posts)})")
    print(f"Total abnormal posters in system: {len(poster_summary)}")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node12_input_raw", "entity_type": "dataset", "location": str(raw_input),
             "attributes": {"from_node": "node_01", "usage": "分析所有 SaidIT 行为"}},
            {"id": "node12_input_org_chart", "entity_type": "dataset", "location": str(org_chart_input),
             "attributes": {"usage": "获取人员身份和组织结构"}},
            {"id": "node12_output_analysis", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"john_posts": len(john_posts), "abnormal_posters": len(poster_summary)}}
        ],
        activities=[
            {"id": "node12_analyze_john_posts", "activity_type": "compare",
             "description": "分析 John Windward 的所有发帖行为并与组织结构和其他异常发帖人对比",
             "attributes": {"john_post_count": len(john_posts), "abnormal_posters_count": len(poster_summary)}}
        ],
        agents=[
            {"id": "node12_agent", "agent_type": "python_code", "name": "node_12_analyze_john_all_posts",
             "attributes": {"script": "node_12_analyze_john_all_posts.py"}}
        ],
        relations=[
            ("node12_analyze_john_posts", "node12_input_raw", "used"),
            ("node12_analyze_john_posts", "node12_input_org_chart", "used"),
            ("node12_output_analysis", "node12_analyze_john_posts", "wasGeneratedBy"),
            ("node12_analyze_john_posts", "node12_agent", "wasAssociatedWith"),
            ("node12_output_analysis", "node12_input_raw", "wasDerivedFrom"),
            ("node12_output_analysis", "node12_input_org_chart", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_12",
        step_name="analyze_john_all_posts",
        description="分析 John Windward 的所有 SaidIT 发帖行为，结合组织结构对比其他异常发帖人",
        code_generated=[
            "john_events = [events where John involved in SaidIT]",
            "john_abnormal_posts = [posts with content_source]",
            "all_abnormal_posts = [all posts with content_source]",
            "poster_summary = aggregate by poster with org chart info"
        ],
        code_files=["src/node_12_analyze_john_all_posts.py"],
        commands_run=["python src/node_12_analyze_john_all_posts.py"],
        input_files=[str(raw_input), str(org_chart_input)],
        output_files=[str(output_file)],
        parameters={
            "john_post_count": len(john_posts),
            "john_abnormal_count": len(john_abnormal_posts),
            "total_abnormal_posters": len(poster_summary),
            "next_step_basis": "基于发现决定后续分析"
        }
    )

    print("[OK] Node 12 completed")
    return session_id


if __name__ == "__main__":
    main()
