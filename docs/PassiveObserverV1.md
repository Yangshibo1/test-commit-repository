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

`observe start` 不提交初始 prompt，也不改变 Claude 的权限模式。Claude 启动后由用户正常输入
任务。只有显式传入 `--permission-mode` 时，Observer 才把该参数转交 Claude Code。

## 管理和处理

```powershell
agentvast observe sessions
agentvast observe status <session-id>
agentvast observe stop <session-id>
agentvast observe derive <session-id>
agentvast observe validate <session-id>
agentvast observe export <session-id>
```

`observe stop`只执行 transcript snapshot 和 manifest finalization，不终止 Claude 进程。正常
交互式使用时，直接退出 Claude；`observe start` 会在 Claude 退出后自动 finalization。

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
│  ├─ messages.jsonl
│  ├─ tool_calls.jsonl
│  └─ agents.jsonl
└─ diagnostics/
   ├─ missing_events.json
   ├─ unmatched_events.json
   ├─ validation_report.json
   └─ otel_collector.stderr.log
```

可以使用 `--storage-root` 或 `AGENTVAST_OBSERVER_ROOT` 修改根目录。观察文件不写入 Claude
当前分析项目，避免被 Agent 搜索或读取。

`observe start` 会在 `~/.agentvast/observer-registry/` 保存 session 到 storage root 的映射。
Hook runner 根据 Claude payload 自带的 `session_id` 查询该映射；Observer 不向 Claude 注入
`AGENTVAST_OBSERVER_*` 环境变量，也不修改 Claude 分析子进程的 `PYTHONPATH`。
Observer 同样不会重排 Claude 的 `PATH`；启动前要求用户原有环境已经可以运行 `python`。

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
