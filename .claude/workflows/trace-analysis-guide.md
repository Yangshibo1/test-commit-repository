# 数据血缘追踪分析工作流

## 概述

这个工作流定义了一种标准的数据分析方法，确保每一步数据操作都被记录到 OpenTrace 系统中，形成完整的数据血缘图谱。

## 核心原则

1. **Agent 逐步分析** - 每轮只执行一个明确的数据处理动作，禁止一次性 pipeline 脚本直接完成全部分析
2. **每步操作生成中间文件** - 不要只在内存中处理，每次操作都保存结果
3. **每步调用 trace 系统** - 使用 `server.record_prov_relation()` 记录 DAG
4. **每步记录详情** - 使用 `server.record_step_details()` 记录代码、命令、输入输出和参数
5. **每步结束后读取输出** - agent 必须检查本步结果文件，不能在未观察结果时预设后续步骤
6. **每步结束后反思决策** - agent 必须总结本步发现，并基于结果决定下一步分析方向
7. **数据流转清晰** - 明确每步读取哪些文件，输出哪些文件
   - 支持读取原始数据
   - 支持读取多个中间结果
   - 支持回溯重新分析
8. **迭代式分析** - 根据上一步结果决定下一步方向

## 禁止模式

不要编写一个完整 Python pipeline 一次性完成加载、过滤、追踪、报告生成的全部工作。允许为单个步骤编写小脚本或一次性命令，但每个步骤完成后必须回到 agent 循环：读取输出、总结发现、记录 trace 和 step details、再决定下一步。

## 快速开始

### 方法1: 使用 Agent 迭代模板

```python
from opentrace.mcp_server import get_server
from opentrace.prov_visualizer import visualize_prov_dag
import json
from pathlib import Path

# 初始化
server = get_server()
result = server.init_session(
    task_description="你的分析任务",
    data_path="data.json",
    data_type="json"
)
session_id = result["session_id"]
work_dir = Path(server.base_dir) / session_id

# Step 1: 加载数据并记录
with open("data.json") as f:
    data = json.load(f)
output = work_dir / "step1_loaded.json"
with open(output, 'w') as f:
    json.dump(data, f)

server.record_step(
    session_id=session_id,
    step_name="load_data",
    operation="load",
    description="加载原始数据并保存为第一个中间文件",
    metadata={"output_file": str(output)}
)

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw", "entity_type": "dataset", "location": "data.json"},
        {"id": "loaded", "entity_type": "dataset", "location": str(output)}
    ],
    activities=[
        {"id": "act1", "activity_type": "load", "description": "加载数据"}
    ],
    agents=[
        {"id": "agent1", "agent_type": "script", "name": "step1"}
    ],
    relations=[
        ("act1", "raw", "used"),
        ("loaded", "act1", "wasGeneratedBy"),
        ("act1", "agent1", "wasAssociatedWith"),
        ("loaded", "raw", "wasDerivedFrom")
    ]
)

server.record_step_details(
    session_id=session_id,
    step_id="step_1",
    step_name="load_data",
    description="加载原始数据并保存为中间文件；本步完成后 agent 需要读取输出并决定下一步",
    code_files=["<本步脚本或命令来源>"],
    commands_run=["<本步运行的命令>"],
    input_files=["data.json"],
    output_files=[str(output)],
    parameters={"next_decision_required": True}
)

# Agent 必须读取 step1_loaded.json，总结数据规模/关键字段，再决定 Step 2。

# Step 2: 处理数据（读取 step1，输出 step2）
with open(work_dir / "step1_loaded.json") as f:
    data = json.load(f)
filtered = [x for x in data if condition(x)]
output = work_dir / "step2_filtered.json"
with open(output, 'w') as f:
    json.dump(filtered, f)

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "上一步输出文件"},
        {"id": "output", "entity_type": "dataset", "location": "当前步骤输出文件", "attributes": {"count": len(filtered)}}
    ],
    activities=[
        {"id": "act", "activity_type": "filter", "description": "过滤数据"}
    ],
    agents=[
        {"id": "agent", "agent_type": "script", "name": "step2"}
    ],
    relations=[
        ("act", "input", "used"),              # 活动 使用输入实体 ✓
        ("output", "act", "wasGeneratedBy"),   # 输出实体由活动生成 ✓
        ("act", "agent", "wasAssociatedWith"), # 活动关联代理 ✓
        ("output", "input", "wasDerivedFrom")  # 输出源自输入 ✓
    ]
)

server.record_step_details(
    session_id=session_id,
    step_id="step_2",
    step_name="filter_data",
    description="基于上一步输出执行一次筛选；本步完成后 agent 需要读取筛选结果并决定下一步",
    code_generated=["filtered = [x for x in data if condition(x)]"],
    code_files=["<本步脚本或命令来源>"],
    commands_run=["<本步运行的命令>"],
    input_files=[str(work_dir / "step1_loaded.json")],
    output_files=[str(output)],
    parameters={"decision_after_reading_output": "继续追踪、回溯原始数据、或结束分析"}
)

# Agent 必须读取 step2_filtered.json，总结发现，并明确下一步理由。

# 最终: 生成可视化
visualize_prov_dag(str(work_dir), str(work_dir / "viz.txt")
```

## 每步 Agent 循环

每个数据处理步骤必须按以下顺序执行：

1. 明确本步问题和输入文件。
2. 运行一个小脚本、命令或工具完成本步处理。
3. 保存本步输出到 session 工作目录。
4. 调用 `server.record_step()` 记录基础步骤。
5. 调用 `server.record_prov_relation()` 记录输入输出文件关系。
6. 调用 `server.record_step_details()` 记录代码、命令、参数、输入和输出。
7. 读取本步输出文件。
8. 总结本步发现。
9. 基于已观察结果决定下一步；如果结果不足，说明要回溯或补充哪类分析。

只有最后一步才能生成 `final_report.json`。最终报告必须基于已经读取和记录过的中间结果，不能由一次性 pipeline 直接跳过中间观察过程生成。

## 记录步骤详情

每步还需要记录详细信息：

```python
# 记录步骤详情（包含代码、命令、描述）
server.record_step_details(
    session_id=session_id,
    step_id="step_1",
    step_name="filter_events",
    description="过滤出 SaidIT 相关事件，保留关键字段",
    code_generated=[
        "filtered = [e for e in events if 'saidit' in str(e).lower()]",
        "result = {'events': filtered, 'count': len(filtered)}"
    ],
    code_files=["step1_filter.py"],
    commands_run=["python step1_filter.py"],
    input_files=["loaded_data.json"],
    output_files=["filtered_events.json"],
    parameters={"filter": "saidit", "fields": ["id", "when", "parties"]}
)
```

## 多输入示例

```python
# Step 3: 合并多个中间结果
with open(work_dir / "step1_filtered.json") as f:
    filtered = json.load(f)
with open(work_dir / "step2_stats.json") as f:
    stats = json.load(f)

# 合并处理
result = {"filtered_count": len(filtered), "stats": stats}
output = work_dir / "step3_merged.json"
with open(output, 'w') as f:
    json.dump(result, f)

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input1", "entity_type": "dataset", "location": str(work_dir / "step1_filtered.json")},
        {"id": "input2", "entity_type": "dataset", "location": str(work_dir / "step2_stats.json")},
        {"id": "output", "entity_type": "dataset", "location": str(output)}
    ],
    activities=[{"id": "act3", "activity_type": "aggregate", "description": "合并结果"}],
    agents=[{"id": "agent3", "agent_type": "script", "name": "step3"}],
    relations=[
        ("act3", "input1", "used"),
        ("act3", "input2", "used"),
        ("output", "act3", "wasGeneratedBy"),
        ("act3", "agent3", "wasAssociatedWith"),
        ("output", "input1", "wasDerivedFrom"),
        ("output", "input2", "wasDerivedFrom")
    ]
)
```

## 回溯原始数据示例

```python
# Step 4: 从原始数据重新分析
with open("data.json") as f:  # 直接读原始数据
    raw = json.load(f)

new_analysis = process_raw(raw)
output = work_dir / "step4_reanalysis.json"
with open(output, 'w') as f:
    json.dump(new_analysis, f)

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_input", "entity_type": "dataset", "location": "data.json"},
        {"id": "output", "entity_type": "dataset", "location": str(output)}
    ],
    activities=[{"id": "act4", "activity_type": "analyze", "description": "重新分析原始数据"}],
    agents=[{"id": "agent4", "agent_type": "script", "name": "step4"}],
    relations=[
        ("act4", "raw_input", "used"),
        ("output", "act4", "wasGeneratedBy"),
        ("act4", "agent4", "wasAssociatedWith"),
        ("output", "raw_input", "wasDerivedFrom")
    ]
)
```

## PROV 关系说明

### 实体类型 (entity_type)
- `dataset`: 数据集/文件
- `artifact`: 最终产出物（报告、图表等）

### 活动类型 (activity_type)
- `load`: 加载数据
- `filter`: 过筛选选
- `transform`: 转换处理
- `analyze`: 分析计算
- `trace`: 追踪溯源
- `compare`: 比较对照
- `aggregate`: 汇总合并

### 关系类型（重要！顺序和方向）

| 关系 | 方向 | 示例 | 说明 |
|------|------|------|------|
| `used` | Activity → Entity | `("act", "input", "used")` | 活动使用输入实体 |
| `wasGeneratedBy` | Entity → Activity | `("output", "act", "wasGeneratedBy")` | 输出实体由活动生成 |
| `wasAssociatedWith` | Activity → Agent | `("act", "agent", "wasAssociatedWith")` | 活动关联代理 |
| `wasDerivedFrom` | Entity → Entity | `("output", "input", "wasDerivedFrom")` | 输出源自输入 |

**⚠️ 常见错误：**
```python
# ❌ 错误：activity 使用自己的输出
relations=[("act", "output", "used")]

# ✓ 正确：activity 使用输入实体
relations=[("act", "input", "used")]
```

**正确的数据流：**
```
输入实体 --[used]-- 活动 --[wasGeneratedBy]-- 输出实体
                ↓
           [wasAssociatedWith]
                ↓
              代理
```

## 输出文件

### 数据文件
- `step1_*.json` - 第1步输出
- `step2_*.json` - 第2步输出
- ...
- `final_report.json` - 最终报告

### PROV 文件
- `prov_dag.json` - DAG 元数据
- `prov_nodes.json` - 节点信息
- `prov_edges.json` - 边关系
- `pipeline_visualization.txt` - 可视化（含 Mermaid 代码）

## 成功案例

参见 `VAST_Challenge_2026_MC2/mc2_pipeline_analysis.py` 中的完整实现。

## 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| "源节点不存在" | 临时 ID 未提供 | 在 entities/activities/agents 中添加 `id` 字段 |
| "无效的关系类型" | 关系方向错误 | 检查关系是否符合 PROV 标准 |
| "会话不存在" | session_id 错误 | 使用 `server.list_sessions()` 查看现有会话 |
