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

- `output_file_version_ids`
- `intermediate_file_version_ids`

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

只实现记录真实人机协作所需的最小模型，不实现审批流。

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

8. `opentrace_register_human_contribution`
9. `opentrace_apply_human_contribution`

执行记录不是 Agent 工具，由 Hook 调用内部接口写入。

### 6.1 `start_step` 的 Agent 输入

- `run_id`
- `node_id`
- `objective`
- `input_files`

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

## 7. Claude Code Plugin 约束

插件由三部分组成。

### 7.1 Skill

提供简短、稳定的规则：

- 什么是语义 Step
- 什么不是 Step
- 何时开始和完成 Step
- 如何调整计划
- 哪些字段由 Agent 补充

不再把完整 API 手册和 PROV 标准放进 Agent 工作说明。

### 7.2 MCP Server

提供上述类型化工具，并由状态机拒绝非法调用。

### 7.3 Hooks

只在 OpenTrace Run 活动时启用门禁。

- `SessionStart`：恢复未完成 Run 和 active step。
- `UserPromptSubmit`：捕获可能影响工作流的人工输入。
- `PreToolUse`：没有 active step 时阻止 Bash、Write、Edit 等实质操作。
- `PostToolUse`：记录成功的命令、程序修改和文件变化。
- `PostToolUseFailure`：记录失败和重试。
- `Stop`：存在 active step、缺失结果或 Run 未完成时阻止 Agent 提前结束。
- `SessionEnd`：将未完成会话标记为 interrupted，而不是 completed。

## 8. Step 颗粒度约束

### 8.1 标准定义

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

### 8.2 不应成为 Step

- 查看目录
- 读取一个文件
- 写一行 Python
- 执行一次 groupby
- 修复路径错误
- 重试失败命令
- 调整图表颜色

这些是 Step 内的执行事件。

### 8.3 颗粒度验证

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

## 9. 真实性保证

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

## 10. 实施阶段

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

- 实现标准 MCP Server。
- 创建 Plugin manifest 和 Skill。
- 将 MCP Server 随插件加载。
- 验证工具 schema、错误返回和会话恢复。

产出：

- Claude Code 可以直接调用 OpenTrace 工具。

预计：2～3 个工作日。

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
- 编写精简 Skill 和正反例。
- 实现软验证结果与修正循环。
- 实现最小 HumanContribution 记录及历史 Step challenge。

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

## 11. 时间评估

以一名熟悉现有代码的开发者、Claude Code 辅助开发、暂不重做前端计算：

| 交付级别 | 范围 | 预计时间 |
|---|---|---:|
| 技术原型 | 新模型、Python API、单条成功工作流 | 6～9 个工作日 |
| 可用 MVP | MCP、核心 Hook、文件血缘、基本颗粒度约束 | 15～20 个工作日 |
| 稳定个人版 | 人工介入、恢复、兼容导出、完整端到端测试 | 20～28 个工作日 |

推荐按 4 周安排：

- 第 1 周：Phase 0～1。
- 第 2 周：Phase 2～3。
- 第 3 周：Phase 4。
- 第 4 周：Phase 5～6 和稳定性修复。

最大不确定性不是数据模型，而是 Claude Code Hook 在不同工具、失败、会话恢复和上下文压缩场景下的稳定行为。应为 Hook 集成和端到端调试保留约 25% 缓冲时间。

## 12. 验收标准

### 目标一：完整记录 Step 级真实工作流

- 每个实质性分析动作都归属到一个 active step。
- 每个 Step 都包含目标、输入文件、数据操作、程序、真实命令、输出文件和处理结果。
- 分析类 Step 包含分析结论。
- 失败和重试不会被丢弃。
- 同一路径的不同内容形成不同 FileVersion。
- 任意输出文件都能回溯到产生它的 Step 和输入文件。
- Agent 声明、Hook 观察和系统计算字段可以区分。
- 会话恢复后不会创建重复 Run 或丢失 active step。

### 目标二：约束 Agent 合理分析

- Run 活动且没有 active step 时，Agent不能执行实质性 Bash、Write、Edit。
- Agent不能在未登记计划节点的情况下开始新 Step。
- 过细节点会收到合并或重写提示。
- 包含内部分析决策边界的过粗节点会收到拆分提示。
- Step 缺少真实输出或处理结果时不能完成。
- Run 存在未完成 Step 时不能结束。
- Skill 内容保持简短，不再要求 Agent理解底层 PROV 结构。

## 13. 开发优先级

严格按照以下顺序：

1. Step 模型与单一事实源。
2. 文件级输入输出和真实执行记录。
3. 两阶段 Step API。
4. MCP 接入。
5. Hook 自动采集和门禁。
6. 颗粒度验证。
7. 最小 HumanContribution。
8. 兼容导出。

在以上内容达到验收标准前，不开发新的可视化、细粒度血缘、云服务、协作功能或通用 Agent 能力。
