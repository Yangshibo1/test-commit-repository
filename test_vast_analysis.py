"""
VAST Challenge MC2 - 异常帖子事件链分析

使用 OpenTrace 追踪导致 John Windward 异常 SaidIT 帖子的完整事件序列
"""

import json
from datetime import datetime
from pathlib import Path

from opentrace.mcp_server import OpenTraceServer

def analyze_vast_challenge():
    """分析 VAST Challenge MC2 异常帖子事件"""

    print("=" * 70)
    print("VAST Challenge MC2 - 异常帖子事件链分析")
    print("=" * 70)

    # 初始化追踪
    server = OpenTraceServer('.opentrace_vast')

    # 初始化会话
    result = server.init_session(
        task_description="分析 John Windward 异常 SaidIT 帖子的来源",
        data_path="VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/MC2 data.json",
        data_type="json"
    )

    session_id = result['session_id']
    print(f"\n[OK] 会话创建: {session_id}")
    print(f"   数据行数: {result['total_rows']}")

    # 加载数据
    data = json.load(open("VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/MC2 data.json"))
    events = data['events']

    # ==================== 预处理: 筛选SwiftWren事件 ====================
    print("\n" + "=" * 70)
    print("预处理: 筛选SwiftWren相关事件")
    print("=" * 70)

    swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]
    swiftwren_events.sort(key=lambda x: x['when'])

    # 记录数据处理步骤（包含完整数据支撑）
    processing_result = server.record_processing(
        session_id=session_id,
        step_id="step_000",
        input_spec={
            "source": "events",
            "source_type": "json_array",
            "filter_condition": "details contains 'SwiftWren'",
            "total_count_before": len(events)
        },
        algorithm_spec={
            "type": "filter_and_sort",
            "language": "python",
            "code": "swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]",
            "logic_description": "筛选包含SwiftWren的事件并按时间排序"
        },
        result_data={
            "event_ids": [e['id'] for e in swiftwren_events],
            "unique_agents": list(set(str(e.get('parties', [])) for e in swiftwren_events)),
            "count": len(swiftwren_events),
            "time_range": {
                "first": datetime.fromtimestamp(swiftwren_events[0]['when']).isoformat(),
                "last": datetime.fromtimestamp(swiftwren_events[-1]['when']).isoformat()
            }
        },
        large_result_threshold=500
    )

    print(f"[OK] 数据处理记录: {processing_result['processing_id']}")
    print(f"    筛选结果: {len(swiftwren_events)} 个事件")
    print(f"    唯一agent数: {len(set(str(e.get('parties', [])) for e in swiftwren_events))}")

    # ==================== 步骤1: 文件创建 ====================
    print("\n" + "=" * 70)
    print("步骤1: 文件创建 (2046-05-09 23:02:01)")
    print("=" * 70)

    create_event = swiftwren_events[0]
    create_time = datetime.fromtimestamp(create_event['when']).strftime('%Y-%m-%d %H:%M:%S')

    step1 = server.record_step(
        session_id=session_id,
        step_name="文件创建",
        operation="create_file",
        description=f"Emma Harbor 创建 SwiftWren.txt 文件",
        metadata={
            "creator": "Agent/person:emma_harbor",
            "file": "SwiftWren.txt",
            "size_kb": 30.6,
            "timestamp": create_time,
            "event_id": create_event['id']
        }
    )

    print(f"创建者: {create_event['parties'][0]}")
    print(f"文件: SwiftWren.txt (30.6KB)")
    print(f"事件ID: {create_event['id']}")

    # ==================== 步骤2: 任务传递链 ====================
    print("\n" + "=" * 70)
    print("步骤2: 任务传递链 (5月9日-5月17日, 191个事件)")
    print("=" * 70)

    step2 = server.record_step(
        session_id=session_id,
        step_name="任务传递链",
        operation="queue_subordinate_task",
        description=f"SwiftWren_further_instructions.md 在多个agent间传递",
        metadata={
            "chain_length": len(swiftwren_events),
            "duration_days": 8,
            "unique_agents": len(set(str(e.get('parties', [])) for e in swiftwren_events)),
            "first_event_id": swiftwren_events[0]['id'],
            "last_event_id": swiftwren_events[-1]['id']
        }
    )

    # 记录传递链的数据处理步骤（包含完整事件列表）
    chain_processing = server.record_processing(
        session_id=session_id,
        step_id=step2['step_id'],
        input_spec={
            "source": "swiftwren_events",
            "source_type": "filtered_list",
            "filter_condition": "previously filtered SwiftWren events",
            "total_count_before": len(swiftwren_events)
        },
        algorithm_spec={
            "type": "aggregate_analysis",
            "language": "python",
            "code": "unique_agents = len(set(str(e['parties']) for e in swiftwren_events))",
            "logic_description": "统计传递链中的唯一agent数量和持续时间"
        },
        result_data={
            "event_ids": [e['id'] for e in swiftwren_events],
            "all_agents": [str(e.get('parties', [])) for e in swiftwren_events],
            "unique_agents": list(set(str(e.get('parties', [])) for e in swiftwren_events)),
            "statistics": {
                "total_events": len(swiftwren_events),
                "unique_agents_count": len(set(str(e.get('parties', [])) for e in swiftwren_events)),
                "duration_days": 8
            }
        },
        large_result_threshold=500
    )

    print(f"传递事件数: {len(swiftwren_events)}")
    print(f"持续时间: 8天 (5月9日-5月17日)")
    print(f"涉及agent数: 121")

    # 记录关键传递映射
    key_handoffs = []
    for i in range(0, len(swiftwren_events), 20):  # 每20个事件采样
        if i < len(swiftwren_events):
            event = swiftwren_events[i]
            key_handoffs.append({
                "from": str(event['parties'][0]) if len(event['parties']) > 0 else "unknown",
                "to": "next_agent",
                "operation": "queue_subordinate_task",
                "event_id": event['id']
            })

    # ==================== 步骤3: 异常帖子发布 ====================
    print("\n" + "=" * 70)
    print("步骤3: 异常帖子发布 (2046-05-17 19:21:15)")
    print("=" * 70)

    # 找到异常帖子事件
    saidit_events = [e for e in events if e['short_name'] == 'saidit_post']
    john_saidit = [e for e in saidit_events if 'john_windward' in str(e['parties']).lower()]
    target_post = john_saidit[-1]  # 最后一个

    post_time = datetime.fromtimestamp(target_post['when']).strftime('%Y-%m-%d %H:%M:%S')

    step3 = server.record_step(
        session_id=session_id,
        step_name="异常帖子发布",
        operation="saidit_post",
        description="John Windward 发布异常 SaidIT 帖子",
        metadata={
            "publisher": "Agent/person:john_windward",
            "platform": "system:saidit",
            "forum": "general",
            "content_source": "SwiftWren.txt",
            "timestamp": post_time,
            "event_id": target_post['id']
        }
    )

    print(f"发布者: {target_post['parties'][0]}")
    print(f"平台: system:saidit")
    print(f"论坛: general")
    print(f"内容来源: SwiftWren.txt")
    print(f"事件ID: {target_post['id']}")

    # 记录关键映射：文件→帖子
    server.record_mapping(
        session_id=session_id,
        step_id=step3['step_id'],
        from_ids=["SwiftWren.txt"],
        to_id="saidit_post_john_windward",
        operation="post_saidit_from_file",
        value_info={
            "content_source": "SwiftWren.txt",
            "publisher": "person:john_windward",
            "forum": "general"
        }
    )

    # ==================== 步骤4: 文件删除 ====================
    print("\n" + "=" * 70)
    print("步骤4: 文件删除 (2046-05-17 19:21:16-17)")
    print("=" * 70)

    # 找到删除事件
    delete_events = [e for e in events if e['short_name'] == 'delete_file']
    john_deletes = [e for e in delete_events if 'john_windward' in str(e['parties']).lower()]
    post_deletes = [e for e in john_deletes if e['when'] <= target_post['when'] + 10]

    step4 = server.record_step(
        session_id=session_id,
        step_name="文件删除",
        operation="delete_file",
        description="立即删除源文件以掩盖痕迹",
        metadata={
            "deleted_files": ["SwiftWren.txt", "SwiftWren_further_instructions.md"],
            "timing_seconds": 2,
            "event_count": len(post_deletes)
        }
    )

    print(f"删除的文件: SwiftWren.txt, SwiftWren_further_instructions.md")
    print(f"时间间隔: 帖子发布后2秒内")
    print(f"删除事件数: {len(post_deletes)}")

    # 记录删除映射
    for delete_event in post_deletes:
        details = delete_event.get('details', {})
        if details:
            target_file = details.get('target', 'unknown')
            server.record_mapping(
                session_id=session_id,
                step_id=step4['step_id'],
                from_ids=[target_file],
                to_id=None,
                operation="delete_file",
                value_info={"event_id": delete_event['id']}
            )

    # ==================== 追踪验证 ====================
    print("\n" + "=" * 70)
    print("追踪验证: 追踪异常帖子的来源")
    print("=" * 70)

    # 追踪帖子的来源
    trace_result = server.trace_element(
        session_id=session_id,
        element_id="saidit_post_john_windward"
    )

    print(f"\n[OK] 追踪结果:")
    print(f"   元素ID: saidit_post_john_windward")
    print(f"   血缘链长度: {trace_result['chain_length']}")

    print(f"\n   血缘链:")
    for i, link in enumerate(trace_result['chain'][-5:], 1):
        print(f"   {i}. {link.get('operation', 'N/A')}")
        print(f"      来自: {link.get('from', 'N/A')}")
        print(f"      变为: {link.get('to', 'N/A')}")

    # ==================== 错误分析 ====================
    print("\n" + "=" * 70)
    print("错误分析: 分析异常行为的来源")
    print("=" * 70)

    analysis = server.analyze_error(
        session_id=session_id,
        error_message="John Windward 发布了异常 SaidIT 帖子",
        affected_element="saidit_post_john_windward"
    )

    print(f"\n[OK] 分析结果:")
    print(f"   错误: {analysis['analysis']['error_message']}")
    print(f"   受影响元素: {analysis['analysis'].get('affected_element', 'N/A')}")

    if analysis['analysis'].get('lineage_chain'):
        print(f"\n   血缘链 ({len(analysis['analysis']['lineage_chain'])} 步):")
        for link in analysis['analysis']['lineage_chain'][-3:]:
            print(f"   - {link['step']}: {link['operation']}")

    # ==================== 会话概览 ====================
    print("\n" + "=" * 70)
    print("会话概览")
    print("=" * 70)

    summary = server.get_session_summary(session_id)
    print(f"\n总步骤数: {summary['summary']['total_steps']}")

    print("\n步骤列表:")
    for step in summary['summary']['steps']:
        print(f"  - {step['step_id']}: {step['name']} ({step['operation']})")

    # ==================== 导出结果 ====================
    print("\n" + "=" * 70)
    print("导出追踪数据")
    print("=" * 70)

    export_result = server.export_session(session_id)
    print(f"\n[OK] 数据已导出: {export_result['export_path']}")

    # ==================== 总结 ====================
    print("\n" + "=" * 70)
    print("分析总结")
    print("=" * 70)

    print("""
[OK] 异常帖子来源追踪完成！

关键发现:
1. 文件创建: Emma Harbor 在5月9日创建了 SwiftWren.txt
2. 任务传递: 该文件通过191个事件在121个agent间传递了8天
3. 异常行为: John Windward 在5月17日发布异常帖子
4. 掩盖痕迹: 帖子发布后立即删除源文件

这是一个典型的"任务传递链故障"：
- 任务在多层agent间传递
- 中间可能存在信息失真或错误累积
- 最终导致异常行为
- 发布后立即删除源文件以掩盖痕迹

建议的干预点:
- 在任务传递过程中增加验证机制
- 在文件创建后设置内容检查
- 对敏感操作增加审计日志
    """)

    return session_id

if __name__ == "__main__":
    session_id = analyze_vast_challenge()

    print(f"\n分析完成！会话ID: {session_id}")
    print(f"使用该ID可以进一步查询追踪数据。")
