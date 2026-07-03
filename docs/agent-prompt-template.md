# OpenTrace Agent Prompt 模板

## 基础使用说明

当使用 OpenTrace 追踪数据分析流程时，请按以下方式操作：

---

## 初始化会话

任务开始时，首先初始化追踪会话：

```
init_session(
    task_description="描述你的数据分析任务",
    data_path="数据文件路径",
    data_type="json"  # 或 "csv"
)
```

系统会返回一个 session_id，请在后续所有操作中使用此 ID。

---

## 记录处理步骤

### 方式 1: 分步记录

**1. 先记录步骤：**
```
record_step(
    session_id="{session_id}",
    step_name="步骤名称",
    operation="操作类型",
    description="详细描述这步做了什么"
)
```

**2. 然后记录映射关系：**
```
record_mapping(
    session_id="{session_id}",
    step_id="{上一步返回的step_id}",
    from_ids=["元素ID列表"],
    to_id="新元素ID",
    operation="变换操作描述",
    value_info={可选：值变化信息}
)
```

### 方式 2: 一步完成（推荐）

```
record_step_with_mappings(
    session_id="{session_id}",
    step_name="数据清洗",
    operation="fillna",
    description="处理缺失值",
    mappings=[
        {
            "from": ["json_abc123", "json_def456"],
            "to": "json_new123",
            "operation": "合并并填充",
            "value_info": {
                "json_abc123": {"old": null, "new": 0},
                "json_def456": {"old": 10, "new": 10},
                "json_new123": {"value": 10}
            }
        }
    ]
)
```

---

## 元素 ID 格式

### JSON 数据

使用路径作为 ID：

```
根元素:          root
数组元素:        root[0], root[1]
嵌套字段:        root[0].user.age
深层嵌套:        root[0].orders[2].amount
```

或者使用生成的标准 ID：
```
json_abc123def   (基于路径哈希)
```

### CSV 数据

使用行列格式：
```
单元格ID:        cell_{row}_{column}
行ID:           row_{row}
列ID:           col_{column}

示例:
cell_0_age      # 第0行，age列
cell_5_amount  # 第5行，amount列
row_3           # 第3行
```

---

## 追踪和分析

### 追踪元素来源

```
trace_element(
    session_id="{session_id}",
    element_id="要追踪的元素ID"
)
```

### 分析错误

当遇到错误时：

```
analyze_error(
    session_id="{session_id}",
    error_message="错误描述",
    affected_element="出问题的元素ID"
)
```

### 查看会话概览

```
get_session_summary(session_id="{session_id}")
```

---

## 完整示例

### 场景：处理 JSON 用户数据

```
# 1. 初始化
init_session(
    task_description="分析用户数据，计算总订单金额",
    data_path="users.json",
    data_type="json"
)
# 返回: session_20250115_143022

# 2. 数据加载和清洗
record_step_with_mappings(
    session_id="session_20250115_143022",
    step_name="数据清洗",
    operation="fill_missing_values",
    description="填充缺失的age字段",
    mappings=[
        {
            "from": ["root[0].age"],
            "to": "root[0].age_cleaned",
            "operation": "fillna(0)",
            "value_info": {"root[0].age": {"old": null, "new": 0}}
        },
        {
            "from": ["root[1].age"],
            "to": "root[1].age_cleaned",
            "operation": "fillna(0)",
            "value_info": {"root[1].age": {"old": 25, "new": 25}}
        }
    ]
)

# 3. 派生新字段
record_step_with_mappings(
    session_id="session_20250115_143022",
    step_name="派生字段",
    operation="calculate_total",
    description="计算每个用户的总订单金额",
    mappings=[
        {
            "from": ["root[0].orders[0].amount", "root[0].orders[1].amount"],
            "to": "root[0].total_amount",
            "operation": "sum(orders[*].amount)",
            "value_info": {
                "root[0].orders[0].amount": 100,
                "root[0].orders[1].amount": 200,
                "root[0].total_amount": 300
            }
        }
    ]
)

# 4. 发现错误，分析来源
analyze_error(
    session_id="session_20250115_143022",
    error_message="发现 NaN 值",
    affected_element="root[5].total_amount"
)

# 5. 导出结果
export_session(session_id="session_20250115_143022")
```

---

## 常见操作模板

### 数据过滤

```
record_step_with_mappings(
    session_id="{session_id}",
    step_name="过滤数据",
    operation="filter",
    description="只保留状态为completed的订单",
    metadata={
        "filter_condition": "status == 'completed'",
        "rows_before": 1000,
        "rows_after": 850
    },
    mappings=[
        {
            "from": ["row_0"],
            "to": "row_0",
            "operation": "kept",
            "value_info": {"reason": "status == 'completed'"}
        },
        {
            "from": ["row_5"],
            "to": null,
            "operation": "filtered_out",
            "value_info": {"reason": "status != 'completed'"}
        }
    ]
)
```

### 列变换

```
record_step_with_mappings(
    session_id="{session_id}",
    step_name="列变换",
    operation="transform_column",
    description="将price列转换为float",
    mappings=[
        {
            "from": ["cell_0_price"],
            "to": "cell_0_price_float",
            "operation": "astype(float)",
            "value_info": {
                "cell_0_price": {"old": "\"100\"", "new": 100.0}
            }
        }
    ]
)
```

### 聚合操作

```
record_step_with_mappings(
    session_id="{session_id}",
    step_name="聚合分析",
    operation="groupby_sum",
    description="按类别汇总销售额",
    metadata={
        "group_by": ["category"],
        "aggregation": "sum(amount)"
    },
    mappings=[
        {
            "from": ["cell_0_amount", "cell_3_amount", "cell_7_amount"],
            "to": "agg_category_A_total",
            "operation": "sum() where category='A'",
            "value_info": {
                "source_values": [100, 200, 150],
                "result_value": 450
            }
        }
    ]
)
```

---

## 注意事项

1. **ID 一致性**：确保在同一会话中使用一致的 ID 格式
2. **映射完整性**：尽可能记录所有重要的数据变换
3. **错误时记录**：遇到错误时立即调用 analyze_error
4. **性能考虑**：大数据集时只记录关键步骤和重要映射
5. **描述清晰**：operation 和 description 应清晰易懂

---

## 故障排查

### 映射记录失败

- 检查 step_id 是否正确
- 确保 from_ids 和 to_id 格式正确
- 查看错误信息了解具体问题

### 追踪不到元素

- 确认元素 ID 正确
- 检查是否记录了相关映射
- 使用 get_session_summary 查看所有步骤

### 分析错误无结果

- 确保 affected_element 正确
- 检查是否有相关的映射记录
- 尝试查看会话概览了解完整流程
