# Claude Node 工作流程约束设计

## 1. 目标

OpenTrace 约束 Claude Code 按照可记录、可解释且颗粒度合理的 Node 链完成数据分析：

1. 没有 Plan 时不能开始实质性分析。
2. 每个实质性工具调用都属于一个 active Node。
3. 每个实际 Node 对应当前 Plan Revision 中同一 `node_id`。
4. 目标或依赖变化时必须先修订 Plan。
5. 人工介入不能被静默忽略。
6. 只有全部 Node 记录完整后 Run 才能完成。

对外字段见[记录字段设计.md](记录字段设计.md)。

## 2. 四层约束

```text
SessionStart规则注入
→ SQLite状态机
→ PreToolUse/Stop门禁
→ 记录命令校验
```

Prompt 帮助 Claude 理解；状态机和 Hook 负责强制执行。

## 3. 状态机

```text
RUN_CREATED
  ↓ set-plan
PLAN_READY
  ↓ start-node
NODE_ACTIVE
  ↓ complete-node
PLAN_READY
  ↓ start-node / set-plan / finish-run
RUN_COMPLETED
```

异常终止：

```text
NODE_ACTIVE → NODE_INTERRUPTED
任意运行状态 → RUN_ABORTED / RUN_FAILED
```

内部 SQLite 可以继续使用旧 `steps/step_id` 表结构承载 active 状态和 Hook 关联，但该名称
不进入 Agent 协议或最终 JSON。

## 4. SessionStart 注入

每次 Claude 会话启动时动态注入：

- 当前 Run；
- 最新 Plan Revision；
- active Node；
- 声明的输入文件；
- 未处理人工输入；
- Node 颗粒度规则；
- 当前合法的记录命令。

主要命令：

```text
set-plan
start-node
complete-node
classify-user-input
apply-user-input
state
finish-run
```

旧 `start-step/complete-step` 只作为历史兼容别名，不写入新提示和文档。

## 5. 工具门禁

所有可能读取数据、执行程序、修改文件或委派分析的工具统一经过 `PreToolUse`：

```text
Read
Write
Edit
NotebookEdit
Bash
PowerShell
WebFetch
WebSearch
Agent
未知的新工具
```

规则：

```text
没有Plan → 拒绝实质性工具
没有active Node → 拒绝实质性工具
存在active Node → 允许并把真实事件关联到该Node
存在未处理人工输入 → 拒绝继续分析
Run已结束 → 拒绝新的分析
```

OpenTrace 自己的单条记录命令可以绕过 Node 门禁，避免形成循环。

## 6. 记录命令安全识别

允许：

```text
python -m opentrace.agent_cli <action>
cd "当前项目" && python -m opentrace.agent_cli <action>
```

必须满足：

- `cd` 目标就是当前 `project_root`；
- 只有一条记录命令；
- payload 是合法 JSON object；
- action 属于白名单；
- 不包含附加命令、管道、重定向或命令替换。

## 7. Plan 校验

`set-plan` 校验：

- 至少一个 Node；
- `node_id` 唯一；
- `objective` 非空；
- `depends_on` 指向存在的 Node；
- 不允许自依赖和循环；
- 已启动 Node 不能被删除或改写；
- 首次 Revision 使用 `initial`；
- 后续 Revision 使用 `agent_replan` 或 `human_intervention`。

纯实现动作被拒绝为独立 Node：

```text
保存或确认文件
导出文件
运行脚本或命令
安装依赖
重试失败操作
```

这些动作属于真正产生或消费结果的语义 Node。

## 8. Node 启动

```bash
python -m opentrace.agent_cli start-node --payload '{"node_id":"profile_data","input_files":["result/sample.json"]}'
```

必须满足：

1. Run 为 active。
2. 当前没有其他 active Node。
3. `node_id` 存在于最新 Plan。
4. 依赖 Node 已经 completed。
5. Node 尚未执行完成。
6. 至少一个输入文件。
7. 输入是 Run 声明输入或之前 completed Node 的输出。
8. 没有未处理人工介入。

Node 的 Objective 直接来自 Plan，不要求 Agent 重复提交。

## 9. Node 执行观察

active Node 存在时：

| 工具行为 | 记录用途 |
|---|---|
| Read | 数据访问诊断 |
| Bash / PowerShell | `operation.commands` |
| Write / Edit | 程序或输出候选 |
| NotebookEdit | 分析程序载体 |
| Agent | 委派执行诊断 |

最终 JSON 只输出规范化后的命令、程序和文件，不输出完整 Hook payload。

`inputs` 表示 Node 使用的数据来源，不要求为了记录而重复执行一次 Read。Agent 在前一 Node
已经理解文件内容、并在后续 Node 使用该内容时，仍可声明该文件或前序产物为语义输入。

## 10. Node 完成

```bash
python -m opentrace.agent_cli complete-node --payload '{"node_id":"profile_data","operation_summary":"检查数据结构和质量","output_files":["result/profile.json"],"result_summary":"发现两个高缺失率字段","analysis_conclusion":"建模前需要验证字段可用性"}'
```

必须满足：

- 指定 Node 当前 active；
- `operation_summary` 非空；
- `result_summary` 非空；
- 结论是字符串或 `null`；
- 输出文件真实存在；
- 未变化的输入不能同时声明为输出；
- 命令和程序只能来自真实 Hook 事件；
- completed Node 不允许回写。

发现旧结论有误时，创建验证或纠正 Node；不能修改历史 Node。

## 11. 人工介入

`UserPromptSubmit` 自动保存原文并关联当时的 active Node 和 Plan Revision。

分类：

```text
conversation_only
analysis_guidance
planning_input
challenge
```

除普通交流外，Claude 必须记录真实 `workflow_effect`。如果目标或依赖变化，必须先创建新的
Plan Revision。人工输入本身不是 Node。

## 12. Stop 与完成

Stop Hook 检查：

- 已存在 Plan；
- 当前没有 active Node；
- 没有待处理人工输入；
- 当前 Plan 的所有 Node 均 completed；
- 已执行 `finish-run`。

不满足时阻止 Claude 结束并给出下一条合法动作。

`finish-run` 成功后：

1. Run 标记为 completed。
2. 自动导出规范化 workflow JSON。
3. 最终 JSON 使用 `nodes`，不输出内部 `steps/step_id`。

## 13. 可以与不能保证的边界

可以保证：

- 没有 Plan 或 active Node 时不能进行实质性工具调用；
- 实际 Node 与 Plan Node 使用同一 `node_id`；
- Plan 依赖、执行顺序和文件血缘可验证；
- 人工介入不能被静默绕过；
- 无效执行不能成为 completed Run。

不能绝对保证：

- Agent 的自然语言结论一定正确；
- 所有 Python 内部资源访问都能从外部 Hook 观察；
- 语义颗粒度判断永远完美；
- 第三方 API 网关完整支持 Claude Code。

因此 OpenTrace 的目标是让有效 Run 具备真实、完整、可审计的 Node 工作流，而不是记录
Agent 的隐藏推理。
