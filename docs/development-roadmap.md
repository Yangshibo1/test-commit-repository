# OpenTrace 后续开发规划

## 三大重点方向

1. **数据记录方式设计**
2. **Agent使用引导**
3. **可视化系统构建**

---

## 方向1: 数据记录方式设计

### 现状分析

当前记录方式：
- 每步需要调用 `record_prov_relation()` + `record_step_details()`
- 数据分散存储在多个JSON文件中
- 需要手动管理临时ID映射

**痛点**：
- API调用繁琐，容易遗漏
- 数据结构复杂，学习成本高
- 缺少自动化和智能辅助

### 改进方向

#### 1.1 简化API接口

**目标**: 一次调用完成记录

```python
# 当前方式（繁琐）
server.record_prov_relation(...)
server.record_step_details(...)

# 改进方式（简洁）
server.record_step(
    session_id=session_id,
    step_name="filter_data",
    input_files=["data.json"],
    output_files=["filtered.json"],
    code="filtered = [x for x in data if condition(x)]",
    description="过滤数据"
)
```

#### 1.2 上下文感知记录

**目标**: 自动推断和填充信息

```python
# 自动记录输入输出
@opentrace.step
def filter_data(data):
    return [x for x in data if condition(x)]

# 自动捕获：
# - 输入数据来源
# - 输出数据位置
# - 执行的代码
# - 处理时间
```

#### 1.3 结构化存储优化

**目标**: 更高效的数据组织

```
当前结构：
session_XXXX/
├── prov_dag.json
├── prov_nodes.json
├── prov_edges.json
├── step_details.json
└── step_*.json

改进结构：
session_XXXX/
├── session.json          # 统一的会话文件
├── steps/                # 步骤目录
│   ├── step_001.json
│   └── step_002.json
└── artifacts/            # 产物目录
    ├── data_flow.json
    └── visualization.json
```

### 实施计划

1. 创建简化API包装器
2. 实现上下文感知装饰器
3. 设计新的存储结构
4. 保持向后兼容

---

## 方向2: Agent使用引导

### 现状分析

当前引导方式：
- 文档：AGENT_GUIDE.md, API_REFERENCE.md
- 工作流：.claude/workflows/trace-analysis.yaml
- Skill：.claude/skills/opentrace-data-analysis.md

**痛点**：
- 文档分散，难以快速理解
- 缺少实时验证和反馈
- 没有渐进式引导

### 改进方向

#### 2.1 渐进式引导系统

**目标**: 从简单到复杂的引导路径

```
Level 1: 基础使用
- 只需提供输入输出文件
- 系统自动记录其余信息

Level 2: 标准使用
- 添加代码和描述记录
- 手动确认每步记录

Level 3: 高级使用
- 自定义PROV关系
- 复杂的数据流记录
```

#### 2.2 实时验证和反馈

**目标**: 即时指出问题和建议

```python
# 验证检查
validator = OpenTraceValidator()
validator.check_step(step_data)
# => ⚠️ 警告: 缺少 step_details 记录
# => 💡 建议: 调用 record_step_details()

# 自动建议
advisor = OpenTraceAdvisor()
advisor.suggest_next_step(current_state)
# => 💡 下一步建议: 基于 filtered.json，可以：
#    1. 聚合统计
#    2. 深入分析
#    3. 生成报告
```

#### 2.3 交互式引导

**目标**: 对话式帮助系统

```python
guide = OpenTraceGuide()
guide.start_session()

# Guide: 你好！我是OpenTrace引导助手。
# Guide: 请告诉我你想分析什么数据？
# User: 我想分析销售数据
# Guide: 好的。让我们从第一步开始：加载数据。
# Guide: 你需要我帮你生成代码模板吗？
```

### 实施计划

1. 设计引导级别系统
2. 实现实时验证器
3. 创建建议引擎
4. 构建交互式引导

---

## 方向3: 可视化系统构建

### 现状分析

当前可视化：
- 文本格式数据流图
- Mermaid图表代码
- 静态节点/边信息

**痛点**：
- 可视化形式单一
- 缺少交互性
- 难以理解复杂流程

### 改进方向

#### 3.1 多层次可视化

**目标**: 不同粒度的可视化视图

```
Level 1: 概览视图
├── 总步骤数
├── 数据流向图
└── 关键指标

Level 2: 详细视图
├── 每步详情
├── 代码片段
└── 输入输出关系

Level 3: 追溯视图
├── 数据溯源链
├── 影响分析
└── 历史对比
```

#### 3.2 交互式可视化

**目标**: 可探索的数据流界面

```python
# 交互式探索
explorer = DataFlowExplorer(session_id)
explorer.show()

# 功能：
# - 点击节点查看详情
# - 拖拽重新组织视图
# - 缩放查看细节
# - 高亮数据流向
# - 时间轴回放
```

#### 3.3 智能洞察

**目标**: 自动发现和展示关键信息

```python
insights = OpenTraceInsights(session_id)

# 自动发现：
# - 异常步骤（处理时间过长）
# - 数据瓶颈（文件过大）
# - 重复操作
# - 可优化的路径

# 展示：
insights.show_dashboard()
# ├── 处理效率分析
# ├── 数据质量指标
# ├── 流程健康度
# └── 优化建议
```

### 实施计划

1. 设计多层次视图系统
2. 构建交互式界面原型
3. 实现智能洞察引擎
4. 集成到现有可视化模块

---

## 优先级排序

| 优先级 | 方向 | 任务 | 预期收益 |
|--------|------|------|----------|
| P0 | 方向2 | 实时验证和反馈 | 立即提升使用正确性 |
| P0 | 方向1 | 简化API接口 | 降低使用门槛 |
| P1 | 方向3 | 多层次可视化 | 提升用户体验 |
| P1 | 方向2 | 渐进式引导系统 | 改善学习曲线 |
| P2 | 方向1 | 上下文感知记录 | 提升自动化程度 |
| P2 | 方向3 | 交互式可视化 | 增强探索能力 |
| P3 | 方向3 | 智能洞察 | 提供决策支持 |

---

## 下一步行动

### 立即开始（P0）

1. **实时验证器**
   - 扩展 `validate_session()` 功能
   - 添加实时检查API
   - 提供具体错误定位

2. **简化API**
   - 设计统一的 `record_step()` 接口
   - 保持现有API向后兼容
   - 添加迁移指南

### 近期规划（P1）

3. **多层次可视化**
   - 设计视图层次结构
   - 实现概览和详细视图
   - 添加视图切换功能

4. **渐进式引导**
   - 定义引导级别
   - 创建Level 1引导内容
   - 实现自动级别检测

### 中长期规划（P2-P3）

5. **上下文感知记录**
6. **交互式可视化**
7. **智能洞察系统**

---

## 反馈和迭代

持续收集用户反馈，优化这三个方向：
- 通过实际使用发现痛点
- 定期评估改进效果
- 保持文档和实现同步更新
