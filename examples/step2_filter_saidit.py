"""
Step 2: 过滤SaidIT相关事件

这是VAST Challenge 2026 MC2分析的第二步。
读取Step 1的输出，过滤出SaidIT相关事件。

输入: step1_loaded.json
预期输出: step2_saidit_events.json
下一步: 分析事件链和参与者
"""

import json
import sys
from pathlib import Path
from datetime import datetime as dt

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from opentrace.mcp_server import get_server


def main():
    print("=" * 60)
    print("Step 2: 过滤SaidIT相关事件")
    print("=" * 60)

    # 获取服务器实例
    server = get_server()
    sessions = server.list_sessions()

    if not sessions:
        raise Exception("未找到会话，请先运行 step1_load_data.py")

    session_id = sessions[0]['session_id']
    work_dir = Path(server.base_dir) / session_id

    # 读取Step 1的输出
    input_file = work_dir / "step1_loaded.json"
    if not input_file.exists():
        raise Exception(f"未找到输入文件: {input_file}。请先运行 step1_load_data.py")

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    events = data['events']
    org_chart = data['org_chart']

    print(f"输入事件总数: {len(events):,}")

    # 目标时间窗口
    ANOMALOUS_POST_TIME = "2046-05-17T04:21:00"
    target_timestamp = dt(2046, 5, 17, 4, 21).timestamp()
    time_window = 3600 * 24  # 前后24小时

    # 过滤相关事件
    saidit_events = []
    for event in events:
        # 时间窗口过滤
        if abs(event.get('when', 0) - target_timestamp) >= time_window:
            continue

        # SaidIT相关过滤
        short_name = event.get('short_name', '')
        parties = event.get('parties', [])

        if 'saidit' in short_name.lower() or any('saidit' in str(p).lower() for p in parties):
            saidit_events.append(event)

    # 去重
    seen_ids = set()
    unique_events = []
    for event in saidit_events:
        if event.get('id') not in seen_ids:
            seen_ids.add(event.get('id'))
            unique_events.append(event)

    print(f"找到SaidIT相关事件: {len(unique_events)}")

    # 保存中间文件
    output_file = work_dir / "step2_saidit_events.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'events': unique_events,
            'metadata': {
                'total_events': len(unique_events),
                'target_time': ANOMALOUS_POST_TIME,
                'time_window_hours': 24
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"已保存到: {output_file}")

    # 记录PROV关系
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "input", "entity_type": "dataset", "location": str(input_file), "attributes": {}},
            {"id": "output", "entity_type": "dataset", "location": str(output_file), "attributes": {"events": len(unique_events)}}
        ],
        activities=[
            {"id": "filter_activity", "activity_type": "filter", "description": "过滤SaidIT相关事件", "attributes": {"time_window": "24h"}}
        ],
        agents=[
            {"id": "filter_agent", "agent_type": "python_code", "name": "step2_filter_saidit", "attributes": {}}
        ],
        relations=[
            ("filter_activity", "input", "used"),
            ("output", "filter_activity", "wasGeneratedBy"),
            ("filter_activity", "filter_agent", "wasAssociatedWith"),
            ("output", "input", "wasDerivedFrom")
        ]
    )

    # 记录步骤详情（必填）
    server.record_step_details(
        session_id=session_id,
        step_id="step_2",
        step_name="filter_saidit_events",
        description="基于Step 1输出，过滤目标时间窗口内的SaidIT相关事件。本步完成后需要读取输出，分析事件链和参与者。",
        code_generated=[
            "events = [e for e in all_events if abs(e['when'] - target_timestamp) < time_window]",
            "saidit_events = [e for e in events if 'saidit' in e['short_name'].lower()]"
        ],
        code_files=[__file__],
        commands_run=[f"python {__file__}"],
        input_files=[str(input_file)],
        output_files=[str(output_file)],
        parameters={
            "target_time": ANOMALOUS_POST_TIME,
            "time_window_hours": 24,
            "next_step": "分析事件链和参与者",
            "decision_required": "需要读取step2_saidit_events.json，分析事件链中的人员和系统交互"
        }
    )

    print("\nStep 2 完成！")
    print(f"会话ID: {session_id}")
    print(f"输出文件: {output_file}")
    print("\n下一步: 运行 step3_analyze_chain.py")


if __name__ == "__main__":
    main()
