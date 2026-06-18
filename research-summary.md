# Claude Code 架构研究与 Workflow Tracing 实现方案

## 研究摘要

本报告基于对 Claude Code 本地架构的深入研究，评估并提供了 workflow tracing 的完整实现方案。

---

## 一、关键发现

### 1.1 Claude Code 本地架构

Claude Code 在用户系统上维护完整的会话状态和数据持久化：

| 目录 | 作用 |
|------|------|
| `~/.claude/sessions/` | 实时会话状态映射 (PID -> session_id) |
| `~/.claude/history.jsonl` | 用户输入历史记录 |
| `~/.claude/file-history/` | 文件变更历史 (版本控制) |
| `~/.claude/telemetry/` | 内部事件日志 (缓存统计等) |
| `~/.claude/tasks/` | 任务追踪数据 |
| `~/.claude/plugins/` | MCP 插件系统 |
| `~/.claude/skills/` | 技能系统 |

### 1.2 Hook 系统能力

研究发现 Claude Code 支持的 Hook 事件：

| 事件 | 触发时机 | 可拦截 | 输入数据 |
|------|----------|--------|----------|
| SessionStart | 会话开始 | 否 | session_id, project_path |
| PreToolUse | 工具调用前 | 是 | tool_name, tool_input |
| PostToolUse | 工具调用后 | 否 | tool_name, tool_output |
| UserPromptSubmit | 用户提交 | 是 | user_prompt |
| Stop | 会话停止 | 是 | reason, transcript_path |

### 1.3 参考实现：Hookify 插件

研究分析了 `hookify` 插件（位于 `~/.claude/skills/claude-plugins-official/plugins/hookify/`）：

- 实现了 PreToolUse/PostToolUse/Stop/UserPromptSubmit Hook
- 使用 Python 脚本处理 Hook 输入
- 通过规则引擎匹配模式
- 支持警告和阻止操作

---

## 二、技术路径对比

### 路径1: Hook 系统 (推荐)

**实现方式**: 在 `~/.claude/settings.json` 配置 Hook，调用自定义 Python 脚本

**优势**:
- 实时捕获所有工具调用
- 可获取工具输入/输出
- 支持时间戳计算执行时长
- 可拦截危险操作

**劣势**:
- 无法获取 LLM 响应内容
- Hook 执行时间计入超时

**复杂度**: 中等

### 路径2: 文件监控

**实现方式**: 监控 `~/.claude/` 目录变更，解析 JSON 文件

**优势**:
- 完全非侵入
- 可追溯历史数据

**劣势**:
- 实时性差
- LLM 响应内容有限

**复杂度**: 中等

### 路径3: MCP 服务器

**实现方式**: 自定义 MCP 工具，Claude 主动调用记录

**优势**:
- 标准化集成
- 支持双向通信

**劣势**:
- 依赖 Claude 主动调用
- 可能遗漏数据

**复杂度**: 中等

---

## 三、推荐实现方案

### 3.1 混合架构

**组合**: Hook 系统 (主要) + 文件监控 (补充) + SQLite 存储

```
┌─────────────────┐
│  Claude Code    │
└────────┬────────┘
         │
    ┌────▼────┐
    │  Hooks  │ (PreToolUse, PostToolUse, UserPromptSubmit)
    └────┬────┘
         │
    ┌────▼──────┐
    │  SQLite   │ (traces.db)
    └────┬──────┘
         │
    ┌────▼──────┐
    │  API/Web  │ (可选: 可视化Dashboard)
    └───────────┘
```

### 3.2 数据模型

```sql
sessions (id, started_at, project_path, model, status)
tool_calls (id, session_id, tool_name, tool_input, started_at, completed_at, duration_ms, output_preview, error_message)
user_prompts (id, session_id, prompt_text, timestamp)
```

### 3.3 实现文件清单

| 文件 | 用途 |
|------|------|
| `hooks/pre_tool_use.py` | 捕获工具调用开始 |
| `hooks/post_tool_use.py` | 捕获工具调用结束 |
| `hooks/user_prompt.py` | 捕获用户输入 |
| `storage/trace_db.py` | SQLite 存储层 |
| `mcp-server/trace_server.py` | MCP 查询接口 (可选) |
| `frontend/dashboard.html` | 可视化界面 (可选) |

---

## 四、数据捕获能力

### 可完整捕获

- 用户输入流 (history.jsonl + UserPromptSubmit)
- 工具调用序列 (PreToolUse)
- 工具输入参数 (tool_input)
- 文件变更历史 (file-history)
- 执行时间 (PreToolUse + PostToolUse 时间差)

### 部分捕获

- 工具输出 (PostToolUse，可能截断)
- 错误信息 (telemetry)

### 难以捕获

- LLM 响应内容 (内部处理)
- 思考过程 (redacted)
- Token 消耗 (不完整)

---

## 五、限制与挑战

1. **LLM 响应不可见**: Hook 无法获取 Claude 的原始响应文本
2. **并发处理**: 多工具并发时顺序保证困难
3. **性能影响**: Hook 执行时间影响响应速度
4. **存储设计**: 需处理大量追踪数据

---

## 六、可行性结论

| 维度 | 评级 |
|------|------|
| 技术可行性 | 高 |
| 数据完整性 | 中高 |
| 实时性 | 高 |
| 实施难度 | 中 |
| 维护成本 | 低 |

**结论**: 在 Claude Code 上实现 workflow tracing **完全可行**。

---

## 七、相关文档

- `feasibility-report.md` - 详细可行性评估
- `implementation-guide.md` - 完整实现指南

---

*研究环境: Claude Code 2.1.158 on Windows 11*
*生成时间: 2025-06-15*
