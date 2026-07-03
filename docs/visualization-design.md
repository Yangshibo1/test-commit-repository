# 可视化系统设计

## 设计目标

让用户能够直观地理解和探索Agent的数据分析工作流。

---

## 当前问题

### 问题1: 可视化形式单一

- 只有文本格式和Mermaid图表
- 缺少交互性
- 难以理解复杂流程

### 问题2: 信息展示不足

- 缺少关键指标
- 没有趋势分析
- 缺少对比功能

### 问题3: 探索能力弱

- 无法追溯数据来源
- 无法分析影响范围
- 无法对比不同会话

---

## 改进方案

### 方案1: 多层次视图

#### Level 1: 概览视图

```
┌─────────────────────────────────────┐
│  数据分析工作流概览                 │
├─────────────────────────────────────┤
│  📊 关键指标                        │
│  • 总步骤数: 15                     │
│  • 处理时间: 3.5分钟                │
│  • 数据量: 1.2GB → 850MB           │
│  • 健康度: 85%                     │
├─────────────────────────────────────┤
│  📈 数据流向图                      │
│  [简化版流程图]                     │
├─────────────────────────────────────┤
│  ⚠️ 需要关注                        │
│  • Step 5 处理时间过长              │
│  • Step 8 文件过大                 │
└─────────────────────────────────────┘
```

#### Level 2: 详细视图

```
┌─────────────────────────────────────┐
│  工作流详细视图                     │
├─────────────────────────────────────┤
│  [交互式流程图]                     │
│                                     │
│  节点详情:                          │
│  • Step 3: 过滤数据                │
│    - 输入: step2.json (100MB)      │
│    - 输出: step3.json (80MB)       │
│    - 代码: filter.py:15-30         │
│    - 时间: 2.3秒                   │
│    - 描述: 过滤无效记录            │
├─────────────────────────────────────┤
│  数据统计:                          │
│  • 过滤率: 20%                     │
│  • 处理速度: 43MB/s               │
└─────────────────────────────────────┘
```

#### Level 3: 追溯视图

```
┌─────────────────────────────────────┐
│  数据溯源                           │
├─────────────────────────────────────┤
│  选择: final_report.json            │
│                                     │
│  溯源链:                            │
│  final_report.json                  │
│    ↑                                │
│  step5_aggregated.json              │
│    ↑                                │
│  step4_analyzed.json                │
│    ↑                                │
│  step3_filtered.json                │
│    ↑                                │
│  step2_loaded.json                  │
│    ↑                                │
│  raw_data.json                      │
├─────────────────────────────────────┤
│  影响分析:                          │
│  • 受影响 downstream: 2个节点       │
│  • 变更传播路径: ...                │
└─────────────────────────────────────┘
```

### 方案2: 交互式探索

#### 节点交互

```python
# 点击节点
explorer.on_node_click(node_id):
    # 显示详情
    show_node_details(node_id)
    
    # 高亮相关
    highlight_connected(node_id)
    
    # 显示操作菜单
    show_menu([
        "查看详情",
        "追溯来源",
        "查看影响",
        "查看代码"
    ])

# 拖拽节点
explorer.on_node_drag(node_id):
    # 重新组织视图
    reorganize_layout()
```

#### 缩放和平移

```python
# 缩放
explorer.zoom_in()   # 放大查看细节
explorer.zoom_out()  # 缩小查看全局
explorer.fit_to_view()  # 自适应视图

# 平移
explorer.pan_to(node_id)  # 聚焦到节点
explorer.pan_to_center()  # 回到中心
```

#### 时间轴回放

```python
# 时间轴控制
timeline = TimelineExplorer(session_id)
timeline.show()

# 功能：
# - 播放整个分析过程
# - 暂停在某一步
# - 前进/后退单步
# - 调整播放速度
```

### 方案3: 智能洞察

#### 自动发现问题

```python
insights = OpenTraceInsights(session_id)

# 问题检测
issues = insights.detect_issues()
for issue in issues:
    print(f"⚠️ {issue.type}: {issue.description}")
    print(f"   位置: {issue.location}")
    print(f"   影响: {issue.impact}")
    print(f"   建议: {issue.suggestion}")
```

#### 性能分析

```python
# 性能指标
metrics = insights.analyze_performance()
# {
#     "total_time": "3.5分钟",
#     "bottlenecks": ["Step 5", "Step 8"],
#     "optimization_potential": "40%",
#     "recommendations": [...]
# }
```

#### 数据质量

```python
# 数据质量评估
quality = insights.assess_data_quality()
# {
#     "completeness": 95,
#     "consistency": 88,
#     "accuracy": 92,
#     "issues": [
#         "Step 3: 发现20%缺失值",
#         "Step 7: 数据类型不一致"
#     ]
# }
```

### 方案4: 对比分析

#### 会话对比

```python
# 对比两个会话
comparator = SessionComparator(session_id_1, session_id_2)
comparator.show_diff()

# 显示：
# - 步骤差异
# - 数据差异
# - 性能差异
# - 代码差异
```

#### 版本对比

```python
# 对比同一会话的不同版本
comparator = VersionComparator(session_id, version_1, version_2)
comparator.show_changes()
```

---

## 可视化技术栈

### 前端技术

```typescript
// 使用现代Web技术
- React/Vue - 组件化UI
- D3.js - 数据可视化
- Cytoscape.js - 图网络可视化
- Recharts - 统计图表
- Monaco Editor - 代码展示
```

### 后端API

```python
# 可视化数据API
class VisualizationAPI:
    def get_overview(self, session_id):
        """概览数据"""
        
    def get_details(self, session_id, step_id):
        """步骤详情"""
        
    def get_lineage(self, session_id, entity_id):
        """数据溯源"""
        
    def get_insights(self, session_id):
        """智能洞察"""
```

---

## 实施计划

### Phase 1: 基础可视化（立即）

1. 改进文本格式输出
2. 增强Mermaid图表
3. 添加关键指标展示

### Phase 2: 交互式原型（近期）

1. 设计交互界面
2. 实现节点点击交互
3. 添加缩放平移功能

### Phase 3: 智能洞察（中期）

1. 实现问题检测
2. 添加性能分析
3. 构建建议系统

### Phase 4: 完整系统（长期）

1. Web界面开发
2. 实时数据更新
3. 多会话对比

---

## 界面原型

### 主界面

```
┌────────────────────────────────────────────────────┐
│  OpenTrace - 数据分析工作流可视化                  │
├──────────────┬─────────────────────────────────────┤
│              │                                      │
│  📊 概览     │         📈 工作流图                 │
│              │                                      │
│  • 15 步骤   │         [交互式流程图]               │
│  • 3.5 分钟  │                                      │
│  • 1.2GB     │                                      │
│  • 85% 健康  │                                      │
│              │                                      │
├──────────────┼─────────────────────────────────────┤
│  📋 步骤列表 │         📝 详情面板                  │
│              │                                      │
│  1. 加载     │         Step 3: 过滤数据             │
│  2. 转换     │         • 输入: step2.json          │
│  3. 过滤 ⭐  │         • 输出: step3.json          │
│  4. 分析     │         • 代码: filter.py           │
│  5. 聚合     │         • 时间: 2.3秒               │
│  ...         │         • 描述: 过滤无效记录         │
│              │                                      │
└──────────────┴─────────────────────────────────────┘
```

---

## 评估标准

| 指标 | 当前 | 目标 |
|------|------|------|
| 视图类型 | 2种 | 5+种 |
| 交互性 | 无 | 高 |
| 洞察能力 | 无 | 强 |
| 对比功能 | 无 | 有 |
| 实时更新 | 无 | 有 |
