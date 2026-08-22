# AgentVAST 系统设计与当前工作总览

## 1. 文档目的

本文整理 AgentVAST 当前的产品定位、系统设计、记录模型、Claude Code 集成方式、人工介入
机制、原型实现进度，以及已经通过真实数据分析 Run 暴露的问题。

文档特别区分三类内容：

- **最终目标**：系统希望长期成立的设计原则；
- **当前原型**：代码已经具备的能力；
- **待修正项**：当前实现与最终目标之间仍存在的差异。

AgentVAST 当前只服务个人本地数据分析场景，不在本阶段扩展团队协作、云平台或通用分析引擎。

## 2. 产品定位

AgentVAST 是一个面向 Coding Agent 数据分析任务的本地工作流记录与约束工具。

当前主要执行 Agent 是 Claude Code，未来可以适配 OpenCode 等其他 Coding Agent，但不应
为了尚未发生的平台适配提前引入复杂抽象。

系统职责边界是：

```text
Claude Code
负责读取数据、编写和执行程序、选择分析方法、解释结果、决定后续分析方向

AgentVAST
负责建立任务边界、约束执行顺序、观察真实操作、记录文件产物、导出真实工作流
```

AgentVAST 不执行数据分析，也不代替 Agent 选择算法或生成结论。它记录的是 Agent 实际完成
的数据分析工作流，而不是一份事后编写的理想流程。

现阶段只有两个最高优先级目标：

1. 完整记录以语义 Node 为颗粒度的 Agent 数据分析工作流。
2. 约束 Agent 按照可记录、可解释且颗粒度合理的方式进行数据分析。

## 3. 明确边界

### 3.1 当前要做

- 记录完整 Run；
- 记录动态 Plan Revision；
- 记录完成后的真实 Node；
- 记录真实命令、程序、输入文件、输出文件、阶段结果和分析结论；
- 保存代码、中间数据、阶段报告和可视化产物；
- 建立文件级数据血缘；
- 记录实际影响分析过程的人工介入；
- 通过 Claude Code Plugin 和 Hook 约束工作流；
- 导出稳定、规范化的 JSON，供现有前端生成 DAG 和详情页面。

### 3.2 当前不做

- 不记录 Agent 的 Thought、chain-of-thought 或隐藏推理；
- 不把所有工具调用直接展示为工作流；
- 不要求 Agent 为记录而额外整理算法名、参数表、输出角色或结构化统计对象；
- 不在当前阶段做字段级、记录级或 item 级血缘；
- 不判断自然语言分析结论一定正确；
- 不成为 Python 运行时、Notebook 内核或分析算法引擎；
- 不建设多用户、权限、审批、团队协作、云同步等功能；
- 不重新设计已有前端的页面布局；
- 不为尚未确定的其他 Agent 平台实现完整通用协议。

## 4. 核心设计原则

### 4.1 记录真实语义任务链

AgentVAST 需要记录的是：

> Agent 为完成分析目标，实际执行了哪些有语义意义的分析任务；每项任务使用了什么程序和
> 命令，处理了哪些文件，产生了哪些文件，得到了什么结果，又形成了什么分析结论。

这不同于两种常见记录：

- **操作日志**：按 Read、Write、Bash、Edit 等调用逐条排列，颗粒度过细，不能表达分析任务；
- **事后报告**：只保留最终结论，无法还原真实执行过程和中间产物。

AgentVAST 用 Node 组织工具事件，但不把工具事件本身当作 Node。

### 4.2 计划与事实分离

Plan 是执行前对未来工作的预期，Completed Node 是执行后对真实工作的记录。

```text
Plan Revision：准备做什么
Active Node：当前工作的内部边界
Completed Node：刚才实际上做了什么
```

计划可以动态调整，已经完成的事实不能被新计划重写。

### 4.3 尽量自动观察，减少 Agent 额外负担

如果某个字段可以由 AgentVAST 从 Hook、文件系统或内部状态中可靠获得，就不要求 Agent
再次整理和提交。

Agent 主要负责提供语义信息：

- Node 目标；
- 实际操作的简短说明；
- 实际结果；
- 分析结论；
- 完成时实际使用的输入文件。

AgentVAST 主要负责提供事实信息：

- 稳定 Node 编号；
- Plan 版本和执行顺序；
- 时间与状态；
- 真实命令；
- 实际程序文件；
- 自动发现的输出文件；
- 文件哈希；
- 文件级血缘；
- Claude session 和人工介入上下文。

### 4.4 可验证不等于正确

程序实际执行、文件真实存在、报告和可视化成功生成，只能说明 Agent 留下了可复核的分析
过程，不能证明：

- 数据理解正确；
- 统计口径正确；
- 因果解释正确；
- 可视化逻辑正确；
- 最终结论科学可靠。

AgentVAST 应忠实记录错误的工作流和错误的结论，而不应在导出时将其改写成“正确答案”。

## 5. 统一领域模型

### 5.1 Run

Run 表示一次完整的数据分析任务，包含：

- 用户原始任务；
- 项目目录；
- Run 独立结果目录；
- 声明的初始输入；
- 执行 Agent 与 session；
- 开始、完成时间和最终状态；
- 该 Run 的全部计划修订、Node、人工介入和文件血缘。

### 5.2 Plan Revision

Plan Revision 是某个时刻对完整剩余任务结构的快照。

它不是一次性、不可更改的静态计划。Agent 可以在以下时机重新判断后续工作：

- 某个 Node 开始前；
- 某个 Node 执行过程中；
- 某个 Node 完成后；
- 收到人工指导、规划建议或异议后。

新的 Plan Revision 保存完整快照，旧 Revision 永久保留。

### 5.3 Node

系统对外只使用一个业务概念：

```text
Node = 一个可以独立说明、执行和验收的语义分析任务
```

Plan Revision 中的 Node 表示计划任务；顶层 `nodes` 中的 Node 表示已经真实执行的任务。
二者使用相同的稳定 `node_id`，并通过 `plan_version` 建立对应关系。

内部 SQLite 暂时可以继续使用 `steps`、`step_id` 等历史字段，以兼容已有数据库和 Hook
关联，但这些名称不进入对外模型。

### 5.4 Artifact

Artifact 是 Node 在真实执行中创建或修改的正式分析产物。当前原型关注四类：

- `code`：Python 或 Notebook 分析程序；
- `data`：中间数据集或结构化分析结果；
- `report`：阶段分析报告；
- `visualization`：图表或交互式可视化成果。

### 5.5 Human Intervention

Human Intervention 表示用户在 Claude 分析过程中提供的指导、下一步规划意见或对既有处理
提出的异议。

人工输入本身不是 Node。只有它真正引发的验证、修正或新分析目标，才可能形成新的 Node。

## 6. Node 颗粒度

### 6.1 适合成为独立 Node

一项工作满足以下任一条件时，通常值得成为独立 Node：

- 有独立且可验收的分析问题；
- 完成后能形成可以单独说明的结果；
- 该结果会影响下一步分析决策；
- 产生的中间数据将被后续另一项语义任务消费；
- 必须先观察当前结果，才能决定后续做什么；
- 对旧结论进行独立验证或纠正。

示例：

```text
node-001：检查原始数据结构、完整性和基本质量
node-002：基于清洗后的事件表还原关键事件链
node-003：验证异常事件与干预行为之间的时间关系
node-004：汇总结论并生成最终可视化
```

### 6.2 不应单独成为 Node

以下行为本身通常只是某个 Node 的实现动作：

- 读取文件；
- 编写 Python 脚本；
- 执行命令；
- 保存或导出文件；
- 创建图表；
- 修改函数；
- 重试失败命令；
- 创建缓存或调试文件；
- 确认文件已经存在。

例如，“编写 profile.py”“运行 profile.py”“保存 profile.json”不应成为三个 Node。它们
应属于“建立数据结构与质量概况”这一个语义 Node。

### 6.3 脚本和中间数据是否意味着需要新 Node

脚本或中间数据的出现并不会自动创建新 Node。

判断依据是其语义作用：

- 如果脚本和中间数据只是完成当前分析目标的方法和产物，它们属于当前 Node；
- 如果中间数据结束了一个独立分析阶段，并会被后续不同分析目标消费，该阶段适合形成 Node；
- 如果必须先检查中间结果才能决定下一步，则当前阶段与后续决策通常应拆成不同 Node。

因此，Node 颗粒度由分析目标和决策边界决定，而不是由文件数量或命令数量决定。

### 6.4 防止 Node 过大

一个 Node 如果同时包含多个可以分别验证、并可能导向不同后续决策的问题，就过于宽泛。

真实 VAST 分析中曾将精确事件链、内容来源、历史模式和干预效果同时放进一个 Node。这类
Node 虽然不是工具日志，但仍然难以验证，也不利于后续修订计划，应拆成更清晰的语义目标。

## 7. 动态 Plan 设计

### 7.1 基本规则

每个实际 Node 必须对应其启动时 Plan Revision 中的一个 Node。

如果后续任务的目标、依赖或产物要求发生变化，Agent 必须先创建新的 Plan Revision，再启动
受影响的 Node。

### 7.2 可以修改的内容

计划修订只允许修改尚未开始的未来 Node：

- 增加新 Node；
- 删除不再需要的未来 Node；
- 修改未来 Node 的目标；
- 修改未来 Node 的依赖；
- 修改未来 Node 的最低产物要求。

### 7.3 不能修改的内容

- 已完成 Node 不能被删除、改名或修改目标；
- active Node 的目标、依赖和产物要求不能被 Revision 偷换；
- 已使用的 Node 编号不能回收复用；
- 新 Revision 不能隐藏已经发生的执行历史；
- 当前任务目标发生实质变化时，不能直接重写 active Node。

如果 active Node 的目标已经不再成立，应将其记录为中断或完成当前可说明部分，再用新 Node
承载新的目标。

### 7.4 Node 与 Plan 版本绑定

Node 启动时锁定：

- `node_id`；
- `plan_version`；
- 当时的 `objective`；
- 当时的 `depends_on`；
- 当时的 `required_artifacts`。

即使 Agent 在 Node 执行期间修订了未来计划，当前 Node 仍绑定启动时的 Plan Revision。

## 8. 目标执行生命周期

目标工作流如下：

```text
创建 Run 并启动 Claude Code
        ↓
Claude 提交初始 Plan Revision
        ↓
选择一个依赖已满足的计划 Node
        ↓
start-node：建立内部执行边界
        ↓
Claude 自由完成该语义任务
        ↓
生成并执行代码，产生中间数据、报告或可视化
        ↓
complete-node：按真实执行情况记录 Node
        ↓
决定保留或修订未来 Plan
        ↓
执行下一个 Node
        ↓
finish-run 并导出规范化 JSON
```

### 8.1 `start-node` 应记录什么

按照最终目标，Node 开始时只建立内部边界，不提前声称真实工作结果。应锁定或自动记录：

- `node_id`；
- 启动时的 `plan_version`；
- 来自 Plan 的目标、依赖和产物要求；
- `started_at`；
- 当前文件版本和结果目录快照；
- 后续 Hook 事件归属范围。

Node 开始时不应要求 Agent 最终确定全部 `input_files`。因为 Agent 可能只有在实际分析后才
知道真正消费了哪些初始数据和上游中间产物。

### 8.2 Node 执行期间

Claude 仍然拥有分析自由，可以：

- 阅读数据；
- 编写、修改和运行 Python；
- 使用命令行程序；
- 生成中间数据；
- 撰写阶段报告；
- 创建可视化；
- 根据结果判断是否需要修订未来计划；
- 接受并处理用户的人工介入。

AgentVAST 在后台观察真实命令、文件变化和 Hook 事件，并将其关联到 active Node。

### 8.3 `complete-node` 应记录什么

Node 完成后，Agent 根据真实执行过程提交：

- 实际使用的 `input_files`；
- `operation_summary`；
- `result_summary`；
- `analysis_conclusion`。

AgentVAST 自动补充：

- 实际执行命令；
- 实际程序文件；
- 自动发现的输出文件；
- 文件 SHA-256；
- 开始与完成时间；
- Node 顺序和 Plan 版本；
- 文件血缘。

完成时应校验：

- 输入是 Run 初始输入、Node执行中首次发现的外部输入或已完成 Node 的输出；
- 输入版本在本 Node 执行期间确实可用；
- Plan 直接依赖没有贡献文件输入时给出诊断提示，但允许其作为纯语义依赖；
- 输出确实由本 Node 新增或修改；
- 必需产物存在、非空且命名合规；
- 代码产物中至少有一个被真实成功执行；
- Node 的完成记录没有与真实 Hook 和文件状态冲突。

### 8.4 完成后记录的意义

Node 的正式记录发生在 Node 结束后，是对已经发生的真实工作的回顾性描述。

这能避免：

- 在开始前猜测输入文件；
- 计划中的操作被误当成实际命令；
- 声称生成了实际上不存在的产物；
- 使用了上游结果却只记录原始文件；
- Plan 和真实执行记录混为一体。

## 9. 正式产物约束

每个 Run 使用独立结果目录：

```text
result/<run_id>/
├─ code/
├─ data/
├─ report/
└─ visualization/
```

产物文件名以生成它的 Node 编号开头：

```text
code/node-001_profile.py
data/node-001_profile.json
report/node-001_findings.json
visualization/node-002_anomaly_chart.html
```

当前原型规则：

- `code` 支持 `.py`、`.ipynb`；
- `data` 支持 `.csv`、`.json`、`.jsonl`、`.parquet`、`.feather`、`.arrow`；
- `report` 使用有效的 `.json` object；
- `visualization` 支持 `.html`、`.svg`、`.png`、`.jpg`、`.jpeg`、`.pdf`；
- 正式产物必须非空；
- 每个Node需要哪些产物由Claude在Plan中判断；
- 不强制每个Node生成报告，也不强制Plan覆盖全部四类产物；
- 实质 Python 分析应保存为文件并真实执行，不使用长 `python -c` 代替可复核程序。

四类产物是当前原型聚焦的验证对象，不意味着每个 Node 都必须产生四类文件。每个 Node 的
最低要求由 `required_artifacts` 决定。

## 10. 对外 JSON 设计

规范化 JSON 是前端、DAG 生成器和后续适配器使用的唯一对外事实来源。

### 10.1 顶层结构

```json
{
  "schema_version": "1.3",
  "run": {},
  "plan_revisions": [],
  "nodes": [],
  "human_interventions": [],
  "file_lineage": []
}
```

### 10.2 Run

```json
{
  "run_id": "run_001",
  "task": "分析示例数据，说明主要特征和异常",
  "project_root": "C:/project",
  "result_root": "result/run_001",
  "agent": "claude-code",
  "session_id": "session-001",
  "status": "completed",
  "started_at": "2026-07-29T10:00:00Z",
  "completed_at": "2026-07-29T10:20:00Z",
  "declared_inputs": [
    {
      "path": "data/sample.json",
      "sha256": "601b252d..."
    }
  ]
}
```

Run 描述整个分析任务，不记录文件大小。文件版本当前使用 `path + sha256` 标识。

### 10.3 Plan Revision

```json
{
  "version": 2,
  "created_at": "2026-07-29T10:08:00Z",
  "trigger": "agent_replan",
  "change_reason": "初步检查发现需要先验证时间字段口径",
  "nodes": [
    {
      "node_id": "node-001",
      "objective": "建立数据结构与质量概况",
      "depends_on": [],
      "required_artifacts": ["code", "data", "report"]
    },
    {
      "node_id": "node-002",
      "objective": "验证时间字段及其时区口径",
      "depends_on": ["node-001"],
      "required_artifacts": ["code", "data", "report"]
    }
  ]
}
```

`trigger` 当前包括：

```text
initial
agent_replan
human_intervention
```

### 10.4 完成后的真实 Node

```json
{
  "node_id": "node-001",
  "sequence": 1,
  "plan_version": 1,
  "objective": "建立数据结构与质量概况",
  "inputs": [
    {
      "path": "data/sample.json",
      "sha256": "601b252d..."
    }
  ],
  "operation": {
    "summary": "读取原始数据并检查结构、完整性和主要字段分布。",
    "commands": [
      "python result/run_001/code/node-001_profile.py"
    ],
    "programs": [
      "result/run_001/code/node-001_profile.py"
    ]
  },
  "outputs": [
    {
      "path": "result/run_001/data/node-001_profile.json",
      "sha256": "8a7c..."
    },
    {
      "path": "result/run_001/report/node-001_findings.json",
      "sha256": "91bd..."
    }
  ],
  "result_summary": "完成数据概况，并识别出两个需要进一步核验的时间字段。",
  "analysis_conclusion": "后续事件链分析前必须先统一时间字段和时区口径。",
  "status": "completed",
  "started_at": "2026-07-29T10:01:00Z",
  "completed_at": "2026-07-29T10:07:30Z"
}
```

其中：

```text
result_summary
= 实际得到了什么事实结果

analysis_conclusion
= 这些结果对分析意味着什么
```

纯转换 Node 可以使用 `analysis_conclusion: null`，不能为了填字段编造结论。

### 10.5 不进入对外 JSON 的内容

- 文件大小；
- 算法列表；
- 参数对象；
- 输出角色；
- 结构化 `processing_result`；
- Agent Thought 或 chain-of-thought；
- 原始 Hook payload；
- 内部门禁状态；
- 目录快照；
- 完成条件；
- SQLite 兼容字段 `steps/step_id`；
- 普通聊天；
- 前端 DAG 坐标和布局。

删除这些字段的原因是：它们要么可以自动推导，要么会迫使 Agent 为记录做额外工作，要么
属于运行时诊断而非真实语义工作流。

## 11. 文件血缘与 DAG

### 11.1 文件级血缘

当前只做到文件版本级：

```text
上游文件 path + sha256
        ↓
完成的 Node
        ↓
下游文件 path + sha256
```

`file_lineage` 从完成 Node 的真实 `inputs` 和 `outputs` 自动派生，不要求 Agent 再提交一份
独立血缘数据。

未来如果确有需要，可以扩展到字段、记录或 item 粒度，但不属于当前个人原型范围。

### 11.2 DAG 生成

不需要在实际 Node 中增加 `depends_on_steps`。

DAG 生成器使用：

```text
nodes[].node_id
nodes[].plan_version
plan_revisions[].nodes[].depends_on
nodes[].inputs
nodes[].outputs
human_interventions[].active_node_id
```

自动生成：

- Node 之间的计划依赖边；
- 文件到 Node 的输入边；
- Node 到文件的输出边；
- 人工介入对 active Node 或后续 Plan 的影响关系。

Agent 不提交 DAG 节点、边或布局坐标。现有前端只需要消费规范化 JSON 或由它派生的
`dag.json`。

## 12. 人工介入

### 12.1 交互方式

用户直接在当前 Claude Code CLI 会话中输入消息，不需要另建人工审批页面。

典型人工介入包括：

- 帮助 Agent 理解数据或分析背景；
- 指导下一步分析决策；
- 建议调整未来计划；
- 对刚才的数据处理提出异议；
- 要求验证或纠正已有结论。

### 12.2 分类

```text
conversation_only
analysis_guidance
planning_input
challenge
```

- `conversation_only`：普通交流，不进入最终 JSON；
- `analysis_guidance`：影响当前分析方式；
- `planning_input`：影响后续任务计划；
- `challenge`：质疑已有处理或结论。

### 12.3 记录原则

AgentVAST 保存用户原文，并自动关联介入发生时的：

- active Node；
- Plan Revision；
- 时间。

Claude 只需记录该输入实际造成的 `workflow_effect`。

如果人工输入改变未来目标或依赖，Claude 必须先创建新的 Plan Revision。对历史结论的异议
不应修改旧 Node，而应创建验证或纠正 Node，从而保留真实发生过的错误和修正过程。

## 13. Claude Code 的启动与规则注入

### 13.1 启动方式

用户从项目目录执行：

```powershell
agentvast run --project "." --task "分析示例数据，说明主要特征和异常" --data "data\sample.json"
```

AgentVAST 负责：

1. 创建 Run 和本地 SQLite 状态；
2. 记录声明输入的文件版本；
3. 创建 Run 独立结果目录；
4. 生成并绑定 Claude session；
5. 设置本次 Run 的环境信息；
6. 通过插件目录启动 Claude Code；
7. 将初始任务和 AgentVAST 规则注入会话。

用户之后仍在正常 Claude Code 终端中与 Agent 对话。

### 13.2 Plugin 如何注入约束

Claude Code Plugin 不是只提供一份静态 workflow 文档，而是通过生命周期 Hook 共同工作。

#### SessionStart

动态注入：

- 当前 Run；
- 最新 Plan Revision；
- active Node；
- 声明输入；
- 待处理人工介入；
- Node 颗粒度规则；
- 产物目录和命名约束；
- 当前合法的记录命令；
- AgentVAST 只记录、不执行分析的职责边界。

#### PreToolUse

在 Claude 使用 Read、Write、Edit、NotebookEdit、Bash、PowerShell、Web、子 Agent 等实质性
工具前检查：

- 是否已经存在 Plan；
- 是否已经启动 active Node；
- 依赖是否满足；
- 是否存在未处理人工输入；
- Run 是否已经结束；
- 当前命令是否试图绕过记录流程。

#### PostToolUse / PostToolUseFailure

观察真实发生的：

- 命令；
- 程序运行；
- 文件操作；
- 成功或失败结果；
- 事件归属的 active Node。

#### UserPromptSubmit

捕获用户在分析过程中的人工介入，并关联当时的 Node 和 Plan。

#### Stop

阻止 Claude 在以下状态直接结束：

- 没有 Plan；
- 仍有 active Node；
- 仍有未处理人工输入；
- 当前 Plan 仍有未完成 Node；
- 没有成功执行 `finish-run`；
- 关键产物或一致性检查未通过。

### 13.3 为什么不能只依赖文档

仅向 Claude 提供说明文档不能稳定保证遵守工作流，因为：

- 长任务中静态说明容易被上下文稀释；
- Agent 可能理解规则但忘记执行记录命令；
- Agent 可能用 PowerShell、子 Agent 或其他工具绕过预期路径；
- Agent 会根据当前任务自行调整执行方式；
- 提示词无法验证文件是否真实存在、程序是否执行成功。

因此采用四层机制：

```text
简短规则注入
→ SQLite 状态机
→ PreToolUse / Stop 强制门禁
→ Hook、文件系统和完成命令交叉校验
```

Prompt 用于帮助 Agent 理解，状态机和 Hook 用于保证最低执行约束。

### 13.4 记录通道

当前默认使用：

```text
python -m agentvast.agent_cli <action>
```

而不是强制使用 MCP。原因是目前使用过的第三方 Claude API 兼容网关曾因
`tool_reference` 参数不兼容返回 400。CLI 记录通道可以绕开该模型网关兼容问题。

MCP 可以作为未来的可选适配方式，但不应成为当前记录闭环的单点依赖。

## 14. 存储与导出架构

### 14.1 内部 SQLite

SQLite 是运行期间的内部事实和控制状态，适合保存：

- Run；
- 完整 Plan Revision；
- active/completed/interrupted Node 状态；
- 文件版本；
- Node 输入输出关联；
- 人工输入；
- Hook 原始事件；
- 门禁状态；
- 目录快照；
- 迁移和兼容字段。

选择 SQLite 是为了事务、一致性、查询和崩溃恢复，而不是为了替代对外 JSON。

默认位置：

```text
.agentvast/workflow.sqlite3
```

### 14.2 规范化 JSON

JSON 是完成后对外使用的稳定数据：

```text
result/<run_id>/workflow.json
```

它用于：

- 人工查看；
- 前端展示；
- DAG 派生；
- 后续导入、迁移和兼容；
- 与其他 Agent 平台对接。

内部 SQLite 可以比 JSON 更详细，但不能把运行时诊断字段直接泄漏进对外工作流。

## 15. 当前原型已经实现

截至本文整理时，当前代码已经具备：

- `agentvast run/resume/state/export/abort` 用户命令；
- `declare-inputs/set-plan/start-node/complete-node/pause-for-user/finish-run` Agent 记录命令；
- Run 与 Claude session 绑定；
- SessionStart、PreToolUse、PostToolUse、UserPromptSubmit、Stop Hook；
- 不存在 Plan 或 active Node 时的实质工具门禁；
- 稳定的 `node-001`、`node-002` 编号；
- Plan Revision、依赖校验和循环检测；
- 后续Plan只能删除或修改未来pending Node；active/completed Node定义不可改写或删除；
- Node 与启动时 `plan_version` 绑定；
- Node 启动时冻结当时可用的初始输入和上游输出版本；
- Node 完成时才提交并绑定真实使用的输入；
- 没有实际变化的 Plan 不生成空 Revision，后续 Revision 必须说明原因；
- 每个 Run 独立的四类结果目录；
- Node 文件名前缀和非空校验；
- Node 启动时目录快照；
- Node 完成时自动发现新增或修改的产物；
- Python 代码产物执行校验；
- Hook 中真实命令的归集；
- 人工介入捕获与分类；
- 未显式提供输入文件时，Claude可在受限只读阶段理解任务；Node执行中首次使用的外部
  文件在完成时记录，不要求提前登记；
- Plan Node目标统一使用中文；计划生成时终端与Web右上展示字段一致的完整Plan，终端末尾提示用户在右侧编辑或确认；
- 当前Plan完成后Run保持active，支持在同一Trace中追加多轮Plan Revision；
- Web `New Task Trace`封存旧Run并在同一Claude会话创建新Run；
- `finish-run` 后自动导出 schema 1.3 规范化 JSON；
- 内部旧 `steps/step_id` 与对外 `nodes/node_id` 的兼容；
- 在真实 Claude Code Run 中完成多 Node 分析并生成四类产物。

这些能力说明原型已经能够形成可运行的记录闭环，而不再只是静态字段设计。

## 16. P0 已实现、仍待手动验收的改动

### 16.1 完成后绑定真实输入

当前代码已经调整为：

```text
start-node
只建立边界，锁定Plan版本，并冻结当时可用的文件版本

complete-node
提交并验证本 Node 实际使用的 input_files
```

完成时接受 Run 初始输入、completed Node 输出在 Node 启动时的冻结版本，以及Node执行中
首次发现的外部文件。首次发现文件在完成时计算SHA-256并加入Run输入。Plan 的`depends_on`
可以是没有文件传递的语义依赖；这种情况只产生内部诊断提示，不硬性阻断。

### 16.2 程序路径规范化

程序识别不再直接把命令中的相对路径拼接到项目根目录。当前实现：

- 从成功的 PostToolUse 事件获取真实命令；
- 以本 Node 真实代码产物和代码输入作为候选；
- 使用绝对路径、项目相对路径和唯一文件名与命令匹配；
- 去重后保存规范化绝对路径，对外导出项目相对路径。

该行为仍需要通过包含 `cd 子目录 && python file.py` 的真实 Claude Run 手动验收。

### 16.3 动态 Plan 生命周期

当前代码和 Plugin 规则已经明确：

- Node开始前、执行期间和完成后都可以调整未来pending Node；
- active/completed Node不能删除，也不能修改其目标、依赖或产物要求；
- 当前实际执行永远绑定启动时的Plan版本；
- 正式 Node 记录只在完成后根据真实执行形成。
- 后续 Revision 必须有真实 `change_reason`；
- Plan 没有实质变化时拒绝生成空 Revision。

这些规则仍需人工介入和执行中 replan 场景的真实手动验收。

### 16.4 产物存在不代表产物有效

当前可以验证文件存在、非空、命名正确以及代码执行成功，但无法保证：

- HTML 中的 JavaScript 能实际运行；
- 图表数据与报告一致；
- 报告中的数字口径正确；
- 结论没有过度推断。

可以考虑增加轻量的产物有效性检查，例如 HTML/JavaScript 启动检查，但不能让 AgentVAST
演变成分析结论审查器。

### 16.5 Node 颗粒度仍主要依赖语义规则

目前可以拒绝明显的“保存文件”“运行命令”型 Node，但无法完全自动判断一个 Node 是否同时
包含过多分析问题。

下一步可以通过：

- 更清晰的 Node 目标模板；
- Plan 提交时的语义规则；
- Node 完成后的计划复核提示；
- 对包含多个独立分析动词和结果的目标给出修订建议；

提高颗粒度一致性，但不应强行按命令数量拆分任务。

## 17. 真实 Run 带来的经验

### 17.1 已证明有效

真实 Run 已经证明 AgentVAST 可以记录：

- 稳定 Node 链；
- 动态 Plan 版本；
- 真实命令和程序；
- 代码、中间数据、报告和可视化产物；
- 文件哈希；
- Node 输出；
- 完成状态；
- 可由前端使用的规范化 JSON。

VAST Run 生成了多类正式产物，说明“要求 Agent 留下可复核分析成果”的约束能够实际运行。

### 17.2 暴露出的分析问题

同一次真实分析也出现了：

- 时区换算错误；
- 将删除记录数误写为事件数；
- 忽略关键来源记录；
- 上游事件链判断错误；
- 对“故意行为”作出证据不足的推断；
- 错误描述干预行为的时间效果；
- 可视化脚本存在逻辑或运行问题。

这正好验证了 AgentVAST 的定位：系统应忠实保留 Agent 的实际分析过程和错误结论，为后续
复核提供材料，而不是只展示一份被美化的最终答案。

### 17.3 暴露出的记录问题

- 后续 Node 使用了上游产物，但开始时声明的输入仍只有原始文件；
- 程序路径受 `cd` 和相对路径影响而重复或错误；
- 某些 Node 包含过多独立分析问题；
- 生成文件和执行成功只能证明“做过”，不能证明“做对”。

这些问题构成下一轮优化的直接依据。

## 18. 后续优先级

### P0：修正真实 Node 记录语义（代码完成，待手动验收）

1. 将实际输入申报从 `start-node` 移到 `complete-node`。
2. 在完成时验证输入版本并生成真实文件血缘，语义依赖无文件传递时只提示。
3. 规范化真实程序路径并消除重复。
4. 明确 Plan 可在 Node 开始和完成后动态修订。
5. 明确 Plan 是预期，Completed Node 是完成后形成的事实记录。
6. 使用真实 Claude Code Run 手动验证完整闭环。

### P1：提高可复核性

1. 为 HTML/JavaScript 可视化增加轻量运行检查。
2. 改进过宽 Node 的提示和计划校验。
3. 在 Node 完成后提示 Agent 判断是否需要修订未来 Plan。
4. 改进前端 DAG 和产物详情对规范化 JSON 的消费。

### 暂不进入计划

- item 级血缘；
- 多用户和权限；
- 云端服务；
- 审批系统；
- 通用模型网关；
- 自动判断分析结论真伪；
- 与记录目标无关的前端重构。

## 19. 验收标准

一个符合目标的 Run 至少应满足：

1. Claude 在实质分析前建立初始 Plan。
2. 每个实质性工具操作都能归属到一个 active Node。
3. 每个完成 Node 都能定位到启动时的 Plan Revision。
4. Node 完成记录反映真实使用的输入、命令、程序和输出。
5. 上游依赖能在实际输入血缘中得到体现。
6. 代码、中间数据、报告和可视化保存在 Run 独立结果目录。
7. 正式产物带稳定 Node 编号并可以被复核。
8. 人工介入被关联到当时的 Node 和 Plan，并记录真实影响。
9. 计划变化通过新 Revision 保留历史，而不是覆盖旧事实。
10. 最终规范化 JSON 不包含 Thought、原始 Hook 日志或要求 Agent 额外加工的冗余字段。
11. Run 完成时不存在 active Node、未处理人工输入或缺失的关键产物。
12. 前端可以仅根据规范化 JSON 派生语义 DAG 和文件级血缘。

## 20. 一句话架构

```text
Claude Code 自由完成数据分析
→ AgentVAST 用动态 Plan 和 active Node 建立语义边界
→ Hook 观察真实命令与文件变化
→ Node 完成后记录实际输入、操作、产物、结果和结论
→ SQLite 保证运行状态
→ 规范化 JSON 提供真实、可复核的语义工作流
```

## 21. 当前 Run 交互与归档约定

`agentvast run --checkpoint plan|node|none` 将人工交互节奏固化为Run配置，默认 `plan`。
每次 `set-plan` 创建新Revision都会自动打开Plan checkpoint；用户可编辑pending Node，且
只有明确确认最新Revision后，`plan`模式才继续自动执行。结束当前Plan时不再确认，也不
自动关闭Run。后续分析要求继续使用相同Run并增加Plan Revision，该Revision同样先等待编辑
或确认。只有用户点击Web的`New Task Trace`时，当前Run才完成、导出并由同一Claude
会话创建新的Run。`node`模式在确认每个Plan Revision后继续在每个Node完成后调用
`pause-for-user`。明确确认使用内部 `checkpoint_continue`，异议、指导和规划建议继续记录为
真实Human Intervention。completed或aborted Run不允许resume。

后续手动验证固定使用
`VAST_Challenge_2026_MC2（1）/VAST_Challenge_2026_MC2` 作为分析项目。每个 Run 的
代码、中间数据、阶段报告、可视化和规范化记录统一位于：

```text
result/<run_id>/
├─ code/
├─ data/
├─ report/
├─ visualization/
└─ workflow.json
```

`.agentvast/workflow.sqlite3` 只保存内部状态、Hook 事件和门禁事实。
