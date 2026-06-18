# OpenTrace MCP 工具参考手册

## 工具清单

| # | 工具名称 | 功能分类 |
|---|---------|---------|
| 1 | `init_session` | 会话管理 |
| 2 | `record_step` | 步骤记录 |
| 3 | `record_mapping` | 血缘记录 |
| 4 | `record_step_with_mappings` | 组合操作 |
| 5 | `record_processing` | 数据处理 |
| 6 | `trace_element` | 查询工具 |
| 7 | `analyze_error` | 分析工具 |
| 8 | `get_session_summary` | 查询工具 |
| 9 | `get_step_detail` | 查询工具 |
| 10 | `export_session` | 导出工具 |
| 11 | `get_processing_detail` | 查询工具 |
| 12 | `list_processings` | 查询工具 |

---

## 工具 #1: init_session

### 功能是什么
初始化一个新的数据血缘追踪会话，加载数据文件并创建存储目录。

### 何时调用
- 在开始任何数据分析任务之前
- 每次新的分析任务创建一个新会话
- 一次分析任务只调用一次

### 如何调用
```python
server.init_session(
    task_description="分析 SwiftWren 事件传递链",
    data_path="VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/MC2 data.json",
    data_type="json"
)
```

### LLM 调用参数
```json
{
  "task_description": {
    "type": "string",
    "required": true,
    "description": "分析任务的描述，说明要做什么分析"
  },
  "data_path": {
    "type": "string",
    "required": true,
    "description": "数据文件的完整路径"
  },
  "data_type": {
    "type": "string",
    "required": false,
    "default": "json",
    "enum": ["json", "csv"],
    "description": "数据文件类型"
  }
}
```

### 输出结果
```json
{
  "session_id": "session_20260615_110055",
  "task_description": "分析 SwiftWren 事件传递链",
  "status": "initialized",
  "total_rows": 185147,
  "structure": {
    "type": "dict",
    "keys": ["description", "events"],
    "fields": {...}
  },
  "working_copy": ".opentrace/session_xxx/working_data.json"
}
```

**错误返回**：
```json
{
  "error": "文件不存在",
  "status": "failed"
}
```

---

## 工具 #2: record_step

### 功能是什么
记录一个数据处理步骤（如"数据清洗"、"数据筛选"），只记录步骤信息，不记录详细数据。

### 何时调用
- 完成一个数据处理操作后
- 需要记录分析过程的某个阶段时
- 配合 `record_processing` 使用

### 如何调用
```python
server.record_step(
    session_id="session_20260615_110055",
    step_name="数据清洗",
    operation="fillna",
    description="填充缺失的 age 字段"
)
```

### LLM 调用参数
```json
{
  "session_id": {
    "type": "string",
    "required": true,
    "description": "会话ID，由 init_session 返回"
  },
  "step_name": {
    "type": "string",
    "required": true,
    "description": "步骤名称，简短描述这一步做什么"
  },
  "operation": {
    "type": "string",
    "required": true,
    "description": "操作类型，如 filter, aggregate, transform 等"
  },
  "description": {
    "type": "string",
    "required": false,
    "description": "详细描述这一步的操作"
  },
  "metadata": {
    "type": "object",
    "required": false,
    "description": "额外的元数据信息"
  }
}
```

### 输出结果
```json
{
  "step_id": "step_001",
  "step_name": "数据清洗",
  "status": "recorded"
}
```

---

## 工具 #3: record_mapping

### 功能是什么
记录数据元素之间的血缘映射关系（如"raw_data → cleaned_data"）。

### 何时调用
- 需要追踪数据元素的来源时
- 记录数据转换关系时
- 配合 `record_step` 使用

### 如何调用
```python
server.record_mapping(
    session_id="session_20260615_110055",
    step_id="step_001",
    from_ids=["raw_data[0].age", "raw_data[1].age"],
    to_id="cleaned_data[0].age",
    operation="fillna(0)",
    value_info={
      "raw_data[0].age": {"old": null, "new": 0},
      "raw_data[1].age": {"old": 25, "new": 25}
    }
)
```

### LLM 调用参数
```json
{
  "session_id": {
    "type": "string",
    "required": true,
    "description": "会话ID"
  },
  "step_id": {
    "type": "string",
    "required": true,
    "description": "步骤ID，由 record_step 返回"
  },
  "from_ids": {
    "type": "array",
    "required": true,
    "items": {"type": "string"},
    "description": "源数据ID列表"
  },
  "to_id": {
    "type": "string",
    "required": true,
    "description": "目标数据ID"
  },
  "operation": {
    "type": "string",
    "required": true,
    "description": "操作描述"
  },
  "value_info": {
    "type": "object",
    "required": false,
    "description": "值的变化信息"
  }
}
```

### 输出结果
```json
{
  "status": "recorded",
  "mapping_count": 2,
  "to_id": "cleaned_data[0].age"
}
```

---

## 工具 #4: record_step_with_mappings

### 功能是什么
一步同时记录步骤和映射关系，便捷方法。

### 何时调用
- 需要同时记录步骤和映射时
- 简化代码时使用

### 如何调用
```python
server.record_step_with_mappings(
    session_id="session_20260615_110055",
    step_name="数据清洗",
    operation="fillna",
    description="填充缺失值",
    mappings=[
      {
        "from": ["raw_data[0].age"],
        "to": "cleaned_data[0].age",
        "operation": "fillna(0)"
      }
    ]
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "step_name": {"type": "string", "required": true},
  "operation": {"type": "string", "required": true},
  "description": {"type": "string", "required": true},
  "mappings": {
    "type": "array",
    "required": true,
    "items": {
      "from": {"type": "array"},
      "to": {"type": "string"},
      "operation": {"type": "string"}
    }
  },
  "metadata": {"type": "object", "required": false}
}
```

### 输出结果
```json
{
  "step_id": "step_001",
  "step_name": "数据清洗",
  "mappings_count": 1,
  "status": "recorded"
}
```

---

## 工具 #5: record_processing

### 功能是什么
**核心工具**：记录数据处理的完整三要素（input/algorithm/result），提供完整的数据支撑。

### 何时调用
- 需要完整记录数据处理过程时
- 需要追溯数据来源时
- 需要验证分析结果时
- 学术研究需要可重复性时

### 如何调用
```python
server.record_processing(
    session_id="session_20260615_110055",
    step_id="step_001",
    input_spec={
        "source": "events",
        "source_type": "json_array",
        "filter_condition": "details contains 'SwiftWren'",
        "total_count_before": 185147
    },
    algorithm_spec={
        "type": "filter_and_sort",
        "language": "python",
        "code": "swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]",
        "logic_description": "筛选包含SwiftWren的事件并按时间排序"
    },
    result_data={
        "event_ids": [21202, 21208, ..., 373913],
        "count": 191
    },
    large_result_threshold=1000
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "step_id": {"type": "string", "required": true},
  "input_spec": {
    "type": "object",
    "required": true,
    "description": "输入规格，包含 source, source_type, filter_condition, total_count_before 等"
  },
  "algorithm_spec": {
    "type": "object",
    "required": true,
    "description": "算法规格，包含 type, language, code, logic_description 等"
  },
  "result_data": {
    "type": "object",
    "required": true,
    "description": "结果数据，包含处理结果"
  },
  "large_result_threshold": {
    "type": "integer",
    "required": false,
    "default": 1000,
    "description": "超过此数量则外存为文件"
  }
}
```

### 输出结果
```json
{
  "processing_id": "processing_step_001",
  "step_id": "step_001",
  "status": "recorded"
}
```

---

## 工具 #6: trace_element

### 功能是什么
追踪特定数据元素的完整血缘链，回答"这个数据从哪里来"的问题。

### 何时调用
- 需要了解某个结果的来源时
- 需要验证数据处理的正确性时
- 分析错误来源时

### 如何调用
```python
server.trace_element(
    session_id="session_20260615_110055",
    element_id="saidit_post_john_windward",
    max_depth=50
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "element_id": {
    "type": "string",
    "required": true,
    "description": "要追踪的数据元素ID"
  },
  "max_depth": {
    "type": "integer",
    "required": false,
    "default": 50,
    "description": "最大追踪深度"
  }
}
```

### 输出结果
```json
{
  "element_id": "saidit_post_john_windward",
  "chain_length": 3,
  "chain": [
    {
      "step": "文件创建",
      "step_id": "step_001",
      "operation": "create_file",
      "from": ["SwiftWren.txt"],
      "to": "saidit_post_john_windward",
      "timestamp": "2026-05-17T19:21:15",
      "value_info": {"publisher": "person:john_windward"}
    },
    {
      "step": "任务传递链",
      "step_id": "step_002",
      "operation": "queue_subordinate_task",
      "from": ["events"],
      "to": "SwiftWren.txt",
      "timestamp": "2026-05-09T23:02:01"
    }
  ],
  "status": "success"
}
```

---

## 工具 #7: analyze_error

### 功能是什么
分析错误的可能来源，基于血缘链推断问题所在。

### 何时调用
- 出现错误需要分析原因时
- 数据结果异常时
- 需要定位问题步骤时

### 如何调用
```python
server.analyze_error(
    session_id="session_20260615_110055",
    error_message="发现 NaN 值",
    affected_element="final_result",
    context={"operation": "aggregate"}
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "error_message": {
    "type": "string",
    "required": true,
    "description": "错误信息描述"
  },
  "affected_element": {
    "type": "string",
    "required": false,
    "description": "受影响的数据元素ID"
  },
  "context": {
    "type": "object",
    "required": false,
    "description": "额外上下文信息"
  }
}
```

### 输出结果
```json
{
  "analysis": {
    "error_message": "发现 NaN 值",
    "affected_element": "final_result",
    "timestamp": "2026-06-15T12:00:00",
    "lineage_chain": [...],
    "possible_sources": [
      {
        "step": "数据除法",
        "reason": "可能存在除零错误",
        "operation": "division"
      },
      {
        "step": "类型转换",
        "reason": "类型转换可能失败",
        "operation": "astype"
      }
    ],
    "suggestions": [
      "检查除数是否为0，添加除零保护",
      "检查填充策略，确保填充值合理"
    ]
  },
  "status": "success"
}
```

---

## 工具 #8: get_session_summary

### 功能是什么
获取会话的概览信息，包括所有步骤列表。

### 何时调用
- 需要了解会话整体情况时
- 需要查看所有步骤时
- 开始新的分析前了解历史时

### 如何调用
```python
server.get_session_summary(session_id="session_20260615_110055")
```

### LLM 调用参数
```json
{
  "session_id": {
    "type": "string",
    "required": true,
    "description": "会话ID"
  }
}
```

### 输出结果
```json
{
  "summary": {
    "session_id": "session_20260615_110055",
    "created_at": "2026-06-15T11:00:55",
    "total_steps": 5,
    "steps": [
      {
        "step_id": "step_000",
        "name": "数据加载",
        "operation": "load_json",
        "mappings_count": 0,
        "timestamp": "2026-06-15T11:00:55"
      },
      {
        "step_id": "step_001",
        "name": "文件创建",
        "operation": "create_file",
        "mappings_count": 0,
        "timestamp": "2026-06-15T11:00:56"
      }
    ]
  },
  "status": "success"
}
```

---

## 工具 #9: get_step_detail

### 功能是什么
获取某个步骤的详细信息，包括元数据和映射关系。

### 何时调用
- 需要查看某个步骤的详细信息时
- 需要了解步骤的映射关系时
- 验证步骤的元数据时

### 如何调用
```python
server.get_step_detail(
    session_id="session_20260615_110055",
    step_id="step_001"
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "step_id": {
    "type": "string",
    "required": true,
    "description": "步骤ID"
  }
}
```

### 输出结果
```json
{
  "detail": {
    "step_id": "step_001",
    "step_name": "文件创建",
    "operation": "create_file",
    "description": "Emma Harbor 创建 SwiftWren.txt 文件",
    "timestamp": "2026-06-15T11:00:56",
    "metadata": {
      "creator": "Agent/person:emma_harbor",
      "file": "SwiftWren.txt",
      "size_kb": 30.6
    },
    "mappings": [],
    "mappings_count": 0
  },
  "status": "success"
}
```

---

## 工具 #10: export_session

### 功能是什么
导出会话的完整数据为单个文件，便于分享和归档。

### 何时调用
- 分析完成需要分享结果时
- 需要归档会话数据时
- 需要备份会话时

### 如何调用
```python
server.export_session(
    session_id="session_20260615_110055",
    format="json"
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "format": {
    "type": "string",
    "required": false,
    "default": "json",
    "enum": ["json"],
    "description": "导出格式"
  }
}
```

### 输出结果
```json
{
  "export_path": ".opentrace/session_20260615_110055/export_20260615_110100.json",
  "status": "success"
}
```

---

## 工具 #11: get_processing_detail

### 功能是什么
获取数据处理记录的详细信息，包括 input/algorithm/result 三要素。

### 何时调用
- 需要查看数据处理的完整信息时
- 需要验证数据处理过程时
- 需要了解算法细节时

### 如何调用
```python
server.get_processing_detail(
    session_id="session_20260615_110055",
    processing_id="processing_step_001"
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "processing_id": {
    "type": "string",
    "required": true,
    "description": "处理记录ID"
  }
}
```

### 输出结果
```json
{
  "detail": {
    "processing_id": "processing_step_001",
    "step_id": "step_001",
    "timestamp": "2026-06-15T11:00:56",
    "input": {
      "source": "events",
      "source_type": "json_array",
      "filter_condition": "details contains 'SwiftWren'",
      "total_count_before": 185147
    },
    "algorithm": {
      "type": "filter_and_sort",
      "language": "python",
      "code": "swiftwren_events = [e for e in events if 'SwiftWren' in json.dumps(e.get('details', {}))]",
      "logic_description": "筛选包含SwiftWren的事件并按时间排序"
    },
    "result": {
      "format": "inline",
      "data": {
        "event_ids": [21202, 21208, ..., 373913],
        "count": 191
      },
      "item_count": 191
    }
  },
  "status": "success"
}
```

---

## 工具 #12: list_processings

### 功能是什么
列出会话中的所有数据处理记录，可以按步骤筛选。

### 何时调用
- 需要查看所有数据处理记录时
- 需要找到特定的处理记录时
- 需要了解处理记录的概览时

### 如何调用
```python
server.list_processings(
    session_id="session_20260615_110055",
    step_id="step_001"  # 可选，筛选特定步骤
)
```

### LLM 调用参数
```json
{
  "session_id": {"type": "string", "required": true},
  "step_id": {
    "type": "string",
    "required": false,
    "description": "可选，筛选特定步骤的处理记录"
  }
}
```

### 输出结果
```json
{
  "processings": [
    {
      "processing_id": "processing_step_001",
      "step_id": "step_001",
      "timestamp": "2026-06-15T11:00:56",
      "algorithm_type": "filter_and_sort",
      "result_format": "inline",
      "item_count": 191
    },
    {
      "processing_id": "processing_step_002",
      "step_id": "step_002",
      "timestamp": "2026-06-15T11:01:00",
      "algorithm_type": "aggregate_count",
      "result_format": "external_file",
      "item_count": 11500
    }
  ],
  "count": 2,
  "status": "success"
}
```

---

## 调用顺序建议

### 典型分析流程

```
1. init_session()          # 开始会话
   ↓
2. record_step()           # 记录第一步
   ↓
3. record_processing()     # 记录详细处理过程（可选）
   ↓
4. record_mapping()        # 记录映射关系（可选）
   ↓
5. record_step()           # 记录第二步
   ↓
...（重复步骤2-4）
   ↓
6. trace_element()         # 追踪血缘（查询）
   ↓
7. analyze_error()         # 分析错误（查询）
   ↓
8. export_session()        # 导出结果
```

### 工具依赖关系

```
init_session() 必须最先调用
   ↓
record_*() 系列工具需要 session_id
   ↓
trace_element() 和 analyze_error() 需要先有记录
   ↓
export_session() 最后调用
```

---

## 错误处理

### 通用错误格式

所有工具在出错时返回：

```json
{
  "error": "错误描述信息",
  "status": "failed"
}
```

### 常见错误

| 错误信息 | 原因 | 解决方法 |
|---------|------|---------|
| "会话不存在" | session_id 错误 | 检查 session_id 是否正确 |
| "步骤不存在" | step_id 错误 | 检查 step_id 是否正确 |
| "处理记录不存在" | processing_id 错误 | 使用 list_processings() 查看正确的 ID |
| "文件不存在" | data_path 错误 | 检查数据文件路径是否正确 |
| "不支持的数据类型" | data_type 错误 | 使用 "json" 或 "csv" |

---

## 总结

### 核心概念

1. **会话 (Session)**：一次完整的数据分析任务
2. **步骤 (Step)**：分析过程中的一个操作阶段
3. **映射 (Mapping)**：数据元素之间的转换关系
4. **处理 (Processing)**：包含 input/algorithm/result 的完整记录

### 使用建议

- **必用工具**：`init_session`, `record_step`, `export_session`
- **推荐工具**：`record_processing`（提供完整数据支撑）
- **查询工具**：`trace_element`, `analyze_error`, `get_session_summary`
- **按需使用**：`record_mapping`, `get_processing_detail`, `list_processings`
