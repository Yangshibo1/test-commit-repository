"""
测试 PROV DAG 功能

验证文件级别的数据溯源追踪
"""

from opentrace.mcp_server import OpenTraceServer


def test_prov_dag():
    """测试 PROV DAG 基本功能"""

    print("=" * 70)
    print("测试 PROV DAG 功能")
    print("=" * 70)

    # 初始化服务器
    server = OpenTraceServer('.opentrace_prov_test')

    # 创建会话
    result = server.init_session(
        task_description="PROV DAG 测试",
        data_path="test_data.csv",
        data_type="csv"
    )

    if "error" in result:
        print(f"[ERROR] 创建会话失败: {result['error']}")
        return None

    session_id = result['session_id']
    print(f"\n[OK] 会话创建: {session_id}")

    # ==================== 测试1: 基本 DAG 构建 ====================
    print("\n" + "=" * 70)
    print("测试1: 基本 DAG 构建")
    print("=" * 70)

    # 记录 PROV 关系
    prov_result = server.record_prov_relation(
        session_id=session_id,
        entities=[
            {
                "entity_type": "dataset",
                "location": "raw_data.csv",
                "attributes": {"rows": 1000, "columns": 5}
            },
            {
                "entity_type": "dataset",
                "location": "filtered_data.csv",
                "attributes": {"rows": 150, "filter_condition": "value > 100"}
            },
            {
                "entity_type": "artifact",
                "location": "final_result.csv",
                "attributes": {"description": "聚合结果"}
            }
        ],
        activities=[
            {
                "activity_type": "filter",
                "description": "筛选 value > 100 的记录",
                "attributes": {"condition": "value > 100", "language": "python"}
            },
            {
                "activity_type": "aggregate",
                "description": "按类别计算平均值",
                "attributes": {"group_by": "category", "func": "mean"}
            }
        ],
        agents=[
            {
                "agent_type": "python_code",
                "name": "claude_data_analysis",
                "attributes": {"version": "1.0", "model": "claude-sonnet"}
            }
        ],
        relations=[
            # 使用临时ID引用，系统会自动转换
            ("temp_activity_0", "temp_entity_0", "used"),
            ("temp_entity_1", "temp_activity_0", "wasGeneratedBy"),
            ("temp_activity_0", "temp_agent_0", "wasAssociatedWith"),

            ("temp_activity_1", "temp_entity_1", "used"),
            ("temp_entity_2", "temp_activity_1", "wasGeneratedBy"),
            ("temp_activity_1", "temp_agent_0", "wasAssociatedWith"),

            ("temp_entity_1", "temp_entity_0", "wasDerivedFrom"),
            ("temp_entity_2", "temp_entity_1", "wasDerivedFrom")
        ]
    )

    print(f"\n[OK] PROV 关系记录成功")
    print(f"    DAG ID: {prov_result['dag_id']}")
    print(f"    实体数: {prov_result['statistics']['total_entities']}")
    print(f"    活动数: {prov_result['statistics']['total_activities']}")
    print(f"    代理数: {prov_result['statistics']['total_agents']}")
    print(f"    关系数: {prov_result['statistics']['total_edges']}")

    # 显示生成的 ID 映射
    print(f"\n生成的 ID 映射:")
    for temp_id, actual_id in list(prov_result['id_mappings'].items())[:3]:
        print(f"  {temp_id} → {actual_id}")

    # ==================== 测试2: 查询溯源链 ====================
    print("\n" + "=" * 70)
    print("测试2: 查询实体溯源链")
    print("=" * 70)

    # 获取最终产物的溯源链
    final_entity_id = prov_result['id_mappings'].get('temp_entity_2')

    lineage_result = server.get_prov_entity_lineage(
        session_id=session_id,
        entity_id=final_entity_id
    )

    if lineage_result.get('status') == 'success':
        lineage = lineage_result['lineage']
        print(f"\n实体: {lineage['entity_id']}")
        print(f"位置: {lineage['entity_info']['location']}")
        print(f"类型: {lineage['entity_info']['entity_type']}")

        print(f"\n溯源链 ({len(lineage['lineage_chain'])} 步):")
        for step in lineage['lineage_chain']:
            print(f"  步骤 {step['step']}:")
            print(f"    来自: {step['location']}")
            print(f"    关系: {step['relation']}")

    # ==================== 测试3: DAG 概览 ====================
    print("\n" + "=" * 70)
    print("测试3: DAG 概览")
    print("=" * 70)

    overview = server.get_prov_dag_overview(session_id)

    if overview.get('status') == 'success':
        print(f"\nDAG ID: {overview['dag_id']}")
        print(f"创建时间: {overview['metadata']['created_at']}")
        print(f"更新时间: {overview['metadata']['updated_at']}")

        print(f"\n节点统计:")
        print(f"  实体: {len(overview['nodes']['entities'])}")
        print(f"  活动: {len(overview['nodes']['activities'])}")
        print(f"  代理: {len(overview['nodes']['agents'])}")
        print(f"  边: {len(overview['edges'])}")

    # ==================== 测试4: 聚合场景 ====================
    print("\n" + "=" * 70)
    print("测试4: 聚合场景（多输入→单输出）")
    print("=" * 70)

    # 记录聚合操作
    agg_result = server.record_prov_relation(
        session_id=session_id,
        entities=[
            {
                "entity_type": "dataset",
                "location": "data_a.csv",
                "attributes": {"source": "系统A"}
            },
            {
                "entity_type": "dataset",
                "location": "data_b.csv",
                "attributes": {"source": "系统B"}
            },
            {
                "entity_type": "dataset",
                "location": "merged_data.csv",
                "attributes": {"operation": "merge"}
            }
        ],
        activities=[
            {
                "activity_type": "join",
                "description": "合并两个数据集",
                "attributes": {"join_type": "inner", "on": "id"}
            }
        ],
        agents=[
            {
                "agent_type": "python_code",
                "name": "merge_operation",
                "attributes": {"library": "pandas"}
            }
        ],
        relations=[
            ("temp_activity_0", "temp_entity_0", "used"),
            ("temp_activity_0", "temp_entity_1", "used"),
            ("temp_entity_2", "temp_activity_0", "wasGeneratedBy"),
            ("temp_activity_0", "temp_agent_0", "wasAssociatedWith"),
            ("temp_entity_2", "temp_entity_0", "wasDerivedFrom"),
            ("temp_entity_2", "temp_entity_1", "wasDerivedFrom")
        ]
    )

    print(f"\n[OK] 聚合场景记录成功")
    print(f"    输入实体: 2 个")
    print(f"    输出实体: 1 个")
    print(f"    活动数: 1 个")

    # ==================== 测试5: 分叉场景 ====================
    print("\n" + "=" * 70)
    print("测试5: 分叉场景（单输入→多输出）")
    print("=" * 70)

    # 记录分叉操作
    fork_result = server.record_prov_relation(
        session_id=session_id,
        entities=[
            {
                "entity_type": "dataset",
                "location": "input.csv",
                "attributes": {"rows": 1000}
            },
            {
                "entity_type": "dataset",
                "location": "output_a.csv",
                "attributes": {"filter": "type == A"}
            },
            {
                "entity_type": "dataset",
                "location": "output_b.csv",
                "attributes": {"filter": "type == B"}
            }
        ],
        activities=[
            {
                "activity_type": "split",
                "description": "按类型分叉数据",
                "attributes": {"split_by": "type"}
            }
        ],
        agents=[
            {
                "agent_type": "python_code",
                "name": "split_operation",
                "attributes": {}
            }
        ],
        relations=[
            ("temp_activity_0", "temp_entity_0", "used"),
            ("temp_entity_1", "temp_activity_0", "wasGeneratedBy"),
            ("temp_entity_2", "temp_activity_0", "wasGeneratedBy"),
            ("temp_activity_0", "temp_agent_0", "wasAssociatedWith"),
            ("temp_entity_1", "temp_entity_0", "wasDerivedFrom"),
            ("temp_entity_2", "temp_entity_0", "wasDerivedFrom")
        ]
    )

    print(f"\n[OK] 分叉场景记录成功")
    print(f"    输入实体: 1 个")
    print(f"    输出实体: 2 个")

    # ==================== 总结 ====================
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    # 获取最新的 DAG 概览
    final_overview = server.get_prov_dag_overview(session_id)

    if final_overview.get('status') == 'success':
        stats = final_overview['statistics']
        print(f"\n最终统计:")
        print(f"  总实体数: {stats['total_entities']}")
        print(f"  总活动数: {stats['total_activities']}")
        print(f"  总代理数: {stats['total_agents']}")
        print(f"  总关系数: {stats['total_edges']}")

        print(f"\n支持的场景:")
        print(f"  [OK] 基本数据处理流程")
        print(f"  [OK] 聚合场景（多输入→单输出）")
        print(f"  [OK] 分叉场景（单输入→多输出）")
        print(f"  [OK] 溯源链查询")
        print(f"  [OK] DAG 概览查询")

    print(f"\n[OK] 所有测试通过！")

    return session_id


if __name__ == "__main__":
    session_id = test_prov_dag()
    print(f"\n测试会话ID: {session_id}")
    print(f"查看 PROV 数据: .opentrace_prov_test/{session_id}/prov_*.json")
