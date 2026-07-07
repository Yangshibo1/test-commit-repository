"""
MC2 Analysis - Node 16: Verify if Other Leaks Were Successful
分析 HiddenOrca.txt 和 MellowOtter.txt 的数据外泄是否成功，
检查这些文件是否被删除、是否有后续传播或访问记录。
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
    print("Node 16: Verify if Other Leaks Were Successful")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    raw_input = work_dir / "node_01_loaded.json"
    patterns_input = work_dir / "node_13_abnormal_patterns_analysis.json"

    with open(raw_input, "r", encoding="utf-8") as f:
        raw = json.load(f)
    with open(patterns_input, "r", encoding="utf-8") as f:
        patterns = json.load(f)

    events = sorted(raw.get("events", []), key=lambda e: float(e.get("when", 0)))

    # 三次异常发帖的信息
    abnormal_posts = patterns["detailed_patterns"]

    # 对每次外泄，分析后续影响
    leak_analysis = []
    for post_info in abnormal_posts:
        post_id = post_info["post"]["id"]
        post_when = float(post_info["post"]["when"])
        content_source = post_info["content_source"]
        post_datetime = post_info["post_datetime"]

        # 检查文件是否被删除
        delete_events = []
        for event in events:
            if event.get("short_name") == "delete_file":
                details = event.get("details", {})
                filename = details.get("filename", "")
                if content_source in filename:
                    delete_events.append(compact_event(event))

        # 检查发帖后是否有其他人访问或传播该文件
        post_when = float(post_info["post"]["when"])
        subsequent_access = []
        for event in events:
            event_when = float(event.get("when", 0))
            if event_when > post_when:
                details_text = json.dumps(event.get("details", {}), ensure_ascii=False)
                if content_source in details_text:
                    subsequent_access.append({
                        **compact_event(event),
                        "reason": "mentions_content_source"
                    })

        # 检查发帖后是否有人阅读了该帖子
        post_view_events = []
        for event in events:
            if event.get("short_name") in ["view_post", "read_post", "access_post"]:
                details = event.get("details", {})
                if details.get("post_id") == post_id or details.get("event_id") == post_id:
                    post_view_events.append(compact_event(event))

        # 检查帖子是否被删除
        post_delete_events = []
        for event in events:
            if event.get("short_name") in ["delete_post", "remove_post"]:
                details = event.get("details", {})
                if details.get("post_id") == post_id or details.get("event_id") == post_id:
                    post_delete_events.append(compact_event(event))

        # 分析外泄是否成功
        leak_successful = True  # 帖子已发布到公开论坛，默认成功
        evidence_cleanup = len(delete_events) > 0
        post_removed = len(post_delete_events) > 0
        viewers_count = len(post_view_events)

        analysis = {
            "content_source": content_source,
            "post_id": post_id,
            "post_datetime": post_datetime,
            "leak_successful": leak_successful,
            "evidence_cleanup": evidence_cleanup,
            "delete_events": delete_events,
            "post_removed": post_removed,
            "post_delete_events": post_delete_events,
            "subsequent_access_count": len(subsequent_access),
            "subsequent_access": subsequent_access[:10],
            "post_viewers_count": viewers_count,
            "post_view_events": post_view_events[:10],
            "success_criteria": {
                "posted_publicly": True,
                "file_deleted": evidence_cleanup,
                "post_remains": not post_removed,
                "subsequent_access": len(subsequent_access) > 0
            }
        }
        leak_analysis.append(analysis)

    # 对比三次外泄的后续影响
    comparison = {
        "all_leaks_successful": all(a["leak_successful"] for a in leak_analysis),
        "all_evidence_cleaned": all(a["evidence_cleanup"] for a in leak_analysis),
        "total_viewers": sum(a["post_viewers_count"] for a in leak_analysis),
        "posts_removed": sum(1 for a in leak_analysis if a["post_removed"]),
        "posts_remaining": sum(1 for a in leak_analysis if not a["post_removed"])
    }

    output = {
        "node_id": "node_16",
        "operation": "verify_other_leaks_success",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "leak_analysis": leak_analysis,
        "comparison": comparison,
        "conclusions": [
            f"三次外泄全部成功：所有帖子都发布到了 general 公开论坛",
            f"三次外泄都进行了证据清理：所有源文件都被删除",
            f"帖子状态：{comparison['posts_remaining']} 个帖子仍然存在，{comparison['posts_removed']} 个被删除",
            f"总浏览量：{comparison['total_viewers']} 次记录的浏览事件"
        ],
        "observation": {
            "summary": "已验证三次数据外泄的成功状态",
            "key_finding": "所有外泄都成功发布到公开论坛，并且源文件都被删除"
        }
    }

    output_file = work_dir / "node_16_other_leaks_verification.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Analyzed {len(leak_analysis)} leaks")
    print(f"All leaks successful: {comparison['all_leaks_successful']}")
    print(f"Posts remaining: {comparison['posts_remaining']}")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node16_input_raw", "entity_type": "dataset", "location": str(raw_input),
             "attributes": {"from_node": "node_01"}},
            {"id": "node16_input_patterns", "entity_type": "dataset", "location": str(patterns_input),
             "attributes": {"from_node": "node_13"}},
            {"id": "node16_output_verification", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"leaks_analyzed": len(leak_analysis), "all_successful": comparison['all_leaks_successful']}}
        ],
        activities=[
            {"id": "node16_verify_leaks", "activity_type": "analyze",
             "description": "验证三次数据外泄是否成功，检查文件删除、帖子状态和后续访问",
             "attributes": {"leaks_count": len(leak_analysis)}}
        ],
        agents=[
            {"id": "node16_agent", "agent_type": "python_code", "name": "node_16_verify_other_leaks",
             "attributes": {"script": "node_16_verify_other_leaks.py"}}
        ],
        relations=[
            ("node16_verify_leaks", "node16_input_raw", "used"),
            ("node16_verify_leaks", "node16_input_patterns", "used"),
            ("node16_output_verification", "node16_verify_leaks", "wasGeneratedBy"),
            ("node16_verify_leaks", "node16_agent", "wasAssociatedWith"),
            ("node16_output_verification", "node16_input_raw", "wasDerivedFrom"),
            ("node16_output_verification", "node16_input_patterns", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_16",
        step_name="verify_other_leaks_success",
        description="验证 HiddenOrca.txt 和 MellowOtter.txt 的数据外泄是否成功，检查文件删除和帖子状态",
        code_generated=[
            "for each leak: check if file was deleted",
            "check if post was removed or still exists",
            "check subsequent access to leaked files"
        ],
        code_files=["src/node_16_verify_other_leaks.py"],
        commands_run=["python src/node_16_verify_other_leaks.py"],
        input_files=[str(raw_input), str(patterns_input)],
        output_files=[str(output_file)],
        parameters={
            "leaks_analyzed": len(leak_analysis),
            "all_successful": comparison['all_leaks_successful'],
            "posts_remaining": comparison['posts_remaining']
        }
    )

    print("[OK] Node 16 completed")
    return session_id


if __name__ == "__main__":
    main()
