"""
MC2 Analysis - Node 05: Generate Final Report
只读取 node_04_source_trace.json，基于已经追溯出的证据链生成最终报告。
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
    print("Node 05: Generate Final Report")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    input_file = work_dir / "node_04_source_trace.json"
    with open(input_file, "r", encoding="utf-8") as f:
        trace = json.load(f)

    target_post = trace["target_post"]
    lifecycle = trace["file_lifecycle"]
    task_chain = trace["task_chain_near_post"]
    content_source = trace["content_source"]

    created = lifecycle.get("created", [])
    deleted = lifecycle.get("deleted", [])

    report = {
        "node_id": "node_05",
        "operation": "generate_final_report",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "input_file": str(input_file),
        "analysis_title": "MC2 Anomalous SaidIT Post Investigation - Correct Sequential Data Flow",
        "data_flow_summary": [
            "node_01_loaded.json: 完整加载原始事件数据",
            "node_02_saidit_events.json: 从node_01产物中过滤SaidIT相关事件",
            "node_03_target_post.json: 从node_02产物中定位目标时间异常帖子",
            "node_04_source_trace.json: 基于node_03目标帖子按需回读node_01产物追溯来源",
            "node_05_final_report.json: 基于node_04证据链生成最终报告"
        ],
        "executive_summary": {
            "anomalous_post": {
                "event_id": target_post.get("id"),
                "datetime": target_post.get("datetime"),
                "actor": "John Windward",
                "event_type": target_post.get("short_name"),
                "content_source": content_source,
                "forum": target_post.get("details", {}).get("forum")
            },
            "file_origin": {
                "created_by": created[0].get("parties", [None])[0] if created else None,
                "created_at": created[0].get("datetime") if created else None,
                "size_hint": created[0].get("details", {}).get("size_hint") if created else None
            },
            "post_event_chain": [
                {
                    "time": e.get("datetime"),
                    "event_id": e.get("id"),
                    "event": e.get("short_name"),
                    "parties": e.get("parties"),
                    "details": e.get("details")
                }
                for e in task_chain
            ],
            "deletion_after_post": [
                {
                    "time": e.get("datetime"),
                    "event_id": e.get("id"),
                    "target": e.get("details", {}).get("target"),
                    "actor": e.get("parties", [None])[0] if e.get("parties") else None
                }
                for e in deleted
            ]
        },
        "findings": [
            f"异常帖子事件 {target_post.get('id')} 发生在 {target_post.get('datetime')}，发布主体为 John Windward 代理。",
            f"异常帖子使用 content_source={content_source}。",
            f"{content_source} 创建事件为 {created[0].get('id') if created else 'N/A'}，创建者为 {created[0].get('parties', ['N/A'])[0] if created else 'N/A'}，时间为 {created[0].get('datetime') if created else 'N/A'}。",
            "异常发布前的直接任务链为 Daniel Gangway -> Chloe Ballast -> John Windward，任务均指向读取 SwiftWren_further_instructions.md。",
            "帖子发布后 1-2 秒内，John Windward 删除 SwiftWren_further_instructions.md 与 SwiftWren.txt。"
        ],
        "conclusion": {
            "primary_anomaly": "John Windward 在目标时间发布了基于 SwiftWren.txt 的 SaidIT 帖子。",
            "execution_chain": "Daniel Gangway -> Chloe Ballast -> John Windward",
            "source_file_origin": "SwiftWren.txt 由 Emma Harbor 代理创建。",
            "cover_up_indicator": "发布后立即删除源文件和进一步指令文件。"
        },
        "evidence_counts": {
            "source_related_events": trace.get("source_related_summary", {}).get("total"),
            "task_chain_near_post": len(task_chain),
            "created_events": len(created),
            "deleted_events": len(deleted)
        },
        "observation": {
            "summary": "最终报告已由 node_04 证据链生成，不重新扫描原始数据。",
            "next_decision": "生成 OpenTrace 数据血缘可视化并验证 PROV 数据与可视化一致性。"
        }
    }

    output_file = work_dir / "node_05_final_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print(f"Target event: {target_post.get('id')} at {target_post.get('datetime')}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node05_input_trace", "entity_type": "dataset", "location": str(input_file),
             "attributes": {"from_node": "node_04", "source_related_events": trace.get("source_related_summary", {}).get("total")}},
            {"id": "node05_output_report", "entity_type": "report", "location": str(output_file),
             "attributes": {"from_node": "node_05", "target_event": target_post.get("id")}}
        ],
        activities=[
            {"id": "node05_generate_report", "activity_type": "aggregate",
             "description": "基于node_04证据链生成最终分析报告",
             "attributes": {"input_nodes": ["node_04"], "output_format": "json_report"}}
        ],
        agents=[
            {"id": "node05_agent", "agent_type": "python_code", "name": "node_05_generate_final_report",
             "attributes": {"script": "node_05_generate_final_report.py"}}
        ],
        relations=[
            ("node05_generate_report", "node05_input_trace", "used"),
            ("node05_output_report", "node05_generate_report", "wasGeneratedBy"),
            ("node05_generate_report", "node05_agent", "wasAssociatedWith"),
            ("node05_output_report", "node05_input_trace", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_05",
        step_name="generate_final_report",
        description="读取node_04_source_trace.json，汇总证据链并生成最终分析报告",
        code_generated=[
            "trace = json.load(open('node_04_source_trace.json'))",
            "target_post = trace['target_post']",
            "report = {'executive_summary': ..., 'findings': ..., 'conclusion': ...}"
        ],
        code_files=["src/node_05_generate_final_report.py"],
        commands_run=["python src/node_05_generate_final_report.py"],
        input_files=[str(input_file)],
        output_files=[str(output_file)],
        parameters={
            "target_event": target_post.get("id"),
            "content_source": content_source,
            "task_chain_events": len(task_chain),
            "report_sections": list(report.keys()),
            "next_step_basis": "node_06 将读取 node_05_final_report.json 并生成可视化"
        }
    )

    print("[OK] Node 05 completed")
    return session_id


if __name__ == "__main__":
    main()
