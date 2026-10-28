# AgentVAST 文档索引

## 现行文档

- [`../README.md`](../README.md)：安装、启动和常用命令。
- [`AgentVAST系统设计总览.md`](AgentVAST系统设计总览.md)：当前产品边界、领域模型和系统架构。
- [`记录字段设计.md`](记录字段设计.md)：schema 1.3 对外 JSON 与记录字段规范。
- [`Claude工作流程约束设计.md`](Claude工作流程约束设计.md)：Plugin/Hook、Plan、Node 和人工介入规则。
- [`Web终端交互层P0计划.md`](Web终端交互层P0计划.md)：Web 终端设计与手动验收依据。
- [`Web交互层P1实施说明.md`](Web交互层P1实施说明.md)：Web Plan 控制、SSE 和多轮 Trace 设计。
- [`PassiveObserverV1.md`](PassiveObserverV1.md)：不介入 Claude 工作流的 Hook/OTel/Transcript 观察模式。
- [`EventSchemaV2.md`](EventSchemaV2.md)：六类 Event 的精简字段、Tool Use 配对和执行关系。
- [`SemanticWorkflowV1.md`](SemanticWorkflowV1.md)：证据驱动的阶段划分、语义标注与校验。
- [`SemanticSwimlanes.md`](SemanticSwimlanes.md)：工作流可视化的输入、规划、执行、修改四泳道及现有阶段上的语义聚合。
- [`EventWorkflowInferenceV1.md`](EventWorkflowInferenceV1.md)：已实现的逐 Event 行为摘要、逻辑关系、四类行为角色评估与加权执行图。
- [`EventLogicalRelationCatalog.md`](EventLogicalRelationCatalog.md)：已接入 0.2 的逻辑关系固定表，包含 13 类关系的成立条件、排除条件与独立审查门槛。
- [`EventBehaviorRoles.md`](EventBehaviorRoles.md)：关键决策、正常执行、关键转折、关键结果的分类标准与旧版兼容。
- [`EventWorkflowTurnView.md`](EventWorkflowTurnView.md)：当前各 Turn 横向并列、轮内向下展开的完整 Event 工作流布局和交互。
- [`EventFeedback.md`](EventFeedback.md)：选择 Event、预览修改意见 Prompt 并发送给同一 Claude 会话，指导后续执行。
- [`EventWorkflowVisualizationV1.md`](EventWorkflowVisualizationV1.md)：已被 Turn 展示替换的主线折叠和固定列布局实验记录。

当前默认记录通道是 `python -m agentvast.agent_cli` 配合
`claude-plugin/skills/data-analysis/SKILL.md`。`agentvast.mcp_stdio` 是可选通道；旧
`AgentVASTServer`、PROV 多文件 Session 和手动 Tracker API 不属于当前主工作流。

## 历史归档

- [`archive/legacy-tracker/`](archive/legacy-tracker/)：旧 Tracker、PROV 和手动 MCP/API 文档。
- [`archive/implementation-history/`](archive/implementation-history/)：阶段计划、开发上下文和 VAST 实施记录。
- [`archive/incidents/`](archive/incidents/)：已结束的工具和开发故障记录。

归档文档用于历史复核，不应作为当前开发或 Agent 执行指令。

- [动态 Turn Trace 第一版](DynamicTurnTraceV1.md)：持续读取 transcript、逐轮固定快照分析、恢复及页面自动更新。
