"""
MC2 Analysis - Node 03: Locate Target SaidIT Post
基于 node_02_saidit_events.json，在 SaidIT 子集中定位 2046-05-17 19:21:15 的异常帖子。
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def main():
    print("=" * 60)
    print("Node 03: Locate Target SaidIT Post")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    input_file = work_dir / "node_02_saidit_events.json"
    with open(input_file, "r", encoding="utf-8") as f:
        saidit_data = json.load(f)

    records = saidit_data.get("records", [])
    target_date = "2046-05-17"
    target_time = "19:21:15"

    # 最小处理节点：只在 node_02 的 SaidIT 子集内定位目标日期/时间的发布事件。
    candidate_posts = []
    target_matches = []
    john_matches = []
    for record in records:
        short_name = record.get("short_name")
        if short_name not in ["saidit_post", "post_saidit"]:
            continue
        candidate_posts.append(record)
        dt = record.get("datetime", "")
        parties_text = " ".join(record.get("parties", [])).lower()
        details = record.get("details", {})
        details_text = json.dumps(details, ensure_ascii=False).lower()
        if "john_windward" in parties_text or "john_windward" in details_text:
            john_matches.append(record)
        if target_date in dt and target_time in dt:
            target_matches.append(record)

    # 若精确秒匹配存在，异常帖子即为匹配结果；否则保留最接近目标的候选用于人工审阅。
    target_timestamp = datetime(2046, 5, 17, 19, 21, 15).timestamp()
    nearby_posts = sorted(
        candidate_posts,
        key=lambda r: abs(float(r.get("when", 0)) - target_timestamp)
    )[:10]

    output = {
        "node_id": "node_03",
        "input_file": str(input_file),
        "operation": "locate_target_saidit_post",
        "target": {"date": target_date, "time": target_time, "timestamp": target_timestamp},
        "input_saidit_records": len(records),
        "candidate_post_events": len(candidate_posts),
        "john_windward_post_events": len(john_matches),
        "target_matches_count": len(target_matches),
        "target_matches": target_matches,
        "nearby_posts": nearby_posts,
        "observation": {
            "summary": "在SaidIT子集中定位到目标时间的异常帖子。" if target_matches else "未精确定位到目标时间，已输出最近候选。",
            "next_decision": "读取异常帖子的content_source，并追溯该文件来源、任务传递链和删除行为。"
        }
    }

    output_file = work_dir / "node_03_target_post.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Input SaidIT records: {len(records):,}")
    print(f"Candidate post events: {len(candidate_posts):,}")
    print(f"Target matches: {len(target_matches)}")
    if target_matches:
        match = target_matches[0]
        print(f"Matched event: id={match.get('id')}, datetime={match.get('datetime')}, details={match.get('details')}")
    print(f"Output: {output_file}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node03_input_saidit", "entity_type": "dataset", "location": str(input_file),
             "attributes": {"events": len(records), "from_node": "node_02"}},
            {"id": "node03_output_target", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"target_matches": len(target_matches), "candidate_posts": len(candidate_posts), "from_node": "node_03"}}
        ],
        activities=[
            {"id": "node03_locate_target", "activity_type": "filter",
             "description": "在SaidIT中间数据集中定位目标时间的异常帖子",
             "attributes": {"target_datetime": f"{target_date} {target_time}", "input_records": len(records), "matches": len(target_matches)}}
        ],
        agents=[
            {"id": "node03_agent", "agent_type": "python_code", "name": "node_03_locate_target_post",
             "attributes": {"script": "node_03_locate_target_post.py"}}
        ],
        relations=[
            ("node03_locate_target", "node03_input_saidit", "used"),
            ("node03_output_target", "node03_locate_target", "wasGeneratedBy"),
            ("node03_locate_target", "node03_agent", "wasAssociatedWith"),
            ("node03_output_target", "node03_input_saidit", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_03",
        step_name="locate_target_saidit_post",
        description="读取node_02的SaidIT事件子集，筛选目标日期时间的异常帖子",
        code_generated=[
            "for record in records:",
            "    if record['short_name'] in ['saidit_post', 'post_saidit']:",
            "        if target_date in record['datetime'] and target_time in record['datetime']:",
            "            target_matches.append(record)"
        ],
        code_files=["src/node_03_locate_target_post.py"],
        commands_run=["python src/node_03_locate_target_post.py"],
        input_files=[str(input_file)],
        output_files=[str(output_file)],
        parameters={
            "input_saidit_records": len(records),
            "candidate_posts": len(candidate_posts),
            "john_windward_posts": len(john_matches),
            "target_matches": len(target_matches),
            "next_step_basis": "node_04 将读取 node_03_target_post.json 获取 content_source，再按需读取 node_01_loaded.json 追溯来源"
        }
    )

    print("[OK] Node 03 completed")
    return session_id


if __name__ == "__main__":
    main()
