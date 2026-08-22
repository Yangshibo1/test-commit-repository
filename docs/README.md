# AgentVAST 文档索引

## 现行文档

- [`../README.md`](../README.md)：安装、启动和常用命令。
- [`AgentVAST系统设计总览.md`](AgentVAST系统设计总览.md)：当前产品边界、领域模型和系统架构。
- [`记录字段设计.md`](记录字段设计.md)：schema 1.3 对外 JSON 与记录字段规范。
- [`Claude工作流程约束设计.md`](Claude工作流程约束设计.md)：Plugin/Hook、Plan、Node 和人工介入规则。
- [`Web终端交互层P0计划.md`](Web终端交互层P0计划.md)：Web 终端设计与手动验收依据。
- [`Web交互层P1实施说明.md`](Web交互层P1实施说明.md)：Web Plan 控制、SSE 和多轮 Trace 设计。

当前默认记录通道是 `python -m agentvast.agent_cli` 配合
`claude-plugin/skills/data-analysis/SKILL.md`。`agentvast.mcp_stdio` 是可选通道；旧
`AgentVASTServer`、PROV 多文件 Session 和手动 Tracker API 不属于当前主工作流。

## 历史归档

- [`archive/legacy-tracker/`](archive/legacy-tracker/)：旧 Tracker、PROV 和手动 MCP/API 文档。
- [`archive/implementation-history/`](archive/implementation-history/)：阶段计划、开发上下文和 VAST 实施记录。
- [`archive/incidents/`](archive/incidents/)：已结束的工具和开发故障记录。

归档文档用于历史复核，不应作为当前开发或 Agent 执行指令。
