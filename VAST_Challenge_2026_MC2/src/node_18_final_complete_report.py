"""
MC2 Analysis - Node 18: Final Complete Investigation Report
汇总完整的调查结果，回答两个关键问题。
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
    print("Node 18: Final Complete Investigation Report")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 读取所有分析结果
    leak_verification_input = work_dir / "node_16_other_leaks_verification.json"
    it_investigation_input = work_dir / "node_17_it_personnel_investigation.json"
    john_report_input = work_dir / "node_14_final_john_analysis_report.json"

    with open(leak_verification_input, "r", encoding="utf-8") as f:
        leak_verification = json.load(f)
    with open(it_investigation_input, "r", encoding="utf-8") as f:
        it_investigation = json.load(f)
    with open(john_report_input, "r", encoding="utf-8") as f:
        john_report = json.load(f)

    # 问题 1：另外两次数据外泄成功了吗
    q1_answer = {
        "question": "另外两次数据外泄成功了吗",
        "answer": "YES - 三次外泄全部成功",
        "evidence": [
            f"所有三次帖子（HiddenOrca.txt, MellowOtter.txt, SwiftWren.txt）都成功发布到了 general 公开论坛",
            f"所有三个源文件都在发帖后被删除（证据销毁）",
            f"所有三个帖子仍然存在（没有被删除）",
            f"总浏览量：0 次记录的浏览事件（但这不意味着没人看到，只是系统未记录）"
        ],
        "per_leak_status": [
            {
                "content_source": "HiddenOrca.txt",
                "post_datetime": "2046-05-10 20:45:42",
                "successful": True,
                "file_deleted": True,
                "post_still_exists": True
            },
            {
                "content_source": "MellowOtter.txt",
                "post_datetime": "2046-05-11 08:56:04",
                "successful": True,
                "file_deleted": True,
                "post_still_exists": True
            },
            {
                "content_source": "SwiftWren.txt",
                "post_datetime": "2046-05-17 19:21:15",
                "successful": True,
                "file_deleted": True,
                "post_still_exists": True
            }
        ],
        "conclusion": "所有三次数据外泄都完全成功：敏感内容被发布到公开论坛，源文件被删除，帖子仍然存在"
    }

    # 问题 2：进一步审查 IT 部门的 Chloe Ballast 和 Lily Anchorline
    q2_answer = {
        "question": "进一步审查 IT 部门的 Chloe Ballast 和 Lily Anchorline",
        "profiles": it_investigation["personnel_profiles"],
        "involvement_in_leaks": it_investigation["per_leak_analysis"],
        "suspicion_levels": it_investigation["suspicion_levels"],
        "key_findings": [
            "Chloe Ballast：IT Department Lead，涉及 2/3 次外泄（HiddenOrca.txt 和 SwiftWren.txt）",
            "Lily Anchorline：Infrastructure Team 成员，涉及 1/3 次外泄（MellowOtter.txt）",
            "两人之间有 32 次记录的交互",
            "Chloe 有 161 次敏感文件访问记录，Lily 有 61 次",
            "所有三次外泄都遵循相同的指令模式：queue_subordinate_task(read_file XXX_further_instructions.md)"
        ],
        "chloe_specific_analysis": {
            "role": "IT Department Lead",
            "total_events": 3801,
            "sensitive_file_access": 161,
            "leaks_involved": 2,
            "suspicion_level": "HIGH",
            "reasoning": [
                "作为 IT Dept Lead 拥有最高权限",
                "涉及 2/3 的外泄事件",
                "有大量敏感文件访问记录",
                "两次外泄间隔一周（5/10 和 5/17），暗示可能是主谋"
            ]
        },
        "lily_specific_analysis": {
            "role": "Infrastructure Team Member",
            "total_events": 3226,
            "sensitive_file_access": 61,
            "leaks_involved": 1,
            "suspicion_level": "MEDIUM",
            "reasoning": [
                "Infrastructure Team 成员，可能直接处理文件系统",
                "只涉及 1/3 的外泄事件",
                "也有敏感文件访问记录",
                "可能是被利用或知情者，不一定是主谋"
            ]
        },
        "instruction_pattern_analysis": {
            "pattern": "所有三次外泄都使用相同的指令格式",
            "instruction_structure": "queue_subordinate_task(target=John Windward, task=read_file, args=[XXX_further_instructions.md])",
            "timing": "指令到发帖的时间间隔：2-3 秒",
            "implication": "这种高度一致的模式暗示可能是预先策划或自动化执行"
        },
        "recommended_actions": [
            "立即冻结 Chloe Ballast 和 Lily Anchorline 的系统访问权限",
            "审查 Chloe 与 John Windward 的所有通信记录",
            "检查这些敏感文件的创建历史和原始创建者",
            "评估 IT 部门内部的权限管理流程是否存在漏洞",
            "考虑是否有其他未被发现的数据外泄事件"
        ]
    }

    # 综合结论
    overall_conclusions = [
        "这是一起精心策划的跨部门数据外泄事件，而非单一意外",
        "John Windward（Customer Support Dept Lead）是执行者，负责实际发布敏感内容",
        "Chloe Ballast（IT Dept Lead）很可能是主谋，涉及 2/3 的外泄并提供指令",
        "Lily Anchorline（Infrastructure Team）可能参与其中或被利用，涉及 1/3 的外泄",
        "攻击模式高度一致：指令 → 检查 → 发布 → 删除，在 2-4 秒内完成",
        "所有外泄都成功：敏感内容发布到公开论坛，源文件被删除，帖子仍然存在",
        "需要立即采取行动：冻结权限、审查通信、评估损失"
    ]

    report = {
        "node_id": "node_18",
        "operation": "final_complete_investigation_report",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "report_title": "John Windward 数据外泄事件完整调查报告",
        "investigation_scope": "三次数据外泄事件及相关人员审查",
        "questions_answered": {
            "q1_other_leaks_successful": q1_answer,
            "q2_it_personnel_investigation": q2_answer
        },
        "overall_conclusions": overall_conclusions,
        "data_exfiltration_summary": {
            "total_leaks": 3,
            "all_successful": True,
            "timeline": {
                "leak_1": "2046-05-10 20:45:42 (HiddenOrca.txt)",
                "leak_2": "2046-05-11 08:56:04 (MellowOtter.txt)",
                "leak_3": "2046-05-17 19:21:15 (SwiftWren.txt)"
            },
            "attack_pattern_consistency": "100%",
            "posts_remaining_public": 3,
            "source_files_deleted": 3
        },
        "personnel_assessment": {
            "john_windward": {
                "role": "执行者",
                "department": "Customer Support",
                "involvement": "执行所有三次外泄",
                "suspicion": "EXTREME"
            },
            "chloe_ballast": {
                "role": "可能的主谋",
                "department": "Information Technologies",
                "involvement": "提供 2/3 的外泄指令",
                "suspicion": "HIGH"
            },
            "lily_anchorline": {
                "role": "可能的参与者或被利用者",
                "department": "Information Technologies (Infrastructure Team)",
                "involvement": "提供 1/3 的外泄指令",
                "suspicion": "MEDIUM"
            }
        },
        "observation": {
            "summary": "已完成 John Windward 三次数据外泄事件及相关人员的完整调查",
            "final_assessment": "这是一起精心策划的跨部门合谋数据外泄事件，需要立即采取行动"
        }
    }

    output_file = work_dir / "node_18_final_complete_investigation_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Complete investigation report generated")
    print(f"Total leaks: 3, All successful: True")
    print(f"High suspicion personnel: Chloe Ballast (IT Dept Lead)")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node18_input_leak_verification", "entity_type": "dataset", "location": str(leak_verification_input),
             "attributes": {"from_node": "node_16"}},
            {"id": "node18_input_it_investigation", "entity_type": "dataset", "location": str(it_investigation_input),
             "attributes": {"from_node": "node_17"}},
            {"id": "node18_input_john_report", "entity_type": "dataset", "location": str(john_report_input),
             "attributes": {"from_node": "node_14"}},
            {"id": "node18_output_report", "entity_type": "report", "location": str(output_file),
             "attributes": {"report_type": "final_complete_investigation", "leaks": 3}}
        ],
        activities=[
            {"id": "node18_generate_final_report", "activity_type": "aggregate",
             "description": "汇总完整调查结果，回答两个关键问题并给出综合结论",
             "attributes": {"questions_answered": 2, "leaks_analyzed": 3}}
        ],
        agents=[
            {"id": "node18_agent", "agent_type": "python_code", "name": "node_18_final_complete_report",
             "attributes": {"script": "node_18_final_complete_report.py"}}
        ],
        relations=[
            ("node18_generate_final_report", "node18_input_leak_verification", "used"),
            ("node18_generate_final_report", "node18_input_it_investigation", "used"),
            ("node18_generate_final_report", "node18_input_john_report", "used"),
            ("node18_output_report", "node18_generate_final_report", "wasGeneratedBy"),
            ("node18_generate_final_report", "node18_agent", "wasAssociatedWith"),
            ("node18_output_report", "node18_input_leak_verification", "wasDerivedFrom"),
            ("node18_output_report", "node18_input_it_investigation", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_18",
        step_name="final_complete_investigation_report",
        description="汇总完整调查结果，回答两个关键问题并给出综合结论和行动建议",
        code_generated=[
            "q1_answer = {其他两次外泄成功状态}",
            "q2_answer = {IT 人员详细审查}",
            "overall_conclusions = [综合结论和行动建议]"
        ],
        code_files=["src/node_18_final_complete_report.py"],
        commands_run=["python src/node_18_final_complete_report.py"],
        input_files=[str(leak_verification_input), str(it_investigation_input), str(john_report_input)],
        output_files=[str(output_file)],
        parameters={
            "questions_answered": 2,
            "leaks_analyzed": 3,
            "personnel_investigated": 3,
            "all_leaks_successful": True
        }
    )

    print("[OK] Node 18 completed")
    return session_id


if __name__ == "__main__":
    main()
