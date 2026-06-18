# OpenTrace 使用指南

## 快速开始

### 1. 获取服务器实例

```python
from opentrace.mcp_server import get_server

# 默认服务器（数据存储在 opentrace 项目目录）
server = get_server()

# 自定义存储位置
server = get_server("/path/to/storage")
```

### 2. 初始化追踪会话

```python
result = server.init_session(
    task_description="销售数据分析",
    data_path="sales.csv",
    data_type="csv"
)
session_id = result["session_id"]
print(f"会话ID: {session_id}")
```

### 3. 记录数据处理步骤

#### 筛选操作示例

```python
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {
            "id": "raw_data",                           # ← 临时 ID（必填）
            "entity_type": "dataset",
            "location": "sales.csv",
            "attributes": {"rows": 1000, "columns": 5}
        },
        {
            "id": "filtered_data",
            "entity_type": "dataset",
            "location": "sales_filtered.csv",
            "attributes": {"rows": 750, "filter": "amount > 0"}
        }
    ],
    activities=[
        {
            "id": "filter_step",
            "activity_type": "filter",
            "description": "移除无效销售记录",
            "attributes": {
                "condition": "amount > 0 AND status = 'active'",
                "language": "python_pandas"
            }
        }
    ],
    agents=[
        {
            "id": "processor",
            "agent_type": "python_code",
            "name": "data_cleaning_step",
            "attributes": {"version": "1.0", "library": "pandas"}
        }
    ],
    relations=[
        ("filter_step", "raw_data", "used"),
        ("filtered_data", "filter_step", "wasGeneratedBy"),
        ("filter_step", "processor", "wasAssociatedWith"),
        ("filtered_data", "raw_data", "wasDerivedFrom")
    ]
)
```

#### 聚合操作示例

```python
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "sales_filtered.csv", "attributes": {"rows": 750}},
        {"id": "summary", "entity_type": "artifact", "location": "sales_summary.csv", "attributes": {"rows": 10}}
    ],
    activities=[
        {
            "id": "agg",
            "activity_type": "aggregate",
            "description": "按产品分组统计销售额",
            "attributes": {
                "group_by": "product_id",
                "aggregations": ["sum", "mean", "count"]
            }
        }
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "analysis_step1", "attributes": {}}
    ],
    relations=[
        ("agg", "input", "used"),
        ("summary", "agg", "wasGeneratedBy"),
        ("agg", "agent", "wasAssociatedWith"),
        ("summary", "input", "wasDerivedFrom")
    ]
)
```

#### 分叉操作示例

```python
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "sales.csv", "attributes": {"rows": 100}},
        {"id": "north", "entity_type": "artifact", "location": "north_sales.csv", "attributes": {"region": "North"}},
        {"id": "south", "entity_type": "artifact", "location": "south_sales.csv", "attributes": {"region": "South"}},
        {"id": "east", "entity_type": "artifact", "location": "east_sales.csv", "attributes": {"region": "East"}}
    ],
    activities=[
        {
            "id": "split",
            "activity_type": "split",
            "description": "按地区拆分数据",
            "attributes": {"split_by": "region", "regions": ["North", "South", "East"]}
        }
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "regional_split", "attributes": {}}
    ],
    relations=[
        ("split", "input", "used"),
        ("north", "split", "wasGeneratedBy"),
        ("south", "split", "wasGeneratedBy"),
        ("east", "split", "wasGeneratedBy"),
        ("split", "agent", "wasAssociatedWith"),
        ("north", "input", "wasDerivedFrom"),
        ("south", "input", "wasDerivedFrom"),
        ("east", "input", "wasDerivedFrom")
    ]
)
```

### 4. 生成可视化

```python
from opentrace.prov_visualizer import visualize_prov_dag
from pathlib import Path

session_dir = Path(".opentrace") / session_id
visualize_prov_dag(str(session_dir), "data_flow.txt")
```

生成的 `data_flow.txt` 包含：
- 文本格式数据流图
- 节点和关系详情
- Mermaid 渲染代码

### 5. 查看现有会话

```python
# 列出所有会话
sessions = server.list_sessions()
for session in sessions:
    print(f"会话ID: {session['session_id']}")
    print(f"描述: {session['task_description']}")
    print(f"创建时间: {session['created_at']}")
```

## PROV 标准说明

### 实体类型 (Entity)

| 类型 | 说明 | 示例 |
|------|------|------|
| `dataset` | 数据集文件 | sales.csv, data.json |
| `artifact` | 处理结果产物 | summary.csv, chart.png |
| `file` | 其他文件类型 | config.yaml, schema.sql |

### 活动类型 (Activity)

| 类型 | 说明 | 示例 |
|------|------|------|
| `filter` | 筛选/过滤 | 移除无效记录 |
| `aggregate` | 聚合/统计 | 分组求和 |
| `transform` | 转换 | 格式转换、清洗 |
| `split` | 分叉 | 按条件拆分 |
| `join` | 合并 | 连接多个数据源 |
| `sort` | 排序 | 按字段排序 |

### 代理类型 (Agent)

| 类型 | 说明 |
|------|------|
| `python_code` | Python 代码执行 |
| `agent` | AI Agent |
| `user` | 用户手动操作 |

### 关系类型及方向

| 关系 | 方向 | 说明 | 示例 |
|------|------|------|------|
| `used` | Activity → Entity | 活动使用了实体 | filter → raw_data |
| `wasGeneratedBy` | Entity → Activity | 实体由活动生成 | output → filter |
| `wasAssociatedWith` | Activity → Agent | 活动由谁执行 | filter → python_script |
| `wasDerivedFrom` | Entity → Entity | 实体派生自另一个 | output → input |
| `wasStartedBy` | Activity → Activity | 活动由另一个启动 | step2 → step1 |
| `wasInformedBy` | Activity → Activity | 活动使用了另一个的输出 | aggregate → filter |
| `actedOnBehalfOf` | Agent → Agent | 代理代表另一个行动 | assistant → user |

## 数据验证和保护

### 使用受保护的 DAG

```python
from opentrace.prov_validation import ProtectedProvDAG

# 创建受保护的 DAG（追加模式）
protected_dag = ProtectedProvDAG(session_dir, append_only=True)

# 所有操作自动验证
try:
    protected_dag.add_relation(from_id, to_id, relation)
except ValueError as e:
    print(f"验证失败: {e}")
```

### 验证现有会话

```python
from opentrace.prov_validation import validate_session

is_valid, errors = validate_session(session_dir)
if not is_valid:
    for error in errors:
        print(f"错误: {error}")
```

### 完整性检查

```python
from opentrace.prov_validation import ProvValidator

validator = ProvValidator(session_dir)

# 计算完整性哈希
hash_value = validator.compute_integrity_hash()

# 验证完整性
is_valid, details = validator.verify_integrity()
```

## API 参考

### OpenTraceServer

#### 方法列表

| 方法 | 说明 |
|------|------|
| `init_session()` | 初始化新会话 |
| `record_prov_relation()` | 记录 PROV 关系 |
| `get_prov_dag_overview()` | 获取 DAG 概览 |
| `get_prov_entity_lineage()` | 获取实体溯源链 |
| `list_sessions()` | 列出所有会话 |

### 全局函数

| 函数 | 说明 |
|------|------|
| `get_server(base_dir=None)` | 获取服务器实例 |
| `list_all_servers()` | 列出所有服务器实例 |

## 存储结构

```
.opentrace/
├── session_YYYYMMDD_HHMMSS/
│   ├── meta.json              # 会话元数据
│   ├── prov_dag.json          # DAG 元信息
│   ├── prov_nodes.json        # 所有节点
│   ├── prov_edges.json        # 所有关系
│   ├── step_*.json            # 处理步骤
│   └── .integrity.json        # 完整性记录
└── ...
```

## 常见问题

### Q: 临时 ID 是什么？

A: 临时 ID 是在调用 `record_prov_relation` 时为实体、活动、代理提供的唯一标识符，用于在 `relations` 中引用它们。系统会自动将其转换为正式 ID。

### Q: 为什么必须提供临时 ID？

A: 因为系统会自动为每个节点生成唯一 ID（如 `entity_abc123`），临时 ID 允许你在不知道最终 ID 的情况下建立关系。

### Q: 数据存储在哪里？

A: 默认存储在 `opentrace` 项目目录下的 `.opentrace/` 文件夹。可以通过环境变量 `OPENTRACE_BASE_DIR` 或传入参数自定义。

### Q: 如何在不同脚本中共享会话？

A: 使用相同的 `base_dir` 获取服务器实例，然后通过 `session_id` 访问会话：
```python
server = get_server()
# 使用已存在的 session_id
server.list_sessions()  # 查看所有会话
```
