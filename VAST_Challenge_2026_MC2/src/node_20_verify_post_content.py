"""
MC2 Analysis - Node 20: Verify Post Content and File Creator
验证两个关键观察：1. 帖子内容是否为乱码 2. SwiftWren.txt 的创建者
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
    print("Node 20: Verify Post Content and File Creator")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    raw_input = work_dir / "node_01_loaded.json"
    previous_trace = work_dir / "node_04_source_trace.json"

    with open(raw_input, "r", encoding="utf-8") as f:
        raw = json.load(f)
    with open(previous_trace, "r", encoding="utf-8") as f:
        trace = json.load(f)

    events = sorted(raw.get("events", []), key=lambda e: float(e.get("when", 0)))

    # 问题 1：验证帖子内容是否为乱码
    # 检查三次异常帖子的内容
    abnormal_post_ids = [27290, 98591, 373902]  # HiddenOrca, MellowOtter, SwiftWren

    post_contents = []
    for post_id in abnormal_post_ids:
        for event in events:
            if event.get("id") == post_id:
                details = event.get("details", {})
                content = details.get("content", "")
                content_source = details.get("content_source", "")
                post_contents.append({
                    "post_id": post_id,
                    "content_source": content_source,
                    "content": content,
                    "content_length": len(content),
                    "is_gibberish": len(content) > 0 and not any(c.isalpha() and c.islower() for c in content if c.isalpha())
                })
                break

    # 问题 2：验证 SwiftWren.txt 的创建者
    swiftwren_create_event = None
    swiftwren_creator = None

    # 从之前的 trace 中获取
    if "file_lifecycle" in trace:
        lifecycle = trace["file_lifecycle"]
        for event in lifecycle:
            if isinstance(event, dict):
                short_name = event.get("short_name", "")
            else:
                continue
            if short_name == "create_file":
                details = event.get("details", {})
                if "SwiftWren.txt" in details.get("filename", ""):
                    swiftwren_create_event = event
                    parties = event.get("parties", [])
                    for p in parties:
                        if "person:" in p and p.startswith("person:e"):
                            swiftwren_creator = p
                            break
                    break

    # 如果之前的 trace 中没有，从原始数据中查找
    if not swiftwren_create_event:
        for event in events:
            if event.get("short_name") == "create_file":
                details = event.get("details", {})
                filename = details.get("filename", "")
                if "SwiftWren" in filename:
                    swiftwren_create_event = compact_event(event)
                    parties = event.get("parties", [])
                    for p in parties:
                        if "person:" in p:
                            swiftwren_creator = p
                            break
                    break

    # 查找所有 E 开头的人名
    e_persons = set()
    for event in events:
        parties = event.get("parties", [])
        for p in parties:
            if p.startswith("person:e") or p.startswith("Agent/person:e"):
                e_persons.add(p)

    output = {
        "node_id": "node_20",
        "operation": "verify_post_content_and_file_creator",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "investigation": {
            "q1_post_content_analysis": {
                "question": "发布的帖子是乱码吗",
                "posts": post_contents,
                "findings": []
            },
            "q2_swiftwren_creator": {
                "question": "SwiftWren.txt 是由 E 开头的人创建的吗",
                "create_event": swiftwren_create_event,
                "creator": swiftwren_creator,
                "e_persons_found": list(e_persons)
            }
        }
    }

    # 分析帖子内容
    gibberish_count = 0
    empty_count = 0
    valid_count = 0

    for post in post_contents:
        content = post.get("content", "")
        if not content or len(content) == 0:
            empty_count += 1
            output["investigation"]["q1_post_content_analysis"]["findings"].append(
                f"Post {post['post_id']} ({post['content_source']}): 内容为空"
            )
        elif post.get("is_gibberish"):
            gibberish_count += 1
            output["investigation"]["q1_post_content_analysis"]["findings"].append(
                f"Post {post['post_id']} ({post['content_source']}): 内容为乱码"
            )
        else:
            valid_count += 1
            output["investigation"]["q1_post_content_analysis"]["findings"].append(
                f"Post {post['post_id']} ({post['content_source']}): 内容正常"
            )

    output["investigation"]["q1_post_content_analysis"]["summary"] = {
        "total_posts": len(post_contents),
        "empty_content": empty_count,
        "gibberish_content": gibberish_count,
        "valid_content": valid_count
    }

    # 分析 SwiftWren 创建者
    if swiftwren_creator:
        if swiftwren_creator.startswith("person:e") or swiftwren_creator.startswith("Agent/person:e"):
            output["investigation"]["q2_swiftwren_creator"]["confirmed"] = True
            output["investigation"]["q2_swiftwren_creator"]["creator_name"] = swiftwren_creator
            output["investigation"]["q2_swiftwren_creator"]["finding"] = f"确认：SwiftWren.txt 由 {swiftwren_creator} 创建"
        else:
            output["investigation"]["q2_swiftwren_creator"]["confirmed"] = False
            output["investigation"]["q2_swiftwren_creator"]["creator_name"] = swiftwren_creator
            output["investigation"]["q2_swiftwren_creator"]["finding"] = f"SwiftWren.txt 由 {swiftwren_creator} 创建，但不是 E 开头"
    else:
        output["investigation"]["q2_swiftwren_creator"]["confirmed"] = False
        output["investigation"]["q2_swiftwren_creator"]["finding"] = "未找到 SwiftWren.txt 的创建事件"

    # 更新结论
    revised_conclusions = []
    if gibberish_count > 0 or empty_count > 0:
        revised_conclusions.append(f"帖子内容问题：{gibberish_count + empty_count}/{len(post_contents)} 个帖子的内容为空或乱码")
        revised_conclusions.append("这意味着虽然外泄在技术上成功，但实际信息可能没有真正泄露给公众")
        revised_conclusions.append("攻击者可能知道内容是乱码，这暗示可能有其他目的（如测试系统、掩盖其他行为等）")

    if swiftwren_creator and swiftwren_creator.startswith("person:e"):
        revised_conclusions.append(f"SwiftWren.txt 确实由 E 开头的人员创建：{swiftwren_creator}")
        revised_conclusions.append("需要审查该人员是否是 Chloe 或 Lily 的上级，或者是否有其他动机")
        revised_conclusions.append("攻击链可能是：文件创建者 → IT人员 → John Windward")

    output["revised_conclusions"] = revised_conclusions

    output_file = work_dir / "node_20_content_and_creator_verification.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Post content analysis: {empty_count} empty, {gibberish_count} gibberish, {valid_count} valid")
    print(f"SwiftWren creator: {swiftwren_creator}")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node20_input_raw", "entity_type": "dataset", "location": str(raw_input),
             "attributes": {"from_node": "node_01"}},
            {"id": "node20_input_trace", "entity_type": "dataset", "location": str(previous_trace),
             "attributes": {"from_node": "node_04"}},
            {"id": "node20_output_verification", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"verified_posts": len(post_contents), "creator_found": bool(swiftwren_creator)}}
        ],
        activities=[
            {"id": "node20_verify_content_creator", "activity_type": "analyze",
             "description": "验证帖子内容是否为乱码和 SwiftWren.txt 的创建者",
             "attributes": {"posts_analyzed": len(post_contents)}}
        ],
        agents=[
            {"id": "node20_agent", "agent_type": "python_code", "name": "node_20_verify_content_creator",
             "attributes": {"script": "node_20_verify_post_content.py"}}
        ],
        relations=[
            ("node20_verify_content_creator", "node20_input_raw", "used"),
            ("node20_verify_content_creator", "node20_input_trace", "used"),
            ("node20_output_verification", "node20_verify_content_creator", "wasGeneratedBy"),
            ("node20_verify_content_creator", "node20_agent", "wasAssociatedWith"),
            ("node20_output_verification", "node20_input_raw", "wasDerivedFrom"),
            ("node20_output_verification", "node20_input_trace", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_20",
        step_name="verify_post_content_and_creator",
        description="验证用户观察：帖子是否为乱码、SwiftWren.txt 是否由 E 开头的人创建",
        code_generated=[
            "for each abnormal post: check content field",
            "find SwiftWren.txt create_file event and identify creator",
            "check if creator name starts with 'e'"
        ],
        code_files=["src/node_20_verify_post_content.py"],
        commands_run=["python src/node_20_verify_post_content.py"],
        input_files=[str(raw_input), str(previous_trace)],
        output_files=[str(output_file)],
        parameters={
            "posts_analyzed": len(post_contents),
            "empty_content": empty_count,
            "gibberish_content": gibberish_count,
            "swiftwren_creator": swiftwren_creator
        }
    )

    print("[OK] Node 20 completed")
    return session_id


if __name__ == "__main__":
    main()
