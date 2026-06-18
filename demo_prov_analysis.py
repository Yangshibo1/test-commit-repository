"""
演示：Claude Code 进行数据分析并调用 PROV MCP 服务

模拟完整的数据分析流程，包括 PROV 关系记录
"""

import pandas as pd
from opentrace.mcp_server import OpenTraceServer


def data_analysis_with_prov():
    """数据分析 + PROV 记录演示"""

    print("=" * 70)
    print("演示：数据分析 + PROV 追踪")
    print("=" * 70)

    # ==================== 步骤1：初始化追踪系统 ====================
    print("\n步骤1：初始化 OpenTrace 追踪系统")
    print("-" * 70)

    server = OpenTraceServer('.opentrace_demo')
    session = server.init_session(
        task_description="销售数据分析",
        data_path="sales_data.csv",
        data_type="csv"
    )

    if "error" in session:
        print(f"[ERROR] 创建会话失败: {session['error']}")
        return None

    session_id = session['session_id']
    print(f"[OK] 会话创建: {session_id}")

    # ==================== 步骤2：创建模拟数据 ====================
    print("\n步骤2：准备分析数据")
    print("-" * 70)

    # 创建模拟销售数据
    sales_data = pd.DataFrame({
        'date': pd.date_range('2026-01-01', periods=100),
        'product': ['A'] * 50 + ['B'] * 30 + ['C'] * 20,
        'region': ['North'] * 40 + ['South'] * 35 + ['East'] * 25,
        'sales': [100 + i * 10 + (i % 3) * 50 for i in range(100)],
        'quantity': [10 + i % 20 for i in range(100)]
    })

    # 保存原始数据
    sales_data.to_csv('sales_data.csv', index=False)
    print(f"[OK] 原始数据: sales_data.csv ({len(sales_data)} 行)")
    print(f"   列: {list(sales_data.columns)}")
    print(f"   前3行预览:")
    print(sales_data.head(3).to_string(index=False))

    # ==================== 步骤3：数据分析 - 筛选高销量产品 ====================
    print("\n步骤3：分析操作1 - 筛选高销量产品")
    print("-" * 70)

    high_sales_data = sales_data[sales_data['sales'] > 300]
    high_sales_data.to_csv('high_sales_data.csv', index=False)

    print(f"[OK] 筛选完成: high_sales_data.csv ({len(high_sales_data)} 行)")
    print(f"   筛选条件: sales > 300")

    # 记录这一步的 PROV 关系
    prov_step1 = server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"entity_type": "dataset", "location": "sales_data.csv",
             "attributes": {"rows": len(sales_data), "operation": "原始数据"}},
            {"entity_type": "dataset", "location": "high_sales_data.csv",
             "attributes": {"rows": len(high_sales_data), "filter": "sales > 300"}}
        ],
        activities=[
            {"activity_type": "filter", "description": "筛选销量大于300的记录",
             "attributes": {"condition": "sales > 300", "language": "python_pandas"}}
        ],
        agents=[
            {"agent_type": "python_code", "name": "claude_analysis_step1",
             "attributes": {"step": 1, "description": "高销量筛选"}}
        ],
        relations=[
            ("temp_activity_0", "temp_entity_0", "used"),
            ("temp_entity_1", "temp_activity_0", "wasGeneratedBy"),
            ("temp_activity_0", "temp_agent_0", "wasAssociatedWith"),
            ("temp_entity_1", "temp_entity_0", "wasDerivedFrom")
        ]
    )

    print(f"[OK] PROV 关系已记录 (步骤1)")
    print(f"   实体ID: {list(prov_step1['id_mappings'].values())[:2]}")

    # ==================== 步骤4：数据分析 - 按产品聚合 ====================
    print("\n步骤4：分析操作2 - 按产品聚合统计")
    print("-" * 70)

    product_stats = high_sales_data.groupby('product').agg({
        'sales': ['sum', 'mean', 'count'],
        'quantity': 'sum'
    }).round(2)

    product_stats.to_csv('product_stats.csv')
    print(f"[OK] 聚合完成: product_stats.csv")
    print(f"   聚合结果:")
    print(product_stats.to_string())

    # 记录这一步的 PROV 关系
    prov_step2 = server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"entity_type": "dataset", "location": "high_sales_data.csv",
             "attributes": {"rows": len(high_sales_data)}},
            {"entity_type": "artifact", "location": "product_stats.csv",
             "attributes": {"shape": product_stats.shape, "operation": "聚合统计"}}
        ],
        activities=[
            {"activity_type": "aggregate", "description": "按产品计算销售统计",
             "attributes": {"group_by": "product", "aggregations": ["sum", "mean", "count"]}}
        ],
        agents=[
            {"agent_type": "python_code", "name": "claude_analysis_step2",
             "attributes": {"step": 2, "description": "产品聚合"}}
        ],
        relations=[
            ("temp_activity_0", "temp_entity_0", "used"),
            ("temp_entity_1", "temp_activity_0", "wasGeneratedBy"),
            ("temp_activity_0", "temp_agent_0", "wasAssociatedWith"),
            ("temp_entity_1", "temp_entity_0", "wasDerivedFrom")
        ]
    )

    print(f"[OK] PROV 关系已记录 (步骤2)")

    # ==================== 步骤5：数据分析 - 分地区统计 ====================
    print("\n步骤5：分析操作3 - 分地区统计（分叉处理）")
    print("-" * 70)

    # 按地区分组保存
    region_stats = {}
    for region in ['North', 'South', 'East']:
        region_data = high_sales_data[high_sales_data['region'] == region]
        region_summary = pd.DataFrame({
            'total_sales': [region_data['sales'].sum()],
            'avg_sales': [region_data['sales'].mean()],
            'record_count': [len(region_data)]
        })
        region_summary.to_csv(f'region_{region}_stats.csv', index=False)
        region_stats[region] = region_summary
        print(f"   {region}: {len(region_data)} 条记录, 总销量: {region_data['sales'].sum()}")

    # 记录分叉操作的 PROV 关系
    prov_step3 = server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"entity_type": "dataset", "location": "high_sales_data.csv",
             "attributes": {"rows": len(high_sales_data)}},
            {"entity_type": "artifact", "location": "region_North_stats.csv",
             "attributes": {"region": "North", "records": len(high_sales_data[high_sales_data['region'] == 'North'])}},
            {"entity_type": "artifact", "location": "region_South_stats.csv",
             "attributes": {"region": "South", "records": len(high_sales_data[high_sales_data['region'] == 'South'])}},
            {"entity_type": "artifact", "location": "region_East_stats.csv",
             "attributes": {"region": "East", "records": len(high_sales_data[high_sales_data['region'] == 'East'])}}
        ],
        activities=[
            {"activity_type": "split", "description": "按地区分叉统计",
             "attributes": {"split_by": "region", "regions": ["North", "South", "East"]}}
        ],
        agents=[
            {"agent_type": "python_code", "name": "claude_analysis_step3",
             "attributes": {"step": 3, "description": "地区分叉"}}
        ],
        relations=[
            ("temp_activity_0", "temp_entity_0", "used"),
            ("temp_entity_1", "temp_activity_0", "wasGeneratedBy"),
            ("temp_entity_2", "temp_activity_0", "wasGeneratedBy"),
            ("temp_entity_3", "temp_activity_0", "wasGeneratedBy"),
            ("temp_activity_0", "temp_agent_0", "wasAssociatedWith"),
            ("temp_entity_1", "temp_entity_0", "wasDerivedFrom"),
            ("temp_entity_2", "temp_entity_0", "wasDerivedFrom"),
            ("temp_entity_3", "temp_entity_0", "wasDerivedFrom")
        ]
    )

    print(f"[OK] PROV 关系已记录 (步骤3 - 分叉)")

    # ==================== 步骤6：查看 PROV DAG 概览 ====================
    print("\n步骤6：查看 PROV DAG 概览")
    print("-" * 70)

    dag_overview = server.get_prov_dag_overview(session_id)

    if dag_overview.get('status') == 'success':
        stats = dag_overview['statistics']
        print(f"\n[OK] DAG 统计信息:")
        print(f"   DAG ID: {dag_overview['dag_id']}")
        print(f"   实体数: {stats['total_entities']}")
        print(f"   活动数: {stats['total_activities']}")
        print(f"   代理数: {stats['total_agents']}")
        print(f"   关系数: {stats['total_edges']}")

        print(f"\n   节点类型分布:")
        print(f"   - 实体: {len(dag_overview['nodes']['entities'])} 个")
        print(f"   - 活动: {len(dag_overview['nodes']['activities'])} 个")
        print(f"   - 代理: {len(dag_overview['nodes']['agents'])} 个")

    # ==================== 步骤7：查询最终产物溯源链 ====================
    print("\n步骤7：查询最终产物溯源链")
    print("-" * 70)

    # 获取 product_stats 的溯源链
    final_entity_id = None
    for entity_id in dag_overview['nodes']['entities']:
        if 'product_stats' in entity_id:
            final_entity_id = entity_id
            break

    if final_entity_id:
        lineage = server.get_prov_entity_lineage(session_id, final_entity_id)

        if lineage.get('status') == 'success':
            lineage_data = lineage['lineage']
            print(f"\n[OK] 溯源查询: {lineage_data['entity_info']['location']}")
            print(f"   实体类型: {lineage_data['entity_info']['entity_type']}")

            print(f"\n   溯源链:")
            for step in lineage_data['lineage_chain']:
                print(f"   步骤 {step['step']}:")
                print(f"     - 来自: {step['location']}")
                print(f"     - 关系: {step['relation']}")
                print(f"     - 类型: {step['entity_type']}")

    # ==================== 步骤8：总结 ====================
    print("\n" + "=" * 70)
    print("分析完成总结")
    print("=" * 70)

    print(f"""
分析流程:
  sales_data.csv (100行)
       ↓ [筛选 sales > 300]
  high_sales_data.csv ({len(high_sales_data)}行)
       ↓ [按产品聚合]
  product_stats.csv ({product_stats.shape[0]}个产品)
       ↓ [按地区分叉]
  region_North_stats.csv
  region_South_stats.csv
  region_East_stats.csv

PROV 记录:
  - 实体: {dag_overview['statistics']['total_entities']} 个数据集/产物
  - 活动: {dag_overview['statistics']['total_activities']} 个处理步骤
  - 代理: {dag_overview['statistics']['total_agents']} 个执行者
  - 关系: {dag_overview['statistics']['total_edges']} 个PROV关系

存储位置:
  .opentrace_demo/{session_id}/
    ├── prov_dag.json     (DAG 元数据)
    ├── prov_nodes.json   (节点详情)
    └── prov_edges.json   (关系边)
    """)

    # 导出会话
    export_result = server.export_session(session_id)
    print(f"[OK] 会话已导出: {export_result['export_path']}")

    return session_id


if __name__ == "__main__":
    session_id = data_analysis_with_prov()
    print(f"\n演示完成！会话ID: {session_id}")
    print(f"查看 PROV 数据: .opentrace_demo/{session_id}/prov_*.json")
