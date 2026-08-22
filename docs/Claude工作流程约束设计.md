# Claude Node 工作流程约束设计

## 1. 目标

AgentVAST 约束 Claude Code 按照可记录、可解释且颗粒度合理的 Node 链完成数据分析：

1. 没有 Plan 时不能开始实质性分析。
2. 每个实质性工具调用都属于一个 active Node。
3. 每个实际 Node 对应当前 Plan Revision 中同一 `node_id`。
4. 目标、依赖或产物要求变化时必须先修订 Plan。
5. 人工介入不能被静默忽略。
6. 只有全部 Node 记录完整后 Run 才能完成。
7. 每个 completed Node 都有可验证的阶段产物。

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
- Run 独立产物目录与文件命名规则；
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

AgentVAST 自己的单条记录命令可以绕过 Node 门禁，避免形成循环。

## 6. 记录命令安全识别

允许：

```text
python -m agentvast.agent_cli <action>
cd "当前项目" && python -m agentvast.agent_cli <action>
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
- Agent 提交的 `node_id` 只是本次请求内的别名，AgentVAST 分配并返回稳定的
  `node-001` 格式编号；
- `objective` 非空；
- `depends_on` 指向存在的 Node；
- `required_artifacts` 只允许 `code`、`data`、`report`、`visualization`；
- 每个 Node 由 Claude 根据分析目标选择非空的 `required_artifacts` 子集；
- 不要求每个 Node 生成报告，也不要求当前 Plan 覆盖全部四类产物；
- 不允许自依赖和循环；
- 首次 Revision 使用 `initial`；
- 后续 Revision 使用 `agent_replan` 或 `human_intervention`，并必须提供真实
  `change_reason`；
- Plan 没有实质变化时不能创建空 Revision。

Plan 是动态快照：

- Node开始前、active Node执行期间或Node完成后，都允许修订未来的pending Node；
- active/completed Node必须保留，不能修改其目标、依赖或产物要求；
- 实际执行仍绑定其启动时的Plan Revision；
- 真实结果没有改变后续计划时，不创建空 Revision；
- 每个 Node 完成后，Claude 应判断剩余 Plan 是否仍然适用；
- completed Node 是回顾性事实，不随 Plan Revision 变化。

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
python -m agentvast.agent_cli start-node --payload '{"node_id":"node-001"}'
```

必须满足：

1. Run 为 active。
2. 当前没有其他 active Node。
3. `node_id` 存在于最新 Plan。
4. 依赖 Node 已经 completed。
5. Node 尚未执行完成。
6. 没有未处理人工介入。
7. `plan` 或 `node` 模式下的最新 Plan Revision 已获得人工确认。

Node 的 Objective 直接来自 Plan，不要求 Agent 重复提交。
Node 启动时，AgentVAST：

- 锁定 `node_id`、`plan_version`、Objective、依赖和产物要求；
- 冻结当时已经知道的 Run 初始输入和 completed Node 输出版本；执行中首次发现的外部输入
  不受该集合限制，在完成时观察并记录；
- 对四类产物目录建立快照，作为完成时判断本 Node 真正新增或修改了什么的基线。

启动时不申报最终 `input_files`，因为真实输入应在执行完成后根据事实确定。

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

`inputs` 表示 Node 实际使用的数据来源，不要求为了记录而重复执行一次 Read。Agent 在完成
Node 时提交真实使用的路径。已知文件绑定到 Node 启动时冻结的版本；执行中首次发现的
外部文件在完成时观察SHA-256并加入Run输入。

较完整的 Python 分析必须先写成当前 Node 的 `.py` 或 `.ipynb` 产物再执行。Hook 拒绝
使用 `python -c` 或标准输入承载实质分析，避免只有一条不可复核的长命令而没有分析程序。

## 10. Node 完成

```bash
python -m agentvast.agent_cli complete-node --payload '{"node_id":"node-001","input_files":["data/sample.json"],"operation_summary":"检查数据结构和质量","result_summary":"发现两个高缺失率字段","analysis_conclusion":"建模前需要验证字段可用性","analysis_outcome":"partial"}'
```

必须满足：

- 指定 Node 当前 active；
- `input_files` 是非空数组，只包含本 Node 实际使用的文件；
- 每个输入对应 Node 启动时已知的文件版本，或执行中首次发现并在完成时观察的外部文件版本；
- `operation_summary` 非空；
- `result_summary` 非空；
- 结论是字符串或 `null`；
- AgentVAST 自动比较 Node 启动快照和当前目录，不依赖 Agent 声称有哪些输出；
- 新增或修改的产物位于 `result/<run_id>/<category>/`；
- 每个文件名以当前 `node-xxx_` 开头且文件非空；
- `report`目录中的报告必须是有效JSON object；
- `required_artifacts` 中每种类别都存在符合格式的产物；
- 只要本 Node 生成代码产物，至少一个程序必须被真实成功执行；
- `output_files` 可省略；如果提交，只能引用自动发现到的本 Node 产物；
- 未变化的输入不能同时声明为输出；
- 命令和程序只能来自真实 Hook 事件；
- completed Node 不允许回写。

Plan 的 `depends_on` 是语义或执行依赖，不强制等同于文件依赖。某个依赖没有贡献实际输入
文件时只产生诊断提示，不阻止 Node 如实完成。

发现旧结论有误时，创建验证或纠正 Node；不能修改历史 Node。

## 11. 人工介入

`UserPromptSubmit` 自动保存原文并关联当时的 active Node 和 Plan Revision。

分类：

```text
conversation_only
checkpoint_continue
analysis_guidance
planning_input
challenge
```

`checkpoint_continue` 仅用于 checkpoint 中用户明确确认或要求继续，与
`conversation_only` 一样不生成对外 Human Intervention，也不需要
`apply-user-input`。其余三类必须记录真实 `workflow_effect`。如果目标或依赖变化，必须先
创建新的 Plan Revision。人工输入本身不是 Node。

## 12. 人工 checkpoint 与完成

Run 级 `checkpoint_mode` 有三种：

- `plan`（默认）：每个新Plan Revision提交后自动暂停，确认当前版本后继续自动执行，结束时不再确认；
- `node`：每个Plan Revision先确认，并在每个completed Node后暂停；
- `none`：不主动暂停。

Plan checkpoint由每次成功创建Revision的 `set-plan` 自动打开。`node`模式还会在Node完成后通过以下命令打开
后续checkpoint：

```bash
python -m agentvast.agent_cli pause-for-user
```

此命令不完成 Run。Stop Hook 在 `awaiting_user` 状态允许 Claude 结束当前回合，用户继续在
同一 Claude Code session 中回复。回复自动关联 checkpoint 对应的 completed Node 和
Plan Revision。`node`模式在checkpoint被回复前禁止修订Plan或启动下一Node。

用户在Plan checkpoint提出异议后，Claude必须分类和应用真实workflow effect并提交修订
Plan；修订后的Plan再次等待确认。无论Revision由初始规划、后续追问、Claude动态调整还是
Web编辑产生，只要创建了新Revision，都必须确认该最新版本。确认后，`plan`模式自动执行到
下一个Plan Revision或当前Plan结束，不要求最终确认。

## 13. Stop 与完成

Stop Hook 检查：

- 已存在 Plan；
- 当前没有 active Node；
- 没有待处理人工输入；
- 当前 Plan 的所有 Node 均 completed；
- 已记录产物未在后续被删除或篡改；
- 最新Plan Revision已经确认，或模式为 `none`；
- `node`模式要求最近完成的Node checkpoint已经确认；
- 已执行 `finish-run`。

不满足时阻止 Claude 结束并给出下一条合法动作。

`finish-run` 成功后：

1. Run 标记为 completed。
2. 自动导出规范化 workflow JSON 到 `result/<run_id>/workflow.json`。
3. 最终 JSON 使用 `nodes`，不输出内部 `steps/step_id`。

已完成或 aborted 的 Run 不能恢复；新增分析应创建新 Run。内部运行状态继续保存在
`.agentvast/workflow.sqlite3`，不与公开 Run 产物混合。

## 14. 可以与不能保证的边界

可以保证：

- 没有 Plan 或 active Node 时不能进行实质性工具调用；
- 实际 Node 与 Plan Node 使用同一 `node_id`；
- Plan 依赖、执行顺序和文件血缘可验证；
- Node 编号、产物目录、文件命名和最低完成条件可验证；
- 人工介入不能被静默绕过；
- 无效执行不能成为 completed Run。

不能绝对保证：

- Agent 的自然语言结论一定正确；
- 所有 Python 内部资源访问都能从外部 Hook 观察；
- 语义颗粒度判断永远完美；
- 第三方 API 网关完整支持 Claude Code。

因此 AgentVAST 的目标是让有效 Run 具备真实、完整、可审计的 Node 工作流，而不是记录
Agent 的隐藏推理。
