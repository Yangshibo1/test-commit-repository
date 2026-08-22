# AgentVAST

AgentVAST 是一个面向 Coding Agent 的数据分析工作流记录器。

当前快速原型以 Claude Code 为宿主。Claude Code 独立完成全部数据分析，包括读取数据、编写和运行 Python、选择方法、解释结果以及决定下一步。AgentVAST 不执行分析，只负责：

- 创建并绑定 Run 与 Claude Code session。
- 记录 Claude 声明并实际执行的语义 Node。
- 通过 Hook 记录真实的 Read、Bash、Write、Edit 和 NotebookEdit 事件。
- 对输入和输出文件计算 SHA-256，形成文件级血缘。
- 为每个 Run 创建独立的代码、数据、报告和可视化产物目录。
- 自动发现每个 Node 真实新增或修改的产物，并据此判断是否允许完成。
- 记录和分类分析过程中的人工指导、规划建议与异议。
- 在没有 active Node 或存在未分类人工输入时阻止新的实质性操作。
- 将完整 Run 导出为 JSON。

## 快速安装

在 AgentVAST 仓库中执行：

```powershell
python -m pip install -e .
```

需要本机已经安装并登录 Claude Code。

## 一键启动 Web 前后端

Windows 下双击仓库根目录的 `启动AgentVAST.bat`。脚本默认使用
`VAST_Challenge_2026_MC2（1）\VAST_Challenge_2026_MC2` 作为分析项目，并分别启动：

- AgentVAST Web 后端：`http://127.0.0.1:8765`
- 前端：`http://localhost:3000`

也可以在命令行传入其他分析项目目录：

```powershell
.\启动AgentVAST.bat "C:\path\to\analysis-project"
```

Web 功能依赖尚未安装时，先执行：

```powershell
python -m pip install -e ".[web]"
```

## 启动一次被记录的数据分析

```powershell
agentvast run `
  --project C:\path\to\analysis-project `
  --task "分析销售数据中的异常变化并说明原因" `
  --data data\sales.csv `
  --checkpoint plan
```

AgentVAST 会先创建 Run 和标准产物目录，再启动加载了本仓库 `claude-plugin` 的交互式 Claude Code。之后仍然由用户和 Claude 在原来的终端中完成数据分析。每个 Node 需要哪些代码、数据、JSON报告或可视化产物，由 Claude 根据真实分析目标在 Plan 中判断。

AgentVAST 启动的 Claude 默认使用 `--dangerously-skip-permissions`，避免分析过程中反复出现
文件和命令权限确认。AgentVAST 自身的 Plan、Node、人工输入和 checkpoint Hook 门禁仍然
生效。

为避免兼容网关在 Claude Code 自动压缩前先返回 context-window 错误，启动器固定设置：

```text
CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000
CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80
```

即按 200,000 token 的计算窗口在约 80%（约 160,000 token）时触发压缩，为压缩请求和
模型输出预留空间。可通过 `agentvast run/resume` 的 `--compact-window` 与
`--compact-percent` 覆盖；兼容网关的实际限制更小时，应继续提前阈值。插件同时记录
`PreCompact`、`PostCompact` 和 `StopFailure` 内部事件；压缩后 `SessionStart` 会重新注入
当前 AgentVAST 状态。

默认记录通道是 Claude Code 内置 Bash 工具调用 `python -m agentvast.agent_cli` 命令。插件不会注册 AgentVAST MCP server，因此不会产生动态 `tool_reference` 内容块，可以兼容不支持该协议块的 Anthropic API 网关。MCP server 代码仍作为未来可选通道保留，但当前启动器不会加载它。

该命令只接受结构化 JSON 并写入当前 Run，不读取数据、不运行分析程序。典型记录命令如下：

```bash
python -m agentvast.agent_cli set-plan --payload '{"nodes":[{"node_id":"profile","objective":"检查数据结构和质量","depends_on":[],"required_artifacts":["code","data"]},{"node_id":"visualize","objective":"可视化主要特征与异常","depends_on":["profile"],"required_artifacts":["visualization"]}]}'
# plan checkpoint 模式会在这里自动暂停；用户确认 Plan 后才能 start-node。
# 使用 set-plan 返回的稳定编号，而不是提交时的别名：
python -m agentvast.agent_cli start-node --payload '{"node_id":"node-001"}'
python -m agentvast.agent_cli complete-node --payload '{"node_id":"node-001","input_files":["C:/data/input.csv"],"operation_summary":"检查结构并汇总数据质量","result_summary":"文件包含100行，两个字段具有较高缺失率。","analysis_conclusion":"建模前需要验证这两个字段是否可用。","analysis_outcome":"partial"}'
```

未指定输入文件时，Claude 可以先使用只读文件发现能力理解任务。`declare-inputs`保留为可选的
提前登记方式，不再是分析前置条件：

```bash
python -m agentvast.agent_cli declare-inputs --payload '{"input_files":["C:/absolute/input.csv"]}'
```

初始文件和提前登记文件不是输入白名单。Node 启动后，Claude 可以像普通 Claude Code
会话一样使用其有权限访问的相关文件；`complete-node` 再提交该 Node 实际使用的文件。
AgentVAST 对已知文件使用 Node 启动时冻结的版本，对执行中首次发现的外部文件在完成时计算
SHA-256、加入 Run 输入并形成文件血缘。Run 结果目录内由当前 Node 新建的文件仍只能作为
输出，不能伪报为输入。

每个 Run 的正式产物保存在 `result/<run_id>/` 下：

```text
code/           node-001_profile.py
data/           node-001_profile.json
report/         node-001_findings.json
visualization/  node-002_anomalies.html
workflow.json   最终规范化工作流记录
```

Node 完成时 AgentVAST 自动比较目录快照并记录变化，不要求 Claude 额外整理输出清单。
新建文件必须带生成它的 Node 编号；后续 Node 可以原位编辑先前产物，并把编辑前版本申报
为输入、编辑后版本记录为当前 Node 输出。需要代码的 Node 还必须真实执行其中至少一个代码产物。
`start-node` 只建立执行边界并冻结当时可用的文件版本；`complete-node` 才提交本 Node
实际使用的输入文件。Agent只能调整未来的pending Node；active/completed Node必须继续保留，
且其目标、依赖和产物要求不能被后续Plan Revision改写。

开发和自动化测试时，可以只创建 Run、不启动 Claude：

```powershell
agentvast run --project . --task "分析数据质量" --data data.csv --no-launch
```

## 人工介入

直接在正在运行的 Claude Code 会话中输入即可。Hook 会保存原文，Claude 在继续实质性分析前将输入分类为：

- `conversation_only`
- `checkpoint_continue`
- `analysis_guidance`
- `planning_input`
- `challenge`

人工输入不是 Node。`checkpoint_continue` 只表示用户在 checkpoint 明确确认或要求继续，不作为对外展示的人工贡献；其余有效介入可以改变当前 Node 的执行、生成 Plan 修订，或者触发后续验证/纠正 Node。

对于后三种输入，Claude 还会运行 `python -m agentvast.agent_cli apply-user-input` 记录它实际造成的计划或执行变化；仅仅完成分类不能解除实质操作门禁。

人工输入记录命令支持简写。例如：

```bash
python -m agentvast.agent_cli classify-user-input input_526013878f88 challenge
python -m agentvast.agent_cli apply-user-input input_526013878f88 "用户否定原分析方向，后续计划改为验证传播链与系统机制"
```

`--checkpoint` 控制 Claude 主动停下来等待用户的时机：

- `plan`：默认值；每个新Plan Revision提交后都自动暂停，用户确认当前版本后继续执行，结束时不再确认。
- `node`：每个Plan Revision都先确认，之后每个Node完成后再暂停。
- `none`：不设置人工 checkpoint，保留全自动运行方式。

checkpoint期间Claude当前回合可以正常结束，但Run仍为 `active`。在Plan checkpoint中，用户可以确认、修改或质疑规划；确认被分类为 `checkpoint_continue` 后，且确认版本等于最新Plan Revision，才允许继续实质性分析。`plan`模式不设置最终checkpoint。

当前 Plan 全部完成后，Run 默认继续保持 `active`。用户后续在同一 Claude 会话中提出分析
要求时，Claude 必须保留已完成 Node，并通过新的 Plan Revision 增加后续 Node。只有用户
明确点击“完成并封存 Trace”或 `New Task Trace` 时，AgentVAST 才结束并导出当前记录；
`New Task Trace`还会继续在同一Claude会话中创建新的Run。

Web中的Plan“保存”只创建结构化Revision，不向Claude提交执行。“确认当前Revision并执行”
才发送一次继续消息，避免编辑保存和确认产生重复任务。右下任务区由SQLite计算的Run phase
驱动：生成Plan、等待确认、执行、等待后续输入和已结束状态不会共用同一个提交表单。

## 查看、恢复和导出

```powershell
agentvast state <run-id> --project C:\path\to\analysis-project
agentvast resume <run-id> --project C:\path\to\analysis-project
agentvast export <run-id> --project C:\path\to\analysis-project
```

内部数据库位于分析项目的 `.agentvast/workflow.sqlite3`。默认公开导出文件与分析产物统一位于
`result/<run_id>/workflow.json`。Claude 成功执行 `finish-run` 时会自动生成最终规范化 JSON；也可以随时使用
`agentvast export` 手动重新生成。

普通终端关闭或网络中断时，使用同一个 Claude transcript 恢复：

```powershell
agentvast resume <run-id> --project C:\path\to\analysis-project
```

如果旧 transcript 已达到上下文上限，使用 fresh-session 恢复：

```powershell
agentvast resume <run-id> --project C:\path\to\analysis-project --fresh-session
```

fresh-session 会创建新的 Claude session，但继续绑定同一个 active AgentVAST Run。恢复提示
包含当前 Plan、completed Node 摘要、active Node、待处理人工输入和已有 Run 产物；SQLite
仍是工作流状态来源。completed Node 不会重做，active Node 从现有产物继续。

已完成或已终止的 Run 不可继续恢复；需要追加分析时创建一个新 Run。`agentvast resume`
只用于仍为 `active` 的 Run，例如 API 错误或主动关闭终端后的恢复。

如果 Claude 会话因 API 或工具参数错误而无法恢复，保留历史并终止 Run：

```powershell
agentvast abort <run-id> --project C:\path\to\analysis-project --reason "Claude API error"
```

## Reviewer 派生资产

Run 完成后，AgentVAST 可以启动一个与主分析 Claude 会话分离的短任务 Reviewer。它不会
改写 `workflow.json`、代码、中间数据或报告，只在 `trace_assets/` 中生成供前端使用的
派生内容：代码逻辑说明、中间数据画像与图表数据、报告核心发现，以及整次分析对原始问题
的回答覆盖、分析缺陷和后续方向。

Reviewer 使用 OpenAI-compatible Chat Completions API。启动 AgentVAST Web 前设置：

```powershell
$env:AGENTVAST_REVIEW_API_BASE_URL = "https://your-provider.example/v1"
$env:AGENTVAST_REVIEW_API_KEY = "your-api-key"
$env:AGENTVAST_REVIEW_MODEL = "your-model"
```

点击“完成并保存 Trace”或 `New Task Trace` 后，如果这些变量已经配置，Web 后端会在
后台自动生成派生资产；失败不会改变已完成 Run。也可以手动启动或强制创建新版本：

```powershell
agentvast review <run-id> --project C:\path\to\analysis-project
agentvast review-status <run-id> --project C:\path\to\analysis-project
agentvast review <run-id> --project C:\path\to\analysis-project --force
```

生成目录采用不可变版本，`current.json` 只指向当前可用版本：

```text
result/<run_id>/trace_assets/
  current.json
  review_status.json
  review-001/
    manifest.json
    answer_review.json
    nodes/node-001.json
    chart_data/node-001-data-001-chart-001.json
```

Reviewer 不靠文件名猜测工作流。它以 `workflow.json` 的 Node 输出和 SHA-256 为入口，
只处理与 Node 完成时一致的文件版本。每个产物任务会注入原始任务、声明的任务说明文本、
当前 Node、最近前序 Node 的结果/结论/文件流，以及已经生成的前序 Reviewer 摘要；只有
Run 级综合复核才注入完整 Plan Revision 和人工介入摘要。这样保留真实分析上下文，同时
避免把整份 workflow 和大数据文件反复塞进模型上下文。

Web 查询接口为 `GET /api/runs/<run-id>/review` 和
`GET /api/runs/<run-id>/review/assets`；也可以用
`POST /api/runs/<run-id>/review` 手动调度，JSON 请求体为 `{"force": false}`。

## Node 边界

Python 脚本、命令或文件创建都不会自动形成 Node。Node 必须表示一个可以独立说明和验收的分析目标。Node 编号由 AgentVAST 分配为 `node-001`、`node-002` 等。

如果中间结果必须先被 Claude 观察才能决定后续工作，或者中间文件会被另一个语义任务消费，它通常值得作为正式输出记录。仅在当前 Node 内使用的缓存、调试和临时文件不进入对外 workflow JSON。

## 原型边界

- 文件血缘只到文件版本级。
- AgentVAST 不解析 Python 内部的所有读写行为。
- Node 目标来自 Plan；操作摘要、结果摘要和分析结论由 Claude 如实提交；命令和程序路径由 Hook 观察。
- 原型不包含多人协作、审批、云同步、细粒度字段血缘或前端重构。
