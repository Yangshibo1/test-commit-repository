"""
Step 3: 分析事件链和参与者

这是VAST Challenge 2026 MC2分析的第三步。
读取Step 2的输出，分析事件链中的关键参与者。

输入: step2_saidit_events.json
预期输出: step3_chain_analysis.json
下一步: 生成最终报告
"""

import json
import sys
from pathlib import Path

# 添加 agentvast 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from agentvast.mcp_server import get_server


def main():
    print("=" * 60)
    print("Step 3: 分析事件链和参与者")
    print("=" * 60)

    # 获取服务器实例
    server = get_server()
    sessions = server.list_sessions()

    if not sessions:
        raise Exception("未找到会话，请先运行 step1_load_data.py 和 step2_filter_saidit.py")

    session_id = sessions[0]['session_id']
    work_dir = Path(server.base_dir) / session_id

    # 读取Step 2的输出
    input_file = work_dir / "step2_saidit_events.json"
    if not input_file.exists():
        raise Exception(f"未找到输入文件: {input_file}。请先运行 step2_filter_saidit.py")

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    events = data['events']
    print(f"输入事件数: {len(events)}")

    # 分析关键参与者
    key_participants = set()
    for event in events:
        parties = event.get('parties', [])
        key_participants.update(parties)

    # 构建事件链
    post_chain = []
    for event in events:
        post_chain.append({
            "id": event.get('id'),
            "short_name": event.get('short_name'),
            "parties": event.get('parties'),
            "when": event.get('when'),
            "details": str(event.get('details', {}))[:200]
        })

    # 分析结果
    results = {
        "key_participants": list(key_participants),
        "participant_count": len(key_participants),
        "post_chain": post_chain,
        "chain_length": len(post_chain)
    }

    print(f"关键参与者: {len(key_participants)}")
    print(f"事件链长度: {len(post_chain)}")

    # 保存中间文件
    output_file = work_dir / "step3_chain_analysis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"已保存到: {output_file}")

    # 记录PROV关系
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "input", "entity_type": "dataset", "location": str(input_file), "attributes": {}},
            {"id": "output", "entity_type": "artifact", "location": str(output_file), "attributes": {"participants": len(key_participants)}}
        ],
        activities=[
            {"id": "analyze_activity", "activity_type": "analyze", "description": "分析事件链和关键参与者", "attributes": {}}
        ],
        agents=[
            {"id": "analyze_agent", "agent_type": "python_code", "name": "step3_analyze_chain", "attributes": {}}
        ],
        relations=[
            ("analyze_activity", "input", "used"),
            ("output", "analyze_activity", "wasGeneratedBy"),
            ("analyze_activity", "analyze_agent", "wasAssociatedWith"),
            ("output", "input", "wasDerivedFrom")
        ]
    )

    # 记录步骤详情（必填）
    server.record_step_details(
        session_id=session_id,
        step_id="step_3",
        step_name="analyze_chain",
        description="基于Step 2输出，分析事件链中的关键参与者和系统交互。本步完成后可以生成最终报告。",
        code_generated=[
            "key_participants = set(event['parties'] for event in events)",
            "post_chain = [{'id': e['id'], 'short_name': e['short_name'], ...} for e in events]"
        ],
        code_files=[__file__],
        commands_run=[f"python {__file__}"],
        input_files=[str(input_file)],
        output_files=[str(output_file)],
        parameters={
            "key_participants_count": len(key_participants),
            "next_step": "生成最终报告或可视化",
            "decision_required": "基于分析结果生成最终报告"
        }
    )

    print("\nStep 3 完成！")
    print(f"会话ID: {session_id}")
    print(f"输出文件: {output_file}")
    print("\n下一步: 运行 generate_report.py 生成最终报告和可视化")


if __name__ == "__main__":
    main()
