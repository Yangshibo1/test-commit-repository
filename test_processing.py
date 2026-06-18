"""
测试 record_processing 功能

验证数据处理步骤的完整记录（input/algorithm/result 三要素）
"""

import json
from pathlib import Path
from opentrace.mcp_server import OpenTraceServer


def test_processing_record():
    """测试数据处理记录功能"""

    print("=" * 70)
    print("测试 record_processing 功能")
    print("=" * 70)

    # 创建测试数据
    test_data = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
        {"id": 3, "name": "Charlie"}
    ]
    test_file = Path("test_data.json")
    test_file.write_text(json.dumps(test_data, ensure_ascii=False))

    # 初始化服务器
    server = OpenTraceServer('.opentrace_processing_test')

    # 创建测试会话
    result = server.init_session(
        task_description="测试数据处理记录",
        data_path=str(test_file),
        data_type="json"
    )

    if "error" in result:
        print(f"[ERROR] 初始化失败: {result['error']}")
        return None

    session_id = result['session_id']
    print(f"\n[OK] 会话创建: {session_id}")

    # 创建测试步骤
    step_result = server.record_step(
        session_id=session_id,
        step_name="筛选SwiftWren事件",
        operation="filter",
        description="从事件中筛选包含SwiftWren的事件"
    )

    step_id = step_result['step_id']
    print(f"[OK] 步骤创建: {step_id}")

    # ==================== 测试1: 小结果集（内嵌） ====================
    print("\n" + "=" * 70)
    print("测试1: 小结果集（内嵌存储）")
    print("=" * 70)

    # 模拟小结果集
    small_result = {
        "event_ids": [21202, 34501, 45678],
        "agents": ["Agent/person:emma_harbor", "Agent/person:john_windward"],
        "count": 3
    }

    proc_result_1 = server.record_processing(
        session_id=session_id,
        step_id=step_id,
        input_spec={
            "source": "events",
            "source_type": "json_array",
            "filter_condition": "details contains 'SwiftWren'",
            "total_count_before": 185147
        },
        algorithm_spec={
            "type": "filter_and_aggregate",
            "language": "python",
            "code": "swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]",
            "logic_description": "筛选包含SwiftWren的事件并统计"
        },
        result_data=small_result,
        large_result_threshold=1000
    )

    processing_id_1 = proc_result_1['processing_id']
    print(f"[OK] 处理记录创建: {processing_id_1}")
    print(f"    输入来源: events (185147 项)")
    print(f"    算法类型: filter_and_aggregate")
    print(f"    结果项数: {small_result['count']}")

    # ==================== 测试2: 大结果集（外存） ====================
    print("\n" + "=" * 70)
    print("测试2: 大结果集（外存文件存储）")
    print("=" * 70)

    # 创建另一个步骤
    step_result_2 = server.record_step(
        session_id=session_id,
        step_name="分析所有事件",
        operation="aggregate",
        description="分析所有事件的模式"
    )

    # 模拟大结果集
    large_result = {
        "event_ids": list(range(10000, 20000)),  # 10000个ID
        "agents": [f"Agent_{i}" for i in range(500)],  # 500个agent
        "patterns": ["pattern_1"] * 1000  # 1000个模式
    }

    proc_result_2 = server.record_processing(
        session_id=session_id,
        step_id=step_result_2['step_id'],
        input_spec={
            "source": "events",
            "source_type": "json_array",
            "filter_condition": "all events",
            "total_count_before": 185147
        },
        algorithm_spec={
            "type": "pattern_analysis",
            "language": "python",
            "code": "patterns = analyze_event_patterns(events)",
            "logic_description": "分析事件中的模式"
        },
        result_data=large_result,
        large_result_threshold=1000  # 超过1000项就外存
    )

    processing_id_2 = proc_result_2['processing_id']
    print(f"[OK] 处理记录创建: {processing_id_2}")
    print(f"    结果项数: 11500（超过阈值，自动外存）")

    # ==================== 验证: 查询处理记录 ====================
    print("\n" + "=" * 70)
    print("验证: 查询处理记录详情")
    print("=" * 70)

    # 查询小结果集的处理记录
    detail_1 = server.get_processing_detail(session_id, processing_id_1)

    print(f"\n处理记录 1 ({processing_id_1}):")
    print(f"  输入来源: {detail_1['detail']['input']['source']}")
    print(f"  筛选条件: {detail_1['detail']['input']['filter_condition']}")
    print(f"  算法类型: {detail_1['detail']['algorithm']['type']}")
    print(f"  代码片段: {detail_1['detail']['algorithm']['code'][:50]}...")
    print(f"  结果格式: {detail_1['detail']['result']['format']}")
    print(f"  结果数据: {detail_1['detail']['result']['data']}")

    # 查询大结果集的处理记录
    detail_2 = server.get_processing_detail(session_id, processing_id_2)

    print(f"\n处理记录 2 ({processing_id_2}):")
    print(f"  输入来源: {detail_2['detail']['input']['source']}")
    print(f"  算法类型: {detail_2['detail']['algorithm']['type']}")
    print(f"  结果格式: {detail_2['detail']['result']['format']}")
    print(f"  外存文件: {detail_2['detail']['result']['file']}")
    print(f"  加载的数据项: {len(detail_2['detail']['result']['data']['event_ids'])} 个event_ids")

    # ==================== 验证: 列出处理记录 ====================
    print("\n" + "=" * 70)
    print("验证: 列出所有处理记录")
    print("=" * 70)

    list_result = server.list_processings(session_id)

    print(f"\n总共 {list_result.get('count', len(list_result.get('processings', [])))} 个处理记录:")
    for proc in list_result['processings']:
        print(f"  - {proc['processing_id']}")
        print(f"    步骤: {proc['step_id']}")
        print(f"    算法类型: {proc['algorithm_type']}")
        print(f"    结果格式: {proc['result_format']}")
        print(f"    数据项数: {proc['item_count']}")

    # ==================== 验证: 导出会话 ====================
    print("\n" + "=" * 70)
    print("验证: 导出会话")
    print("=" * 70)

    export_result = server.export_session(session_id)
    export_path = export_result['export_path']

    print(f"\n[OK] 会话已导出: {export_path}")

    # 检查导出文件
    export_data = json.loads(Path(export_path).read_text())
    print(f"  导出步骤数: {export_data['metadata']['total_steps']}")

    print("\n" + "=" * 70)
    print("[OK] 所有测试通过！")
    print("=" * 70)

    return session_id


if __name__ == "__main__":
    session_id = test_processing_record()
    if session_id:
        print(f"\n测试会话ID: {session_id}")
        print(f"查看处理记录文件: .opentrace_processing_test/{session_id}/processing_*.json")

    # 清理测试文件
    test_file = Path("test_data.json")
    if test_file.exists():
        test_file.unlink()
