# AgentVAST 使用示例

本目录包含 AgentVAST 的使用示例，用于演示正确的逐步处理模式。

## 说明

**这些脚本仅作为示例展示如何使用 AgentVAST API**，实际分析任务需要根据您的具体需求调整。

AgentVAST 是一个**通用的数据分析工作流记录服务**，适用于任何需要数据血缘追踪的分析任务。

## 通用模式

所有分析任务都应遵循以下模式：

1. **初始化会话** → `init_session()`
2. **逐步处理** → 每步调用：
   - `record_prov_relation()` - 记录数据流
   - `record_step_details()` - 记录详情（必填）
3. **读取输出** → 观察结果
4. **决策下一步** → 基于观察结果

## 示例脚本

| 脚本 | 演示内容 | 关键API |
|------|----------|---------|
| `step1_load_data.py` | 数据加载 | init_session, record_prov_relation, record_step_details |
| `step2_filter_saidit.py` | 数据过滤 | record_prov_relation, record_step_details |
| `step3_analyze_chain.py` | 数据分析 | record_prov_relation, record_step_details |
| `generate_report.py` | 报告生成 | record_prov_relation, record_step_details |

## 关键要点

1. **每步都是独立脚本** - 不使用一次性pipeline
2. **必须调用record_step_details()** - 这是验证规则要求的
3. **每步读取输出** - 不能在未观察结果时预设后续步骤
4. **基于观察决策** - 下一步取决于上一步的发现

## 应用到您的任务

这些示例展示了API的使用方式，但您需要根据您的分析任务调整：
- 数据源格式和位置
- 过滤和分析逻辑
- 中间文件的结构
- 最终报告的内容

请参考 `.claude/workflows/trace-analysis.yaml` 和 `.claude/workflows/trace-analysis-guide.md` 了解完整的工作流规范。
