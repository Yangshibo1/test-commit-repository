# AgentVAST Web 交互层 P1 实施说明

## 1. P1 目标

在 P0 的真实 Claude Code Web 终端基础上，允许用户在同一个 Claude
会话中自由对话，并在需要执行正式数据分析时显式启动 AgentVAST 记录。
AgentVAST 仍然只记录和约束 workflow，不执行数据分析。

## 2. 状态模型

```text
ordinary_conversation
    -> planning
    -> plan_review
    -> ready / executing
    -> handling_input
    -> idle
    -> completed / aborted / failed
    -> ordinary_conversation
```

- Claude 启动时加载 AgentVAST Plugin，但没有 active Run 时 Hook 休眠并放行。
- Web 创建 Run 后，将 `terminal_session_id`、`claude_session_id` 和
  `run_id` 建立持久化绑定。
- Hook 每次根据 Claude session 查询 active Run，不再要求 Run ID 在 Claude
  进程启动前就固定到环境变量。
- `WorkflowStore.get_state`根据SQLite事实计算唯一`run.phase`。终端是否存活只表示
  Claude进程状态，不再用于推断任务处于规划、执行还是等待追问。
- 前端除SSE外每两秒重新核对当前Run和终端绑定，修复Run在其他入口变化后界面长期停留
  在旧任务表单的问题。
- Run completed/aborted 后释放绑定，Plugin 自动恢复休眠。

## 3. Plan 与 Node 控制闭环

1. 用户在 Web 中填写任务和输入文件，点击“开始数据分析记录”。
2. 后端创建 Run、结果目录和 session binding，并向同一个 Claude 终端发送
   `AGENTVAST_ACTIVATE` 控制消息。
3. Claude 必须先记录初始 Plan；在 Plan 出现前，实质分析工具被 Hook 阻止。
4. 任一新 Plan Revision 写入后，Run 进入 Plan approval checkpoint。
5. 用户可先在 Web 修改 pending Node；每次保存都会再产生一个Revision，但保存只写
   SQLite，不向Claude终端提交控制消息。用户确认当前最新Revision后，后端才发送唯一
   一次继续执行消息，并直接写入结构化 checkpoint approval，不让
   Claude 猜测用户输入类别。
6. Claude 自动执行依赖已满足的 Node。每个 Node 使用 `start-node` 建立边界，
   使用 `complete-node` 记录真实命令、程序、输入文件、输出文件、处理结果和
   分析结论。
7. 真实发现改变分析路径时，Claude 只能调整未来 pending Node；active 和
   completed Node 保持不可变。新Revision再次进入人工编辑/确认checkpoint，确认前
   不允许继续实质分析。
8. 所有当前 Plan Node 完成后，Claude 结束当前回合，但 Run 保持 active，等待下一轮
   分析要求。后续要求通过新 Plan Revision 追加 pending Node。
9. 用户可以点击“完成并封存 Trace”只结束和导出当前Run，也可以点击`New Task Trace`
   原子地封存旧Run并在同一Claude会话创建新的Run ID和初始Plan。

这里的“不可变”仅指 Plan 中已经开始或完成的 Node 定义（目标、依赖和产物
要求）不能被后续 Revision 覆盖或删除，并不冻结文件。后续 Node 可以读取、
复用和原位编辑先前 Node 的产物；完成后，AgentVAST 将编辑前版本记录为输入，
将编辑后版本记录为当前 Node 输出。只有新建文件必须使用当前 Node 前缀。

## 4. 人工介入

Web 提供三种显式人工介入：

- `challenge`：对之前的数据处理或结论提出异议。
- `planning_input`：帮助规划下一步分析决策。
- `analysis_guidance`：提供分析方法、背景或口径指导。

Web 直接创建并分类 input event。完整的内部控制内容保存在 SQLite 的
`control_messages` 表中，PTY 只向 Claude 输入一条短的单行 nonce，例如
`[AGENTVAST_CONTROL id=control_xxx]`。UserPromptSubmit Hook 使用 nonce 从
SQLite 读取并一次性消费控制内容。Claude 处理真实 workflow 影响后使用
`apply-user-input` 完成记录。内部控制内容不依赖多行终端粘贴，也不会被再次
登记为用户输入。

用户仍可直接在终端中自由输入；记录模式中的普通终端输入继续由 Claude
按现有 recorder contract 分类。需要影响 workflow 的输入优先使用 Web 人工
介入控件，以避免含义不明确。

## 5. 两条独立实时通道

- PTY WebSocket：只传输 Claude Code 原始终端字符流、键盘输入、尺寸和
  Ctrl+C，不解释终端文字。
- AgentVAST SSE：每秒检查结构化 SQLite 状态，仅在状态变化时推送 Run、
  Plan、Node、checkpoint 和 pending input 快照。

前端的 Plan/Node 状态来自 SQLite，而不是从 Claude 的终端回复中提取。

控制面板只应在 Claude 已完成当前回复、终端等待输入时触发。AgentVAST 不
解析终端文字来猜测 Claude 是否空闲，因此 P1 不提供自动 busy 检测。
Web 控制消息的文本和回车分开写入 PTY，因此在输入提示符空闲时会直接执行，
不再只停留在终端输入框。Claude Code CLI 的一次 agent turn 仍是线性的；
执行期间提交的控制只能排队到本轮结束，或由用户先发送 Ctrl+C 再提交。

## 6. 前端 Plan 编辑

- 右侧固定分为上下两区：当前Plan及编辑器始终位于右上滚动区，所有任务输入、
  后续分析、规划介入和`New Task Trace`输入始终位于右下输入区。
- 初始任务和后续轮次不再使用位置不同的输入卡片；输入区只根据当前状态切换提交语义。
- 创建或切换到新Run时，前端立即清空旧Plan、编辑草稿和Revision状态；新Plan尚未
  写入SQLite时，右上只显示初始Plan生成状态。旧Run的延迟SSE事件不得覆盖新Run界面。
- 初始任务、新Trace任务和人工介入使用互相独立的草稿；Run ID或phase变化时关闭失效的
  New Task Trace表单，不能把旧草稿当作新任务再次提交。
- Web 允许直接修改 pending Node 的目标、依赖和产物类型，并支持新增或删除
  pending Node。
- active/completed Node 在编辑器中只读，后端也会再次校验，不能通过请求绕过。
- 保存不会覆盖旧 Plan，而是追加一个 `human_intervention` Plan Revision，并
  记录修改原因；用户可留空，由Web写入默认说明。保存按钮不向终端写入任何内容，
  “确认当前Revision并执行”才提交一次控制消息。
- 每次编辑保存都会生成新Revision并继续等待确认；即使分析已经开始，当前active Node
  也只能在新Revision确认后继续完成。
- 任一Plan Revision生成或修订时，Claude终端打印与Web相同的稳定Node编号、
  中文目标、依赖和产物类型，并以“Plan 已生成，请在右侧查看、编辑或确认。”结束。
- 右下以“追加分析或调整后续计划”提交时，界面显示等待目标Revision；Claude必须先
  创建新Plan Revision。Revision生成后不直接执行，而是等待用户在右上编辑或确认。
  SSE检测到版本增加后自动刷新、提示并将右上Plan滚动到顶部，同时保留手动刷新入口。

## 7. 输入文件发现与多轮 Trace

- 输入文件字段可留空。Claude 在建立 Plan 前只能使用 `Glob`、`Grep`、`Read` 做只读
  文件选择，并通过 `declare-inputs` 登记真实外部输入；这一步不允许写文件或执行分析命令。
- 每次 Plan 完成只是一个可继续的空闲边界，不会自动结束 Run。
- 不点击 `New Task Trace` 时，后续用户要求、Plan Revision、Node 和产物血缘继续属于
  当前 Run。
- 点击 `New Task Trace` 时，当前 Run 必须没有 active/pending Node 或未处理输入；后端
  先执行完成与导出，再创建独立的新 Run。

## 8. 中断恢复

- 每个 Web Claude 进程都使用 AgentVAST 生成的明确 Claude session ID。
- 原会话仍可用时，通过 `--resume <claude_session_id>` 恢复。
- 原会话上下文不可用或已经饱和时，创建新 Claude session，将 active Run
  binding 原子迁移到新 session，并注入 SQLite 恢复快照。
- 恢复快照包含任务、当前 Plan、completed Node、active Node、pending
  input 和 result root；completed Node 不允许重做或改写。
- Claude 启动环境设置 200,000 token 配置目标和 80% 自动压缩阈值。API
  网关的实际窗口上限仍可能低于该值，因此新会话恢复不能被自动压缩替代。
- Web 服务重启后，可从默认项目的 SQLite 找回最近的 active session binding。

## 9. P1 边界

P1 不实现 Claude Agent SDK、多人协作、远程开放端口、终端内容解析、云端
同步、item 级血缘和自动评价分析质量。记录页面现有 DAG 展示保持不变；P1
只在 Claude 页面增加当前 Run 的实时 Plan/Node 控制。
