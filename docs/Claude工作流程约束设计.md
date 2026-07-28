# Claude 工作流程约束设计

## 1. 文档目的

本文档定义 OpenTrace 如何约束 Claude Code 按照可记录、可解释且颗粒度合理的数据分析
workflow 执行任务。

目标不是限制 Claude 的分析方法，而是保证：

1. 没有语义 Plan 时不能开始实质性分析。
2. 每个实质性分析操作都发生在一个 active Step 内。
3. 每个实际 Step 都对应当前 Plan Revision 中的一个 Node。
4. 任务目标或依赖发生变化时先修订 Plan。
5. 人工介入不能被静默忽略。
6. 只有记录完整且通过校验的 Run 才能成为 `completed`。

对外 JSON 字段定义见 [记录字段设计.md](记录字段设计.md)。本文档描述的是运行时控制规则，
其中部分状态只保存在内部 SQLite，不进入对外 workflow JSON。

## 2. 约束方法

单独提供 workflow 文档或 Prompt 不能保证 Claude 遵守要求。OpenTrace 使用四层机制：

```text
规则注入
→ 状态机
→ 工具门禁
→ 完成校验
```

各层职责：

| 层级 | 作用 |
|---|---|
| Plugin/Skill 规则 | 让 Claude 理解任务边界、Step 颗粒度和记录命令 |
| SQLite 状态机 | 保存 Run、Plan、active Step 和人工输入状态 |
| Claude Code Hooks | 在工具调用和会话结束前执行强制门禁 |
| 记录命令校验 | 验证 Plan、Step、文件和结果是否满足协议 |

Prompt 负责理解，Hook 和状态机负责强制执行。

## 3. 内部状态机

OpenTrace 在内部维护以下主要状态：

```text
RUN_CREATED
    ↓ set-plan
PLAN_READY
    ↓ start-step
STEP_ACTIVE
    ↓ complete-step
PLAN_READY
    ↓ start-step / revise-plan / finish-run
RUN_COMPLETED
```

异常终止路径：

```text
STEP_ACTIVE → STEP_INTERRUPTED
RUN_CREATED / PLAN_READY / STEP_ACTIVE → RUN_ABORTED
任意运行状态 → RUN_FAILED
```

### 3.1 状态与允许操作

| 状态 | 允许操作 | 禁止操作 |
|---|---|---|
| `RUN_CREATED` | `set-plan`、`abort` | 实质性数据分析 |
| `PLAN_READY` | `start-step`、`set-plan`、`finish-run`、处理人工输入 | 没有 active Step 的实质性分析 |
| `STEP_ACTIVE` | 分析工具、`complete-step`、处理人工输入 | 启动第二个 Step、直接结束 Run |
| 存在未处理人工输入 | 分类和落实人工输入、必要时修订 Plan | 继续实质性分析 |
| `RUN_COMPLETED` | 查看和导出 | 新的分析或记录变更 |
| `RUN_ABORTED` / `RUN_FAILED` | 查看和导出 | 恢复为成功 Run 或改写历史 |

任何 Hook 或记录器错误默认采用 fail-closed：拒绝新的实质性操作，并明确返回失败原因。

## 4. SessionStart 规则注入

通过 Claude Code Plugin 的 `SessionStart` Hook 注入：

- 当前 `run_id`；
- 当前 Plan Revision；
- 当前 active Step；
- 已声明初始输入文件；
- 未处理人工输入；
- Agent 与 OpenTrace 的职责边界；
- Step 颗粒度规则；
- OpenTrace 记录命令及字段协议；
- 下一步合法操作。

注入内容必须简短、结构明确，并根据当前状态动态生成。不能只提供一份长文档后期待
Claude 自行寻找和理解。

SessionStart 注入只提供指导，真正的执行保证来自后续工具门禁。

## 5. 实质性工具统一门禁

### 5.1 覆盖范围

所有可能读取数据、执行程序、修改文件或委派分析的工具都必须经过 `PreToolUse`：

```text
Read
Write
Edit
NotebookEdit
Bash
PowerShell
WebFetch
WebSearch
Agent / Task
以及后续出现的其他实质性工具
```

优先采用“匹配所有工具，再由 OpenTrace 分类”的方式，避免 Claude Code 新增工具后形成
未受控旁路。

非实质性工具必须使用明确 allowlist，不能因为工具名称未知而默认允许。

### 5.2 门禁规则

```text
没有Plan
→ 拒绝所有实质性分析工具

有Plan但没有active Step
→ 拒绝所有实质性分析工具

存在active Step
→ 允许分析工具，并将事件自动关联到该Step

存在未处理人工介入
→ 拒绝继续分析

Run已经结束
→ 拒绝新的分析和记录变更
```

门禁拒绝信息应明确告诉 Claude：

- 当前状态；
- 拒绝原因；
- 下一条合法记录命令；
- 需要使用的真实 ID。

## 6. OpenTrace 记录命令安全通道

OpenTrace 自身的记录命令必须在没有 active Step 时仍可执行，否则会形成循环门禁：

```text
没有active Step
→ 需要执行start-step
→ start-step又因没有active Step被拦截
```

允许的记录动作：

```text
set-plan
start-step
complete-step
classify-user-input
apply-user-input
state
finish-run
```

当前兼容网关使用：

```text
python -m opentrace.agent_cli <action>
```

### 6.1 安全识别规则

记录器需要兼容 Claude 自动生成的：

```text
cd "当前项目目录" && python -m opentrace.agent_cli <action> ...
```

但必须同时满足：

1. `cd` 目标解析后等于当前 Run 的 `project_root`。
2. `cd` 后只有一条 OpenTrace 记录命令。
3. JSON payload 可以包含换行。
4. 不允许在记录命令后拼接分析命令。
5. 不允许额外管道、重定向或命令替换。
6. action 必须属于允许列表。
7. payload 必须是合法 JSON object。

不能简单地因为命令包含 `&&` 或换行就拒绝，也不能仅根据字符串前缀无条件放行。

## 7. Plan 校验

### 7.1 必须满足

`set-plan` 必须验证：

- 至少有一个 Node；
- `node_id` 在当前 Revision 内唯一；
- `objective` 不为空；
- `depends_on` 指向当前 Revision 内存在的 Node；
- Node 不能依赖自身；
- 依赖图不存在循环；
- 已完成的实际工作不会因 Plan 修改而被删除或覆盖。

### 7.2 Plan 与 Step 的强制映射

内部约束：

> 每个实际 Step 必须对应当前 Plan Revision 中的一个 Node；实际任务依赖发生变化时，
> 必须先修订 Plan。

因此：

1. `start-step.node_id` 必须存在于当前 Plan Revision。
2. Step 记录启动时的 `plan_version` 和 `node_id`。
3. 如果目标或依赖变化，Claude 必须先执行 `set-plan` 创建新 Revision。
4. 已完成 Step 不允许被回写；纠正通过后续 Step 表达。
5. DAG 由 Plan 依赖、实际 Step 和文件输入输出自动生成。

### 7.3 颗粒度规则

一个合理的 Plan Node 应当：

- 表示一个可以独立说明的分析目标；
- 有清晰的完成结果；
- 可以映射为一个实际 Step；
- 与其他节点存在明确的语义或数据依赖。

以下通常只是实现动作，不应单独成为 Node：

```text
读取文件
运行脚本
安装依赖
修复语法错误
保存JSON
重试命令
```

颗粒度判断不能完全依靠关键词。OpenTrace 对确定性错误使用硬拒绝，对语义颗粒度问题使用
警告和纠正提示，避免过度限制 Claude 的分析自由。

## 8. Step 启动校验

`start-step` 必须验证：

1. Run 处于 `PLAN_READY`。
2. 当前没有其他 active Step。
3. `node_id` 存在于当前 Plan Revision。
4. 该 Node 的依赖已经通过实际 completed Step 满足。
5. Step Objective 与 Plan Node Objective 语义一致。
6. 至少声明一个真实输入文件。
7. 输入文件存在。
8. 输入文件是 Run 初始输入，或者之前 completed Step 的输出。
9. 没有未处理人工介入。

Step 的内部完成条件可以保存在 SQLite 中用于门禁，但不进入对外 workflow JSON。

## 9. Step 执行期间的自动观察

active Step 存在时，Hook 将真实工具事件绑定到该 Step：

| 工具行为 | 自动记录用途 |
|---|---|
| `Read` | 输入文件观察 |
| `Bash` / `PowerShell` | `operation.commands` |
| `Write` / `Edit` | 程序文件或输出候选文件 |
| `NotebookEdit` | 程序或分析载体 |
| 子 Agent / Task | 委派执行记录及其归属 |

OpenTrace 自身的记录命令必须从分析命令中排除。

命令和程序路径由 Hook 自动提取，不要求 Claude 在 Step 完成时重新整理。

工具事件仍可以完整保存在内部 SQLite 用于诊断；最终 JSON 只输出规范化后的命令和程序路径。

## 10. Step 完成校验

`complete-step` 只要求 Claude 提供：

```text
operation.summary
result_summary
analysis_conclusion
无法自动识别时的输出文件路径
```

必须验证：

- 当前存在 active Step；
- `operation.summary` 非空；
- `result_summary` 非空；
- 分析 Step 提供真实结论；
- 纯处理 Step 可以使用 `analysis_conclusion: null`；
- 声明的输出文件真实存在；
- 文件 SHA-256 由 OpenTrace 计算；
- 程序和命令来自真实观察事件；
- 完成记录与当前 Step 一致；
- 已完成 Step 不再允许修改。

如果后续发现错误，不回写旧 Step。Claude 应当：

- 创建验证 Step；
- 创建纠正 Step；
- 或修订 Plan 后启动新的 Step。

## 11. 人工介入

用户在 Claude 会话中提供指导、规划建议或异议时：

1. `UserPromptSubmit` Hook 保存原文和发生时间。
2. OpenTrace 自动关联介入发生时的 active Step 和 Plan Revision。
3. Claude 将输入分类为：

```text
analysis_guidance
planning_input
challenge
conversation_only
```

4. `conversation_only` 只保留内部日志，不进入最终 workflow JSON。
5. 其他三类必须记录实际 `workflow_effect`。
6. 在介入被落实前，门禁拒绝新的实质性分析。

人工输入本身不是 Step。它可以：

- 改变当前 Step 的执行方法；
- 触发新的 Plan Revision；
- 产生后续验证或纠正 Step；
- 暂停或否定先前的分析结论。

OpenTrace 记录的是实际影响，不是 Agent 对用户意图的猜测。

## 12. Stop 与 Run 完成校验

Claude 准备结束回答时，`Stop` Hook 必须检查：

- 是否已经建立 Plan；
- 是否至少存在一个 completed Step；
- 是否仍有 active Step；
- 是否存在未处理人工介入；
- 是否存在已经开始但未解决的计划工作；
- 是否已经执行 `finish-run`；
- Run 状态是否为 `completed`。

任一条件不满足时：

```text
阻止Claude结束
→ 返回失败原因
→ 给出下一条合法修复动作
```

`finish-run` 必须验证：

1. 没有 active Step。
2. 没有未处理人工输入。
3. 至少完成一个 Step。
4. 实际 Step 与当前 Plan Revision 保持一致。
5. 所有已记录文件版本可验证。
6. 不存在未解决的记录器错误。

只有 `finish-run` 成功后，Run 才能成为 `completed`。

分析失败可以记录为失败或中断，但不能把没有语义记录的 Run 标记为成功。

## 13. 规范化 JSON 和 DAG 自动生成

以下状态发生变化后：

```text
set-plan
start-step
complete-step
apply-user-input
finish-run
```

OpenTrace 自动：

1. 提交 SQLite 事务。
2. 生成最新规范化 workflow JSON。
3. 根据 Plan、Step 和文件血缘生成 DAG JSON。
4. 允许前端读取或刷新。

Claude 不提交 DAG Node、DAG Edge、PROV Relation 或前端布局坐标。

DAG 的唯一事实来源是规范化 workflow JSON；DAG JSON 是可重新生成的派生视图。

## 14. 一致性审计

OpenTrace 应当能够识别以下异常：

- 实质性工具在没有 active Step 时执行；
- 出现未被 Hook 覆盖的新工具；
- 输出文件存在但没有归属 Step；
- Step 声明的程序没有真实执行记录；
- Step 对应的 Plan Node 不存在；
- Plan 依赖与实际文件流转冲突；
- Claude 已经输出最终答案但 Run 仍为 active；
- Session 已结束但 active Step 未关闭；
- Hook 失败后分析仍继续；
- 同一路径文件发生变化但 SHA-256 未形成新版本。

异常事件保存在内部 SQLite。存在关键一致性异常时，`finish-run` 必须失败。

## 15. 可以保证与不能保证的边界

### 15.1 可以保证

在所有实质性工具都经过 Hook 的前提下，OpenTrace 可以保证：

- 没有 Plan 不能开始实质性分析；
- 没有 active Step 不能调用实质性工具；
- 每个实际 Step 对应当前 Plan Node；
- 依赖变化必须通过 Plan Revision 表达；
- 工具事件能够关联到 active Step；
- 文件输入输出可以形成文件级血缘；
- 人工介入不能被静默忽略；
- 未完成 Step 不能被标记为 completed；
- 无效 Run 不能被标记为成功；
- DAG 与 workflow JSON 来自同一事实来源。

### 15.2 不能绝对保证

OpenTrace 不能仅通过工具门禁绝对保证：

- Agent 的自然语言结论一定正确；
- Agent 的语义颗粒度判断永远完美；
- Python 程序内部访问的全部资源都能被外部 Hook 观察；
- 未知的新工具或外部进程永远不会形成旁路；
- 第三方 API 网关完整支持 Claude Code 的所有协议能力。

因此系统的准确目标是：

> 只有遵守记录协议、通过一致性校验的执行才能成为有效的 completed Run；
> 未记录、未完成或出现关键旁路的执行必须被标记为异常、失败或中止。

## 16. 当前实现状态

P0已经实现：

1. 安全识别带有当前项目`cd ... &&`前缀和多行JSON的合法记录命令。
2. PowerShell、Web、子Agent和未知工具统一进入门禁。
3. 没有Plan、active Step或completed Step时不能正常结束。
4. Agent CLI按最终字段白名单校验payload，旧字段会被明确拒绝。
5. Plan Revision、Step依赖、文件输入来源和人工介入上下文得到强制校验。
6. `finish-run`成功后生成规范化workflow JSON。

仍属于P0之外的工作：

1. 从规范化workflow JSON生成DAG JSON。
2. 前端改为读取新的Run JSON和DAG JSON。
3. 更细粒度的程序内部文件访问观察。

真实Claude Code与当前API网关的最终运行效果由用户在可直接启动`claude`的终端手动验收。
