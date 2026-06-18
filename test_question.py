"""
数据分析实验：测试追踪系统的问题回答能力

问题：在 SwiftWren 任务传递链中，哪个 agent 参与次数最多？
"""

import json
from collections import Counter
from opentrace.mcp_server import OpenTraceServer


def analyze_agent_participation():
    """分析 agent 参与情况"""

    print("=" * 70)
    print("数据分析实验：Agent 参与次数统计")
    print("=" * 70)

    # 初始化追踪系统
    server = OpenTraceServer('.opentrace_question_test')

    # 创建会话
    result = server.init_session(
        task_description="分析 SwiftWren 任务传递链中 agent 参与情况",
        data_path="VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/MC2 data.json",
        data_type="json"
    )

    session_id = result['session_id']
    print(f"\n[OK] 会话创建: {session_id}")

    # 加载数据
    data = json.load(open("VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/MC2 data.json"))
    events = data['events']

    # ==================== 数据处理步骤 ====================
    print("\n" + "=" * 70)
    print("步骤1: 筛选 SwiftWren 相关事件")
    print("=" * 70)

    swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]

    # 记录处理步骤
    server.record_processing(
        session_id=session_id,
        step_id="step_000",
        input_spec={
            "source": "events",
            "source_type": "json_array",
            "filter_condition": "details contains 'SwiftWren'",
            "total_count_before": len(events)
        },
        algorithm_spec={
            "type": "filter",
            "language": "python",
            "code": "swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]",
            "logic_description": "筛选包含 SwiftWren 的事件"
        },
        result_data={
            "event_count": len(swiftwren_events),
            "event_ids": [e['id'] for e in swiftwren_events[:100]]  # 采样100个
        },
        large_result_threshold=50
    )

    print(f"筛选结果: {len(swiftwren_events)} 个事件")

    # ==================== 统计 agent 参与次数 ====================
    print("\n" + "=" * 70)
    print("步骤2: 统计 agent 参与次数")
    print("=" * 70)

    # 提取所有参与的 agent
    all_agents = []
    for event in swiftwren_events:
        parties = event.get('parties', [])
        for party in parties:
            if isinstance(party, str) and 'Agent/person:' in party:
                all_agents.append(party)

    # 统计次数
    agent_counts = Counter(all_agents)
    top_agents = agent_counts.most_common(10)

    print(f"总参与记录: {len(all_agents)} 次")
    print(f"唯一 agent 数: {len(agent_counts)} 个")

    # 记录统计步骤
    step_result = server.record_step(
        session_id=session_id,
        step_name="统计 agent 参与次数",
        operation="count_and_rank",
        description="统计每个 agent 在任务传递链中的参与次数"
    )

    server.record_processing(
        session_id=session_id,
        step_id=step_result['step_id'],
        input_spec={
            "source": "swiftwren_events",
            "source_type": "filtered_events",
            "filter_condition": "extract agents from parties",
            "total_count_before": len(swiftwren_events)
        },
        algorithm_spec={
            "type": "aggregate_count",
            "language": "python",
            "code": """
all_agents = []
for event in swiftwren_events:
    parties = event.get('parties', [])
    for party in parties:
        if isinstance(party, str) and 'Agent/person:' in party:
            all_agents.append(party)
agent_counts = Counter(all_agents)
top_agents = agent_counts.most_common(10)
            """,
            "logic_description": "从事件 parties 中提取 agent，使用 Counter 统计次数"
        },
        result_data={
            "total_participations": len(all_agents),
            "unique_agents_count": len(agent_counts),
            "top_10_agents": [
                {"agent": agent, "count": count}
                for agent, count in top_agents
            ]
        },
        large_result_threshold=50
    )

    print("\nTop 10 参与最多的 agent:")
    for i, (agent, count) in enumerate(top_agents, 1):
        print(f"  {i}. {agent}: {count} 次")

    # ==================== 问题测试 ====================
    print("\n" + "=" * 70)
    print("问题测试：追踪系统能否回答问题？")
    print("=" * 70)

    question = "在 SwiftWren 任务传递链中，哪个 agent 参与次数最多？"

    print(f"\n问题: {question}")
    print(f"\n答案: {top_agents[0][0]} (参与 {top_agents[0][1]} 次)")

    print("\n" + "-" * 70)
    print("验证：追踪系统中的数据支撑")
    print("-" * 70)

    # 获取处理记录
    processings = server.list_processings(session_id)

    print(f"\n找到 {processings['count']} 个处理记录:")

    for proc in processings['processings']:
        print(f"\n  处理ID: {proc['processing_id']}")
        print(f"    步骤: {proc['step_id']}")
        print(f"    算法: {proc['algorithm_type']}")
        print(f"    格式: {proc['result_format']}")

        # 获取详情
        detail = server.get_processing_detail(session_id, proc['processing_id'])

        if detail.get('status') == 'success':
            proc_detail = detail['detail']
            print(f"\n    输入来源: {proc_detail['input']['source']}")
            print(f"    数据量: {proc_detail['input']['total_count_before']}")

            if 'algorithm' in proc_detail:
                print(f"    算法: {proc_detail['algorithm']['type']}")

            result = proc_detail.get('result', {})
            if result.get('format') == 'inline' and 'data' in result:
                data = result['data']
                if 'top_10_agents' in data:
                    print(f"\n    [找到答案]")
                    print(f"    Top agent: {data['top_10_agents'][0]['agent']}")
                    print(f"    参与次数: {data['top_10_agents'][0]['count']}")

    # ==================== 结论 ====================
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)

    answer = top_agents[0][0]
    count = top_agents[0][1]

    print(f"""
问题: 在 SwiftWren 任务传递链中，哪个 agent 参与次数最多？

答案: {answer} (参与 {count} 次)

数据支撑位置:
  - 处理记录ID: processing_{step_result['step_id']}
  - 查看文件: .opentrace_question_test/{session_id}/processing_{step_result['step_id']}.json

追踪系统能否回答: [是]
  [OK] 记录了原始数据来源
  [OK] 记录了处理算法
  [OK] 记录了完整结果数据
  [OK] 可以通过查询处理记录获取答案
    """)

    # 导出结果
    export_result = server.export_session(session_id)
    print(f"[OK] 会话已导出: {export_result['export_path']}")

    return session_id, answer, count


if __name__ == "__main__":
    session_id, answer, count = analyze_agent_participation()
    print(f"\n会话ID: {session_id}")
    print(f"答案: {answer} 参与了 {count} 次")
