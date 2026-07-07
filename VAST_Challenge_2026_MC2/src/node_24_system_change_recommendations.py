"""
MC2 Analysis - Node 24: System Change Recommendations
回答背景问题 6：说明可能的系统变更（干预点）
选择一个干预点，说明为什么该位置可能有效防止未来发生。
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
    print("Node 24: System Change Recommendations")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    # 基于之前的分析，识别可能的干预点
    intervention_points = [
        {
            "name": "content_source 处理验证",
            "location": "SaidIT 系统的 saidit_post 模块",
            "description": "在发布帖子时，如果指定了 content_source，验证该文件存在且内容可读",
            "effectiveness": "高 - 直接防止空内容帖子发布",
            "pros": "直接解决问题根源，防止空内容帖子",
            "cons": "需要修改核心发布逻辑"
        },
        {
            "name": "跨部门指令验证",
            "location": "queue_subordinate_task 模块",
            "description": "当任务涉及跨部门文件访问时，需要额外验证权限",
            "effectiveness": "中 - 可防止不当的文件访问",
            "pros": "增强安全性，减少滥用",
            "cons": "可能影响正常工作流程"
        },
        {
            "name": "文件删除前置审查",
            "location": "delete_file 模块",
            "description": "在删除文件后立即发布的帖子需要触发审查",
            "effectiveness": "中 - 可快速发现异常模式",
            "pros": "可在异常发生后快速响应",
            "cons": "被动措施，不能防止发生"
        },
        {
            "name": "SaidIT 发布内容非空检查",
            "location": "saidit_post 模块",
            "description": "强制要求帖子 content 字段非空",
            "effectiveness": "高 - 直接防止空内容发布",
            "pros": "简单直接，易于实现",
            "cons": "可能影响合法的空帖子（如果有）"
        }
    ]

    # 选择最佳干预点
    recommended_intervention = {
        "name": "SaidIT 发布内容完整性验证",
        "location": "SaidIT saidit_post 模块",
        "intervention_description": "在发布帖子时，如果 content_source 字段存在但 content 字段为空，系统应：(1) 验证 content_source 文件是否存在，(2) 尝试读取文件内容并填充到 content 字段，(3) 如果文件不可读，拒绝发布并报错",
        "why_this_location": [
            "这是异常行为发生的直接位置 - John 发布的帖子有 content_source 但 content 为空",
            "所有 3 个异常实例都遵循此模式：content_source 存在，content 为空",
            "在此处干预可以防止空内容帖子发布到公开论坛",
            "不会影响正常的 SaidIT 使用场景"
        ],
        "implementation": {
            "step_1": "在 saidit_post 处理逻辑中添加 content_source 验证",
            "step_2": "如果 content_source 存在且 content 为空，尝试读取文件",
            "step_3": "如果文件读取成功，将内容填充到 content",
            "step_4": "如果文件读取失败，返回错误并拒绝发布",
            "step_5": "记录所有 content_source 处理尝试用于审计"
        },
        "effectiveness_evidence": [
            "所有 3 个异常帖子都有 content_source 但 content 为空",
            "如果此干预在 5 月 10 日实施，可以防止后 2 个异常帖子",
            "这是最小侵入性的修复，不影响其他系统功能"
        ],
        "visualization_support": {
            "evidence": "PROV 可视化显示所有 3 个异常链都汇聚于 saidit_post 活动",
            "pattern": "所有异常实例中，saidit_post 都是最后一步，且都有相同的问题特征"
        },
        "alternative": "如果不想修改发布逻辑，可以考虑在 saidit_post_check 阶段添加警告，当检测到 content_source 存在但文件可能不可读时，提醒用户"
    }

    # 为什么其他干预点不是最佳选择
    other_points_analysis = [
        {
            "point": "跨部门指令验证",
            "why_not_best": "虽然可以防止不当文件访问，但这次异常中文件访问可能是合法的（John 通过正当渠道接收任务），问题在于后续处理而非访问权限"
        },
        {
            "point": "文件删除前置审查",
            "why_not_best": "这是被动措施，只能在异常发生后检测，不能防止发生。我们的目标是预防而非事后检测"
        },
        {
            "point": "限制 John Windward 的权限",
            "why_not_best": "这是针对个人的措施，不是系统修复。如果系统有缺陷，其他人也可能触发类似问题"
        }
    ]

    output = {
        "node_id": "node_24",
        "operation": "system_change_recommendations",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "question": "背景问题 6：说明可能的系统变更（干预点）",
        "recommended_intervention": recommended_intervention,
        "intervention_points_considered": intervention_points,
        "why_not_other_points": other_points_analysis,
        "expected_outcome": {
            "if_implemented": "所有 3 个异常帖子都会被阻止或正确填充内容",
            "prevention_rate": "100% - 基于历史模式，此干预可防止所有已知的异常实例",
            "side_effects": "最小 - 只影响 content_source 处理逻辑"
        },
        "root_cause_addressed": "系统在处理 content_source 时存在缺陷，导致帖子内容为空而不是文件内容",
        "additional_benefits": [
            "增强系统鲁棒性",
            "提供更好的错误消息",
            "创建审计日志用于未来分析"
        ]
    }

    output_file = work_dir / "node_24_system_change_recommendations.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Recommended intervention: {recommended_intervention['name']}")
    print(f"Location: {recommended_intervention['location']}")
    print(f"Expected prevention: 100% of known anomalies")
    print(f"Output: {output_file}")

    # 记录 PROV
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node24_output_recommendations", "entity_type": "report", "location": str(output_file),
             "attributes": {"question_answered": "Q6", "intervention_recommended": True}}
        ],
        activities=[
            {"id": "node24_recommend_changes", "activity_type": "analyze",
             "description": "分析并推荐系统变更干预点，防止未来发生类似异常",
             "attributes": {"intervention_points_considered": len(intervention_points)}}
        ],
        agents=[
            {"id": "node24_agent", "agent_type": "python_code", "name": "node_24_system_change_recommendations",
             "attributes": {"script": "node_24_system_change_recommendations.py"}}
        ],
        relations=[
            ("node24_recommend_changes", "node24_output_recommendations", "wasGeneratedBy"),
            ("node24_recommend_changes", "node24_agent", "wasAssociatedWith"),
            ("node24_output_recommendations", "node24_recommend_changes", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_24",
        step_name="system_change_recommendations",
        description="回答背景问题 6：推荐系统变更干预点，选择最佳位置并说明原因",
        code_generated=[
            "识别多个可能的干预点",
            "选择最佳干预点：SaidIT 发布内容完整性验证",
            "说明为什么此位置最有效：直接针对问题根源"
        ],
        code_files=["src/node_24_system_change_recommendations.py"],
        commands_run=["python src/node_24_system_change_recommendations.py"],
        input_files=[],
        output_files=[str(output_file)],
        parameters={
            "intervention_points_considered": 4,
            "recommended_intervention": "content_source_validation",
            "expected_prevention_rate": "100%"
        }
    )

    print("[OK] Node 24 completed - All 6 background questions now answered")
    return session_id


if __name__ == "__main__":
    main()
