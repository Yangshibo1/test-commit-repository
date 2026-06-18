# Claude Code Workflow Tracing 可行性评估报告

## 执行摘要

基于对 Claude Code 本地架构的深入研究，评估实现 workflow tracing 的可行性。结论是**可行**，有三种主要技术路径，各有优缺点。

---

## 一、Claude Code 架构发现

### 1.1 关键目录结构

```
~/.claude/
├── sessions/              # 会话状态 (PID映射)
├── history.jsonl          # 用户输入历史
├── file-history/          # 文件变更历史 (按session_id组织)
├── telemetry/             # 内部事件日志
├── tasks/                 # 任务追踪数据
├── plugins/               # MCP插件系统
├── skills/                # 技能系统
└── settings.json          # 配置文件
```

### 1.2 数据捕获能力

| 数据源 | 可捕获内容 | 实时性 | 完整性 |
|--------|------------|--------|--------|
| history.jsonl | 用户输入、时间戳、项目路径 | 低(追加写入) | 高 |
| file-history/ | 文件变更、版本差异 | 中 | 高 |
| sessions/ | 当前会话状态、进程信息 | 实时 | 中 |
| telemetry/ | 内部事件、缓存统计 | 低 | 高 |
| hooks系统 | 工具调用前后、用户提交 | 实时 | 高 |

### 1.3 已有的Hook事件

研究发现的Hook事件类型：

1. **SessionStart** - 会话开始时
2. **PreToolUse** - 工具调用前 (可拦截)
3. **PostToolUse** - 工具调用后
4. **UserPromptSubmit** - 用户提交提示前
5. **Stop** - 会话停止前 (可拦截)

### 1.4 Hook输入数据结构

```json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "...",
    "description": "..."
  },
  "transcript_path": "/path/to/transcript",
  "reason": "...",
  "user_prompt": "..."
}
```

---

## 二、技术路径

### 路径1: Hook系统 + 本地文件存储 (推荐)

**原理**: 通过PreToolUse/PostToolUse Hook捕获工具调用，写入本地数据库/文件

**优势**:
- 实时捕获所有工具调用
- 可捕获工具输入、输出、执行时间
- 不依赖外部服务
- 可扩展为MCP服务器

**劣势**:
- 需要编写Hook脚本
- 需要实现数据存储层
- 无法直接捕获LLM响应内容

**实现复杂度**: 中等

**数据可捕获**:
- 工具调用序列
- 工具输入参数
- 工具执行时间(需PostToolUse时间差)
- 文件变更(通过file-history)
- 用户输入流

---

### 路径2: MCP服务器 + 自定义工具

**原理**: 创建MCP服务器，暴露`trace_*`工具，Claude Code主动调用记录

**优势**:
- 标准化集成
- 可定义自定义追踪工具
- 支持双向通信

**劣势**:
- 需要Claude主动调用(可能遗漏)
- 拦截能力不如Hook
- 依赖MCP协议稳定性

**实现复杂度**: 中等

---

### 路径3: 技能系统(Skills) + 自动化

**原理**: 创建自定义Skill，在特定工作流中自动记录状态

**优势**:
- 用户可控
- 可嵌入业务逻辑
- 结合planning-with-files实现任务追踪

**劣势**:
- 依赖用户主动调用
- 透明度低
- 难以捕获底层操作

**实现复杂度**: 低

---

### 路径4: 文件监控 + 日志解析 (被动方式)

**原理**: 监控`~/.claude`目录变更，解析history.jsonl、telemetry、file-history

**优势**:
- 完全非侵入
- 捕获所有持久化数据
- 可追溯历史会话

**劣势**:
- 实时性差
- 无法捕获内存中数据
- LLM响应内容有限

**实现复杂度**: 中等

---

## 三、数据捕获级别评估

### 3.1 可完整捕获

| 数据类型 | 捕获方式 | 限制 |
|---------|---------|------|
| 用户输入 | history.jsonl / UserPromptSubmit | 无 |
| 工具调用 | PreToolUse Hook | 无 |
| 工具输入 | tool_input字段 | 无 |
| 文件变更 | file-history + Hook | 无 |
| 会话元数据 | sessions/*.json | 无 |
| 执行时间 | PreToolUse + PostToolUse时间差 | 需要两个Hook |

### 3.2 部分捕获

| 数据类型 | 捕获方式 | 限制 |
|---------|---------|------|
| 工具输出 | PostToolUse | 输出可能被截断 |
| 任务节点 | tasks/目录 | 需要主动创建任务 |
| 错误信息 | telemetry/1p_failed_events | 格式不稳定 |

### 3.3 难以捕获

| 数据类型 | 原因 |
|---------|------|
| LLM响应内容 | Claude Code内部处理，不暴露给Hook |
| 内部思考过程 | redact-thinking后不可见 |
| 网络请求细节 | 封装在claude.exe内部 |
| Token消耗 | 部分在telemetry，不完整 |

---

## 四、限制与挑战

### 4.1 技术限制

1. **LLM响应不可见**: Hook无法获取Claude的原始响应文本
2. **输出截断**: PostToolUse的tool_output可能被截断
3. **二进制数据**: 工具输出可能包含二进制(如图像)
4. **并发处理**: 多个工具并发调用时顺序难以保证

### 4.2 架构挑战

1. **Hook执行时间**: Hook执行时间计入Claude超时
2. **错误处理**: Hook崩溃不应阻断Claude
3. **数据一致性**: 多Hook写入同一数据源的竞争
4. **存储设计**: 如何高效存储大量追踪数据

### 4.3 用户体验挑战

1. **性能影响**: Hook可能影响Claude响应速度
2. **隐私敏感**: 追踪可能包含敏感信息
3. **配置复杂**: 用户需要配置Hook系统

---

## 五、具体实现建议

### 5.1 推荐方案: 混合架构

**组合**: Hook系统 + 文件监控 + 简易MCP

**组件**:

```
opentrace/
├── hooks/
│   ├── pre_tool_use.py      # 捕获工具调用开始
│   ├── post_tool_use.py     # 捕获工具调用结束
│   └── user_prompt.py       # 捕获用户输入
├── storage/
│   ├── trace_db.py          # SQLite存储层
│   └── models.py            # 数据模型
├── mcp-server/
│   └── trace_server.py      # MCP服务器(可选)
└── frontend/
    └── dashboard.html       # 可视化(可选)
```

### 5.2 数据模型设计

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    started_at INTEGER,
    project_path TEXT,
    status TEXT
);

CREATE TABLE tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    tool_name TEXT,
    tool_input TEXT,
    started_at INTEGER,
    completed_at INTEGER,
    duration_ms INTEGER,
    success BOOLEAN,
    output_preview TEXT
);

CREATE TABLE user_prompts (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    prompt_text TEXT,
    timestamp INTEGER
);
```

### 5.3 Hook示例

```python
#!/usr/bin/env python3
# hooks/pre_tool_use.py
import json
import sys
import sqlite3
from datetime import datetime

DB_PATH = "~/.claude/opentrace.db"

def main():
    data = json.load(sys.stdin)
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input", {})
    
    # 存储工具调用开始
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO tool_calls 
        (id, session_id, tool_name, tool_input, started_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        generate_id(),
        os.getenv("CLAUDE_SESSION_ID"),
        tool_name,
        json.dumps(tool_input),
        int(datetime.now().timestamp() * 1000)
    ))
    conn.commit()
    
    return {}

if __name__ == "__main__":
    main()
```

### 5.4 部署步骤

1. **初始化存储**
   ```bash
   mkdir -p ~/.claude/opentrace
   python init_db.py
   ```

2. **安装Hook**
   ```bash
   cp hooks/* ~/.claude/opentrace/
   # 更新settings.json添加hooks配置
   ```

3. **验证捕获**
   ```bash
   # 在Claude Code中执行工具
   # 检查数据库
   sqlite3 ~/.claude/opentrace.db "SELECT * FROM tool_calls"
   ```

### 5.5 前端可视化

建议使用React Flow + WebSocket:

- 后端: SSE或WebSocket推送实时更新
- 前端: React Flow渲染任务图
- 数据: 从opentrace.db读取

---

## 六、可行性结论

| 维度 | 评级 | 说明 |
|------|------|------|
| 技术可行性 | 高 | Hook系统成熟，数据可访问 |
| 数据完整性 | 中高 | 工具调用完整，LLM响应有限 |
| 实时性 | 高 | Hook实时触发 |
| 实施难度 | 中 | 需要Python开发，但不复杂 |
| 维护成本 | 低 | 一旦部署，无需频繁维护 |

**最终结论**: 在Claude Code上实现workflow tracing是**完全可行**的。推荐使用Hook系统作为主要数据捕获方式，辅以文件监控获取补充数据。

---

## 七、下一步行动

1. **MVP验证**: 实现PreToolUse/PostToolUse Hook
2. **数据层**: SQLite存储 + 查询API
3. **可视化**: 简易Web dashboard
4. **测试**: 在真实工作流中验证
5. **优化**: 性能调优和错误处理

---

## 八、参考资料

- Claude Code hooks系统: `~/.claude/skills/claude-plugins-official/plugins/hookify`
- Hook数据格式: PostToolUse输入JSON结构
- 会话存储: `~/.claude/sessions/`和`history.jsonl`
- 技能系统: `~/.claude/skills/`目录下的SKILL.md格式

---

*报告生成时间: 2025-06-15*
*研究环境: Claude Code 2.1.158 on Windows 11*
