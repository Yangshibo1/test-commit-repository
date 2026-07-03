# OpenTrace MCP 工具完整指南

## 目录
- [概述](#概述)
- [架构说明](#架构说明)
- [可用工具](#可用工具)
- [调用方式](#调用方式)
- [执行流程](#执行流程)
- [使用示例](#使用示例)
- [数据存储结构](#数据存储结构)
- [故障排查](#故障排查)

---

## 概述

### OpenTrace MCP 是什么？

OpenTrace 是一个**数据血缘追踪工具**，用于记录和追溯数据分析过程中的数据处理步骤。它由两部分组成：

1. **核心库** (`opentrace/tracker.py`)：血缘追踪核心功能
2. **服务器接口** (`opentrace/mcp_server.py`)：对外提供的调用接口

### 当前状态

⚠️ **重要说明**：当前版本是**直接调用接口模式**，不是完整的 MCP 协议实现。

- ✅ 可以通过 Python 代码直接调用
- ⏳ 标准 MCP 协议集成待完善
- ⏳ Claude Code 自动集成待实现

---

## 架构说明

### 组件关系

```
┌─────────────────────────────────────────────────────────┐
│                    你的分析代码                          │
│  (data = load(); result = process(); ...)               │
└────────────────────┬────────────────────────────────────┘
                     │ 手动调用
                     ↓
┌─────────────────────────────────────────────────────────┐
│              OpenTraceServer (mcp_server.py)             │
│  - 提供调用接口                                          │
│  - 管理会话                                              │
│  - 调用核心追踪器                                        │
└────────────────────┬────────────────────────────────────┘
                     │ 内部调用
                     ↓
┌─────────────────────────────────────────────────────────┐
│               LineageTracker (tracker.py)                 │
│  - 核心追踪逻辑                                          │
│  - 文件存储管理                                          │
│  - 血缘链计算                                            │
└────────────────────┬────────────────────────────────────┘
                     │ 文件写入
                     ↓
┌─────────────────────────────────────────────────────────┐
│               .opentrace/ 目录                           │
│  session_xxx/                                            │
│    ├── meta.json                                         │
│    ├── step_*.json                                       │
│    ├── processing_*.json                                 │
│    └── export_*.json                                     │
└─────────────────────────────────────────────────────────┘
```

### 当前限制

```
不是：
  ✗ MCP 协议服务器
  ✗ 自动监控工具
  ✗ 后台守护进程
  ✗ 代码拦截器

是：
  ✓ Python 库
  ✓ 直接调用接口
  ✓ 手动记录工具
  ✓ 文件存储系统
```

---

## 可用工具

### 核心工具（10个）

| 工具名称 | 功能 | 类别 |
|---------|------|------|
| `init_session` | 初始化追踪会话 | 会话管理 |
| `record_step` | 记录处理步骤 | 步骤记录 |
| `record_mapping` | 记录数据映射 | 血缘记录 |
| `record_step_with_mappings` | 一步记录步骤和映射 | 组合操作 |
| `record_processing` | 记录数据处理（三要素） | 数据处理 |
| `trace_element` | 追踪元素血缘链 | 查询工具 |
| `analyze_error` | 分析错误来源 | 分析工具 |
| `get_session_summary` | 获取会话概览 | 查询工具 |
| `get_step_detail` | 获取步骤详情 | 查询工具 |
| `export_session` | 导出会话数据 | 导出工具 |

### 查询工具（3个）

| 工具名称 | 功能 |
|---------|------|
| `get_processing_detail` | 获取数据处理详情 |
| `list_processings` | 列出处理记录 |
| `get_session` | 获取会话追踪器 |

---

## 调用方式

### 方式1：直接导入调用

```python
from opentrace.mcp_server import OpenTraceServer

# 创建服务器实例
server = OpenTraceServer('.opentrace')

# 调用工具
result = server.init_session(
    task_description="分析任务",
    data_path="data.json",
    data_type="json"
)

print(result['session_id'])
```

### 方式2：使用单例

```python
from opentrace.mcp_server import get_server

# 获取单例实例
server = get_server('.opentrace')

# 调用工具
session = server.init_session(...)
```

### 方式3：命令行工具

```bash
# 查看会话状态
python opentrace_cli.py status

# 启动新会话
python opentrace_cli.py start

# 导出会话
python opentrace_cli.py export <session_id>
```

---

## 执行流程

### 典型使用流程

```
1. 初始化
   └─> server = OpenTraceServer()
   └─> session = server.init_session(...)

2. 数据加载（自动记录）
   └─> 初始化时自动创建 step_000

3. 数据处理（手动记录）
   └─> server.record_step(...)        # 记录步骤
   └─> server.record_processing(...)  # 记录三要素

4. 血缘记录（可选）
   └─> server.record_mapping(...)     # 记录映射

5. 查询分析
   └─> server.trace_element(...)      # 追踪血缘
   └─> server.analyze_error(...)       # 分析错误

6. 导出分享
   └─> server.export_session(...)    # 导出会话
```

### 生命周期

```
创建会话 → 记录操作 → 查询分析 → 导出归档
    ↓          ↓          ↓          ↓
 session_id  step_*    trace_*    export_*.json
            processing_*
```

---

## 使用示例

### 示例1：基础追踪

```python
from opentrace.mcp_server import OpenTraceServer

# 1. 初始化
server = OpenTraceServer('.opentrace')
session = server.init_session("数据分析", "data.json", "json")
session_id = session['session_id']

# 2. 记录处理步骤
step = server.record_step(
    session_id,
    step_name="数据清洗",
    operation="fillna",
    description="填充缺失值"
)

# 3. 记录血缘映射
server.record_mapping(
    session_id,
    step['step_id'],
    from_ids=["raw_data"],
    to_id="cleaned_data",
    operation="fill_missing"
)

# 4. 导出结果
server.export_session(session_id)
```

### 示例2：完整数据处理记录

```python
from opentrace.mcp_server import OpenTraceServer
import json

server = OpenTraceServer('.opentrace')
session = server.init_session("分析任务", "data.json", "json")
session_id = session['session_id']

# 你的分析代码
data = json.load(open("data.json"))
filtered = [x for x in data if x['value'] > 100]

# 记录完整的三要素
server.record_processing(
    session_id=session_id,
    step_id="step_001",
    input_spec={
        "source": "data",
        "filter_condition": "value > 100",
        "total_count_before": len(data)
    },
    algorithm_spec={
        "type": "filter",
        "language": "python",
        "code": "filtered = [x for x in data if x['value'] > 100]",
        "logic_description": "筛选值大于100的记录"
    },
    result_data={
        "count": len(filtered),
        "sample": filtered[:10]
    }
)
```

### 示例3：血缘追踪

```python
# 假设已经记录了数据处理过程

# 追踪特定元素
trace_result = server.trace_element(
    session_id=session_id,
    element_id="cleaned_data"
)

print(f"血缘链长度: {trace_result['chain_length']}")
for link in trace_result['chain']:
    print(f"  {link['step']}: {link['operation']}")
```

### 示例4：错误分析

```python
# 分析错误来源
analysis = server.analyze_error(
    session_id=session_id,
    error_message="发现 NaN 值",
    affected_element="final_result"
)

print(f"可能的原因:")
for source in analysis['analysis']['possible_sources']:
    print(f"  - {source['reason']}")
```

---

## 数据存储结构

### 目录结构

```
.opentrace/
├── session_20260615_120000/
│   ├── meta.json                    # 会话元信息
│   ├── step_000.json                # 数据加载步骤
│   ├── step_001.json                # 处理步骤
│   ├── processing_step_001.json     # 数据处理记录（三要素）
│   ├── processing_step_001_result.json  # 大结果外存文件
│   ├── working_data.json            # 工作数据副本
│   └── export_20260615_120530.json  # 导出文件
└── session_20260615_130000/
    └── ...
```

### 文件格式

#### meta.json
```json
{
  "session_id": "session_20260615_120000",
  "created_at": "2026-06-15T12:00:00.000000",
  "total_steps": 2
}
```

#### step_*.json
```json
{
  "step_id": "step_001",
  "step_name": "数据清洗",
  "operation": "fillna",
  "description": "填充缺失值",
  "timestamp": "2026-06-15T12:00:01.000000",
  "metadata": {},
  "mappings": []
}
```

#### processing_*.json
```json
{
  "processing_id": "processing_step_001",
  "step_id": "step_001",
  "timestamp": "2026-06-15T12:00:01.000000",
  "input": {
    "source": "events",
    "total_count_before": 185147
  },
  "algorithm": {
    "type": "filter",
    "language": "python",
    "code": "filtered = [x for x in data if condition]"
  },
  "result": {
    "format": "inline",
    "data": {
      "count": 191,
      "sample": [...]
    }
  }
}
```

---

## 故障排查

### 常见问题

#### Q1: 调用工具时返回 "会话不存在"

**原因**：session_id 错误或会话已过期

**解决**：
```python
# 检查会话是否存在
summary = server.get_session_summary(session_id)
if 'error' in summary:
    print(f"错误: {summary['error']}")
```

#### Q2: 处理记录查询返回错误

**原因**：processing_id 错误

**解决**：
```python
# 先列出所有处理记录
processings = server.list_processings(session_id)
for proc in processings['processings']:
    print(f"{proc['processing_id']}: {proc['algorithm_type']}")
```

#### Q3: 文件编码错误

**原因**：Windows 系统默认编码问题

**解决**：确保使用 UTF-8 编码
```python
# 读取文件时指定编码
with open('file.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
```

#### Q4: 大结果集性能问题

**原因**：结果数据超过阈值

**解决**：调整阈值参数
```python
server.record_processing(
    ...,
    large_result_threshold=5000  # 提高阈值
)
```

---

## API 参考

### init_session

初始化血缘追踪会话

```python
server.init_session(
    task_description: str,    # 任务描述
    data_path: str,          # 数据文件路径
    data_type: str = "json"  # 数据类型 (json/csv)
) -> Dict[str, Any]
```

**返回值**：
```json
{
  "session_id": "session_20260615_120000",
  "task_description": "分析任务",
  "status": "initialized",
  "total_rows": 185147,
  "structure": {...}
}
```

### record_processing

记录数据处理步骤（包含 input/algorithm/result 三要素）

```python
server.record_processing(
    session_id: str,              # 会话ID
    step_id: str,                 # 关联的步骤ID
    input_spec: Dict[str, Any],   # 输入规格
    algorithm_spec: Dict[str, Any],# 算法规格
    result_data: Dict[str, Any],  # 结果数据
    large_result_threshold: int = 1000  # 外存阈值
) -> Dict[str, Any]
```

**input_spec 格式**：
```json
{
  "source": "events",
  "source_type": "json_array",
  "filter_condition": "value > 100",
  "total_count_before": 185147
}
```

**algorithm_spec 格式**：
```json
{
  "type": "filter",
  "language": "python",
  "code": "filtered = [x for x in data if condition]",
  "logic_description": "筛选满足条件的记录"
}
```

### trace_element

追踪数据元素的血缘链

```python
server.trace_element(
    session_id: str,      # 会话ID
    element_id: str,     # 数据元素ID
    max_depth: int = 50  # 最大追踪深度
) -> Dict[str, Any]
```

**返回值**：
```json
{
  "element_id": "cleaned_data",
  "chain_length": 3,
  "chain": [
    {
      "step": "数据清洗",
      "step_id": "step_001",
      "operation": "fillna",
      "from": ["raw_data"],
      "to": "cleaned_data",
      "timestamp": "2026-06-15T12:00:01.000000"
    }
  ],
  "status": "success"
}
```

---

## 总结

### 当前状态

- ✅ **功能完整**：10个核心工具全部可用
- ✅ **直接调用**：可以通过 Python 代码直接使用
- ✅ **文件存储**：数据持久化到本地文件系统
- ⏳ **MCP 协议**：标准 MCP 集成待完善
- ⏳ **自动监控**：Claude Code 自动集成待实现

### 使用建议

**适合使用的场景**：
- 需要追溯数据处理过程
- 需要验证分析结果
- 需要分享分析过程
- 需要长期保存分析记录

**使用步骤**：
1. 导入 OpenTraceServer
2. 初始化会话
3. 在分析代码中调用记录方法
4. 查询和导出结果

### 下一步

如需实现真正的 MCP 协议和自动监控，需要：
1. 实现标准 MCP 服务器
2. 集成到 Claude Code
3. 实现代码自动拦截和记录
