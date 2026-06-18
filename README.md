# OpenTrace - 数据血缘追踪系统

轻量级数据血缘追踪系统，专注于追踪 agent 数据分析流程、定位错误来源、追溯结果数据来源。

## 研究目标

1. **流程追踪**: Agent 如何处理数据
2. **错误定位**: 数据处理错误后追踪来源
3. **结果追溯**: 结果数据的分析来源
4. **可视化**: 数据处理流程可视化展示

## 设计特点

- **双粒度追踪**: 元素级（字段）+ 文件级（数据集）
- **轻量级**: 核心功能，快速验证
- **学术研究**: 面向研究场景设计
- **PROV 标准**: 基于 W3C PROV 数据模型
- **可视化支持**: 生成 Mermaid 流程图

## 安装

```bash
# 基础安装
pip install -e .

# 支持CSV数据
pip install -e ".[pandas]"
```

## 快速开始

### 作为库使用（元素级追踪）

```python
from opentrace.tracker import LineageTracker

# 初始化追踪器
tracker = LineageTracker("my_session")

# 从JSON初始化
result = tracker.init_from_json("data.json")
print(f"数据行数: {result['total_rows']}")

# 记录处理步骤
step_id = tracker.record_step(
    step_name="数据清洗",
    operation="fillna",
    description="填充缺失值"
)

# 记录映射关系
tracker.record_mapping(
    step_id=step_id,
    from_ids=["root[0].age"],
    to_id="root[0].age_cleaned",
    operation="fillna(0)",
    value_info={"root[0].age": {"old": None, "new": 0}}
)

# 追踪元素
chain = tracker.trace_element("root[0].age_cleaned")
print(f"血缘链: {len(chain)} 步")

# 分析错误
analysis = tracker.analyze_error(
    error_message="发现 NaN 值",
    affected_element="root[0].total_amount"
)
```

### 文件级追踪（PROV DAG）

```python
from opentrace.mcp_server import get_server

# 获取服务器实例
server = get_server()

# 创建会话
result = server.init_session(
    task_description="销售数据分析",
    data_path="sales.csv",
    data_type="csv"
)
session_id = result["session_id"]

# 记录数据处理
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "sales.csv"},
        {"id": "output", "entity_type": "dataset", "location": "filtered.csv"}
    ],
    activities=[
        {"id": "activity", "activity_type": "filter", "description": "筛选有效记录"}
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "step1"}
    ],
    relations=[
        ("activity", "input", "used"),
        ("output", "activity", "wasGeneratedBy"),
        ("activity", "agent", "wasAssociatedWith"),
        ("output", "input", "wasDerivedFrom")
    ]
)

# 生成可视化
from opentrace.prov_visualizer import visualize_prov_dag
from pathlib import Path

session_dir = Path(".opentrace") / session_id
visualize_prov_dag(str(session_dir), "data_flow.txt")
```

### 数据验证和保护

```python
from opentrace.prov_validation import ProtectedProvDAG, validate_session

# 使用受保护的 DAG（自动验证）
protected_dag = ProtectedProvDAG(session_dir, append_only=True)

# 验证现有会话
is_valid, errors = validate_session(session_dir)
```

## 数据分析工作流

使用 OpenTrace 进行数据分析时，请参考以下文档：

- **工作流定义**: `.claude/workflows/trace-analysis.yaml`
- **使用指南**: `.claude/workflows/trace-analysis-guide.md`

### 核心原则

1. **每步操作生成中间文件** - 不要在内存中处理，每次操作都保存结果
2. **每步调用 trace 系统** - 使用 `server.record_prov_relation()` 记录 DAG
3. **数据流转清晰** - 明确每步读取哪些文件，输出哪些文件
   - 支持读取原始数据
   - 支持读取多个中间结果
   - 支持回溯重新分析
4. **迭代式分析** - 根据上一步结果决定下一步方向

### PROV 参数格式

**Entity（实体）**
```python
{
    "id": "临时ID",           # 必填
    "entity_type": "dataset", # dataset 或 artifact
    "location": "文件路径",
    "attributes": {"key": "value"}  # 可选
}
```

**Activity（活动）**
```python
{
    "id": "临时ID",
    "activity_type": "filter",  # load/transform/filter/analyze/trace/compare/aggregate
    "description": "操作描述",
    "attributes": {}
}
```

**Agent（代理）**
```python
{
    "id": "临时ID",
    "agent_type": "script",  # script/python_code/person
    "name": "步骤名称",
    "attributes": {}
}
```

**Relation（关系）**
```python
(from_id, to_id, relation_type)
```

关系类型：
- `used`: 活动使用了实体 (Activity → Entity)
- `wasGeneratedBy`: 实体由活动生成 (Entity → Activity)
- `wasAssociatedWith`: 活动关联代理 (Activity → Agent)
- `wasDerivedFrom`: 实体源自实体 (Entity → Entity)

## 核心概念

### 双粒度设计

| 粒度 | 模块 | 追踪对象 | 存储格式 |
|------|------|----------|----------|
| **元素级** | `tracker.py` | JSON/CSV 字段 | 步骤链 |
| **文件级** | `prov_dag.py` | 数据集/文件 | PROV DAG |

### PROV 数据模型

```
Entity (实体) ←→ Activity (活动) ←→ Agent (代理)
     ↓                                            ↑
     └───────────── wasDerivedFrom ────────────────┘
```

### 元素ID格式

**JSON数据:**
```
root                 # 根元素
root[0]              # 数组元素
root[0].user.age     # 嵌套字段
```

**CSV数据:**
```
cell_0_age    # 单元格 (行_列)
row_3         # 行
```

### 映射关系

每个操作记录 `from → to` 的映射：

```python
{
    "from": ["elem_001", "elem_002"],  # 来源
    "to": "elem_new",                   # 目标
    "operation": "add",                 # 操作
    "value_info": {...}                 # 值信息
}
```

## 组件说明

| 模块 | 功能 |
|------|------|
| `tracker.py` | 元素级数据血缘追踪 |
| `prov_dag.py` | PROV 标准 DAG 实现 |
| `prov_visualizer.py` | 数据流可视化 |
| `prov_validation.py` | 数据完整性验证 |
| `mcp_server.py` | 统一服务接口 |

## API 参考

### 核心函数

| 函数 | 说明 |
|------|------|
| `get_server(base_dir=None)` | 获取服务器实例 |
| `list_all_servers()` | 列出所有服务器实例 |
| `validate_session(session_dir)` | 验证会话完整性 |
| `visualize_prov_dag(session_dir, output_file)` | 生成可视化 |

### OpenTraceServer 方法

| 方法 | 说明 |
|------|------|
| `init_session()` | 初始化新会话 |
| `record_prov_relation()` | 记录 PROV 关系 |
| `record_step_details()` | 记录步骤详情（代码、命令、描述） |
| `get_step_details()` | 获取所有步骤详情 |
| `get_prov_dag_overview()` | 获取 DAG 概览 |
| `get_prov_entity_lineage()` | 获取实体溯源链 |
| `list_sessions()` | 列出所有会话 |

## 测试

```bash
# 基础测试
python test_basic.py

# PROV DAG 测试
python test_prov_dag.py

# 演示脚本
python demo_prov_analysis.py
```

## 项目结构

```
opentrace/
├── opentrace/
│   ├── __init__.py
│   ├── tracker.py              # 元素级追踪器
│   ├── prov_dag.py             # PROV DAG 实现
│   ├── prov_visualizer.py      # 可视化工具
│   ├── prov_validation.py      # 验证保护
│   └── mcp_server.py           # 服务接口
├── .claude/
│   └── workflows/
│       ├── trace-analysis.yaml      # 数据分析工作流定义
│       └── trace-analysis-guide.md   # 工作流使用指南
├── docs/
│   ├── data-lineage-system.md      # 血缘系统设计
│   ├── implementation-design.md     # 实现设计
│   ├── agent-prompt-template.md    # Agent Prompt模板
│   ├── mcp-tools-guide.md          # MCP 工具指南
│   └── mcp-tools-reference.md      # MCP 工具参考
├── CLAUDE.md                    # Claude Code 使用指南
├── OPENTRACE_GUIDE.md          # 详细使用指南
├── README.md                   # 本文件
├── test_basic.py               # 基础测试
├── test_prov_dag.py            # PROV 测试
├── demo_prov_analysis.py       # 演示脚本
└── pyproject.toml             # 项目配置
```

## 数据存储

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

## 环境变量

| 变量 | 说明 |
|------|------|
| `OPENTRACE_BASE_DIR` | 自定义数据存储目录 |

## 特性状态

| 特性 | 状态 |
|------|------|
| JSON/CSV 数据支持 | ✅ 完成 |
| 元素级血缘追踪 | ✅ 完成 |
| 文件级血缘追踪 | ✅ 完成 |
| PROV 标准支持 | ✅ 完成 |
| 数据流可视化 | ✅ 完成 |
| 完整性验证 | ✅ 完成 |
| 大数据集优化 | ⚠️ 进行中 |
| Web 界面 | 📋 计划中 |

## 学术研究应用

本系统适用于以下研究场景：

1. **Agent 行为分析**: 研究 agent 如何处理数据
2. **错误诊断研究**: 分析数据错误来源
3. **可重现性研究**: 追踪数据处理过程
4. **人机协作研究**: agent 与人类的数据分析协作
5. **数据溯源研究**: 复杂数据处理流程的可追溯性

## 后续计划

- [ ] 大数据集性能优化
- [ ] 复杂聚合操作支持
- [ ] Web 界面开发
- [ ] 与更多 agent 框架集成
- [ ] 实时数据处理支持

## 许可

MIT License
