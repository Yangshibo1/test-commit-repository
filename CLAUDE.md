# AgentVAST 开发与分析约定

AgentVAST 是面向 Coding Agent 数据分析任务的本地工作流记录与约束系统。Claude Code
负责真实的数据读取、程序执行、分析和结论；AgentVAST 负责 Plan/Node 边界、Hook 观察、
产物校验、文件级血缘和 schema 1.3 导出。

## 当前事实来源

按以下优先级理解系统：

1. `claude-plugin/skills/data-analysis/SKILL.md`：被记录的数据分析 Run 的执行规则。
2. `docs/记录字段设计.md`：schema 1.3 字段规范。
3. `docs/Claude工作流程约束设计.md`：Plan、Node、人工介入和 Hook 门禁。
4. `docs/AgentVAST系统设计总览.md`：产品边界和总体架构。
5. `docs/PassiveObserverV1.md`：不干预 Claude 执行的观察模式。
6. `README.md`：安装、启动和用户命令。

`docs/archive/` 中的内容只用于历史复核，不是当前操作说明。

## 当前运行架构

- 内部事实源：`<analysis-project>/.agentvast/workflow.sqlite3`。
- 对外记录：`<analysis-project>/result/<run_id>/workflow.json`。
- 用户入口：`agentvast run/resume/state/export/review/abort/web`。
- Agent 记录入口：`python -m agentvast.agent_cli <action>`。
- 默认 Claude 集成：`claude-plugin` 的 SessionStart、PreToolUse、PostToolUse、
  UserPromptSubmit 和 Stop Hook。
- `agentvast.mcp_stdio` 是可选通道，默认启动器不依赖 MCP。
- `agentvast observe` 使用独立的 `claude-observer-plugin`，只保存 Hook、OTel 和 Transcript
  原始事件，不创建 enforce Run，也不注入工作流约束。

## 开发规则

- 使用 Run、Plan Revision、Node、Artifact、Human Intervention 术语。
- SQLite 内部兼容字段可以继续使用 `steps/step_id`，对外文档和 JSON 使用 `nodes/node_id`。
- 不把 Read、Write、Bash 等单次工具调用直接当作语义 Node。
- 不记录或要求 chain-of-thought。
- 新功能应优先扩展 `WorkflowStore`、CLI、Plugin/Hook 和规范化 JSON，不应重新依赖旧的
  `AgentVASTServer`、`LineageTracker` 或 PROV 多文件 Session。
- 正式 Python 测试放在 `tests/`，VAST 专项测试放在 `tests/vast/`。
- 临时验证文件放在 `scratch/`，不要在仓库根目录或 `test/` 新建临时脚本。
- 运行产物放在 `result/<run_id>/`，不提交 `result/run_*`、缓存或临时 worktree 备份。

## 兼容模块

`agentvast/mcp_server.py`、`tracker.py`、`prov_dag.py` 和 `step_details.py` 属于旧 Tracker
兼容层。除非任务明确要求维护兼容接口，否则不要用它们设计新的工作流功能。对应旧文档位于
`docs/archive/legacy-tracker/`。
