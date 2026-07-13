# OpenTrace 快速开始

5分钟上手OpenTrace数据血缘追踪系统。

## 什么是OpenTrace？

OpenTrace是一个**通用数据血缘追踪服务**，帮助记录和可视化数据分析流程。

**适用场景**：
- 数据清洗和转换
- 数据溯源和审计
- 数据质量检查
- 任何需要追踪数据处理历史的场景

## 5分钟快速开始

### Step 1: 初始化会话 (1分钟)

```python
from opentrace.mcp_server import get_server

# 获取服务器实例
server = get_server()

# 初始化会话
result = server.init_session(
    task_description="销售数据分析",
    data_path="sales.csv",
    data_type="csv"
)
session_id = result["session_id"]
print(f"会话ID: {session_id}")
```

### Step 2: 记录数据处理步骤 (2分钟)

```python
# 每个数据处理步骤都要记录

# 1. 记录PROV关系（数据流）
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "sales.csv"},
        {"id": "output", "entity_type": "dataset", "location": "filtered.csv"}
    ],
    activities=[
        {"id": "act", "activity_type": "filter", "description": "过滤无效记录"}
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

# 2. 记录步骤详情（必填）
server.record_step_details(
    session_id=session_id,
    step_id="step_1",
    step_name="filter_data",
    description="过滤无效销售记录",
    code_files=["process.py"],
    commands_run=["python process.py"],
    input_files=["sales.csv"],
    output_files=["filtered.csv"]
)
```

### Step 3: 查看结果 (1分钟)

```
.opentrace/
└── session_20260630_120000/
    ├── prov_dag.json          # DAG元数据
    ├── prov_nodes.json        # 节点信息
    ├── prov_edges.json        # 关系信息
    └── step_details.json      # 步骤详情
```

## 核心原则

1. **逐步处理** - 每次只执行一个明确的数据处理动作
2. **完整记录** - 每步必须记录PROV关系和步骤详情
3. **中间文件** - 每步操作都保存结果到文件
4. **观察后决策** - 读取输出后基于结果决定下一步

## 下一步

- 📖 [完整使用指南](OPENTRACE_GUIDE.md)
- 🔧 [API参考文档](docs/API_REFERENCE.md)
- 📚 [最佳实践](docs/BEST_PRACTICES.md)
- 💡 [示例代码](examples/)

## 常见问题

**Q: 数据存储在哪里？**
A: 默认存储在项目根目录 `.opentrace/`，可通过环境变量 `OPENTRACE_BASE_DIR` 自定义。

**Q: 支持哪些数据格式？**
A: 当前支持 JSON 和 CSV，可扩展。

## 获取帮助

- GitHub Issues: [提交问题](https://github.com/your-repo/issues)
- 文档: [完整文档](docs/)
