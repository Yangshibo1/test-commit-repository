# OpenTrace 最佳实践

避免常见陷阱，正确使用OpenTrace。

---

## 核心原则

### 1. 逐步处理

❌ **错误**：一次性pipeline完成全部分析
```python
# 不要这样做
def analyze_all():
    data = load("data.json")
    filtered = filter(data)
    result = analyze(filtered)
    save(result)
```

✅ **正确**：每步独立处理
```python
# Step 1
data = load("data.json")
save(data, "step1.json")
record_prov_relation(...)
record_step_details(...)

# Step 2
filtered = filter(data)
save(filtered, "step2.json")
record_prov_relation(...)
record_step_details(...)
```

### 2. 必填record_step_details

❌ **错误**：只调用record_prov_relation
```python
server.record_prov_relation(...)
# 缺少 record_step_details() - 验证会失败！
```

✅ **正确**：同时调用两者
```python
server.record_prov_relation(...)
server.record_step_details(...)  # 必填！
```

### 3. 读取输出再决策

❌ **错误**：未读取输出就决定下一步
```python
filter(data)
save(filtered, "step2.json")
# 假设知道结果，直接进行下一步
aggregate(filtered)
```

✅ **正确**：读取输出，观察结果，再决策
```python
filter(data)
save(filtered, "step2.json")

# 读取输出
with open("step2.json") as f:
    result = json.load(f)

# 基于观察结果决策
if len(result) > 1000:
    # 决定进行聚合
    aggregate(result)
else:
    # 决定直接分析
    analyze(result)
```

---

## 常见模式

### 模式1: 数据过滤

```python
# 过滤数据
filtered = [x for x in data if condition(x)]
save(filtered, "filtered.json")

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "data.json"},
        {"id": "output", "entity_type": "dataset", "location": "filtered.json"}
    ],
    activities=[
        {"id": "act", "activity_type": "filter", "description": "过滤数据"}
    ],
    agents=[{"id": "agent", "agent_type": "python_code", "name": "filter_step"}],
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
    code_files=["filter.py"],
    commands_run=["python filter.py"],
    input_files=["data.json"],
    output_files=["filtered.json"]
)
```

### 模式2: 数据聚合

```python
# 聚合数据
summary = aggregate(data)
save(summary, "summary.json")

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input", "entity_type": "dataset", "location": "data.json"},
        {"id": "output", "entity_type": "artifact", "location": "summary.json"}
    ],
    activities=[
        {"id": "act", "activity_type": "aggregate", "description": "聚合汇总"}
    ],
    agents=[{"id": "agent", "agent_type": "python_code", "name": "aggregate_step"}],
    relations=[
        ("act", "input", "used"),
        ("output", "act", "wasGeneratedBy"),
        ("act", "agent", "wasAssociatedWith"),
        ("output", "input", "wasDerivedFrom")
    ]
)
```

### 模式3: 多输入合并

```python
# 合并多个数据源
merged = merge(data1, data2)
save(merged, "merged.json")

server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "input1", "entity_type": "dataset", "location": "data1.json"},
        {"id": "input2", "entity_type": "dataset", "location": "data2.json"},
        {"id": "output", "entity_type": "dataset", "location": "merged.json"}
    ],
    activities=[
        {"id": "act", "activity_type": "aggregate", "description": "合并数据"}
    ],
    agents=[{"id": "agent", "agent_type": "python_code", "name": "merge_step"}],
    relations=[
        ("act", "input1", "used"),
        ("act", "input2", "used"),
        ("output", "act", "wasGeneratedBy"),
        ("act", "agent", "wasAssociatedWith"),
        ("output", "input1", "wasDerivedFrom"),
        ("output", "input2", "wasDerivedFrom")
    ]
)
```

---

## 避免的错误

### 错误1: 忘记临时ID

❌ **错误**：
```python
entities=[
    {"entity_type": "dataset", "location": "data.json"}  # 缺少 id
]
```

✅ **正确**：
```python
entities=[
    {"id": "input", "entity_type": "dataset", "location": "data.json"}
]
```

### 错误2: 关系方向错误

❌ **错误**：
```python
relations=[
    ("act", "output", "used")  # 活动使用自己的输出？错误！
]
```

✅ **正确**：
```python
relations=[
    ("act", "input", "used"),  # 活动使用输入
    ("output", "act", "wasGeneratedBy")  # 输出由活动生成
]
```

### 错误3: 跳过step_details

❌ **错误**：
```python
server.record_prov_relation(...)
# 缺少 record_step_details()
```

✅ **正确**：
```python
server.record_prov_relation(...)
server.record_step_details(...)  # 必填！
```

---

## 验证清单

完成分析后，运行验证：

```python
from opentrace.prov_validation import validate_session

is_valid, errors = validate_session(session_dir)
if not is_valid:
    for error in errors:
        print(f"❌ {error}")
else:
    print("✅ 会话验证通过")
```

---

## 文件命名建议

```
step1_<操作>.json    # 第1步输出
step2_<操作>.json    # 第2步输出
...
final_report.json    # 最终报告
visualization.txt   # 可视化
```

---

## 调试技巧

### 查看会话列表

```python
sessions = server.list_sessions()
for s in sessions:
    print(f"{s['session_id']}: {s['task_description']}")
```

### 查看DAG概览

```python
overview = server.get_prov_dag_overview(session_id)
print(f"节点: {overview['statistics']}")
```

### 查看步骤详情

```python
steps = server.get_step_details(session_id)
for step in steps['steps']:
    print(f"{step['step_id']}: {step['step_name']}")
```
