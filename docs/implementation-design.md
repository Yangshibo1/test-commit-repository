# 数据血缘追踪系统 - 实现设计

## 设计原则

**目标**: 学术研究，快速开发快速验证
**约束**: 轻量级、个人适用、MVP优先

---

## 核心方案：基于ID映射的数据单元追踪

### 基本原理

```
原始数据 → 添加全局ID → 操作记录映射 → 追踪查询

每个数据单元都有唯一ID，每次操作记录 from→to 的映射关系。
```

### ID系统设计

```python
# 表格数据ID格式
cell_{row}_{column}     # 单元格ID
row_{row}                # 行ID

# 示例
cell_0_age      # 第0行，age列
cell_5_amount   # 第5行，amount列
row_3           # 第3行

# JSON数据ID格式
json_{path_hash}        # JSON路径ID
```

### 初始化流程

```python
def init_data_with_ids(data_path):
    """初始化数据并添加ID层"""
    
    # 1. 读取原始数据
    df = pd.read_csv(data_path)
    
    # 2. 添加隐藏的ID列
    df['_cell_row_id'] = range(len(df))
    
    # 3. 生成单元格映射
    cell_mapping = {}
    for row_idx in range(len(df)):
        for col_name in df.columns:
            if col_name != '_cell_row_id':
                cell_id = f"cell_{row_idx}_{col_name}"
                cell_mapping[cell_id] = {
                    "row": row_idx,
                    "col": col_name,
                    "value": df.loc[row_idx, col_name]
                }
    
    # 4. 保存副本和映射
    working_copy = f"data_working.csv"
    df.to_csv(working_copy, index=False)
    
    # 5. 记录初始步骤
    step_record = {
        "step_id": "step_000",
        "step_name": "数据初始化",
        "operation": "add_id_layer",
        "cell_mapping": cell_mapping,
        "metadata": {
            "row_count": len(df),
            "col_count": len(df.columns) - 1,
            "source": data_path
        }
    }
    
    return working_copy, step_record
```

---

## 映射记录格式

### Step JSON 结构

```json
{
    "step_id": "step_001",
    "step_name": "数据清洗",
    "operation": "fillna",
    "timestamp": "2024-01-15T10:30:00",
    
    "mappings": [
        {
            "from": "cell_0_age",
            "to": "cell_0_age_v2",
            "operation": "fillna(0)",
            "value_change": {"from": "NaN", "to": 0}
        }
    ],
    
    "row_mappings": [
        {
            "from": "row_5",
            "to": null,
            "reason": "amount <= 100"
        }
    ],
    
    "aggregate_mappings": [
        {
            "from": ["cell_0_amount", "cell_1_amount"],
            "to": "agg_category_A_sum",
            "operation": "sum()",
            "group_key": "category=A"
        }
    ],
    
    "metadata": {
        "input_shape": [100, 5],
        "output_shape": [95, 5],
        "execution_time_ms": 150
    }
}
```

### 不同操作的映射规则

#### 1. 列操作（变换）

```python
# 操作：df['age_cleaned'] = df['age'].fillna(0)

mappings = [
    {
        "from": "cell_0_age",
        "to": "cell_0_age_cleaned",
        "operation": "fillna(0)",
        "value_change": {"from": "NaN", "to": 0}
    },
    {
        "from": "cell_1_age", 
        "to": "cell_1_age_cleaned",
        "operation": "fillna(0)",
        "value_change": {"from": "25", "to": 25}
    }
]
```

#### 2. 行操作（过滤）

```python
# 操作：df = df[df['amount'] > 100]

row_mappings = [
    {"from": "row_0", "to": "row_0", "reason": "kept"},
    {"from": "row_3", "to": null, "reason": "filtered: amount <= 100"},
    {"from": "row_5", "to": "row_2", "reason": "reindex_after_filter"}
]

# 被过滤掉的行不生成cell映射
```

#### 3. 聚合操作

```python
# 操作：df.groupby('category')['amount'].sum()

aggregate_mappings = [
    {
        "from": ["cell_0_amount", "cell_3_amount", "cell_7_amount"],
        "to": "agg_A_amount_sum",
        "operation": "sum()",
        "group_key": "category=A",
        "source_values": [100, 200, 150],
        "result_value": 450
    }
]
```

#### 4. 派生列

```python
# 操作：df['total'] = df['price'] * df['quantity']

mappings = [
    {
        "from": ["cell_0_price", "cell_0_quantity"],
        "to": "cell_0_total",
        "operation": "multiply",
        "value_from": {"price": 100, "quantity": 2},
        "value_to": 200
    }
]
```

---

## 追踪查询

### 单元格追踪

```python
def trace_cell(cell_id, session_id):
    """追踪单元格的完整历史"""
    
    chain = []
    visited = set()
    
    def trace_recursive(current_id, step_index):
        if current_id in visited:
            return
        visited.add(current_id)
        
        # 从后往前查找步骤
        for i in range(step_index, -1, -1):
            step = load_step(session_id, i)
            
            # 查找cell映射
            for mapping in step.get("mappings", []):
                if mapping["to"] == current_id:
                    chain.append({
                        "step": step["step_name"],
                        "step_id": step["step_id"],
                        "from": mapping["from"],
                        "to": mapping["to"],
                        "operation": mapping["operation"],
                        "value_change": mapping.get("value_change")
                    })
                    
                    # 递归追踪来源
                    if isinstance(mapping["from"], list):
                        for source_id in mapping["from"]:
                            trace_recursive(source_id, i - 1)
                    else:
                        trace_recursive(mapping["from"], i - 1)
                    return
            
            # 查找聚合映射
            for agg in step.get("aggregate_mappings", []):
                if agg["to"] == current_id:
                    chain.append({
                        "step": step["step_name"],
                        "step_id": step["step_id"],
                        "from": agg["from"],
                        "to": agg["to"],
                        "operation": agg["operation"],
                        "type": "aggregation"
                    })
                    
                    for source_id in agg["from"]:
                        trace_recursive(source_id, i - 1)
                    return
        
        trace_recursive(cell_id, len(get_all_steps(session_id)) - 1)
        return list(reversed(chain))
```

### 行追踪

```python
def trace_row(row_id, session_id):
    """追踪行的命运"""
    
    journey = []
    
    for step in get_all_steps(session_id):
        # 检查行映射
        for row_map in step.get("row_mappings", []):
            if row_map["from"] == row_id:
                journey.append({
                    "step": step["step_name"],
                    "from": row_map["from"],
                    "to": row_map["to"],
                    "reason": row_map.get("reason"),
                    "status": "kept" if row_map["to"] else "removed"
                })
                
                # 更新当前row_id
                if row_map["to"]:
                    row_id = row_map["to"]
                break
    
    return journey
```

---

## JSON数据处理

### JSON路径ID系统

```python
def generate_json_ids(json_obj, prefix=""):
    """为JSON对象生成ID"""
    
    ids = {}
    
    if isinstance(json_obj, dict):
        for key, value in json_obj.items():
            current_path = f"{prefix}.{key}" if prefix else key
            path_hash = hash_string(current_path)
            json_id = f"json_{path_hash}"
            
            ids[json_id] = {
                "path": current_path,
                "type": type(value).__name__,
                "value": value if not isinstance(value, (dict, list)) else None
            }
            
            if isinstance(value, (dict, list)):
                ids.update(generate_json_ids(value, current_path))
    
    elif isinstance(json_obj, list):
        for idx, item in enumerate(json_obj):
            current_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            path_hash = hash_string(current_path)
            json_id = f"json_{path_hash}"
            
            ids[json_id] = {
                "path": current_path,
                "type": type(item).__name__,
                "value": item if not isinstance(item, (dict, list)) else None
            }
            
            if isinstance(item, (dict, list)):
                ids.update(generate_json_ids(item, current_path))
    
    return ids
```

### JSON转换映射

```json
{
    "from": "json_abc123",
    "to": "cell_0_user_age",
    "operation": "json_extract",
    "json_path": "$.users[0].profile.age"
}
```

---

## 存储结构

```
.opentrace/
├── sessions/
│   └── {session_id}/
│       ├── meta.json              # 会话元信息
│       ├── step_000.json          # 初始步骤
│       ├── step_001.json          # 各个步骤
│       ├── step_002.json
│       ├── ...
│       └── data_working.csv       # 当前工作副本
├── cache/
│   └── trace_cache.json          # 追踪查询缓存
└── config.json                   # 配置
```

---

## MCP工具接口

### 核心工具

```python
# 工具1：初始化
start_traced_session(task_description, data_path)

# 工具2：执行操作并记录映射
execute_with_mapping(session_id, step_name, code, input_data)

# 工具3：查询单元历史
trace_data_unit(session_id, unit_type, unit_id)

# 工具4：获取会话概览
get_session_summary(session_id)

# 工具5：导出血缘链
export_lineage_chain(session_id, unit_id, format="json")
```

---

## 执行包装器

### 自动追踪的代码执行

```python
def execute_with_auto_tracking(code, input_df):
    """执行代码并自动生成映射"""
    
    # 包装代码
    wrapped_code = f'''
import pandas as pd
import tracking as tr

# 启用追踪
tr.enable()

原始代码: {code}

# 获取追踪结果
mappings = tr.get_mappings()
'''
    
    # 执行
    result = execute_safely(wrapped_code)
    
    return result["data"], result["mappings"]
```

---

## 轻量级优化

### MVP简化策略

| 完整功能 | MVP简化 |
|---------|---------|
| 所有单元格映射 | 只记录变化的单元格 |
| 完整值记录 | 只记录值变化 |
| 实时追踪 | 事后解析 |
| 复杂聚合 | 只支持简单聚合 |
| JSON完整支持 | 只支持基础JSON |

### 性能考虑

- 只存储映射关系，不存储实际值
- 使用JSON格式，易于解析
- 按需加载步骤数据
- 支持增量更新
