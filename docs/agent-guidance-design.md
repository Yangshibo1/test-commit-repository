# Agent使用引导设计

## 设计目标

让Agent能够正确、高效地使用OpenTrace，无需深入学习复杂的文档。

---

## 当前问题

### 问题1: 认知负荷过重

Agent需要同时理解：
- 数据分析任务本身
- OpenTrace API
- PROV数据模型
- 正确的工作流程

### 问题2: 缺少即时反馈

- 不知道是否正确使用
- 错误发现太晚
- 缺少改进建议

### 问题3: 学习路径不清晰

- 文档分散
- 缺少从简单到复杂的路径
- 不知道从哪里开始

---

## 改进方案

### 方案1: 渐进式引导系统

#### Level 1: 基础模式（自动化）

```python
# 最简单的使用方式
@opentrace.auto_record
def analyze_data(data_path):
    data = load(data_path)
    filtered = filter(data)
    return filtered

# 系统自动：
# - 记录每一步
# - 生成PROV关系
# - 保存中间结果
```

**适合**: 快速原型、简单任务

#### Level 2: 标准模式（半自动）

```python
# 提供关键信息
with opentrace.recording("filter_data"):
    data = load("input.json")
    filtered = [x for x in data if condition(x)]
    save(filtered, "output.json")
    
    # 手动确认关键信息
    opentrace.confirm(
        description="过滤无效数据",
        code="filtered = [x for x in data if condition(x)]"
    )
```

**适合**: 日常使用、标准任务

#### Level 3: 高级模式（手动控制）

```python
# 完全手动控制
server.record_prov_relation(...)
server.record_step_details(...)
```

**适合**: 复杂任务、精细控制

### 方案2: 实时验证系统

#### 即时检查

```python
validator = OpenTraceValidator()

# 每步后检查
validator.check_last_step(session_id)
# => ✅ 通过 或 ⚠️ 警告 或 ❌ 错误

# 实时反馈
if validator.has_warnings():
    for warning in validator.get_warnings():
        print(f"⚠️ {warning}")
        print(f"💡 建议: {warning.suggestion}")
```

#### 常见检查项

| 检查项 | 说明 | 建议修复 |
|--------|------|----------|
| 缺少step_details | 未调用record_step_details() | 添加调用 |
| 未读取输出 | 保存文件后未读取 | 添加读取代码 |
| 关系方向错误 | PROV关系方向不正确 | 查看速查表 |
| ID重复 | 临时ID冲突 | 使用唯一ID |
| 文件不存在 | 引用的文件不存在 | 检查路径 |

### 方案3: 智能建议系统

#### 下一步建议

```python
advisor = OpenTraceAdvisor()

# 基于当前状态建议
suggestions = advisor.suggest_next_steps(session_id)
for suggestion in suggestions:
    print(f"💡 {suggestion.description}")
    print(f"   优先级: {suggestion.priority}")
    print(f"   预期收益: {suggestion.benefit}")
```

#### 建议类型

| 类型 | 场景 | 示例 |
|------|------|------|
| 数据清洗 | 发现数据质量问题 | "建议过滤缺失值" |
| 数据分析 | 有基础数据 | "可以开始统计分析" |
| 数据聚合 | 数据量过大 | "建议聚合后分析" |
| 结果导出 | 分析完成 | "建议生成报告" |

### 方案4: 交互式引导

#### 对话式助手

```python
guide = OpenTraceGuide()
guide.start()

# Guide: 你好！我是OpenTrace引导助手。
# Guide: 请告诉我你想做什么？

# User: 分析销售数据

# Guide: 好的，让我们一步步来。
# Guide: Step 1: 加载数据
# Guide: 你有现成的代码，还是我帮你生成？

# User: 帮我生成

# Guide: 好的，这是加载代码：
# Guide: [显示代码模板]
# Guide: 运行后告诉我结果。
```

#### 渐进式揭示

```python
# 初学者：只显示核心功能
guide.show_basics()
# => 1. 加载数据 2. 处理数据 3. 保存结果

# 进阶：显示更多选项
guide.show_advanced()
# => + PROV关系 + 自定义元数据

# 专家：显示所有功能
guide.show_all()
```

---

## 实施计划

### Phase 1: 实时验证（立即）

1. 扩展validate_session()功能
2. 添加check_step()方法
3. 实现警告和建议系统

### Phase 2: 渐进式引导（近期）

1. 定义引导级别
2. 实现Level 1自动化
3. 创建引导文档

### Phase 3: 智能建议（中期）

1. 分析常见模式
2. 构建建议引擎
3. 集成到引导系统

### Phase 4: 交互式引导（长期）

1. 设计对话流程
2. 实现引导助手
3. 持续优化对话策略

---

## 引导系统架构

```
┌─────────────────────────────────────┐
│         Agent用户                   │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│      引导入口                       │
│  - 选择引导级别                     │
│  - 描述任务                         │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│      引导引擎                       │
│  ┌──────────┐  ┌──────────┐       │
│  │ 实时验证  │  │ 智能建议  │       │
│  └──────────┘  └──────────┘       │
│  ┌──────────┐  ┌──────────┐       │
│  │ 进度跟踪  │  │ 错误诊断  │       │
│  └──────────┘  └──────────┘       │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│      OpenTrace服务                  │
│  - 简化API                          │
│  - 自动记录                         │
│  - 数据存储                         │
└─────────────────────────────────────┘
```

---

## 评估标准

| 指标 | 当前 | 目标 |
|------|------|------|
| 新手上手时间 | 30+分钟 | 5分钟 |
| 错误发现时间 | 完成后 | 实时 |
| 引导覆盖率 | 低 | 高 |
| 用户满意度 | 中 | 高 |
