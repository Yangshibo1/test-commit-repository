# 数据记录方式设计

## 设计目标

让Agent能够轻松、准确地记录数据分析工作流，而不需要深入了解PROV标准的细节。

---

## 当前问题

### 问题1: API调用繁琐

```python
# 当前方式：需要分别调用两个函数
server.record_prov_relation(
    session_id=session_id,
    entities=[...],
    activities=[...],
    agents=[...],
    relations=[...]
)

server.record_step_details(
    session_id=session_id,
    step_id="step_1",
    step_name="filter_data",
    ...
)
```

### 问题2: 临时ID管理复杂

```python
# 需要手动管理临时ID
entities=[
    {"id": "input", ...},      # 必须提供临时ID
    {"id": "output", ...}
]
relations=[
    ("act", "input", "used"),  # 使用临时ID引用
    ("output", "act", "wasGeneratedBy")
]
```

### 问题3: 缺少自动化

- 不能自动推断输入输出关系
- 不能自动捕获执行的代码
- 不能自动记录时间戳

---

## 改进方案

### 方案1: 统一记录接口

**设计**: 一个函数完成所有记录

```python
def record_step(
    session_id: str,
    step_name: str,
    # 数据相关
    input_files: List[str] = None,
    output_files: List[str] = None,
    input_data: Any = None,
    output_data: Any = None,
    # 代码相关
    code: str = None,
    code_file: str = None,
    command: str = None,
    # 描述相关
    description: str = None,
    parameters: Dict = None,
    # 自动推断
    activity_type: str = None,  # 自动推断
    agent_name: str = None       # 自动生成
):
    """
    一次性记录步骤的所有信息
    
    自动处理：
    - PROV关系生成
    - ID映射
    - 时间戳
    - 数据类型推断
    """
```

### 方案2: 装饰器方式

**设计**: 自动捕获函数执行信息

```python
@opentrace.step(session_id="xxx")
def filter_data(data):
    """过滤数据"""
    return [x for x in data if x['value'] > 0]

# 自动记录：
# - 输入：data（来源自动追溯）
# - 输出：返回值（自动保存）
# - 代码：函数源码
# - 时间：执行时间
# - 关系：自动生成PROV关系
```

### 方案3: 上下文管理器

**设计**: 自动管理步骤上下文

```python
with opentrace.Step(session_id, "filter_data") as step:
    # 读取输入
    data = step.read_input("data.json")
    
    # 处理数据
    filtered = [x for x in data if condition(x)]
    
    # 写入输出
    step.write_output("filtered.json", filtered)
    
    # 自动记录：
    # - 输入输出关系
    # - 处理时间
    # - 数据大小
```

### 方案4: 智能推断

**设计**: 自动分析数据流

```python
# 智能推断输入输出关系
advisor = OpenTraceAdvisor()
advisor.analyze_step(
    code="filtered = data.filter(lambda x: x.value > 0)",
    variables={"data": "data.json"}
)
# => 推断：
#    input: data.json
#    output: (自动生成)
#    activity_type: transform
```

---

## 数据结构优化

### 当前结构问题

```
session_XXXX/
├── prov_dag.json          # 元数据
├── prov_nodes.json        # 节点
├── prov_edges.json        # 边
├── step_details.json      # 步骤详情
└── step_*.json           # 各步骤
```

问题：
- 文件分散，难以管理
- 数据冗余
- 查询效率低

### 优化结构

```
session_XXXX/
├── session.json          # 统一会话文件
│   ├── metadata
│   ├── steps[]          # 所有步骤
│   └── statistics
├── artifacts/            # 产物目录
│   ├── data_flow.json
│   └── visualization.json
└── cache/               # 缓存目录
    └── index.json
```

优势：
- 单一会话文件，易于管理
- 步骤集中存储，便于查询
- 产物分离，清晰明确

---

## 实施计划

### Phase 1: 统一API（向后兼容）

```python
# 新增统一接口，保留旧接口
def record_step_unified(...):
    # 内部调用旧接口
    record_prov_relation(...)
    record_step_details(...)
```

### Phase 2: 装饰器支持

```python
# 实现装饰器
def step(session_id):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 执行前：记录输入
            result = func(*args, **kwargs)
            # 执行后：记录输出
            return result
        return wrapper
    return decorator
```

### Phase 3: 智能推断

```python
# 实现推断引擎
class InferenceEngine:
    def infer_relations(self, code, variables):
        # 分析代码
        # 推断数据流
        # 生成PROV关系
        pass
```

---

## 评估标准

| 指标 | 当前 | 目标 |
|------|------|------|
| API调用数 | 2-3个 | 1个 |
| 必填参数 | 10+个 | 2-3个 |
| 自动化程度 | 低 | 高 |
| 学习曲线 | 陡峭 | 平缓 |
| 错误率 | 高 | 低 |
