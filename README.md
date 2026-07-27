# OpenTrace

OpenTrace 是一个面向 Coding Agent 的数据分析工作流记录器。

当前快速原型以 Claude Code 为宿主。Claude Code 独立完成全部数据分析，包括读取数据、编写和运行 Python、选择方法、解释结果以及决定下一步。OpenTrace 不执行分析，只负责：

- 创建并绑定 Run 与 Claude Code session。
- 记录 Claude 声明的语义 Plan 和 Step。
- 通过 Hook 记录真实的 Read、Bash、Write、Edit 和 NotebookEdit 事件。
- 对输入和输出文件计算 SHA-256，形成文件级血缘。
- 记录和分类分析过程中的人工指导、规划建议与异议。
- 在没有 active Step 或存在未分类人工输入时阻止新的实质性操作。
- 将完整 Run 导出为 JSON。

## 快速安装

在 OpenTrace 仓库中执行：

```powershell
python -m pip install -e .
```

需要本机已经安装并登录 Claude Code。

## 启动一次被记录的数据分析

```powershell
opentrace run `
  --project C:\path\to\analysis-project `
  --task "分析销售数据中的异常变化并说明原因" `
  --data data\sales.csv
```

OpenTrace 会先创建 Run，再启动加载了本仓库 `claude-plugin` 的交互式 Claude Code。之后仍然由用户和 Claude 在原来的终端中完成数据分析。

默认记录通道是 Claude Code 内置 Bash 工具调用 `python -m opentrace.agent_cli` 命令。插件不会注册 OpenTrace MCP server，因此不会产生动态 `tool_reference` 内容块，可以兼容不支持该协议块的 Anthropic API 网关。MCP server 代码仍作为未来可选通道保留，但当前启动器不会加载它。

该命令只接受结构化 JSON 并写入当前 Run，不读取数据、不运行分析程序。典型记录命令如下：

```bash
python -m opentrace.agent_cli set-plan --payload '{"nodes":[{"node_id":"n1","objective":"检查数据结构和质量","step_type":"inspect","depends_on":[]}]}'
python -m opentrace.agent_cli start-step --payload '{"node_id":"n1","objective":"检查数据结构和质量","input_files":["C:/data/input.csv"],"completion_condition":"得到结构、质量问题和关键观察","expected_output_roles":["step_output"]}'
python -m opentrace.agent_cli complete-step --payload '{"step_id":"step_...","operation_summary":"检查结构并计算质量统计","processing_result":{"rows":100},"analysis_conclusion":{"summary":"发现两个高缺失率字段"}}'
python -m opentrace.agent_cli finish-run
```

开发和自动化测试时，可以只创建 Run、不启动 Claude：

```powershell
opentrace run --project . --task "分析数据质量" --data data.csv --no-launch
```

## 人工介入

直接在正在运行的 Claude Code 会话中输入即可。Hook 会保存原文，Claude 在继续实质性分析前将输入分类为：

- `conversation_only`
- `analysis_guidance`
- `planning_input`
- `challenge`

人工输入不是 Step。它可以改变当前 Step 的执行、生成 Plan 修订，或者触发后续验证/纠正 Step。

对于后三种输入，Claude 还会运行 `python -m opentrace.agent_cli apply-user-input` 记录它实际造成的计划或执行变化；仅仅完成分类不能解除实质操作门禁。

## 查看、恢复和导出

```powershell
opentrace state <run-id> --project C:\path\to\analysis-project
opentrace resume <run-id> --project C:\path\to\analysis-project
opentrace export <run-id> --project C:\path\to\analysis-project
```

默认数据库位于分析项目的 `.opentrace/workflow.sqlite3`，导出文件位于 `.opentrace/exports/`。

如果 Claude 会话因 API 或工具参数错误而无法恢复，保留历史并终止 Run：

```powershell
opentrace abort <run-id> --project C:\path\to\analysis-project --reason "Claude API error"
```

## Step 边界

Python 脚本、命令或文件创建都不会自动形成 Step。Step 必须表示一个可以独立说明和验收的分析目标。

如果中间结果必须先被 Claude 观察才能决定后续工作，或者中间文件会被另一个语义任务消费，它通常应当作为当前 Step 的 `step_output`。只在当前 Step 内使用的文件是 `internal_intermediate`，缓存和调试文件是 `temporary`。

## 原型边界

- 文件血缘只到文件版本级。
- OpenTrace 不解析 Python 内部的所有读写行为。
- Step 语义、算法用途、处理结果和结论由 Claude 如实提交；命令和工具事件由 Hook 观察。
- 原型不包含多人协作、审批、云同步、细粒度字段血缘或前端重构。
