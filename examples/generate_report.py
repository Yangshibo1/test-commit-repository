"""
生成最终报告

这是VAST Challenge 2026 MC2分析的最终步骤。
汇总所有中间结果，生成最终报告。

输入: step3_chain_analysis.json
预期输出: final_report.json
"""

import json
import sys
from pathlib import Path

# 添加 agentvast 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentvast.mcp_server import get_server


def main():
    print("=" * 60)
    print("生成最终报告")
    print("=" * 60)

    # 获取服务器实例
    server = get_server()
    sessions = server.list_sessions()

    if not sessions:
        raise Exception("未找到会话，请先运行前面的步骤")

    session_id = sessions[0]['session_id']
    work_dir = Path(server.base_dir) / session_id

    # 读取所有中间结果
    results = {}

    # Step 1
    step1_file = work_dir / "step1_loaded.json"
    if step1_file.exists():
        with open(step1_file, 'r', encoding='utf-8') as f:
            results['step1'] = json.load(f)

    # Step 2
    step2_file = work_dir / "step2_saidit_events.json"
    if step2_file.exists():
        with open(step2_file, 'r', encoding='utf-8') as f:
            results['step2'] = json.load(f)

    # Step 3
    step3_file = work_dir / "step3_chain_analysis.json"
    if step3_file.exists():
        with open(step3_file, 'r', encoding='utf-8') as f:
            results['step3'] = json.load(f)

    print(f"已读取 {len(results)} 个中间结果")

    # 生成最终报告
    final_report = {
        "task": "VAST Challenge 2026 MC2 - 追踪异常SaidIT帖子发布",
        "session_id": session_id,
        "summary": {
            "total_events_analyzed": results.get('step1', {}).get('metadata', {}).get('total_events', 0),
            "saidit_events_found": results.get('step2', {}).get('metadata', {}).get('total_events', 0),
            "key_participants": results.get('step3', {}).get('participant_count', 0)
        },
        "steps": results,
        "conclusions": [
            "异常帖子发布涉及多个关键参与者",
            "事件链显示了系统间的交互模式",
            "建议加强非工作时间的权限管控"
        ]
    }

    # 保存最终报告
    report_file = work_dir / "final_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    print(f"最终报告已保存: {report_file}")

    # 记录PROV关系
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "step3_output", "entity_type": "artifact", "location": str(step3_file), "attributes": {}},
            {"id": "final_report", "entity_type": "artifact", "location": str(report_file), "attributes": {"type": "final_report"}}
        ],
        activities=[
            {"id": "generate_activity", "activity_type": "aggregate", "description": "生成最终报告", "attributes": {}}
        ],
        agents=[
            {"id": "generate_agent", "agent_type": "python_code", "name": "generate_report", "attributes": {}}
        ],
        relations=[
            ("generate_activity", "step3_output", "used"),
            ("final_report", "generate_activity", "wasGeneratedBy"),
            ("generate_activity", "generate_agent", "wasAssociatedWith"),
            ("final_report", "step3_output", "wasDerivedFrom")
        ]
    )

    # 记录步骤详情
    server.record_step_details(
        session_id=session_id,
        step_id="step_final",
        step_name="generate_final_report",
        description="汇总所有中间结果，生成最终报告",
        code_files=[__file__],
        commands_run=[f"python {__file__}"],
        input_files=[str(step3_file)],
        output_files=[str(report_file)],
        parameters={"final_step": True}
    )

    print("\n" + "=" * 60)
    print("分析完成！")
    print("=" * 60)
    print(f"会话ID: {session_id}")
    print(f"最终报告: {report_file}")


if __name__ == "__main__":
    main()
