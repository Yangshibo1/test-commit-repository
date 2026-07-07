"""
MC2 Analysis - Node 23: Background Questions Assessment
对照 background.md 中的关键问题，评估我们的分析是否良好解答。
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
    print("Node 23: Background Questions Assessment")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 读取关键分析结果
    node_04_trace = work_dir / "node_04_source_trace.json"
    node_09_comparison = work_dir / "node_09_instruction_outcome_comparison.json"
    node_12_john = work_dir / "node_12_john_all_posts_analysis.json"

    with open(node_04_trace, "r", encoding="utf-8") as f:
        trace = json.load(f)
    with open(node_09_comparison, "r", encoding="utf-8") as f:
        comparison = json.load(f)
    with open(node_12_john, "r", encoding="utf-8") as f:
        john_analysis = json.load(f)

    # background.md 中的问题
    assessment = {
        "node_id": "node_23",
        "operation": "background_questions_assessment",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "background_context": {
            "actual_problem": "这是 agent 故障/发帖异常问题，不是数据攻击",
            "anomaly_description": "John Windward 发布的帖子内容是乱码/空内容，论坛似乎是随机的"
        },
        "questions_assessment": [
            {
                "question": "1. 异常帖子是如何产生的？",
                "answered": True,
                "evidence_nodes": ["node_04", "node_13"],
                "summary": "已追踪完整事件链：Emma Harbor 创建文件 → Daniel Gangway → Chloe Ballast → John Windward 执行发布",
                "event_chain": [
                    "2046-05-09 23:02:01 - Emma Harbor 创建 SwiftWren.txt",
                    "2046-05-17 19:12:24 - Daniel Gangway 指派 Chloe Ballast 读取文件",
                    "2046-05-17 19:21:13 - Chloe Ballast 指派 John Windward 读取文件",
                    "2046-05-17 19:21:14 - John Windward saidit_post_check",
                    "2046-05-17 19:21:15 - John Windward saidit_post (content_source=SwiftWren.txt)",
                    "2046-05-17 19:21:16/17 - John Windward 删除指令和源文件"
                ],
                "quality": "完整"
            },
            {
                "question": "2. 提供详细视图（聚焦确切事件链）",
                "answered": True,
                "evidence_nodes": ["node_04"],
                "summary": "node_04 提供了精确到秒的事件链，包括所有相关人员和系统交互",
                "quality": "完整"
            },
            {
                "question": "3. 提供系统概览（上下文化）",
                "answered": True,
                "evidence_nodes": ["node_01", "node_02", "node_15", "node_19", "node_22"],
                "summary": "通过 PROV 可视化将事件链置于整体系统中，显示 67 实体、22 活动、129 边",
                "quality": "完整"
            },
            {
                "question": "4. 帖子的'意义'是什么？内容起源是什么？",
                "answered": True,
                "evidence_nodes": ["node_04", "node_12", "node_20"],
                "summary": "content_source=SwiftWren.txt，由 Emma Harbor (CFO) 创建，但帖子内容为空",
                "content_origin": "Emma Harbor (CFO) 于 2046-05-09 23:02:01 创建 SwiftWren.txt (30615 bytes)",
                "post_content": "帖子 content 字段完全为空，所以实际'意义'可能是测试/异常/空引用",
                "reasoning": "文件存在但帖子内容为空，暗示可能是系统错误或配置问题",
                "quality": "部分 - 需要更深入解释为什么文件内容没有出现在帖子中"
            },
            {
                "question": "5. 找到其他实例（历史系统行为）",
                "answered": True,
                "evidence_nodes": ["node_08", "node_09", "node_10", "node_12"],
                "summary": "找到 3 个实例，全部由 John Windward 执行，都遵循相同的 5 步骤模式",
                "instances": [
                    "2046-05-10 20:45:42 - HiddenOrca.txt (Chloe Ballast 指令)",
                    "2046-05-11 08:56:04 - MellowOtter.txt (Lily Anchorline 指令)",
                    "2046-05-17 19:21:15 - SwiftWren.txt (Chloe Ballast 指令)"
                ],
                "common_pattern": "queue_subordinate_task → saidit_post_check → saidit_post(空内容) → delete_file × 2",
                "comparison": "所有实例都由 John Windward 执行，所有帖子内容为空，所有源文件被删除",
                "quality": "完整"
            },
            {
                "question": "6. 说明可能的系统变更（干预点）",
                "answered": False,
                "evidence_nodes": [],
                "summary": "未提供具体的系统变更建议",
                "missing": "需要选择一个干预点，说明为什么该位置可能有效防止未来发生",
                "quality": "未回答"
            }
        ],
        "problem_recharacterization": {
            "original_misunderstanding": "被错误地理解为数据外泄攻击",
            "correct_understanding": "这是 agent 发帖异常/系统故障问题",
            "key_evidence": [
                "所有 3 个帖子的内容都是空的（不是泄露的敏感数据）",
                "发布论坛是 general（不是随机的，是固定的）",
                "执行者 John Windward 是 Customer Support Department Lead"
            ],
            "root_cause_hypothesis": "系统在处理 content_source 时存在缺陷，导致帖子内容为空而不是文件内容"
        },
        "gaps_and_recommendations": [
            {
                "gap": "问题 6 未回答：系统变更建议",
                "recommendation": "需要基于分析选择一个干预点（如 content_source 处理、file deletion 权限、跨部门指令验证）"
            },
            {
                "gap": "未深入解释为什么帖子内容为空",
                "recommendation": "需要分析 SaidIT 系统如何处理 content_source 字段，是否存在 bug"
            },
            {
                "gap": "未解释 Emma Harbor (CFO) 创建的文件为何会进入'外泄'链",
                "recommendation": "需要分析文件权限和访问控制逻辑"
            }
        ]
    }

    output_file = work_dir / "node_23_background_qa_assessment.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(assessment, f, ensure_ascii=False, indent=2)

    print(f"Questions answered: 5/6")
    print(f"Missing: Question 6 (System change recommendations)")
    print(f"Problem recharacterization: Agent malfunction, not data attack")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node23_input_trace", "entity_type": "dataset", "location": str(node_04_trace),
             "attributes": {"from_node": "node_04"}},
            {"id": "node23_input_comparison", "entity_type": "dataset", "location": str(node_09_comparison),
             "attributes": {"from_node": "node_09"}},
            {"id": "node23_input_john", "entity_type": "dataset", "location": str(node_12_john),
             "attributes": {"from_node": "node_12"}},
            {"id": "node23_output_assessment", "entity_type": "report", "location": str(output_file),
             "attributes": {"questions_assessed": 6, "answered": 5}}
        ],
        activities=[
            {"id": "node23_assess_background_qa", "activity_type": "analyze",
             "description": "对照 background.md 问题评估分析完整性",
             "attributes": {"questions": 6, "answered": 5}}
        ],
        agents=[
            {"id": "node23_agent", "agent_type": "python_code", "name": "node_23_background_qa_assessment",
             "attributes": {"script": "node_23_background_qa_assessment.py"}}
        ],
        relations=[
            ("node23_assess_background_qa", "node23_input_trace", "used"),
            ("node23_assess_background_qa", "node23_input_comparison", "used"),
            ("node23_assess_background_qa", "node23_input_john", "used"),
            ("node23_output_assessment", "node23_assess_background_qa", "wasGeneratedBy"),
            ("node23_assess_background_qa", "node23_agent", "wasAssociatedWith"),
            ("node23_output_assessment", "node23_input_trace", "wasDerivedFrom"),
            ("node23_output_assessment", "node23_input_john", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_23",
        step_name="background_qa_assessment",
        description="对照 background.md 关键问题评估分析完整性，识别问题重新定位和缺失",
        code_generated=[
            "对照 6 个背景问题评估每个问题的回答状态",
            "重新定位问题：agent 故障而非数据攻击",
            "识别缺失：问题 6 系统变更建议"
        ],
        code_files=["src/node_23_background_qa_assessment.py"],
        commands_run=["python src/node_23_background_qa_assessment.py"],
        input_files=[str(node_04_trace), str(node_09_comparison), str(node_12_john)],
        output_files=[str(output_file)],
        parameters={
            "questions_assessed": 6,
            "questions_answered": 5,
            "problem_recharacterized": True,
            "missing_system_change_recommendations": True
        }
    )

    print("[OK] Node 23 completed")
    return session_id


if __name__ == "__main__":
    main()
