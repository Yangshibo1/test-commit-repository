# AgentVAST API 速查手册

快速查找AgentVAST API函数和参数。

---

## 核心API

### 1. get_server()

```python
from agentvast.mcp_server import get_server

server = get_server()  # 使用默认目录 (.agentvast/)
server = get_server("/path/to/storage")  # 自定义目录
```

### 2. init_session()

```python
result = server.init_session(
    task_description: str,    # 任务描述
    data_path: str,          # 数据文件路径
    data_type: str = "json"  # 数据类型: "json" | "csv"
)

# 返回: {"session_id": "...", "status": "initialized", ...}
```

### 3. record_prov_relation()

```python
server.record_prov_relation(
    session_id: str,
    entities: List[Dict],     # 实体列表
    activities: List[Dict],   # 活动列表
    agents: List[Dict],       # 代理列表
    relations: List[Tuple]    # 关系列表 [(from, to, relation), ...]
)
```

**Entity格式**:
```python
{
    "id": str,              # 临时ID（必填）
    "entity_type": str,     # "dataset" | "artifact"
    "location": str,        # 文件路径
    "attributes": Dict      # 可选
}
```

**Activity格式**:
```python
{
    "id": str,              # 临时ID（必填）
    "activity_type": str,   # "load" | "filter" | "transform" | "analyze" | "aggregate"
    "description": str,     # 操作描述
    "attributes": Dict      # 可选
}
```

**Agent格式**:
```python
{
    "id": str,              # 临时ID（必填）
    "agent_type": str,      # "python_code" | "agent" | "user"
    "name": str,            # 代理名称
    "attributes": Dict      # 可选
}
```

**Relation格式**:
```python
(from_id, to_id, relation_type)
# relation_type: "used" | "wasGeneratedBy" | "wasAssociatedWith" | "wasDerivedFrom"
```

### 4. record_step_details()

```python
server.record_step_details(
    session_id: str,
    step_id: str,           # 步骤ID，如 "step_1"
    step_name: str,         # 步骤名称
    description: str,       # 工作内容描述
    code_generated: List[str] = None,   # 生成的代码片段
    code_files: List[str] = None,       # 代码文件路径
    commands_run: List[str] = None,     # 运行的命令
    input_files: List[str] = None,      # 输入文件
    output_files: List[str] = None,     # 输出文件
    parameters: Dict = None             # 参数
)
```

**⚠️ 必填项**: 每步数据处理后必须调用此函数，否则验证失败。

这是Agent作为"AgentVAST记录助手"角色的核心职责。

**⚠️ 重要**: 这是必填项，每步都必须调用，否则验证失败。

---

## 常用参数值

### activity_type

| 值 | 用途 |
|----|------|
| `load` | 加载数据 |
| `filter` | 过滤数据 |
| `transform` | 转换数据 |
| `analyze` | 分析数据 |
| `aggregate` | 聚合汇总 |
| `trace` | 追踪溯源 |

### entity_type

| 值 | 用途 |
|----|------|
| `dataset` | 数据集文件 |
| `artifact` | 处理结果产物 |

### agent_type

| 值 | 用途 |
|----|------|
| `python_code` | Python代码执行 |
| `agent` | AI Agent |
| `user` | 用户手动操作 |

---

## 关系方向速查

| 关系 | 方向 | 示例 |
|------|------|------|
| `used` | Activity → Entity | `("act", "input", "used")` |
| `wasGeneratedBy` | Entity → Activity | `("output", "act", "wasGeneratedBy")` |
| `wasAssociatedWith` | Activity → Agent | `("act", "agent", "wasAssociatedWith")` |
| `wasDerivedFrom` | Entity → Entity | `("output", "input", "wasDerivedFrom")` |

**记忆技巧**: 活动使用输入，输出由活动生成。

---

## 数据存储

默认位置: `.agentvast/`

```
.agentvast/
└── session_YYYYMMDD_HHMMSS/
    ├── meta.json              # 会话元数据
    ├── prov_dag.json          # DAG元信息
    ├── prov_nodes.json        # 节点信息
    ├── prov_edges.json        # 关系信息
    ├── step_details.json      # 步骤详情
    └── step_*.json           # 各步骤数据
```

可通过环境变量 `AGENTVAST_BASE_DIR` 自定义。

---

## 完整示例

```python
from agentvast.mcp_server import get_server
from pathlib import Path

# 初始化
server = get_server()
result = server.init_session("任务描述", "data.json", "json")
session_id = result["session_id"]
work_dir = Path(server.base_dir) / session_id

# 记录步骤
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "data.json"},
        {"id": "output", "entity_type": "dataset", "location": "filtered.json"}
    ],
    activities=[
        {"id": "act", "activity_type": "filter", "description": "过滤数据"}
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "step1"}
    ],
    relations=[
        ("act", "input", "used"),
        ("output", "act", "wasGeneratedBy"),
        ("act", "agent", "wasAssociatedWith"),
        ("output", "input", "wasDerivedFrom")
    ]
)

server.record_step_details(
    session_id=session_id,
    step_id="step_1",
    step_name="filter_data",
    description="过滤数据",
    code_files=["process.py"],
    commands_run=["python process.py"],
    input_files=["data.json"],
    output_files=["filtered.json"]
)
```
