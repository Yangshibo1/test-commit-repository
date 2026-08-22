---
name: agentvast-data-analysis
description: 使用 AgentVAST 记录数据分析工作流 - 任务节点驱动，按需生成代码，记录完整trace流程
---

# AgentVAST 数据分析工作流

当用户需要执行数据分析任务并追踪数据血缘时，使用此skill。

## Agent角色定位

使用此skill时，Agent需要**同时扮演两个角色**：

### 角色1: 数据分析师
- **深入完成数据分析任务**，不输出空泛结果
- 按照 **任务拆分 → 最小节点 → 按需生成代码 → 查看产物 → 反思规划** 的循环工作
- 每一步都基于实际观察到的数据产物做决策
- 逐步完成真正的数据分析工作，直到得到深度结果

### 角色2: AgentVAST记录助手
- 在每一步数据处理后，调用AgentVAST工具记录工作流程
- **必填**: 调用 `record_step_details()` 记录步骤详情
- 确保记录完整，便于验证和追溯

## 核心工作流

```
任务拆分 → 最小节点 → 按需生成代码 → 查看产物 → API记录 → 反思规划 → 循环 → 深度结果 → Trace呈现
```

## 核心原则

1. **任务节点驱动** - 将任务拆分为多个具体的任务节点
2. **最小处理单元** - 过滤、聚合、统计等是最小的任务节点
3. **按需生成代码** - 根据任务复杂度和需求，生成1个或多个代码
4. **生成中间产物** - 每个节点产生明确的中间产物
5. **API记录完整** - 调用 `record_prov_relation()` 和 `record_step_details()`
6. **基于观察规划** - 查看产物结果，基于实际观察规划下一步
7. **动态调整规划** - 允许根据中间结果动态拆分或调整
8. **拒绝空泛输出** - 必须得到真实、具体、有深度的分析结果

## 完整工作流

### 阶段0: 初始任务拆分

```python
# 将主要任务拆分为多个具体的任务节点
task_plan = [
    "node_01: 加载数据",
    "node_02: 探索数据结构",
    "node_03: 清洗数据",
    "node_04: 统计分析",
    "node_05: 生成报告"
]
```

### 阶段1: 初始化会话

```python
from agentvast.mcp_server import get_server
from pathlib import Path

server = get_server()
result = server.init_session(
    task_description="销售数据分析",
    data_path="sales.json",
    data_type="json"
)
session_id = result["session_id"]
work_dir = Path(server.base_dir) / session_id

# 创建代码目录
(work_dir / "src").mkdir(exist_ok=True)
```

### 阶段2: 节点处理循环

对每个任务节点执行以下循环：

#### Step 1: 按需生成代码

```python
# 根据任务复杂度和需求，生成1个或多个代码

# 简单任务 - 生成1个代码
code = """
import json
with open("work_dir/node_02_output.json") as f:
    data = json.load(f)
result = [x for x in data if x['amount'] > 0]
with open("work_dir/node_03_output.json", 'w') as f:
    json.dump(result, f)
"""
with open("src/node_03_code.py", 'w') as f:
    f.write(code)
```

#### Step 2: 执行代码，得到产物

```python
import subprocess

subprocess.run(["python", "src/node_03_code.py"])
# 产物保存到 work_dir/node_03_output.json
```

#### Step 3: 查看产物

```python
with open("work_dir/node_03_output.json") as f:
    result = json.load(f)

# 观察结果
print(f"数据量: {len(result)}")
```

#### Step 4: API记录处理过程

```python
# 记录数据流
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "work_dir/node_02_output.json"},
        {"id": "output", "entity_type": "dataset", "location": "work_dir/node_03_output.json"}
    ],
    activities=[
        {"id": "act", "activity_type": "filter", "description": "过滤数据"}
    ],
    agents=[
        {"id": "agent", "agent_type": "python_code", "name": "node_03"}
    ],
    relations=[
        ("act", "input", "used"),
        ("output", "act", "wasGeneratedBy"),
        ("act", "agent", "wasAssociatedWith"),
        ("output", "input", "wasDerivedFrom")
    ]
)

# 记录步骤详情（必填）
# 同时自动生成/同步 step_001.json 等步骤主记录。
# 返回的 step_id 是规范步骤ID，后续如需引用步骤记录应使用它。
step_result = server.record_step_details(
    session_id=session_id,
    step_id="node_03",
    step_name="filter_data",
    description="过滤无效数据",
    code_files=["src/node_03_code.py"],
    commands_run=["python src/node_03_code.py"],
    input_files=["work_dir/node_02_output.json"],
    output_files=["work_dir/node_03_output.json"],
    parameters={"operation": "filter"}
)
step_id = step_result["step_id"]
```

#### Step 5: 反思并规划下一步

```python
# 基于产物结果规划下一步
if len(result) > 1000:
    next_node = "node_04: 聚合数据"
else:
    next_node = "node_04: 深入分析"

# 动态调整任务规划
task_plan.append(next_node)
```

### 阶段3: 结果验证

检查是否得到真实、具体、有深度的分析结果。

### 阶段4: 整合呈现

呈现完整trace流程: 原始数据 → 所有处理程序 → 所有中间产物 → 最终结果

## 禁止模式

❌ **禁止一次性pipeline**：不要编写一个完整的脚本一次性完成全部分析
❌ **禁止跳过步骤详情**：每步必须调用 `record_step_details()` - ⚠️ 必填，验证会检查
❌ **禁止不读产物**：每步完成后必须查看产物结果
❌ **禁止空泛结果**：必须得到真实、具体、有深度的分析结果

## 关系方向速查

| 关系 | 方向 | 示例 |
|------|------|------|
| `used` | Activity → Entity | `("act", "input", "used")` |
| `wasGeneratedBy` | Entity → Activity | `("output", "act", "wasGeneratedBy")` |
| `wasAssociatedWith` | Activity → Agent | `("act", "agent", "wasAssociatedWith")` |
| `wasDerivedFrom` | Entity → Entity | `("output", "input", "wasDerivedFrom")` |
