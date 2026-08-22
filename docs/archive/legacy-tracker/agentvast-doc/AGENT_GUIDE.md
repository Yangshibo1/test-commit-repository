# AgentVAST Agent 使用指南

## 角色定位

作为使用AgentVAST的Agent，你需要**同时扮演两个角色**：

### 角色1: 数据分析师

- **深入完成数据分析任务**，不能输出空泛结果
- 按照 **任务拆分 → 最小节点 → 按需生成代码 → 查看产物 → 反思规划** 的循环工作
- 每一步都基于实际观察到的数据产物做决策
- 逐步完成真正的数据分析工作，直到得到深度结果

**❌ 错误方式**：一次性输出"分析结果"，没有实际数据处理过程

**✅ 正确方式**：
```
阶段0: 任务拆分
├─ node_01: 加载数据
├─ node_02: 探索数据结构
├─ node_03: 清洗数据
└─ node_04: 分析结果

对每个节点：
├─ 按需生成代码（1个或多个）
├─ 执行代码，得到产物
├─ 查看产物，观察结果
├─ 记录处理流程
└─ 反思并规划下一个节点

循环直到得到真实、具体、有深度的结果
```

### 角色2: AgentVAST记录助手

- 在每一步数据处理后，调用AgentVAST工具记录工作流程
- **必填**: 调用 `record_step_details()` 记录步骤详情
- 确保记录完整，便于验证和追溯

---

## 给Agent的检查清单

使用AgentVAST记录数据分析工作流时，按此清单执行：

### ✅ 必做项（双重角色）

**阶段0: 任务拆分**
- [ ] 将主要任务拆分为多个具体的任务节点
- [ ] 每个节点是最小的数据处理单元（过滤、聚合、统计等）

**每个节点处理循环**：
作为**数据分析师**：
- [ ] 评估任务复杂度和需求
- [ ] 按需生成1个或多个代码
- [ ] 执行代码，得到产物
- [ ] 查看产物，观察结果
- [ ] 反思并规划下一个节点
- [ ] 动态调整任务规划

作为**AgentVAST记录助手**：
- [ ] 初始化: `server = get_server()` → `init_session()`
- [ ] 每个节点处理后调用 `record_prov_relation()`
- [ ] 每个节点处理后调用 `record_step_details()` ← **⚠️ 必填；会自动生成/同步 `step_001.json` 等步骤主记录**
- [ ] 确认每个节点都有三类产物：`step_XXX.json`、`step_details.json`、`prov_*.json`

**结果验证**：
- [ ] 检查结果是否真实（基于实际数据处理）
- [ ] 检查结果是否具体（包含具体数字、案例）
- [ ] 检查结果是否有深度（有深入分析）
- [ ] 拒绝空泛输出

### ❌ 禁止项

- [ ] 禁止一次性pipeline脚本完成全部分析
- [ ] 禁止跳过 `record_step_details()`
- [ ] 禁止在未读取输出时预设下一步
- [ ] 禁止输出空泛的分析结果（没有实际数据处理过程）

---

## 代码模板

### 模板1: 初始化会话

```python
from agentvast.mcp_server import get_server
from pathlib import Path

server = get_server()
result = server.init_session(
    task_description="<任务描述>",
    data_path="<数据文件路径>",
    data_type="json"  # 或 "csv"
)
session_id = result["session_id"]
work_dir = Path(server.base_dir) / session_id
```

### 模板2: 每步数据处理

```python
# === 数据处理 ===
# ... 读取 input_file ...
# ... 处理数据 ...
# ... 保存 output_file ...

# === 记录PROV关系 ===
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "<输入文件>"},
        {"id": "output", "entity_type": "dataset", "location": "<输出文件>"}
    ],
    activities=[
        {"id": "act", "activity_type": "filter", "description": "<操作描述>"}
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "<步骤名称>"}
    ],
    relations=[
        ("act", "input", "used"),
        ("output", "act", "wasGeneratedBy"),
        ("act", "agent", "wasAssociatedWith"),
        ("output", "input", "wasDerivedFrom")
    ]
)

# === 记录步骤详情（必填）===
# 该调用会同时确保生成 step_001.json / step_002.json 等步骤主记录。
# 如果传入 node_03 这类节点ID，返回值中的 step_id 是系统生成的规范 step_XXX ID，
# 原始节点ID会保存在 step_XXX.json 的 metadata.node_id 中。
step_result = server.record_step_details(
    session_id=session_id,
    step_id="node_<N>",
    step_name="<步骤名称>",
    description="<本步工作内容>",
    code_files=["<代码文件>"],
    commands_run=["<命令>"],
    input_files=["<输入文件>"],
    output_files=["<输出文件>"],
    parameters={"operation": "filter"}
)
step_id = step_result["step_id"]

# === 读取输出并决策 ===
with open(output_file) as f:
    result = json.load(f)
# 基于result决定下一步
```

---

## 速查表

### activity_type 可选值

| 值 | 用途 |
|----|------|
| `load` | 加载数据 |
| `filter` | 过滤数据 |
| `transform` | 转换数据 |
| `analyze` | 分析数据 |
| `aggregate` | 聚合数据 |
| `trace` | 追踪溯源 |

### entity_type 可选值

| 值 | 用途 |
|----|------|
| `dataset` | 数据集文件 |
| `artifact` | 处理结果产物 |

### 关系方向

| 关系 | 方向 | 示例 |
|------|------|------|
| `used` | Activity → Entity | `("act", "input", "used")` |
| `wasGeneratedBy` | Entity → Activity | `("output", "act", "wasGeneratedBy")` |
| `wasAssociatedWith` | Activity → Agent | `("act", "agent", "wasAssociatedWith")` |
| `wasDerivedFrom` | Entity → Entity | `("output", "input", "wasDerivedFrom")` |

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| "源节点不存在" | entities/activities/agents 缺少 `id` 字段 | 添加 `id` 字段 |
| "验证失败: step_details缺失" | 未调用 `record_step_details()` | 每步必须调用 |
| "无效的关系类型" | 关系方向错误 | 参考上表 |

---

## 更多资源

- 📖 [API速查手册](API_REFERENCE.md) - 完整API文档
- 📚 [完整使用指南](../../AGENTVAST_GUIDE.md) - 详细说明
- 💡 [最佳实践](BEST_PRACTICES.md) - 避免常见陷阱
- 🔍 [示例代码](../../examples/) - 参考实现

---

## 完整示例

参见 `examples/` 目录中的脚本。
