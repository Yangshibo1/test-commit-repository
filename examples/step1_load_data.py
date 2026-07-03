"""
Step 1: 加载MC2数据

这是VAST Challenge 2026 MC2分析的第一步。
加载数据并保存为中间文件，然后记录到OpenTrace。

预期输出: step1_loaded.json
下一步: 基于此数据进行 SaidIT 相关事件过滤
"""

import json
import sys
from pathlib import Path

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from opentrace.mcp_server import get_server


def main():
    print("=" * 60)
    print("Step 1: 加载MC2数据")
    print("=" * 60)

    # 获取服务器实例
    server = get_server()
    session_id = None

    # 初始化会话（如果是首次运行）
    script_dir = Path(__file__).parent
    data_path = str(script_dir / "MC2 data.json")
    org_chart_path = str(script_dir / "org_chart.json")

    # 检查是否已有会话
    sessions = server.list_sessions()
    if sessions:
        # 使用最新会话
        session_id = sessions[0]['session_id']
        print(f"使用现有会话: {session_id}")
    else:
        # 创建新会话
        result = server.init_session(
            task_description="VAST Challenge 2026 MC2 - 追踪异常SaidIT帖子发布",
            data_path=data_path,
            data_type="json"
        )
        session_id = result["session_id"]
        print(f"创建新会话: {session_id}")

    # 加载数据
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    with open(org_chart_path, 'r', encoding='utf-8') as f:
        org_chart = json.load(f)

    events = data.get('events', [])
    print(f"总事件数: {len(events):,}")

    # 保存中间文件
    work_dir = Path(server.base_dir) / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    output_file = work_dir / "step1_loaded.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'events': events,
            'org_chart': org_chart,
            'metadata': {
                'total_events': len(events),
                'org_nodes': len(org_chart.get('nodes', []))
            }
        }, f, ensure_ascii=False, indent=2)

    print(f"已保存到: {output_file}")

    # 记录PROV关系
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "raw_data", "entity_type": "dataset", "location": data_path, "attributes": {"type": "MC2_data.json"}},
            {"id": "org_input", "entity_type": "dataset", "location": org_chart_path, "attributes": {"type": "org_chart.json"}},
            {"id": "loaded_data", "entity_type": "dataset", "location": str(output_file), "attributes": {"total_events": len(events)}}
        ],
        activities=[
            {"id": "load_activity", "activity_type": "load", "description": "加载MC2数据和组织架构", "attributes": {}}
        ],
        agents=[
            {"id": "load_agent", "agent_type": "python_code", "name": "step1_load_data", "attributes": {}}
        ],
        relations=[
            ("load_activity", "raw_data", "used"),
            ("load_activity", "org_input", "used"),
            ("loaded_data", "load_activity", "wasGeneratedBy"),
            ("load_activity", "load_agent", "wasAssociatedWith"),
            ("loaded_data", "raw_data", "wasDerivedFrom")
        ]
    )

    # 记录步骤详情（必填）
    server.record_step_details(
        session_id=session_id,
        step_id="step_1",
        step_name="load_data",
        description="加载MC2事件数据和组织架构，保存为中间文件。本步完成后需要读取输出并决定下一步分析方向。",
        code_generated=[
            "data = json.load(open('MC2 data.json'))",
            "org_chart = json.load(open('org_chart.json'))"
        ],
        code_files=[__file__],
        commands_run=[f"python {__file__}"],
        input_files=[data_path, org_chart_path],
        output_files=[str(output_file)],
        parameters={
            "next_step": "过滤SaidIT相关事件",
            "decision_required": "需要读取step1_loaded.json，观察数据规模和结构，然后决定如何过滤"
        }
    )

    print("\nStep 1 完成！")
    print(f"会话ID: {session_id}")
    print(f"输出文件: {output_file}")
    print("\n下一步: 运行 step2_filter_saidit.py")


if __name__ == "__main__":
    main()
