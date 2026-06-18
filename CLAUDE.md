# OpenTrace 数据血缘追踪指南

## 项目说明

本项目实现 **双粒度数据血缘追踪**：
- **元素级追踪**: 记录 JSON/CSV 数据字段的处理链路
- **文件级追踪**: 使用 PROV 标准记录数据集/文件的流转关系

## 核心组件

### 1. 数据元素追踪 (`tracker.py`)
追踪单个数据字段的处理历史

### 2. PROV DAG (`prov_dag.py`)
基于 W3C PROV 标准的文件级血缘图谱

### 3. 可视化 (`prov_visualizer.py`)
生成数据流图和 Mermaid 代码

### 4. 服务接口 (`mcp_server.py`)
统一的调用接口（支持多实例管理）

### 5. 验证保护 (`prov_validation.py`)
数据完整性验证和保护机制

## 在数据分析中的使用

### 初始化会话

```python
from opentrace.mcp_server import get_server

# 获取服务器实例（默认使用 opentrace 项目目录）
server = get_server()

# 创建新会话
result = server.init_session(
    task_description="销售数据分析",
    data_path="sales.csv",
    data_type="csv"
)
session_id = result["session_id"]
```

### 记录数据处理步骤

**重要**: 每个实体、活动、代理必须提供临时 `id` 字段

```python
# 正确示例 - 包含临时 ID
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "sales.csv", "attributes": {"rows": 1000}},
        {"id": "output", "entity_type": "dataset", "location": "filtered.csv", "attributes": {"rows": 750}}
    ],
    activities=[
        {"id": "activity", "activity_type": "filter", "description": "移除无效记录", "attributes": {}}
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "step1", "attributes": {}}
    ],
    relations=[
        ("activity", "input", "used"),              # 活动 → 实体
        ("output", "activity", "wasGeneratedBy"),   # 实体 → 活动
        ("activity", "agent", "wasAssociatedWith"), # 活动 → 代理
        ("output", "input", "wasDerivedFrom")       # 实体 → 实体
    ]
)
```

### 关系方向规则

| 关系 | 方向 | 示例 |
|------|------|------|
| `used` | Activity → Entity | filter → sales.csv |
| `wasGeneratedBy` | Entity → Activity | output.csv → filter |
| `wasAssociatedWith` | Activity → Agent | filter → step1 |
| `wasDerivedFrom` | Entity → Entity | output → input |

### 可视化数据处理流程

```python
from opentrace.prov_visualizer import visualize_prov_dag
from pathlib import Path

# 生成可视化
session_dir = Path(".opentrace") / session_id
visualize_prov_dag(str(session_dir), "data_flow.txt")

# 输出包含：
# - 文本格式数据流图
# - 节点详情
# - Mermaid 渲染代码
```

## 重要原则

1. **显式提供参数**: 所有关系由 Claude Code 明确提供，不解析代码
2. **独立存储**: DAG 数据存储在独立文件中（prov_dag.json, prov_nodes.json, prov_edges.json）
3. **支持复杂场景**: 支持聚合（多输入→单输出）和分叉（单输入→多输出）
4. **临时 ID 必填**: 实体/活动/代理必须提供临时 ID 用于引用

## 服务器实例管理

```python
from opentrace.mcp_server import get_server, list_all_servers

# 默认实例（使用 opentrace 项目目录）
default_server = get_server()

# 自定义存储位置
custom_server = get_server("/path/to/storage")

# 列出所有活跃的服务器实例
servers_info = list_all_servers()
```

## 数据验证和保护

```python
from opentrace.prov_validation import ProtectedProvDAG, validate_session

# 使用受保护的 DAG（自动验证和完整性检查）
protected_dag = ProtectedProvDAG(session_dir, append_only=True)

# 验证现有会话
is_valid, errors = validate_session(session_dir)
if not is_valid:
    print("验证失败:", errors)
```

## 数据分析工作流

当用户要求数据分析时：
1. 初始化会话（或获取现有会话）
2. 每个处理步骤记录 PROV 关系（包含临时 ID）
3. 分析完成后生成可视化
4. 向用户展示数据流图

## 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| "源节点不存在" | 临时 ID 未提供 | 在 entities/activities/agents 中添加 `id` 字段 |
| "无效的关系类型" | 关系方向错误 | 检查关系方向是否符合 PROV 标准 |
| "会话不存在" | session_id 错误 | 使用 `server.list_sessions()` 查看现有会话 |
