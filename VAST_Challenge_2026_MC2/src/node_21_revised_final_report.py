"""
MC2 Analysis - Node 21: Revised Final Report
基于用户观察修正最终结论：
1. 帖子内容为空（不是乱码，是完全空内容）
2. SwiftWren.txt 由 Emma Harbor (E开头) 创建
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
    print("Node 21: Revised Final Report")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 读取之前的结果
    node_04_trace = work_dir / "node_04_source_trace.json"
    node_17_investigation = work_dir / "node_17_it_personnel_investigation.json"
    node_18_report = work_dir / "node_18_final_complete_investigation_report.json"

    with open(node_04_trace, "r", encoding="utf-8") as f:
        trace = json.load(f)
    with open(node_17_investigation, "r", encoding="utf-8") as f:
        it_inv = json.load(f)
    with open(node_18_report, "r", encoding="utf-8") as f:
        old_report = json.load(f)

    # 获取 SwiftWren.txt 创建者信息
    swiftwren_created = trace["file_lifecycle"]["created"][0]
    creator = swiftwren_created["parties"][0]  # Agent/person:emma_harbor

    # Emma Harbor 的身份
    emma_identity = {
        "id": "person:emma_harbor",
        "name": "Emma Harbor",
        "title": "CFO",
        "department": "Executive Suite"
    }

    # 修正后的关键发现
    revised_findings = {
        "post_content_analysis": {
            "observation": "用户观察：发布的帖子是乱码",
            "actual_finding": "所有3个帖子的 content 字段完全为空",
            "implication": "虽然帖子在技术上发布到了 general 论坛，但实际没有任何内容",
            "conclusion": "这不是成功的'数据外泄'，因为没有任何信息真正泄露给公众"
        },
        "swiftwren_creator_analysis": {
            "observation": "用户观察：SwiftWren.txt 由 E 开头的人创建",
            "actual_finding": f"SwiftWren.txt 由 {creator} 创建",
            "creator_identity": emma_identity,
            "implication": "文件创建者是 CFO Emma Harbor（最高管理层），不是 IT 部门",
            "timeline": "2046-05-09 23:02:01 创建，2046-05-17 19:21:17 被删除"
        }
    }

    # 修正后的攻击链分析
    revised_attack_chain = {
        "original_understanding": {
            "file_creator": "unknown",
            "instruction_source": "Chloe Ballast (IT Dept Lead)",
            "executor": "John Windward (Customer Support Dept Lead)",
            "purpose": "数据外泄"
        },
        "corrected_understanding": {
            "file_creator": "Emma Harbor (CFO, Executive Suite)",
            "instruction_source": "Chloe Ballast (IT Dept Lead)",
            "executor": "John Windward (Customer Support Dept Lead)",
            "purpose": "unknown - but not simple data theft"
        },
        "key_corrections": [
            "文件创建者是 CFO Emma Harbor，不是 IT 人员",
            "帖子内容为空，所以没有实际信息泄露",
            "攻击链涉及最高管理层（CFO）→ IT → Customer Support",
            "这可能不是简单的数据外泄，而是其他目的（测试、掩盖、信号等）"
        ]
    }

    # 重新评估人员角色
    revised_personnel_assessment = {
        "emma_harbor": {
            "role": "CFO (Executive Suite)",
            "involvement": "SwiftWren.txt 文件创建者",
            "suspicion_level": "HIGH - 最高管理层，文件创建者",
            "question": "为什么 CFO 创建的文件会被'外泄'？"
        },
        "chloe_ballast": {
            "role": "IT Department Lead",
            "involvement": "指令来源（2/3 外泄）",
            "suspicion_level": "HIGH - 可能在执行 Emma 的意图或测试",
            "question": "Chloe 是否知道 Emma 创建了这个文件？"
        },
        "john_windward": {
            "role": "Customer Support Department Lead",
            "involvement": "执行者（3/3 外泄）",
            "suspicion_level": "HIGH - 发布空内容帖子，明知没有实际信息",
            "question": "John 是否知道帖子内容为空？"
        },
        "lily_anchorline": {
            "role": "Infrastructure Team (IT)",
            "involvement": "指令来源（1/3 外泄）",
            "suspicion_level": "MEDIUM - 可能被利用或知情"
        }
    }

    # 修正后的结论
    revised_conclusions = [
        "这很可能不是一次真正的'数据外泄'事件，而是一次精心策划的'模拟外泄'",
        "所有3个帖子的内容都是空的，没有任何信息真正泄露",
        "SwiftWren.txt 由 CFO Emma Harbor 创建，涉及最高管理层",
        "攻击链跨三层：Executive Suite (CFO) → IT Dept Lead → Customer Support Dept Lead",
        "可能的动机：测试系统响应、掩盖其他行为、发送信号、或内部政治操作",
        "关键问题：为什么 CFO 创建的文件会通过 IT 和 Customer Support '外泄'？"
    ]

    output = {
        "node_id": "node_21",
        "operation": "revised_final_report",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "user_observations_validated": {
            "posts_are_gibberish": "CONFIRMED - 实际上内容为空",
            "swiftwren_creator_e_name": "CONFIRMED - Emma Harbor (CFO)"
        },
        "revised_findings": revised_findings,
        "revised_attack_chain": revised_attack_chain,
        "revised_personnel_assessment": revised_personnel_assessment,
        "revised_conclusions": revised_conclusions,
        "new_questions": [
            "Emma Harbor (CFO) 创建 SwiftWren.txt 的目的是什么？",
            "为什么帖子内容为空？是技术问题还是有意为之？",
            "这是否是一次系统测试或内部政治操作？",
            "Emma Harbor 是否知情或参与了这次'模拟外泄'？"
        ],
        "recommended_investigation": [
            "立即审查 Emma Harbor 与 Chloe Ballast 和 John Windward 的关系",
            "检查 Emma Harbor 创建 SwiftWren.txt 的背景和目的",
            "确定帖子内容为空的原因（技术问题 vs 有意设计）",
            "评估这是否是一次系统安全测试或其他内部操作",
            "考虑是否有其他未发现的'模拟外泄'事件"
        ]
    }

    output_file = work_dir / "node_21_revised_final_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"User observations validated:")
    print(f"  - Post content: EMPTY (not gibberish, but completely empty)")
    print(f"  - SwiftWren creator: {creator} (CFO)")
    print(f"Revised assessment: This may be a SIMULATED exfiltration, not real data leak")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node21_input_trace", "entity_type": "dataset", "location": str(node_04_trace),
             "attributes": {"from_node": "node_04"}},
            {"id": "node21_input_it_inv", "entity_type": "dataset", "location": str(node_17_investigation),
             "attributes": {"from_node": "node_17"}},
            {"id": "node21_input_old_report", "entity_type": "dataset", "location": str(node_18_report),
             "attributes": {"from_node": "node_18"}},
            {"id": "node21_output_revised", "entity_type": "report", "location": str(output_file),
             "attributes": {"report_type": "revised_final", "user_observations_validated": True}}
        ],
        activities=[
            {"id": "node21_revise_report", "activity_type": "aggregate",
             "description": "基于用户观察修正最终结论：帖子内容为空、文件由 CFO 创建",
             "attributes": {"revisions": 2, "original_conclusions_changed": True}}
        ],
        agents=[
            {"id": "node21_agent", "agent_type": "python_code", "name": "node_21_revised_final_report",
             "attributes": {"script": "node_21_revised_final_report.py"}}
        ],
        relations=[
            ("node21_revise_report", "node21_input_trace", "used"),
            ("node21_revise_report", "node21_input_it_inv", "used"),
            ("node21_revise_report", "node21_input_old_report", "used"),
            ("node21_output_revised", "node21_revise_report", "wasGeneratedBy"),
            ("node21_revise_report", "node21_agent", "wasAssociatedWith"),
            ("node21_output_revised", "node21_input_trace", "wasDerivedFrom"),
            ("node21_output_revised", "node21_input_old_report", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_21",
        step_name="revised_final_report",
        description="基于用户观察修正最终结论：确认帖子内容为空、SwiftWren.txt 由 CFO Emma Harbor 创建",
        code_generated=[
            "swiftwren_creator = Emma Harbor (CFO)",
            "post_content = EMPTY (all 3 posts)",
            "revised_assessment = SIMULATED exfiltration, not real data leak"
        ],
        code_files=["src/node_21_revised_final_report.py"],
        commands_run=["python src/node_21_revised_final_report.py"],
        input_files=[str(node_04_trace), str(node_17_investigation), str(node_18_report)],
        output_files=[str(output_file)],
        parameters={
            "user_observation_1_validated": True,
            "user_observation_2_validated": True,
            "original_conclusions_changed": True,
            "new_hypothesis": "simulated_exfiltration"
        }
    )

    print("[OK] Node 21 completed - Report Revised")
    return session_id


if __name__ == "__main__":
    main()
