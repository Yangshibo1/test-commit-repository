# OpenTrace 核心工作流优化方案

日期：2026-07-27

## 1. 产品定位

OpenTrace 当前定位为个人使用、本地运行的数据分析 Agent 工作流记录系统。

第一目标宿主是 Claude Code。OpenTrace 通过 Claude Code Plugin 提供规则、MCP 工具和生命周期 Hook；后续可以为 OpenCode 等 Coding Agent 增加适配器，但核心记录模型不依赖某个 Agent。

本阶段只服务两个核心目标：

1. 以语义 Step 为颗粒度，完整记录 Agent 实际执行的数据分析工作流。
2. 约束 Agent 以可记录、颗粒度合理、能够形成文件级数据链路的方式完成数据分析。

所有功能都必须能够直接支撑以上两个目标。不能直接支撑的功能不进入当前开发范围。

## 2. 明确边界

### 2.1 本阶段必须完成

- 一次用户数据分析任务对应一个 Run。
- 由 OpenTrace CLI 创建 Run 并启动交互式 Claude Code，确保记录先于 Agent 执行开始。
- Agent 在开始实质性分析前建立可调整的任务计划。
- 每个语义 Step 有明确目标、输入文件、真实执行、数据操作、输出文件、处理结果和可选分析结论。
- 自动记录 Claude Code 实际运行的命令、修改的程序、执行结果、失败和重试。
- 文件使用内容哈希区分版本，建立 `输入文件版本 → Step → 输出文件版本` 的文件级血缘。
- Agent 必须在活动 Step 内执行实质性分析。
- Step 和 Run 完成前执行结构与颗粒度验证。
- Claude Code 会话中断、恢复或上下文压缩后能够继续原 Run。
- 人的分析指导、下一步规划建议和对历史处理的异议，可以作为 HumanContribution 关联到 Run、Step 或计划变化。
- 为现有前端提供稳定的导出数据，不在本阶段重做前端。

### 2.2 本阶段不做

- 不做字段、单元格、JSON item 等细粒度数据血缘。
- 不做多人协作、团队权限、角色管理和审批流。
- 不做云端服务、账号系统、远程同步和分布式执行。
- 不做通用 Agent 编排平台。
- 不记录或推断 Agent 隐藏思维链。
- 不做完整 Notebook 内核追踪。
- 不自动理解任意 Python 程序内部的全部文件读写。
- 不做复杂算法推荐、自动选模和分析质量专家系统。
- 不重构现有前端交互和可视化。
- 不要求所有数据文件复制进 OpenTrace；默认只记录路径、版本和元数据。
- 不重写历史 Session；旧数据只读兼容，新模型用于新建 Run。

## 3. 当前版本的核心问题

### 3.1 记录模型分裂

当前 `meta.json`、`step_*.json`、`step_details.json` 和 PROV DAG 分别更新，缺少单一事实源。现有真实 Session 已出现 `meta.json` 只有 1 个 Step，而 `step_details.json` 和 PROV 中存在 25 个步骤的情况。

### 3.2 Agent 调用负担过高

Agent 需要分别调用 `record_step()`、`record_step_details()` 和 `record_prov_relation()`，并手工维护临时 ID 和关系方向。这些工作不属于数据分析本身，也容易漏记或记录不一致。

### 3.3 文档约束不可执行

“每步记录”“禁止一次性 Pipeline”“每步查看结果”等要求目前主要依赖文档。Agent 可以忽略文档，也没有统一状态机阻止它跳过记录。

### 3.4 尚未形成真实 MCP 集成

当前 `opentrace/mcp_server.py` 主要是 Python 直接调用接口。要让 Claude Code 稳定使用，必须实现真正的 MCP Server，并通过插件自动加载工具。

### 3.5 Step 颗粒度定义不准确

当前“过滤、聚合、统计就是最小节点”的描述偏向代码操作，容易把任务切得过细。Step 应当是一个完整的语义分析单元，而命令、程序、过滤和聚合是 Step 内部的执行或数据操作。

## 4. 核心记录模型

### 4.1 Run

Run 表示整个用户任务。

必需字段：

- `run_id`
- `task_title`
- `task_description`
- `original_request`
- `scope`
- `initial_file_versions`
- `host`
- `host_session_id`
- `model`
- `project_root`
- `git_revision`
- `started_at`
- `completed_at`
- `status`

Run 不保存具体命令和步骤结论。

### 4.2 Plan 与 PlanRevision

Plan 表示 Agent 当前准备执行的语义任务节点。

PlanNode 最小字段：

- `node_id`
- `objective`
- `step_type`
- `depends_on`
- `status`

计划是可变的，但每次修改必须生成不可变的 PlanRevision。支持的最小操作：

- `insert`
- `split`
- `merge`
- `reorder`
- `skip`
- `replace`

计划只表达准备做什么；Step 表达实际做了什么。

### 4.3 Step

Step 是 OpenTrace 的核心记录单位。

定义：

> 一个 Step 是 Agent 为完成一个明确数据分析目标，实际使用一组输入文件，通过一个或多个程序、命令、算法和数据操作，产生一组输出文件、数据处理结果以及可选分析结论的真实执行单元。

Step 字段分为以下部分。

#### 身份与拓扑

- `step_id`
- `run_id`
- `node_id`
- `sequence`
- `depends_on`
- `step_type`
- `execution_status`
- `review_status`
- `started_at`
- `completed_at`

#### 目标

- `objective`
- `target_data`
- `completion_condition`

#### 输入文件

- `input_file_version_ids`

#### 数据操作

- `operation_summary`
- `operation_types`
- `parameters`

#### 算法和方法

- `algorithms`
  - `name`
  - `purpose`
  - `implementation`
  - `parameters`

算法字段只在分析、建模和验证步骤中要求填写。普通文件加载、格式转换不能被迫虚构算法。

#### 程序

- `program_versions`
  - `path`
  - `sha256`
  - `language`
  - `role`

#### 真实执行

- `execution_attempts`
  - `execution_id`
  - `attempt`
  - `tool`
  - `command`
  - `cwd`
  - `started_at`
  - `completed_at`
  - `exit_code`
  - `status`
  - `stdout_summary`
  - `stderr_summary`
  - `changed_files`

执行信息由 Hook 自动采集，不能主要依赖 Agent 自述。

#### 输出文件

- `output_files`
  - `file_version_id`
  - `role`

输出文件角色：

- `step_output`：表达本 Step 的主要数据处理结果，可以被后续 Step 使用。
- `internal_intermediate`：只服务于本 Step 内部执行，不构成新的 Step 边界。
- `temporary`：缓存、调试文件等临时内容，只保留文件事件，不进入正式文件血缘。

#### 数据处理结果

- `processing_result`
  - `status`
  - `summary`
  - `input_rows`
  - `output_rows`
  - `removed_rows`
  - `generated_files`
  - `warnings`

#### 分析结论

- `analysis_conclusion`
  - `summary`
  - `key_results`
  - `limitations`

`analysis_conclusion` 对 `analyze`、`model`、`validate` 类型必填；对 `load`、`transform`、`join` 等处理步骤可以为空。

### 4.4 FileVersion

本阶段的数据血缘只到文件版本级。

字段：

- `file_version_id`
- `path`
- `sha256`
- `format`
- `size`
- `rows`
- `columns`
- `schema_summary`
- `created_by_step_id`
- `created_by_execution_id`
- `status`
- `observed_at`

同一路径内容发生变化时必须生成新的 FileVersion。不能只使用路径作为文件身份。

文件级关系由系统根据 Step 自动生成：

```text
Input FileVersion → Step → Output FileVersion
```

不再要求 Agent 手写 PROV 临时 ID 和边方向。PROV 作为该关系模型的导出投影。

### 4.5 HumanContribution

只实现记录真实人机协作所需的最小模型，不实现审批流。人的主要作用是帮助 Agent 分析、参与规划下一步，或对已执行的数据处理提出异议。

支持三种类型：

- `analysis_guidance`
- `planning_input`
- `challenge`

字段：

- `contribution_id`
- `run_id`
- `target_step_id`
- `target_plan_version`
- `type`
- `original_text`
- `structured_summary`
- `disposition`
- `workflow_effect`
- `created_at`
- `resolved_at`

人的输入不是数据处理 Step。它可以导致当前 Step 增加执行尝试、生成 PlanRevision，或触发新的验证/纠正 Step。

历史 Step 不允许被覆盖。若异议成立，原 Step 保持 `execution_status=completed`，并通过 `review_status=superseded` 指向纠正 Step。

用户直接在交互式 Claude Code 会话中输入自然语言。`UserPromptSubmit` Hook 保存原始输入并生成 `input_event_id`，要求 Agent 在下一次实质性工具调用前调用 `classify_user_input`，将其分类为：

- `conversation_only`
- `analysis_guidance`
- `planning_input`
- `challenge`

只有后三类生成 HumanContribution 并进入正式工作流。`conversation_only` 只关闭待分类事件。原始用户文本由 Hook 记录，Agent只补充结构化类型、目标 Step/Plan 和实际 workflow effect。

处理规则：

- `analysis_guidance`：若不改变当前 Step 的主要目标，作为 HumanContribution 关联当前 Step，并记录后续新增的执行尝试或参数变化。
- `planning_input`：生成 PlanRevision，记录实际新增、调整或跳过的节点。
- `challenge`：关联被质疑的历史 Step、数据操作或输出 FileVersion；如需重新检查，创建新的 `validate` 或纠正 Step，不能修改原始执行记录。

## 5. 单一事实源与存储

使用 Python 标准库 SQLite 作为唯一事实源，避免继续维护多套互相独立的 JSON。

最小表：

- `runs`
- `plans`
- `plan_nodes`
- `plan_revisions`
- `steps`
- `step_dependencies`
- `file_versions`
- `step_inputs`
- `step_outputs`
- `program_versions`
- `execution_attempts`
- `algorithms`
- `human_contributions`
- `validation_results`

采用事务保证以下操作原子完成：

- 开始 Step
- 完成 Step
- 生成文件版本
- 建立文件关系
- 更新 Run/Step 状态

现有前端继续读取导出 JSON。新增一个兼容导出器，从 SQLite 生成前端需要的数据，不让前端成为核心重构的一部分。

## 6. Agent 可调用的最小 MCP 工具

第一版只暴露七个工具：

1. `opentrace_start_run`
2. `opentrace_set_plan`
3. `opentrace_start_step`
4. `opentrace_complete_step`
5. `opentrace_revise_plan`
6. `opentrace_get_state`
7. `opentrace_finish_run`

人工介入增加两个工具：

8. `opentrace_classify_user_input`
9. `opentrace_apply_human_contribution`

执行记录不是 Agent 工具，由 Hook 调用内部接口写入。

### 6.1 `start_step` 的 Agent 输入

- `run_id`
- `node_id`
- `objective`
- `input_files`
- `completion_condition`
- `expected_output_roles`

服务端负责：

- 生成 `step_id`
- 验证计划节点
- 计算输入文件版本
- 建立 active step
- 启动执行采集

### 6.2 `complete_step` 的 Agent 输入

- `step_id`
- `operation_summary`
- `operation_types`
- `parameters`
- `algorithms`
- `output_files`
- `processing_result`
- `analysis_conclusion`

服务端负责：

- 验证输出文件实际存在
- 验证文件在 Step 期间新增或变化
- 计算输出 FileVersion
- 关联程序和执行尝试
- 建立文件级血缘
- 运行结构和颗粒度验证
- 原子完成 Step

## 7. Claude Code 的启动与恢复

### 7.1 主入口

第一版不以“用户先打开 Claude Code，再希望 Claude 自己想起使用 OpenTrace”为主流程。由 OpenTrace CLI 负责创建 Run 并启动 Claude Code：

```text
opentrace run
  --project <project-path>
  --task "<task-description>"
  --data <file-1> <file-2>
```

CLI 顺序：

1. 验证项目路径和初始数据文件。
2. 生成 Claude Code session ID，并创建 Run、计算初始 FileVersion。
3. 写入 Run 启动上下文，将 session ID 持久化到 Run。
4. 为子进程设置 `OPENTRACE_RUN_ID`、数据库路径和项目根目录。
5. 在项目目录启动交互式 Claude Code，并加载 OpenTrace Plugin。
6. 将任务描述、Run ID 和“先建立计划”的短指令作为初始 Prompt。
7. `SessionStart` Hook 从数据库读取 Run 状态并注入 Claude。
8. Claude 调用 `set_plan` 后进入正式分析。

开发模式下，启动器实际执行的命令等价于：

```text
claude
  --session-id <claude-session-id>
  --plugin-dir <opentrace-plugin-path>
  "<initial-prompt>"
```

启动器是 Claude Code 的父进程，但不接管 Claude 的分析循环。Claude 仍在用户熟悉的交互式终端中运行；OpenTrace 只负责在启动前建立 Run、向子进程传递上下文，并在退出后保存最终状态。

开发阶段使用本地插件目录启动；安装插件后的个人日常使用不需要显式传入插件路径。

采用交互式 Claude Code，而不是一次性 `claude -p`，因为用户需要在分析过程中随时提供分析指导、规划建议和异议。

### 7.2 次要入口

已经打开 Claude Code 时，可以使用显式 Skill：

```text
/opentrace:data-analysis <task>
```

该入口内部调用 `start_run`。它用于临时任务和调试，不作为最强保证的默认启动方式。

### 7.3 恢复

```text
opentrace resume <run-id>
```

CLI 根据 Run 中保存的 Claude Code session ID 恢复交互式会话，并设置相同 `OPENTRACE_RUN_ID`。`SessionStart` Hook 注入：

- 当前 Plan 版本
- 已完成 Step
- active/interrupted Step
- 未处理 HumanContribution
- 最近验证错误

Claude Code 异常退出时，`SessionEnd` 只把 Run/Step 标记为 `interrupted`，不能标记为完成。

### 7.4 人工介入的运行方式

人工介入不需要离开 Claude Code，也不需要另做一个审批界面。用户直接在当前交互式会话中输入：

- 对当前分析的补充或方法建议。
- 对下一步方向的规划意见。
- 对已完成处理、结果或结论的异议。

一次输入的处理顺序：

1. `UserPromptSubmit` Hook 先保存原始文本，创建待分类的输入事件。
2. Hook 向 Claude 注入一条短上下文，要求在下一次实质性工具调用前处理该输入。
3. Claude 调用 `classify_user_input` 提交 `input_event_id`、类型及可选的目标 Step/Plan。
4. 若为普通对话，服务端关闭待分类事件，不创建 HumanContribution；否则创建 HumanContribution。
5. 若影响工作流，Claude 调用 `apply_human_contribution`，明确关联的 Step/Plan 及实际采取的动作。
6. `PreToolUse` 在仍有未分类输入时阻止新的实质性操作，但允许 OpenTrace 分类工具和只读查询。

人工输入本身不创建 Step：

- 当前 Step 内的方法建议，只改变该 Step 的参数、程序或新增 execution attempt。
- 对下一步的建议生成 PlanRevision，真正执行时才创建 Step。
- 对历史结果的异议先关联原 Step；需要复查或纠正时，另外创建真实的 `validate` 或纠正 Step。

Agent 可以像普通对话一样主动向用户询问分析决策。只有用户的回答实际改变计划或执行时，才形成 HumanContribution。若用户在长时间运行的命令中主动中断执行，Hook 先记录该 attempt 的中断状态，再按上述流程处理后续输入。

## 8. Claude Code Plugin 约束

插件由三部分组成。

### 8.1 Skill

提供简短、稳定的规则：

- 什么是语义 Step
- 什么不是 Step
- 何时开始和完成 Step
- 如何调整计划
- 哪些字段由 Agent 补充

不再把完整 API 手册和 PROV 标准放进 Agent 工作说明。

### 8.2 MCP Server

提供上述类型化工具，并由状态机拒绝非法调用。

### 8.3 Hooks

只在 OpenTrace Run 活动时启用门禁。

- `SessionStart`：恢复未完成 Run 和 active step。
- `UserPromptSubmit`：捕获可能影响工作流的人工输入。
- `PreToolUse`：没有 active step 时阻止 Bash、Write、Edit 等实质操作。
- `PostToolUse`：记录成功的命令、程序修改和文件变化。
- `PostToolUseFailure`：记录失败和重试。
- `Stop`：存在 active step、缺失结果或 Run 未完成时阻止 Agent 提前结束。
- `SessionEnd`：将未完成会话标记为 interrupted，而不是 completed。

## 9. Step 颗粒度约束

### 9.1 标准定义

一个合格 Step 必须：

1. 只有一个主要数据分析目标。
2. 能够独立判断是否完成。
3. 有明确输入文件。
4. 产生输出文件、数据处理结果或分析结论。
5. 内部不存在“必须先观察中间结果，再决定是否开始另一项分析”的决策边界。

若存在以下结构，应拆分：

```text
操作 A → 查看 A 的结果 → 决定是否执行 B
```

A 和 B 是两个 Step。

若多个命令和数据操作共同服务于同一目标，则保留在同一个 Step 内。

### 9.2 脚本和中间数据是否形成 Step

“使用了一个 Python 脚本”或“生成了一个文件”都不是创建 Step 的充分条件。创建 Step 的必要条件是存在一个可独立说明和验收的语义目标。

在满足语义目标的前提下，出现以下任一边界时，应当完成当前 Step，并在后续工作开始时创建新 Step：

1. Agent 必须查看当前结果，才能决定后续分析怎么做。
2. 当前输出会作为另一个语义任务的输入。
3. 当前操作形成可独立复用或审查的数据状态，例如清洗后的数据集、合并后的主表、模型结果或验证报告。
4. 数据的人群范围、统计口径、模式、结构或分析含义发生了值得独立说明的变化。

因此：

- 一个脚本可以包含一个 Step 的多次操作和重试，不按函数、命令或代码块拆 Step。
- 多个脚本也可以共同属于一个 Step，只要它们服务同一目标，且中间没有观察后决策边界。
- 脚本在 Step 内生成但随后立即继续使用、Agent 未单独检查、后续 Step 也不依赖的文件，记为 `internal_intermediate`。
- 仅用于缓存、调试或程序传递的文件记为 `temporary`。
- 被后续 Step 明确消费，或本身代表可独立复核数据状态的中间数据，记为 `step_output`；它通常意味着当前 Step 可以结束。

示例：

| 实际执行 | 是否单独形成 Step | 原因 |
|---|---|---|
| `profile_data.py` 生成 `profile.json`，Agent 阅读后决定清洗策略 | 是 | 存在“观察结果后决策”的真实边界 |
| `clean_data.py` 将 `raw.csv` 变为后续分析使用的 `clean.parquet` | 是 | 形成独立可复用的数据状态和文件级血缘边界 |
| 同一清洗脚本内部生成临时 CSV，随即读取并删除 | 否 | 只是当前 Step 的内部实现 |
| 为解决编码问题先转一次 UTF-8，再继续同一加载目标 | 通常否 | 技术性处理没有形成新的语义目标 |
| 分析脚本同时生成统计表和配套图表 | 通常否 | 两个产物共同回答同一个分析问题 |
| 先生成特征数据，之后另行训练并比较模型 | 是，至少两个 Step | 特征数据被另一个语义任务消费 |

如果 Agent 一次运行一个“大脚本”，脚本内部完成加载、清洗、分析和报告，且执行期间 Agent 没有观察中间结果或作出新的分析决策，OpenTrace 必须如实记录为一个过粗 Step，并给出颗粒度警告。不能在执行后根据脚本结构虚构多个并未真实发生的语义 Step。

要得到高质量任务链，约束发生在执行前：`set_plan` 和 `start_step` 检查目标及预期输出角色，鼓励 Agent 把可能出现分析决策的阶段拆开执行，而不是事后拆日志。

### 9.3 不应成为 Step

- 查看目录
- 读取一个文件
- 写一行 Python
- 执行一次 groupby
- 修复路径错误
- 重试失败命令
- 调整图表颜色

这些是 Step 内的执行事件。

### 9.4 颗粒度验证

第一版采用“确定性硬规则 + 语义软验证”。

硬规则：

- 目标不能为空。
- 必须声明输入文件。
- 完成时必须有真实输出文件或明确处理结果。
- 分析类 Step 必须有分析结论。
- 已完成 Step 不能覆盖。
- 计划外节点必须先通过 `revise_plan` 创建。

软验证：

- 是否包含多个独立分析目标。
- 是否只是单个命令或代码动作。
- 是否存在应该拆开的中间决策边界。
- 是否过于宽泛，无法独立判断完成。

软验证返回：

- `PASS`
- `SPLIT_RECOMMENDED`
- `MERGE_RECOMMENDED`
- `REWRITE_OBJECTIVE`

第一版软验证不直接永久阻塞执行。Agent必须处理反馈；连续无法修正时允许带警告继续，避免个人系统被误判锁死。

## 10. 真实性保证

字段来源必须严格区分。

### Agent 声明

- 目标
- 数据操作语义
- 算法用途
- 处理结果的自然语言总结
- 分析结论

### Hook 自动记录

- 实际工具调用
- 实际命令
- 程序文件修改
- 执行顺序
- exit code
- stdout/stderr 摘要
- 失败和重试
- 执行时间

### OpenTrace 计算

- 文件哈希和版本
- 文件变化
- 输入输出关系
- Step 依赖
- Run/Step 状态
- 结构完整性

第一版无法完全证明 Python 程序内部读取了哪些文件。因此采用以下边界：

- 输入文件由 Agent 在 `start_step` 时声明并由系统计算哈希。
- 输出文件由 Agent 在 `complete_step` 时声明。
- Hook 根据执行前后文件状态验证输出确实新增或变化。
- 后续再考虑对 `open()`、pandas 和数据库读写进行可选插桩，不进入当前 MVP。

## 11. 实施阶段

### Phase 0：冻结当前行为并建立测试基线

工作：

- 为当前 Session、Step、PROV 和导出行为补充最小回归测试。
- 建立一个小型、确定性的数据分析样例。
- 定义新版 schema 和状态转换测试。

产出：

- 可重复的测试数据和期望工作流。
- 新旧行为边界。

预计：1～2 个工作日。

### Phase 1：统一领域模型和 SQLite 存储

工作：

- 实现 Run、Plan、Step、FileVersion、ExecutionAttempt。
- 实现事务和状态机。
- 实现文件哈希及版本识别。
- 保留旧 Session 只读加载。

产出：

- 单一事实源。
- 不依赖 Claude Code 的核心 Python API。

预计：3～4 个工作日。

### Phase 2：Step 记录工具

工作：

- 实现 `start_run`、`set_plan`、`start_step`、`complete_step`、`revise_plan`、`get_state`、`finish_run`。
- 自动生成文件级血缘。
- 移除 Agent 对 PROV 临时 ID 的直接依赖。
- 实现字段条件验证。

产出：

- 通过 Python API 可完整记录一个真实 Step 链。

预计：3～4 个工作日。

### Phase 3：真实 MCP Server 和 Claude Code Plugin

工作：

- 实现 `opentrace run` 和 `opentrace resume` 启动器。
- 在创建 Run 后以固定 session ID 启动交互式 Claude Code。
- 实现标准 MCP Server。
- 创建 Plugin manifest 和 Skill。
- 将 MCP Server 随插件加载。
- 验证工具 schema、错误返回和会话恢复。

产出：

- 用户通过一个 OpenTrace 命令进入已绑定 Run 的 Claude Code 会话。
- Claude Code 可以直接调用 OpenTrace 工具。

预计：3～4 个工作日。

### Phase 4：Hook 自动采集与执行门禁

工作：

- 实现 SessionStart、PreToolUse、PostToolUse、PostToolUseFailure、Stop、SessionEnd Hook。
- 自动记录命令、程序版本、错误和文件变化。
- 实现 active step 门禁和 Stop 验证。
- 处理 Hook 重复调用和中断恢复。

产出：

- Claude 无需手工填写真实命令和执行状态。
- 缺少 active step 时无法继续实质分析。

预计：4～5 个工作日。

### Phase 5：颗粒度规则和 HumanContribution

工作：

- 实现确定性颗粒度规则。
- 实现输出文件的 `step_output`、`internal_intermediate` 和 `temporary` 分类。
- 编写精简 Skill 和正反例。
- 实现软验证结果与修正循环。
- 实现 UserPromptSubmit 待分类事件、最小 HumanContribution 及历史 Step challenge。

产出：

- Agent 能形成较稳定的语义节点。
- 人的指导、规划和异议能进入真实工作流。

预计：3～4 个工作日。

### Phase 6：兼容导出与端到端稳定

工作：

- 从 SQLite 导出前端当前可读取的数据。
- 端到端运行完整 Claude Code 数据分析样例。
- 验证失败、重试、计划修改、会话恢复和人工异议。
- 修复 Windows 路径、编码和并发写入问题。

产出：

- 可日常使用的个人系统版本。

预计：3～5 个工作日。

## 12. 时间评估

以一名熟悉现有代码的开发者、Claude Code 辅助开发、暂不重做前端计算：

| 交付级别 | 范围 | 预计时间 |
|---|---|---:|
| 技术原型 | 新模型、Python API、单条成功工作流 | 7～10 个工作日 |
| 可用 MVP | 启动器、MCP、核心 Hook、文件血缘、基本颗粒度约束 | 16～22 个工作日 |
| 稳定个人版 | 人工介入、恢复、兼容导出、完整端到端测试 | 22～30 个工作日 |

推荐按 4～5 周安排：

- 第 1 周：Phase 0～1。
- 第 2 周：Phase 2～3。
- 第 3 周：Phase 4。
- 第 4 周：Phase 5 和端到端集成。
- 第 5 周或预留缓冲：Phase 6 和稳定性修复。

最大不确定性不是数据模型，而是 Claude Code Hook 在不同工具、失败、会话恢复和上下文压缩场景下的稳定行为。应为 Hook 集成和端到端调试保留约 25% 缓冲时间。

## 13. 验收标准

### 目标一：完整记录 Step 级真实工作流

- 每个实质性分析动作都归属到一个 active step。
- 每个 Step 都包含目标、输入文件、数据操作、程序、真实命令、输出文件和处理结果。
- 分析类 Step 包含分析结论。
- 失败和重试不会被丢弃。
- 同一路径的不同内容形成不同 FileVersion。
- 任意输出文件都能回溯到产生它的 Step 和输入文件。
- Agent 声明、Hook 观察和系统计算字段可以区分。
- 会话恢复后不会创建重复 Run 或丢失 active step。
- OpenTrace 在启动 Claude Code 前已经创建 Run，并能用同一 session ID 恢复。
- Python 脚本和文件创建事件不会被自动误记为语义 Step。
- 被后续 Step 使用的中间数据能够成为 `step_output` 并建立文件级血缘。
- 单次大脚本的真实执行不会在事后被伪造为多个 Step。

### 目标二：约束 Agent 合理分析

- Run 活动且没有 active step 时，Agent不能执行实质性 Bash、Write、Edit。
- Agent不能在未登记计划节点的情况下开始新 Step。
- 过细节点会收到合并或重写提示。
- 包含内部分析决策边界的过粗节点会收到拆分提示。
- Step 缺少真实输出或处理结果时不能完成。
- Run 存在未完成 Step 时不能结束。
- Skill 内容保持简短，不再要求 Agent理解底层 PROV 结构。
- 人工输入必须在下一次实质操作前完成分类；规划和异议能追溯到对应 Plan 或 Step。

## 14. 开发优先级

严格按照以下顺序：

1. Step 模型与单一事实源。
2. 文件级输入输出和真实执行记录。
3. 两阶段 Step API。
4. OpenTrace 启动器、MCP 接入和会话恢复。
5. Hook 自动采集和门禁。
6. 颗粒度验证及输出角色分类。
7. 最小 HumanContribution。
8. 兼容导出。

在以上内容达到验收标准前，不开发新的可视化、细粒度血缘、云服务、协作功能或通用 Agent 能力。
