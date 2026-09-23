# Claude Code Passive Observer V1

Passive Observer 在不启用 AgentVAST Plan、Node、产物门禁或 prompt 注入的情况下，记录
Claude Code 暴露的原始行为。现有 enforce 模式保持不变。

## 启动

基础观察（Hook + Transcript，禁用 OTel）：

```powershell
agentvast observe start --project "C:\path\to\analysis-project" --no-otel
```

基础 Observer 仅使用 Python 标准库，不需要安装 MCP。

完整观察（Hook + OTel + Transcript）：

```powershell
python -m pip install -e ".[observer]"
agentvast observe start --project "C:\path\to\analysis-project"
```

可选保存 Claude Code Raw API Body：

```powershell
agentvast observe start `
  --project "C:\path\to\analysis-project" `
  --capture-api-bodies
```

`observe start` 不提交初始 prompt，Claude 启动后由用户正常输入任务。所有 Observer 会话
统一使用 `--dangerously-skip-permissions` 启动 Claude Code，避免权限确认打断长时间数据分析。
该参数只关闭 Claude Code 的工具权限询问，不会启用 AgentVAST Plan、Node、prompt 注入或
执行门禁；Observer 仍然只记录可观察事件。

Observer 面向当前 Claude Code Hook schema，启用 MessageDisplay、PostToolBatch、
PermissionDenied、Subagent、Task 和 async Hook。使用前应执行 `claude update` 并确认
`claude --version` 为当前版本。

Transcript fallback 仍然保留：当 Hook 配置错误、异步事件丢失或 Session 异常终止时，可以
从原生 transcript 确定性重建可见消息和工具调用，并明确标记为 `transcript_fallback`，不会
伪装成完整 Hook capture。

`MessageDisplay` 只有在片段索引从 0 连续、没有重复且收到最终片段时，才会被提升为完整的
canonical assistant message。片段缺失时，原始 Hook 仍保留在 `raw/hooks.jsonl`，派生层改用
原生 transcript 中的完整回复；`validate` 会报告
`incomplete_message_display_streams`、缺失索引和降级原因。

## 管理和处理

```powershell
agentvast observe sessions
agentvast observe status <session-id>
agentvast observe stop <session-id>
agentvast observe derive <session-id>
agentvast observe validate <session-id>
agentvast observe semantic <session-id> --rules-only
agentvast observe export <session-id>
```

`observe stop`只执行 transcript snapshot 和 manifest finalization，不终止 Claude 进程。正常
交互式使用时，直接退出 Claude；`observe start` 会在 Claude 退出后自动 finalization。

`observe derive` 同时生成 `derived/observer_trace.json`。该文件是 Passive Observer 页面使用的
只读展示 Bundle；浏览器不直接解析或修改原始 transcript。

旧版 Hook 未记录 transcript path 时，可以显式恢复：

```powershell
agentvast observe stop <session-id> --transcript-path "C:\path\to\claude-session.jsonl"
```

## 查看记录

默认 Session 目录：

```text
C:\Users\<用户名>\.agentvast\observations\<session-id>\
```

建议依次查看：

```text
manifest.json                           数据源与 Hook profile
diagnostics/validation_report.json     完整性和降级状态
derived/canonical_events.jsonl         采集与关联层中间事件（内部使用）
derived/events.jsonl                   Event Schema 2.0 工作流事件
derived/tool_calls.jsonl               工具调用
derived/messages.jsonl                 用户与 Claude 可见消息
derived/observer_trace.json            Passive Observer 页面数据
raw/hooks.jsonl                        原始 Hook payload
raw/otel.jsonl                         原始 OTLP 请求
transcript/transcript.jsonl            Claude 原生 transcript 快照
```

`validation_report.json` 中 `valid: false`、`usable: true`、
`capture_mode: hybrid_fallback` 表示 Hook 存在缺口，但已经用 transcript 恢复，派生记录仍可用于
分析。查看 `warnings`、`incomplete_message_displays`、`unresolved_tools` 可以区分已恢复缺口和
真正无法恢复的事件。

## 存储

默认目录：

```text
~/.agentvast/observations/<session-id>/
├─ manifest.json
├─ raw/
│  ├─ hooks.jsonl
│  ├─ otel.jsonl
│  ├─ transcript.jsonl
│  └─ api/
├─ transcript/
│  ├─ source_path.txt
│  └─ transcript.jsonl
├─ derived/
│  ├─ canonical_events.jsonl
│  ├─ events.jsonl
│  ├─ messages.jsonl
│  ├─ tool_calls.jsonl
│  ├─ agents.jsonl
│  ├─ observer_trace.json
│  ├─ semantic_workflow.json
│  ├─ semantic_workflow_reviewed.json
│  ├─ semantic_reviews.jsonl
│  ├─ semantic_workflows/
│  └─ semantic_stages/
└─ diagnostics/
   ├─ missing_events.json
   ├─ unmatched_events.json
   ├─ validation_report.json
   └─ otel_collector.stderr.log
```

`canonical_events.jsonl` 保留采集源合并、去重和关联所需的内部记录；面向语义提取、关系推断与
可视化的统一输入为 `events.jsonl`。后者只包含 Event Schema 2.0 的六类工作流 Event，不包含
用户手动命令和常规系统遥测。

可以使用 `--storage-root` 或 `AGENTVAST_OBSERVER_ROOT` 修改根目录。观察文件不写入 Claude
当前分析项目，避免被 Agent 搜索或读取。

`observe start` 会在 `~/.agentvast/observer-registry/` 保存 session 到 storage root 的映射。
Hook runner 根据 Claude payload 自带的 `session_id` 查询该映射；Observer 不向 Claude 注入
`AGENTVAST_OBSERVER_*` 环境变量，也不修改 Claude 分析子进程的 `PYTHONPATH`。
Observer 同样不会重排 Claude 的 `PATH`；启动前要求用户原有环境已经可以运行 `python`。

## Transcript-only 处理规则

Observer 对 transcript 采用以下顺序处理：

1. 按 JSONL 行读取并保留原始行号，原文件不覆盖、不清洗；
2. 只把 `origin.kind=human`、`promptSource=typed/pasted/voice` 或带稳定
   `promptId` 的普通文本识别为人工 Prompt；
3. `/exit`、`local-command-caveat` 和用户本地命令不生成工作流 Event；
4. 使用 `message.id` 合并同一模型响应，并将工具请求、可见文本和最终回答统一为
   `model_response`；
5. 使用 `tool_use_id` 精确配对请求和结果；PowerShell、Bash 等 Agent Command 派生为
   `command_execution`，其余结构化工具派生为 `tool_execution`；
6. 使用 `uuid/parentUuid` 保存原始父子链，并从 Prompt、Response、Tool、Final Answer
   确定性生成紧凑执行图；
7. 事件 ID 由 Session、来源行和稳定标识计算，重复 derive 不改变节点 ID；
8. 普通 `turn_duration`、`stop_hook_summary` 等系统记录进入 `telemetry`；只有权限拒绝、
   超时、取消、上下文压缩等改变控制流的记录才生成 `control_event`；
9. 成本、模型、权限模式和会话级耗时作为 Session 指标保存。

`observer-trace/2.0` 的工作流 Event 固定为六类：

```text
user_prompt
model_response
tool_execution
command_execution
subagent_result
control_event
```

每条 Event 保留稳定公共字段，并增加 `event_class`、`event_subtype`、`actor`、`scope`、
`time` 和 `provenance`。完整 Event 流同时写入 `derived/events.jsonl`；原始 transcript 继续作为
不可变证据保存在 `raw/transcript.jsonl`，不会因为 Event 精简而被删除。

`observer_trace.json` 中只有 `observed` 和可重复计算的 `derived` 数据，不生成 Exploration、
Analysis、Validation 等语义阶段。工具调用到结果之间的 transcript 时间差记录为
`observed_elapsed_ms`，它不是精确工具运行时间；只有原始结构化结果提供的 `durationMs` 才作为
精确单次工具耗时。

## Passive Observer 页面

AgentVAST Web 顶部新增“被动观察”页面。页面通过只读接口加载已经 derive 的 Session：

```text
GET /api/observations
GET /api/observations/<session-id>/trace
```

页面提供 Session 列表、执行时间线、Prompt → 模型响应/工具批次 → 工具结果 → 最终回答图、
工具错误状态、成本与耗时指标，以及可回溯到 transcript 行号的 Inspector。也可以离线加载单个
`observer_trace.json`。该页面没有启动、停止、审批或修改 Claude 的控制能力。

页面提供“语义工作流 / 执行轨迹”两级视图。执行轨迹保留 Event 与 transcript 行号回链，并
显示工具执行过程中生成的本地文件节点；点击文件节点可由操作系统默认应用直接打开。语义
工作流属于独立的事后推断层，生成与人工校正规则见
[SemanticWorkflowV1.md](SemanticWorkflowV1.md)。人工校正只写入 Observer 派生目录，不会
向 Claude 发送消息或改变已记录的会话。

## 被动性保证

Observer Hook：

- 不返回 `permissionDecision`、`decision`、`additionalContext` 或 `stopReason`；
- 不修改 prompt 和 tool input；
- 不阻止工具、任务完成或 Stop；
- 正常情况下 stdout/stderr 均为空；
- Collector 自身错误被写入 `observer_errors.jsonl`，Hook 仍退出 0；
- 高频事件使用 Claude Code async command Hook；
- `Stop`、`StopFailure`、`SessionEnd`仅同步执行快速落盘，提高终态完整性。

异步 Hook 仍会产生本地进程和 I/O，因此观察效应不能严格为零，但它不应进入 Claude 上下文
或改变 Claude 的决策。

## OTel 兼容降级

OTLP HTTP Collector 始终先保存完整请求 body 的 Base64 表示。安装
`opentelemetry-proto` 后会同时解析 OTLP protobuf；依赖不可用或 schema 无法解析时：

- raw body 仍保留；
- `decode_error` 明确记录原因；
- validation 产生告警；
- 不根据 timestamp 猜测或伪造 correlation。

## Canonical 数据边界

V1 只产生：

```text
observed
derived
```

不会生成 Exploration、Cleaning、Visualization、Validation 等 workflow 语义。Canonical
事件通过 `tool_use_id`、`prompt_id` 和 transcript 中的稳定 ID 对齐，并在 `evidence` 中保留
来源事件。不能匹配的工具事件进入 diagnostics，不会静默丢弃。

## 隐私与安全

观察数据可能包含：

- 用户 prompt；
- Claude 最终回复和 streaming 文本；
- 文件路径和 Read 结果；
- Bash/PowerShell 命令及输出；
- 子 Agent transcript；
- 可选的完整 API request/response body。

`--capture-api-bodies` 只能在明确同意保存完整会话内容时使用。观察目录应设置适当的访问权限、
保留期限和脱敏流程，不应直接提交到 Git。
