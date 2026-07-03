# 数据血缘追踪系统设计

## 概述

本系统设计用于追踪数据分析工作流中数据元素的完整变换链路，支持列血缘、行血缘、JSON字段血缘和混合血缘。

---

## 核心概念

### 统一的数据定位

使用"路径"统一表示任何数据元素的位置：

```
表格数据:     column_name[row_id]
JSON 数据:    user.profile.age
嵌套数据:     data.users[*].orders[*].amount
```

### 三种血缘类型

| 类型 | 追踪内容 | 标识符 | 应用场景 |
|------|---------|--------|----------|
| **列血缘** | 列的变换链 | column_name | 字段异常、类型问题 |
| **行血缘** | 行的过滤/变换链 | row_id | 数据丢失、行异常 |
| **字段血缘** | JSON路径变换链 | json_path | 嵌套数据处理 |

---

## 数据结构

### 统一血缘记录

```python
lineage_record = {
    # 基础信息
    "step_id": "step_003",
    "step_name": "数据清洗",
    "timestamp": "2024-01-15T10:30:00",
    
    # 列血缘
    "column_lineage": {
        "column_name": {
            "type": "transform|derived|aggregated|original",
            "derived_from": ["source_column"],
            "transformation": "操作描述",
            "logic": "业务逻辑说明"
        }
    },
    
    # 行血缘
    "row_lineage": {
        "type": "filter|transform|aggregate",
        "condition": "过滤条件",
        "stats": {
            "input_rows": 10000,
            "output_rows": 8500,
            "removed_rows": 1500
        },
        "removed_sample": {
            "sample_ids": ["row_001", "row_045"],
            "by_reason": {
                "condition_failed": 1200,
                "null_values": 300
            }
        },
        "row_identifier": "user_id"
    },
    
    # JSON字段血缘
    "field_lineage": {
        "user.profile.age": {
            "type": "derived",
            "source_path": "user.profile.dob",
            "transformation": "calculate_age(dob)"
        },
        "user.orders[*].amount": {
            "type": "transform",
            "source_path": "user.orders[*].original_price",
            "transformation": "apply_discount()"
        }
    }
}
```

---

## 列血缘

### 数据结构

```python
column_lineage = {
    "column_name": {
        "type": "original|transform|derived|aggregated",
        "derived_from": ["source_column"] | None,
        "transformation": "具体操作",
        "logic": "业务含义"
    }
}
```

### 类型说明

| 类型 | 说明 | derived_from | 示例 |
|------|------|-------------|------|
| original | 原始列，未变换 | null | 加载的CSV列 |
| transform | 同列名，内容变换 | [column_name] | fillna、类型转换 |
| derived | 新列，来自其他列 | [source_cols] | col_a + col_b |
| aggregated | 聚合列 | [source_col] | sum(group_by) |

### 记录示例

```python
# 步骤1: 数据加载
column_lineage = {
    "user_id": {"type": "original"},
    "revenue": {"type": "original"},
    "category": {"type": "original"}
}

# 步骤2: 数据清洗
column_lineage = {
    "revenue": {
        "type": "transform",
        "derived_from": ["revenue"],
        "transformation": "fillna(0).astype(float)",
        "logic": "填充缺失值并转float"
    }
}

# 步骤3: 特征工程
column_lineage = {
    "revenue_per_category": {
        "type": "derived",
        "derived_from": ["revenue", "category"],
        "transformation": "revenue / group_mean(revenue, category)",
        "logic": "类别归一化收入"
    }
}

# 步骤4: 聚合
column_lineage = {
    "total_revenue": {
        "type": "aggregated",
        "derived_from": ["revenue_per_category"],
        "transformation": "sum(group_by(category))",
        "logic": "按类别汇总收入"
    }
}
```

---

## 行血缘

### 数据结构

```python
row_lineage = {
    "type": "filter|transform|aggregate|join",
    "condition": "操作条件或逻辑",
    "stats": {
        "input_rows": 10000,
        "output_rows": 8500,
        "removed_rows": 1500,
        "kept_rows": 8500
    },
    "removed_sample": {
        "sample_ids": ["row_001", "row_045"],
        "sample_data": [
            {"row_id": "row_001", "reason": "amount <= 100"}
        ]
    },
    "by_reason": {
        "amount_too_small": 1200,
        "null_values": 300,
        "invalid_type": 0
    },
    "row_identifier": "user_id"  # 用于追踪特定行的列名
}
```

### 类型说明

| 类型 | 说明 | 记录重点 |
|------|------|---------|
| filter | 过滤行 | 被移除行的原因和样本 |
| transform | 行内变换 | 行ID保持不变 |
| aggregate | 聚合操作 | 多对一的映射关系 |
| join | 连接操作 | 行来源追踪 |

---

## JSON字段血缘

### 数据结构

```python
field_lineage = {
    "target_field_path": {
        "type": "original|transform|derived|aggregated|moved|flattened",
        "source_path": "原始字段路径",
        "transformation": "变换操作",
        "logic": "业务逻辑"
    }
}
```

### 路径表示

```
简单字段:     user.profile.age
数组元素:     user.orders[*].amount
特定索引:     data.users[0].name
嵌套数组:     data.users[*].orders[*].amount
```

### 记录示例

```python
field_lineage = {
    # 简单字段变换
    "user.profile.age": {
        "type": "derived",
        "source_path": "user.profile.dob",
        "transformation": "calculate_age(dob)",
        "logic": "从生日计算年龄"
    },
    
    # 字段移动
    "user.country": {
        "type": "moved",
        "source_path": "user.profile.address.country",
        "transformation": "extract_from_nested"
    },
    
    # 数组元素变换
    "user.orders[*].discounted_price": {
        "type": "transform",
        "source_path": "user.orders[*].original_price",
        "transformation": "apply_discount(0.9)"
    },
    
    # 数组聚合
    "user.total_amount": {
        "type": "aggregated",
        "source_path": "user.orders[*].amount",
        "transformation": "sum(orders[*].amount)"
    },
    
    # 嵌套结构展开
    "users_orders_flat": {
        "type": "flattened",
        "source_path": "users[*].orders[*]",
        "transformation": "flatten_nested_array"
    }
}
```

---

## 混合血缘

### 复杂数据结构

当处理包含嵌套结构的表格时，需要混合多种血缘：

```python
complex_lineage = {
    # JSON展开为表格
    "column:order_id": {
        "type": "extracted_from_nested",
        "source": "data[*].orders[*].order_id",
        "transformation": "flatten_json_array",
        "array_path": ["orders"]
    },
    
    # 单元格级别追踪
    "cell[user_456,order_B1,150]": {
        "type": "cell",
        "source_json_path": "data[1].orders[0]",
        "source_coordinates": {
            "user_index": 1,
            "order_index": 0,
            "field": "amount"
        }
    }
}
```

---

## 追踪查询

### 统一追踪接口

```python
def trace_data_element(
    session_id: str,
    element_type: str,  # "column" | "row" | "field" | "cell"
    identifier: str
) -> dict:
    """追踪数据元素的完整血缘链"""
    
    if element_type == "column":
        return trace_column(session_id, identifier)
    elif element_type == "row":
        return trace_row(session_id, identifier)
    elif element_type == "field":
        return trace_json_path(session_id, identifier)
    elif element_type == "cell":
        col, row_id = identifier.split(",")
        return {
            "column_lineage": trace_column(session_id, col),
            "row_lineage": trace_row(session_id, row_id)
        }
```

### 返回结果

```python
lineage_chain = [
    {
        "step": "步骤4: 聚合分析",
        "operation": "sum(group_by)",
        "current_form": "total_revenue",
        "source": "revenue_per_category",
        "status": "completed | failed | warning"
    },
    {
        "step": "步骤3: 特征工程",
        "operation": "列派生",
        "current_form": "revenue_per_category",
        "source": "revenue, category",
        "warning": "可能产生除零错误"
    },
    {
        "step": "步骤2: 数据清洗",
        "operation": "fillna + astype",
        "current_form": "revenue",
        "source": "revenue (原始)",
        "note": "填充缺失值"
    }
]
```

---

## 错误诊断

### 基于血缘的错误分析

当发现数据异常时：

1. **定位异常元素**: 识别具体的列/行/字段
2. **追踪血缘链**: 找到完整的变换历史
3. **分析变换逻辑**: 检查每一步的操作
4. **识别问题步骤**: 找到引入问题的步骤
5. **提供修复建议**: 基于分析给出建议

### 示例诊断流程

```
问题: total_revenue 列包含 NaN

1. 追踪 total_revenue 血缘:
   ← 步骤4: sum(revenue_per_category)
   ← 步骤3: revenue / group_mean(revenue, category)
   ← 步骤2: fillna(0).astype(float)
   ← 步骤1: 原始 revenue 列

2. 分析变换逻辑:
   步骤3的除法操作可能产生 inf/NaN

3. 诊断:
   当 group_mean 为 0 时，除法产生 inf

4. 建议:
   增加除零保护或检查 revenue 分布
```

---

## 大数据集优化

### 记录策略

| 数据集大小 | 列血缘 | 行血缘 | 字段血缘 |
|-----------|--------|--------|----------|
| < 1GB | 完整 | 完整 | 完整 |
| 1-10GB | 完整 | 统计+样本 | 完整 |
| > 10GB | 完整 | 仅统计 | 路径级 |

### 优化原则

1. **只记录元数据**: 不触碰实际数据
2. **采样策略**: 大数据集只采样关键信息
3. **按需记录**: 出错时才记录详细信息
4. **异步存储**: 不阻塞主流程

---

## 总结

### 系统能力

- ✅ 追踪任意数据元素的完整变换链
- ✅ 支持表格、JSON、嵌套结构
- ✅ 大数据集友好的轻量级设计
- ✅ 自动化错误诊断
- ✅ 可重现的数据处理流程

### 应用场景

1. 数据调试: 快速定位数据异常的来源
2. 数据质量监控: 追踪数据变换的质量
3. 合规审计: 完整的数据处理记录
4. 数据文档: 自动生成数据血缘文档

---

## 双粒度追踪设计

### 设计理念

系统支持两种互补的追踪粒度：

| 维度 | 元素级追踪 | 文件级追踪 |
|------|-----------|-----------|
| **追踪对象** | 字段、行、单元格 | 数据集、文件 |
| **应用场景** | 调试具体数据问题 | 理解整体处理流程 |
| **输出格式** | 步骤链 | PROV DAG |
| **可视化** | 列表/表格 | 流程图 |

### 文件级追踪（PROV 标准）

基于 W3C PROV 数据模型，记录文件级别的数据流转：

```python
# 数据结构
prov_dag = {
    "nodes": {
        "entity_xxx": {      # 数据实体
            "type": "entity",
            "entity_type": "dataset | artifact | file",
            "location": "file_path",
            "attributes": {...}
        },
        "activity_xxx": {    # 处理活动
            "type": "activity",
            "activity_type": "filter | aggregate | transform",
            "description": "操作描述",
            "attributes": {...}
        },
        "agent_xxx": {       # 执行代理
            "type": "agent",
            "agent_type": "python_code | agent | user",
            "name": "执行者名称",
            "attributes": {...}
        }
    },
    "edges": [
        {
            "from": "node_id",
            "to": "node_id",
            "relation": "used | wasGeneratedBy | wasAssociatedWith | wasDerivedFrom",
            "timestamp": "ISO时间戳"
        }
    ]
}
```

### PROV 关系语义

| 关系 | 方向 | 含义 | 示例 |
|------|------|------|------|
| `used` | Activity → Entity | 活动使用实体 | filter → raw_data.csv |
| `wasGeneratedBy` | Entity → Activity | 实体由活动生成 | clean_data.csv → filter |
| `wasAssociatedWith` | Activity → Agent | 活动关联代理 | filter → python_script |
| `wasDerivedFrom` | Entity → Entity | 实体派生关系 | output → input |
| `wasStartedBy` | Activity → Activity | 活动启动关系 | step2 → step1 |
| `wasInformedBy` | Activity → Activity | 活动信息流 | aggregate → filter |
| `actedOnBehalfOf` | Agent → Agent | 代理代表关系 | assistant → user |

### 使用场景对比

| 场景 | 使用元素级 | 使用文件级 |
|------|-----------|-----------|
| "为什么这个值是 NaN？" | ✓ 追踪字段变换 | - |
| "这个文件是怎么生成的？" | - | ✓ 查看 DAG |
| "数据丢失在哪里？" | ✓ 行血缘分析 | ✓ 文件级统计 |
| "谁执行了这个操作？" | - | ✓ Agent 关联 |
| "完整的分析流程是什么？" | - | ✓ 流程图可视化 |

### API 对比

```python
# 元素级追踪
from opentrace.tracker import LineageTracker

tracker = LineageTracker(session_id)
tracker.init_from_json("data.json")
tracker.record_step("清洗", "fillna", "填充缺失值")
chain = tracker.trace_element("root[0].age")

# 文件级追踪
from opentrace.mcp_server import get_server

server = get_server()
session = server.init_session("数据分析", "input.csv", "csv")
server.record_prov_relation(
    session_id=session["session_id"],
    entities=[...],
    activities=[...],
    agents=[...],
    relations=[...]
)
```

### 数据完整性保护

文件级追踪支持完整性验证：

```python
from opentrace.prov_validation import ProtectedProvDAG, validate_session

# 使用受保护的 DAG
protected_dag = ProtectedProvDAG(session_dir, append_only=True)

# 验证现有会话
is_valid, errors = validate_session(session_dir)
```

### 可视化输出

文件级追踪生成数据流图：

```
【输入】sales_data.csv
      属性: rows=1000
      ↓ [filter] 移除无效记录
      by: step1
【输出】filtered_sales.csv
      属性: rows=750

【输入】filtered_sales.csv
      属性: rows=750
      ↓ [aggregate] 按产品统计
      by: step2
【输出】product_summary.csv
      属性: rows=50
```

同时生成 Mermaid 格式用于专业可视化工具渲染。

---

## 总结（更新）

### 系统能力

- ✅ 元素级：追踪任意数据元素的完整变换链
- ✅ 文件级：基于 PROV 标准的数据集流转追踪
- ✅ 支持表格、JSON、嵌套结构
- ✅ 双粒度互补的追踪体系
- ✅ 数据完整性验证保护
- ✅ 自动化错误诊断
- ✅ 数据流可视化
- ✅ 可重现的数据处理流程
