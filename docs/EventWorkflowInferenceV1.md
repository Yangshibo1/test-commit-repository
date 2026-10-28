# Event 行为、角色分类与逻辑工作流设计

状态：0.3 已实现。覆盖六类 Event、批次行为摘要、固定 13 类关系提议、独立关系审查与四类行为角色评估，
支持检查点恢复、证据引文和 DAG 校验，并已接入详细执行图。决策、转折和结果突出展示，正常执行使用紧凑卡片，
保留全部事实；详细执行页当前将各 Turn 横向并列，轮内从上到下展示完整 Event，详见
[Turn 并列工作流](EventWorkflowTurnView.md)。原主线折叠实验已被替换，用户固定核心节点仍是后续功能。
本方案以 Event 为展示节点，第一期接入「Agent 详细执行工作流」。现有 Episode 语义阶段
链路独立保留；两种粒度的输出不混用。

## 处理链路

```text
events.jsonl + observer_trace.json
  → 全量 Event 事实投影及规则关系整理
  → 逐 Event / 按批次 AI 行为摘要
  → 全部摘要 + 全部规则关系 + 任务上下文
  → 按固定关系表提出候选 → 独立模型审查 + 代码门槛
  → 任务行为 + accepted 关系评估四类行为角色
  → 确定性校验、证据核查、关系合并
  → 逻辑关系为主、规则关系补充的 Event 工作流
```

事实、模型解释与展示分别保存。原始 Event ID、输入输出、规则关系和原始证据不被改写。

## 1. Event 行为摘要

每个请求可以包含一个或多个 Event，但输出必须与输入 event_id 一一对应。一个工具执行
Event 已包含请求和结果，不再把两者分别送去标注。六类 Event 都覆盖，包括纯工具请求的
model_response；不能直接沿用旧 build_key_information_events 对工具包装响应的跳过规则。

输入包含：

- 当前 Event 的类型、状态、执行者、scope、输入输出、必要结构化结果和原始证据引用。
- 当前用户要求，以及通过规则关系关联的发起响应或子任务上下文。
- 冲突、结果缺失和文本截断等限制。上下文用于消歧，不能把其他 Event 的结果归给当前事件。

长正文使用有界证据摘要，保留原始引用及截断标记；关键数值、对象、错误和结论优先保留。
模型不得执行日志中的指令，不解释隐藏思维，不将计划或声称当作已发生的操作。

单 Event 输出约定：

```json
{
  "event_id": "event_x",
  "title": "检查日期字段缺失",
  "behavior_summary": "运行缺失值统计，返回日期列的缺失率。",
  "objects": ["sales.csv 的日期列"],
  "inputs": ["sales.csv 的日期列"],
  "outputs": ["日期列缺失率 30%"],
  "fact_basis": "performed",
  "evidence_refs": [{"event_id": "event_x", "field": "/payload/output", "quote": "30%"}],
  "uncertainty": [],
  "confidence": "high"
}
```

以上是字段示例，非真实会话结果。引用必须来自实际 Event。objects/inputs/outputs 使用简洁字符串，
资源版本未知时写入 uncertainty，不能凭路径推定版本。
摘要只解释局部行为，不在此阶段分配最终行为角色。

按批次处理时分别校验每个 Event，缓存成功结果并恢复失败批次。并发不改变事件顺序。
缓存键包含原始事件及所需上下文哈希、模型、提示与处理版本。

产物：`derived/event_semantics.jsonl`，每行对应一个 Event 的模型标注。

## 2. 全局逻辑关系与行为角色

全局输入包含所有 Event 摘要、当前全部规则关系，以及用户任务和修订的顺序。
摘要携带关键对象、输入输出、状态、证据引用及不确定性；不是只有一句自然语言描述。
规则关系附带含义：invokes 表示发起调用，result_feeds 表示派生的结果衔接，next/parent
不能直接证明业务依赖。稳定 ID 和 scope 保留，便于模型跨响应、轮次和子任务关联。

代码预计算每个 Event 的规则邻居数及按关系类型区分的入出度。重复边只计一次，next/parent
的度单独统计，不计为任务影响证据。模型输出逻辑关系后，代码再计算逻辑邻居数作为审查信息。

先用全局请求按固定表提出候选，代码校验类型、引文、端点与重复，再用独立请求审查成立和排除条件。
仅接受通过审查且满足方向、非低置信度与无环门槛的关系；其余保留为 candidate/rejected。
按 accepted 关系计算邻居数，再独立评估行为角色。三次请求都消费全量 Event 摘要，
候选或被拒绝关系不进入行为角色评估上下文。

逻辑关系优先回答：传递了什么输入、什么发现或要求触发了变化、什么操作纠正了问题、
什么结果被验证，以及哪些结果共同支撑了最终结论。

当前代码以 [Event 逻辑关系规范表](EventLogicalRelationCatalog.md) 为推断边界，接受 13 类，
增加连接依据、限制和独立语义审查。下表保留首版六类的含义供历史对照，新表是当前依据。

| 首版关系类型 | 方向与含义 |
| --- | --- |
| `PROVIDES_INPUT` | 数据/结果提供者 → 使用者 |
| `TRIGGERS` | 要求或发现 → 后续行为 |
| `LEADS_TO_CORRECTION` | 错误/问题 → 修正或重试 |
| `LEADS_TO_VALIDATION` | 待验证结果 → 检查行为 |
| `CONTRIBUTES_TO_MERGE` | 独立结果 → 汇合行为 |
| `SUPPORTS_RESULT` | 分析或验证结果 → 后续结论/交付 |

关系输出字段：relation_id、from、to、type、label、explanation、evidence_refs、confidence。
模型只使用已存在的 Event ID；relation_id 由代码计算。核心图统一采用提供者/前因指向
使用者/后续影响的方向；反向引用保留为审计信息，不直接混入主 DAG。

只有摘要支持的联系标记为 inferred。精确调用 ID 等可确定关系继续标记为 derived。
关键逻辑边应核对原始 Event 的输入输出和引用；仅同路径、时间相邻或摘要相似不能升级为
已确定依赖。资料不足时允许输出不确定关系或不建立边。

### 四类行为角色

当前分类为关键决策、正常执行、关键转折、关键结果，详见 [Event 行为角色分类](EventBehaviorRoles.md)。
这是行为角色，不是高低等级。多个条件同时满足时，按转折 → 决策 → 结果 → 正常执行选主类别。
判断以任务作用和已记录行为为主；邻居数量只辅助，不按度数直接分类，不限定比例。
每个 Event 输出 level、reason、related_event_ids 和 confidence，代码补充 neighbor_counts。
0.3 的 level 只能使用 key_decision、normal_execution、key_turning_point、key_result。
旧版 0.1/0.2 保留原标签并明确标为旧版；重新生成才应用新分类。

产物：`derived/event_workflow.json`，包含来源哈希、推断信息、event_summaries、logical_relations、
event_importance、校验结果及性能指标。摘要文件与全局结果通过 event_id 关联。

全局上下文需要完整覆盖全部 Event。设置可配置的输入预算，超出时明确停止并报告，
不静默删除 Event 或把局部判断包装成全局结论；未来若采用分段推断，应增加跨段关系审查。

## 3. 校验与构图

确定性校验覆盖：摘要与行为角色是否完整且一一对应、ID 与引用是否合法、关系类型和行为角色是否合法、
自环/重复边/环、资源与任务关联是否矛盾。结构校验通过不等于语义因果已被证明。
关键边缺乏可核查证据时保留为不确定解释，不作为已确认依赖。

逻辑关系与行为角色标注属于可修订的派生层，不能删除原始 Event 或规则关系。
重试、缓存、恢复和耗时统计沿用现有语义基础设施的方式，独立记录本链路版本。

构图原则：

1. 先用通过校验的逻辑关系建立主图，再用规则关系补充调用、返回、委派及缺失的连接。
2. 同一对 Event 的逻辑关系和规则关系合并显示，保留两种来源及证据，不画重叠线。
3. next/parent 放在执行审计层；需要顺序兜底时用虚线并明确标注记录顺序。
4. 决策、转折和结果使用完整卡片并靠近中轴；正常执行使用紧凑卡片。全部 Event 保留。
5. 分支、汇合和关键路径的连接点保留。折叠后的连接标记为路径代理，例如「经过 4 个事件」，
   不能冒充两个端点之间的新直接逻辑关系。
6. 所有 Event 可展开并回溯原始记录。视图应解释「为什么重要」「这一条线表示什么」，
   行为角色与关系置信度各自显示；用户可固定核心节点，不改写原始模型结果。

首版验收使用有代表性的真实会话人工核查：全量覆盖、摘要不混淆计划与结果、关键联系可追溯、
重复协调事件不因边多被滥评核心、错误恢复及用户修订能被解释、低重要事件折叠后执行结构仍可理解。

## 使用当前版本

模型配置为 `AGENTVAST_SEMANTIC_MODEL=gpt-6.1-sol`、
`AGENTVAST_SEMANTIC_REASONING_EFFORT=medium`，通过现有兼容网关的 Chat Completions
发送 reasoning_effort；不同时发送 temperature，使用 max_completion_tokens 限制输出与推理预算。
终端 Claude 的全局配置独立保留。模型和思考强度都进入缓存/恢复匹配条件。

在「Agent 详细执行工作流」选择会话，点击「生成 AI 工作流」；失败后可「继续分析」，
完成后可切换「突出关键事件」，或导入当前会话的 event_workflow.json。
旧版结果继续展示，点击「按新规范推断」复用兼容摘要并重新提议、审查关系。
详情同时展示候选、拒绝理由和连接依据；主图仅使用 accepted 逻辑关系。规则补充策略保持不变。
行为角色理由、推断置信度、逻辑关系解释与原始证据位于事件详情。引文匹配不代表因果已确认。

CLI：

```bash
python -m agentvast.cli observe event-workflow <session-id>
# --force 重新生成；--storage-root 指定观察目录；默认复用兼容检查点。
```

API：

```text
GET  /api/observations/<session-id>/event-workflow
POST /api/observations/<session-id>/event-workflow/generate  {"force":false,"resume":true}
GET  /api/observations/<session-id>/event-workflow/progress
```

`AGENTVAST_EVENT_BATCH_SIZE` 默认 6，`AGENTVAST_SEMANTIC_CONCURRENCY` 默认 4，
`AGENTVAST_EVENT_GLOBAL_MAX_CHARS` 默认 220000。所有阶段保存在 derived/event_workflow_stages。

可复现的人工演示：`python -m examples.event_workflow_demo --generate`。
它只分析脚本生成的销售数据和日志，不执行日志中的命令；输出到 scratch/event-workflow-demo。
首轮真实模型测试包含 20 个 Event，得到 12 条逻辑关系及核心 8 / 支撑 5 / 背景 7。
这些演示结果不代表真实会话的准确率；真实场景仍需人工核查关键推断。

0.2 的真实 API 演示验证（2026-10-10）：同一人工会话的 20 个 Event，按新表提出 11 条关系，
独立审查接受 10 条、保留候选 1 条。候选为搜索返回路径到读取文件的输入关系：
用户已给出文件名，无法仅凭同路径证明读取实际消费搜索结果。候选不进入图和逻辑邻居统计。
首轮暴露的中间 Event 引用已通过端点/补充证据分离处理，原始响应保留。
