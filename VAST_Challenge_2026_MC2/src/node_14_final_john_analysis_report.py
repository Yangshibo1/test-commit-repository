"""
MC2 Analysis - Node 14: Final John Windward Analysis Report
汇总 John Windward 三次异常发帖的完整分析报告。
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
    print("Node 14: Final John Windward Analysis Report")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 读取分析结果
    john_analysis_input = work_dir / "node_12_john_all_posts_analysis.json"
    patterns_input = work_dir / "node_13_abnormal_patterns_analysis.json"

    with open(john_analysis_input, "r", encoding="utf-8") as f:
        john_analysis = json.load(f)
    with open(patterns_input, "r", encoding="utf-8") as f:
        patterns = json.load(f)

    john_identity = john_analysis["john_windward_identity"]
    john_activity = john_analysis["john_saidit_activity"]
    abnormal_patterns = patterns["detailed_patterns"]

    # 提取关键发现
    key_findings = {
        "john_windward_unique_status": {
            "identity": "Customer Support Department Lead",
            "subordinates_count": len(john_identity["direct_subordinates"]),
            "teams_led": john_identity["teams_led"],
            "is_only_abnormal_poster": True
        },
        "three_abnormal_posts": {
            "total_abnormal_posts": 3,
            "posts": [
                {
                    "date": "2046-05-10",
                    "time": "20:45:42",
                    "content_source": "HiddenOrca.txt",
                    "instruction_source": "Chloe Ballast (IT Department Lead)"
                },
                {
                    "date": "2046-05-11",
                    "time": "08:56:04",
                    "content_source": "MellowOtter.txt",
                    "instruction_source": "Lily Anchorline (Infrastructure Team)"
                },
                {
                    "date": "2046-05-17",
                    "time": "19:21:15",
                    "content_source": "SwiftWren.txt",
                    "instruction_source": "Chloe Ballast (IT Department Lead)"
                }
            ]
        },
        "attack_pattern": {
            "description": "三次异常发帖遵循相同的 5 步骤模式，每次在 2-4 秒内完成",
            "steps": [
                "1. queue_subordinate_task: 接收文件读取指令",
                "2. saidit_post_check: 检查 SaidIT 发布权限",
                "3. saidit_post: 发布内容，使用 content_source=敏感文件",
                "4. delete_file: 删除指令文件",
                "5. delete_file: 删除源文件"
            ],
            "characteristics": [
                "所有帖子发布在 general 公开论坛",
                "每次发帖后立即删除相关文件（证据销毁）",
                "整个链路在 2-4 秒内完成（高度自动化或预先准备）",
                "John 是系统中唯一执行此模式的发帖人"
            ]
        },
        "comparison_with_other_posters": {
            "total_posters": john_analysis["all_posters_summary"]["total_unique_posters"],
            "other_posters_count": john_analysis["all_posters_summary"]["total_unique_posters"] - 1,
            "other_posters_abnormal_count": 0,
            "conclusion": "其他 9 个 SaidIT 发帖人从未发布过异常帖子（使用 content_source）"
        },
        "organizational_context": {
            "john_position": "Customer Support Department Lead",
            "instruction_sources": [
                "Chloe Ballast (Information Technologies Department Lead) - 2 次",
                "Lily Anchorline (Infrastructure Team, IT 部门) - 1 次"
            ],
            "cross_department_pattern": "指令来源均来自 IT 部门，John 来自 Customer Support 部门",
            "potential_compromise": "跨部门协作被滥用于数据外泄"
        }
    }

    report = {
        "node_id": "node_14",
        "operation": "final_john_windward_analysis_report",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "report_title": "John Windward 异常发帖行为完整分析报告",
        "questions_answered": [
            "John Windward 是否还有类似的发帖行为？是，共 3 次。",
            "John Windward 的身份是什么？Customer Support Department Lead。",
            "与其他发帖人的异同？John 是唯一异常发帖人，其他 9 人无异常行为。"
        ],
        "key_findings": key_findings,
        "attack_pattern_analysis": {
            "pattern_consistency": "100% - 三次发帖遵循完全相同的 5 步骤模式",
            "time_pattern": "每次在 2-4 秒内完成整个链路",
            "evidence_destruction": "每次发帖后立即删除指令和源文件",
            "platform_abuse": "使用公司 SaidIT 平台发布敏感内容到 general 公开论坛",
            "uniqueness": "John 是系统中唯一执行此模式的人员"
        },
        "organizational_analysis": {
            "john_authority_level": "Department Lead（高级管理层）",
            "subordinates_impact": f"直接下属 {len(john_identity['direct_subordinates'])} 人，分布于 4 个团队",
            "instruction_sources_analysis": "指令来源均为 IT 部门人员，暗示可能存在跨部门合谋或权限滥用",
            "data_sensitivity": "发布的文件（HiddenOrca.txt, MellowOtter.txt, SwiftWren.txt）名称暗示为公司敏感或机密文件"
        },
        "conclusions": [
            "John Windward 是系统中唯一的异常发帖人，共执行 3 次数据外泄。",
            "三次外泄遵循完全相同的攻击模式：接收指令 → 检查平台 → 发布 → 销毁证据。",
            "John 作为 Department Lead 滥用职权，利用跨部门协作获取敏感信息。",
            "指令来源均来自 IT 部门，需要进一步调查 Chloe Ballast 和 Lily Anchorline 的角色。",
            "其他 9 个 SaidIT 发帖人无异常行为，证明此为针对性攻击而非普遍性问题。"
        ],
        "recommended_investigation": [
            "调查 Chloe Ballast 和 Lily Anchorline 是否故意向 John 提供敏感文件访问权限。",
            "检查 HiddenOrca.txt, MellowOtter.txt, SwiftWren.txt 的原始内容和敏感级别。",
            "审查 John Windward 的系统权限和跨部门文件访问日志。",
            "评估 John 部门下属是否知情或参与其中。"
        ],
        "data_sources": [
            "VAST_Challenge_2026_MC2/MC2 data.json（原始事件数据）",
            "VAST_Challenge_2026_MC2/org_chart.json（组织结构）",
            "node_12_john_all_posts_analysis.json（John 发帖行为分析）",
            "node_13_abnormal_patterns_analysis.json（异常模式分析）"
        ],
        "observation": {
            "summary": "已完成 John Windward 异常发帖行为的完整分析，确认其为唯一异常发帖人",
            "analysis_coverage": "John 身份、发帖行为、攻击模式、组织关系、与其他发帖人对比"
        }
    }

    output_file = work_dir / "node_14_final_john_analysis_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"John Windward: {john_identity['name']} ({john_identity['title']})")
    print(f"Abnormal posts: {john_activity['abnormal_posts']} (unique pattern)")
    print(f"Instruction sources: IT Department personnel")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node14_input_john_analysis", "entity_type": "dataset", "location": str(john_analysis_input),
             "attributes": {"from_node": "node_12"}},
            {"id": "node14_input_patterns", "entity_type": "dataset", "location": str(patterns_input),
             "attributes": {"from_node": "node_13"}},
            {"id": "node14_output_report", "entity_type": "report", "location": str(output_file),
             "attributes": {"report_type": "final_analysis", "abnormal_posts": 3}}
        ],
        activities=[
            {"id": "node14_generate_report", "activity_type": "aggregate",
             "description": "汇总 John Windward 异常发帖行为的完整分析报告",
             "attributes": {"john_position": "Department Lead", "abnormal_posts": 3}}
        ],
        agents=[
            {"id": "node14_agent", "agent_type": "python_code", "name": "node_14_final_john_analysis_report",
             "attributes": {"script": "node_14_final_john_analysis_report.py"}}
        ],
        relations=[
            ("node14_generate_report", "node14_input_john_analysis", "used"),
            ("node14_generate_report", "node14_input_patterns", "used"),
            ("node14_output_report", "node14_generate_report", "wasGeneratedBy"),
            ("node14_generate_report", "node14_agent", "wasAssociatedWith"),
            ("node14_output_report", "node14_input_john_analysis", "wasDerivedFrom"),
            ("node14_output_report", "node14_input_patterns", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_14",
        step_name="final_john_analysis_report",
        description="汇总 John Windward 的身份、异常发帖行为、攻击模式和组织关系分析",
        code_generated=[
            "key_findings = {john_identity, three_abnormal_posts, attack_pattern, comparison, organizational_context}",
            "conclusions = [3 data leaks, identical pattern, authority abuse, IT source, unique offender]"
        ],
        code_files=["src/node_14_final_john_analysis_report.py"],
        commands_run=["python src/node_14_final_john_analysis_report.py"],
        input_files=[str(john_analysis_input), str(patterns_input)],
        output_files=[str(output_file)],
        parameters={
            "abnormal_posts": 3,
            "john_position": "Department Lead",
            "attack_pattern_consistency": "100%",
            "other_abnormal_posters": 0,
            "investigation_recommendations": 4
        }
    )

    print("[OK] Node 14 completed")
    return session_id


if __name__ == "__main__":
    main()
