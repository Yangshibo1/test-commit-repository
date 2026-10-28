# 从 Event 向 Claude 提交修改意见

入口：Agent 详细执行工作流 → 点击 Event → 事件详情中的“提出修改意见”。

1. 填写修改意见，点击“预览修改 Prompt”。此步骤只整理已有上下文，不调用模型或向终端写入。
2. 检查完整 Prompt，点击“发送给当前 Agent”。反馈作为此 Event 所属 Claude 会话的新一轮用户消息提交。
3. 在“Claude 运行”查看执行进展。新增执行继续进入 Transcript 和动态事实图；语义分析保持手动触发。

Prompt 引用事件编号、ID、所属 Turn 与用户任务、执行事实、源行号、关联文件和既有 AI 行为摘要/角色。事实与 AI 解读分别标记；长字段和列表有限截取，并提示按原始记录回溯。用户修改意见完整保留，最多 6000 字符。
历史 Event、Transcript、语义摘要均不因提出反馈而改写；Agent 通过后续执行修正受影响的产物或结论。

## 目标和投递

- 只发送给同一会话中仍在运行的 Claude 终端，提交时重新核对终端 ID。其他会话不会接收此反馈。
- Agent 正在执行或收尾时，可以填写和预览意见，结束后由用户手动发送，不自动中断或自动发送。
- 历史会话可复制完整 Prompt；要直接发送，先在 Claude 运行页恢复同一会话。
- 终端已有未提交输入时保留原内容，用户先提交或用 Ctrl+U 清空后再发送反馈。
- 浏览器当前标签页保存各 Event 的意见草稿和最后一条反馈，切换事件后可继续填写。已发送后可“再提一条意见”。
- 预览记录保存在 `<observations>/<session_id>/feedback/<feedback_id>.json`，包含上下文快照、完整 Prompt、用户意见、目标终端和投递时间。
- 状态为 `draft` → `sending` → `submitted`。`submitted` 只表示已写入终端并提交，不表示 Agent 已完成处理；不确定的写入失败记为 `delivery_uncertain`，不会自动重发。
- 重复请求同一已提交反馈返回原记录，不再次输入 Prompt。多行 Prompt 使用 bracketed paste 和单独 Enter，在同一输入锁下提交，防止与终端按键交错。

## 接口

| 方法与路径（前缀 `/api/observations/{session_id}`） | 用途 |
| --- | --- |
| `POST /events/{event_id}/feedback`，`{content}` | 生成并保存待审阅 Prompt，返回当前可投递状态 |
| `GET /event-feedback/{feedback_id}` | 获取持久化状态和目标会话状态 |
| `POST /event-feedback/{feedback_id}/send`，`{terminal_session_id}` | 发送用户已预览的原始 Prompt，不接受客户端替换上下文 |

`tests/test_event_feedback.py` 覆盖上下文和截断、无效事件和控制字符、预览无终端副作用、实际粘贴/提交顺序、重复提交、忙碌、目标会话/终端变化、未提交输入、投递失败及输入并发。全部使用假 PTY，不向真实 Claude 发送测试消息。
