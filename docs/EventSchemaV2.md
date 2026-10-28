# 六类 Event 的事实与关系信息

Event 是从 Transcript 确定性派生的事实记录，供行为解释、执行图和后续语义处理消费。
六类保持不变：`user_prompt`、`model_response`、`tool_execution`、`command_execution`、
`subagent_result`、`control_event`。语义解释与跨事件推断应保存在独立派生层，不覆盖事实。

## 精简存储

新 derive 的 `derived/events.jsonl` 和 `derived/observer_trace.json.events` 使用相同的
精简 Event。Trace 标记 `event_storage_version=compact/1`，类型体系仍是 Event Schema 2.0。

| 字段 | 保留原因 |
| --- | --- |
| `event_id` | 稳定标识，用于关系、证据与语义结果关联 |
| `sequence` | 原始记录顺序；不等同于执行依赖或完成顺序 |
| `event_type`、`event_subtype` | 行为种类与具体子类型 |
| `status`、`origin` | 已记录状态与信息来源，区分缺失、错误和记录冲突 |
| `actor` | 用户、主 Agent、子 Agent 或系统 |
| `scope` | Session、Turn、Response、Tool Use、Task 的关联 ID；省略未知关联 |
| `time` | 起止时间、结构化结果报告的耗时、日志时间间隔 |
| `title`、`summary` | 短展示标签与规则摘要；完整行为证据仍在 payload |
| `payload` | 各类型的文本、工具/命令输入、返回内容、任务结果或控制信息 |
| `provenance` | 原始行号、UUID、父 UUID；工具还保存内容块索引和请求/结果角色 |

删除重复的顶层关联 ID、`timestamp/ended_at`、`source_lines/evidence`、可推导的
`event_class` 和默认 `hidden_by_default=false`。关联只在 scope 保存，时间只在 time 保存，
原始来源只在 provenance 保存。

Payload 去掉重复的响应 ID、耗时、命令文本、响应类型、最终回答标记和子任务 ID/状态。
这些信息分别由 scope、time、input、event_subtype、stop_reason 和顶层 status 表达。
结构化工具结果的额外字段继续保留；已提取的重复 duration/exit-code/输出流字段不再复制。
精确工具耗时与日志起止间隔具有不同含义，都保留在 time。

`load_observer_trace` 和语义处理入口通过 `expand_event` 接受新旧格式；为现有页面和
调用方按需恢复历史字段别名。旧文件不被自动改写；原始 Transcript 保持完整。

## 同一 Tool Use 的重复与差异记录

- 一个 `tool_use_id` 表示一次调用，用请求 ID 与结果 ID 配对，不按日志相邻位置配对。
- 请求内容和所属响应完全相同、结果内容与结构化结果完全相同，才视为重复副本。
  内容只保存一份，但所有原始行号、UUID 与内容块引用都保留。
- 不同请求或不同结果不直接拼接，也不静默覆盖。保留代表记录及
  `alternate_requests/alternate_results`，设置 `request_conflict/result_conflict`，状态为
  `conflicting`。请求代表取最早不同记录，结果代表取最后不同记录；代表字段不能被视为
  已确定的唯一事实，语义处理会同时接收冲突标记与有界的差异证据。
- 差异可能来自增量片段、修订或损坏的记录；缺少明确协议时不自动判断是哪一种。
- 保留相关响应的 invokes 边、来源上下文和诊断信息。稳定 Event ID 的计算方式不变。

只有请求没有结果时标记 incomplete，不推断超时。只有明确结构化结果提供
`timedOut`、`stdout` 或 `stderr` 时才记录对应值；普通工具返回统一保留在 output，
不能冒充真实独立的 stdout/stderr。未知值为 null。

## 事件之间的关系

`observer_trace.json.relations` 独立保存 `from/to/type/origin` 和关系 ID：
`prompts`、`invokes`、`result_feeds`、`spawns` 等表达派生的执行结构；`next`
表示记录顺序；`parent` 保留原始消息父子链接。这几种含义不能混用。

逐 Event 提取语义时，应消费该 Event 的事实，加当前任务与相关调用上下文；输出与
event_id 关联的行为、对象、可观察结果、作用和证据。跨 Event 依赖仍需独立分析。
Episode 阶段语义流程独立保留；逐 Event 标注和逻辑工作流已在
[EventWorkflowInferenceV1.md](EventWorkflowInferenceV1.md) 的首版实现中接入这些事实。
