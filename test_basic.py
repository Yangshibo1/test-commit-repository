"""
基础测试脚本

测试 OpenTrace 核心功能
"""

import json
from pathlib import Path
from opentrace.tracker import LineageTracker
from opentrace.mcp_server import OpenTraceServer


def create_test_data():
    """创建测试数据"""
    test_data = [
        {
            "id": "user_001",
            "name": "Alice",
            "age": 25,
            "orders": [
                {"id": "order_A", "amount": 100},
                {"id": "order_B", "amount": 200}
            ]
        },
        {
            "id": "user_002",
            "name": "Bob",
            "age": None,  # 缺失值
            "orders": [
                {"id": "order_C", "amount": 150}
            ]
        },
        {
            "id": "user_003",
            "name": "Charlie",
            "age": 35,
            "orders": []
        }
    ]

    test_file = Path("test_data.json")
    test_file.write_text(json.dumps(test_data, indent=2, ensure_ascii=False))
    return test_file


def test_basic_workflow():
    """测试基本工作流"""

    print("=" * 60)
    print("OpenTrace 基础测试")
    print("=" * 60)

    # 创建测试数据
    print("\n1. 创建测试数据...")
    test_file = create_test_data()
    print(f"   测试数据: {test_file}")

    # 初始化追踪器
    print("\n2. 初始化追踪器...")
    tracker = LineageTracker("test_session")
    result = tracker.init_from_json(str(test_file))
    print(f"   会话ID: {result['session_id']}")
    print(f"   数据行数: {result['total_rows']}")

    # 记录第一步：数据清洗
    print("\n3. 记录步骤1: 数据清洗...")
    step_id_1 = tracker.record_step(
        step_name="数据清洗",
        operation="fillna",
        description="填充缺失的age字段"
    )
    print(f"   步骤ID: {step_id_1}")

    # 记录映射
    tracker.record_mapping(
        step_id=step_id_1,
        from_ids=["root[1].age"],
        to_id="root[1].age_cleaned",
        operation="fillna(0)",
        value_info={
            "root[1].age": {"old": None, "new": 0}
        }
    )
    print("   映射已记录: root[1].age → root[1].age_cleaned")

    # 记录第二步：计算总金额
    print("\n4. 记录步骤2: 计算总金额...")
    step_id_2 = tracker.record_step(
        step_name="计算总金额",
        operation="sum",
        description="计算每个用户的订单总金额"
    )

    tracker.record_mapping(
        step_id=step_id_2,
        from_ids=["root[0].orders[0].amount", "root[0].orders[1].amount"],
        to_id="root[0].total_amount",
        operation="sum(orders[*].amount)",
        value_info={
            "root[0].orders[0].amount": 100,
            "root[0].orders[1].amount": 200,
            "root[0].total_amount": 300
        }
    )
    print(f"   步骤ID: {step_id_2}")
    print("   映射已记录: 订单金额 → 总金额")

    # 测试追踪功能
    print("\n5. 测试元素追踪...")
    chain = tracker.trace_element("root[0].total_amount")
    print(f"   血缘链长度: {len(chain)}")
    for link in chain:
        print(f"   - {link['step']}: {link['operation']}")

    # 测试错误分析
    print("\n6. 测试错误分析...")
    analysis = tracker.analyze_error(
        error_message="发现 NaN 值",
        affected_element="root[0].total_amount"
    )
    print(f"   可能的错误来源数量: {len(analysis['possible_sources'])}")
    for source in analysis['possible_sources']:
        print(f"   - {source['step']}: {source['reason']}")

    # 获取会话概览
    print("\n7. 获取会话概览...")
    summary = tracker.get_session_summary()
    print(f"   总步骤数: {summary['total_steps']}")
    for step in summary['steps']:
        print(f"   - {step['step_id']}: {step['name']}")

    # 导出会话
    print("\n8. 导出会话...")
    export_path = tracker.export_session()
    print(f"   导出路径: {export_path}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

    # 清理
    test_file.unlink()


def test_server():
    """测试 OpenTrace 服务器"""

    print("\n" + "=" * 60)
    print("测试 OpenTrace 服务器")
    print("=" * 60)

    # 创建测试数据
    test_file = create_test_data()

    # 初始化服务器
    print("\n1. 初始化服务器...")
    server = OpenTraceServer(".opentrace_test")

    # 测试直接调用接口
    print("\n2. 测试直接调用...")

    result = server.init_session(
        task_description="测试任务",
        data_path=str(test_file),
        data_type="json"
    )
    print(f"   会话ID: {result['session_id']}")
    session_id = result['session_id']

    step_result = server.record_step(
        session_id,
        "测试步骤",
        "test_operation",
        "这是一个测试步骤"
    )
    print(f"   步骤ID: {step_result['step_id']}")

    summary_result = server.get_session_summary(session_id)
    summary = summary_result['summary']
    print(f"   会话概览: {summary['total_steps']} 个步骤")

    print("\n" + "=" * 60)
    print("服务器测试完成！")
    print("=" * 60)

    # 清理
    test_file.unlink()


if __name__ == "__main__":
    test_basic_workflow()
    test_server()
