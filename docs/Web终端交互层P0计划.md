# AgentVAST Web 终端交互层计划

## 1. 目标

AgentVAST 保持“记录系统”的定位，Claude Code CLI 继续负责数据读取、程序执行、分析和可视化。Web 交互层不替代 Claude Code，也不解释或重写 Claude 的终端输出，只把本地 Claude Code 终端搬到网页中，并为后续 AgentVAST 工作流控制提供统一入口。

前端分为两个一级页面：

- **Claude 对话**：在浏览器中直接操作一个真实的 Claude Code 交互终端。
- **工作流记录**：保留当前 Run、Node、文件血缘和 DAG 的查看能力。

## 2. 技术边界

### 2.1 执行链路

```text
Browser / xterm.js
        │ WebSocket（输入、输出、终端尺寸和控制信号）
        ▼
AgentVAST 本地 Web 服务
        │ Windows ConPTY
        ▼
Claude Code CLI
        │
        ├── 文件、Shell、Python、可视化等原生工具能力
        └── 后续由 AgentVAST Plugin / Hook 记录结构化工作流
```

P0 中终端输出和 AgentVAST 记录是两条独立通道：

- 终端通道只传输 Claude Code 的原始字符流，不根据文本猜测 Node、工具调用或状态。
- AgentVAST 的 Plan、Node、产物和人工介入仍通过结构化命令、Hook 与 SQLite 记录；这部分已有能力不会被终端页面替代。

### 2.2 明确不做

- 不改用 Claude Agent SDK。
- 不自行实现 Shell、文件读写、Python 或权限系统。
- 不保存 Claude 的思维过程。
- 不用正则表达式解析终端输出生成工作流记录。
- 不做远程多用户、账号、权限分级、云端部署和会话共享。
- P0 不在普通 Claude 会话中自动启用 AgentVAST Run；按命令切换记录模式属于 P1。

## 3. P0 范围

P0 的验收目标是：用户打开本地网页后，可以像在 Windows 终端中一样连续使用 Claude Code，同时能切换回现有记录页面。

包含以下能力：

1. Claude 对话 / 工作流记录两个一级页面切换。
2. 记录页面保留现有文件夹加载、时间线、DAG 和详情面板。
3. 本地服务通过 Windows ConPTY 启动真实的 `claude` 进程。
4. xterm.js 原样显示 ANSI 色彩、光标移动和 Claude 的流式输出。
5. 键盘输入直接写入 Claude 终端，支持连续多轮对话。
6. 浏览器尺寸变化同步到 ConPTY。
7. 支持发送 Ctrl+C。
8. 支持关闭 Claude 进程。
9. 显示 WebSocket 与 Claude 进程状态。
10. 统一使用 `--dangerously-skip-permissions` 启动，不提供关闭该模式的页面选项。

## 4. P0 本地组件

### 4.1 Python Web 服务

- 使用 FastAPI 提供本地 HTTP API 和 WebSocket。
- 使用 pywinpty / Windows ConPTY 承载交互式 Claude Code CLI。
- 默认仅监听 `127.0.0.1`，不对局域网或公网开放。
- 一个服务实例只维护一个当前终端进程；重复打开网页会连接同一进程，而不是偷偷再启动一个 Claude。
- 服务退出时关闭它创建的 Claude 进程。

### 4.2 前端终端

- 使用 xterm.js 渲染终端。
- 使用 Fit Addon 计算列数和行数并同步到后端。
- WebSocket 消息只负责可靠传输：`output`、`input`、`resize`、`interrupt`、`close`、`status`。
- 输出内容写入 xterm 时保持原始顺序和控制字符，不转成聊天气泡。

## 5. P1 与后续方向

P0 稳定后再实现记录模式切换：

1. 普通 Claude 会话启动时 AgentVAST Plugin 处于休眠状态。
2. 用户通过网页按钮或明确命令创建 Run，设置初始 Plan，并在人工确认后进入自动执行。
3. 记录模式激活后，Plugin/Hook 才启用 Node 门禁和真实产物记录。
4. Node 完成事件通过独立的结构化 WebSocket/SSE 通道更新记录页面，而不是从终端文本中提取。
5. Run 完成后可回到普通对话；对已完成结论的异议应新建或继续一个有效 Run，不直接篡改历史 Node。

## 6. P0 验收标准

- 网页中看到的 Claude Code 界面与直接运行 `claude` 的终端行为一致。
- 可以在同一个 Claude 进程中持续输入、查看工具调用、回答交互问题和中断当前操作。
- 调整浏览器大小后终端不会错行或固定在旧尺寸。
- 切换到记录页再切回时，不会重新创建 Claude 进程。
- 关闭进程后状态明确显示为已退出，并允许启动新进程。
- 未启动 AgentVAST Run 时，普通 Claude 终端不会受到现有工作流 Hook 的阻塞。
