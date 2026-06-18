# Workflow Tracing 实现指南

## 核心实现路径

基于可行性评估，推荐以下实现方案：

---

## 一、Hook系统实现

### 1.1 需要实现的Hook

| Hook | 事件 | 用途 |
|------|------|------|
| PreToolUse | 工具调用前 | 记录调用开始时间、输入参数 |
| PostToolUse | 工具调用后 | 记录结束时间、输出结果 |
| UserPromptSubmit | 用户提交 | 记录用户输入 |

### 1.2 Hook配置位置

在 `~/.claude/settings.json` 中添加：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.claude/opentrace/hooks/pre_tool_use.py",
          "timeout": 5
        }]
      }
    ],
    "PostToolUse": [
      {
        "hooks": [{
          "type": "command", 
          "command": "python3 ~/.claude/opentrace/hooks/post_tool_use.py",
          "timeout": 5
        }]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [{
          "type": "command",
          "command": "python3 ~/.claude/opentrace/hooks/user_prompt.py",
          "timeout": 5
        }]
      }
    ]
  }
}
```

---

## 二、数据存储层设计

### 2.1 SQLite Schema

```sql
-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at INTEGER NOT NULL,
    project_path TEXT,
    model TEXT,
    status TEXT DEFAULT 'active'
);

-- 工具调用表
CREATE TABLE IF NOT EXISTS tool_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_input TEXT,
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    duration_ms INTEGER,
    status TEXT DEFAULT 'running',
    output_preview TEXT,
    error_message TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- 用户输入表
CREATE TABLE IF NOT EXISTS user_prompts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_time ON tool_calls(started_at);
```

### 2.2 存储层接口

```python
# storage/trace_db.py
import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

class TraceDatabase:
    def __init__(self, db_path: str = "~/.claude/opentrace/traces.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(SCHEMA_SESSIONS)
        conn.execute(SCHEMA_TOOL_CALLS)
        conn.execute(SCHEMA_USER_PROMPTS)
        conn.commit()
        conn.close()
    
    def record_session(self, session_id: str, project_path: str, model: str):
        """记录新会话"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO sessions (id, started_at, project_path, model)
            VALUES (?, ?, ?, ?)
        """, (session_id, int(datetime.now().timestamp() * 1000), project_path, model))
        conn.commit()
        conn.close()
    
    def start_tool_call(self, session_id: str, tool_name: str, tool_input: Dict) -> str:
        """开始工具调用"""
        call_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO tool_calls (id, session_id, tool_name, tool_input, started_at, status)
            VALUES (?, ?, ?, ?, ?, 'running')
        """, (call_id, session_id, tool_name, json.dumps(tool_input), int(datetime.now().timestamp() * 1000)))
        conn.commit()
        conn.close()
        return call_id
    
    def complete_tool_call(self, call_id: str, output: str, error: Optional[str] = None):
        """完成工具调用"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            UPDATE tool_calls 
            SET completed_at = ?, 
                duration_ms = ? - started_at,
                status = ?,
                output_preview = ?,
                error_message = ?
            WHERE id = ?
        """, (int(datetime.now().timestamp() * 1000), int(datetime.now().timestamp() * 1000), 
              'completed' if error is None else 'failed', output[:1000], error, call_id))
        conn.commit()
        conn.close()
    
    def record_user_prompt(self, session_id: str, prompt_text: str):
        """记录用户输入"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO user_prompts (id, session_id, prompt_text, timestamp)
            VALUES (?, ?, ?, ?)
        """, (str(uuid.uuid4()), session_id, prompt_text, int(datetime.now().timestamp() * 1000)))
        conn.commit()
        conn.close()
    
    def get_session_traces(self, session_id: str) -> list[Dict]:
        """获取会话的所有追踪数据"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT * FROM tool_calls WHERE session_id = ? ORDER BY started_at
        """, (session_id,))
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
```

---

## 三、Hook实现示例

### 3.1 PreToolUse Hook

```python
#!/usr/bin/env python3
# ~/.claude/opentrace/hooks/pre_tool_use.py
import json
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from storage.trace_db import TraceDatabase

def main():
    try:
        # 读取Hook输入
        input_data = json.load(sys.stdin)
        
        # 提取数据
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})
        session_id = os.getenv("CLAUDE_SESSION_ID", "unknown")
        
        # 存储到数据库
        db = TraceDatabase()
        call_id = db.start_tool_call(session_id, tool_name, tool_input)
        
        # 输出call_id供PostToolUse使用
        print(json.dumps({"call_id": call_id}))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 3.2 PostToolUse Hook

```python
#!/usr/bin/env python3
# ~/.claude/opentrace/hooks/post_tool_use.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from storage.trace_db import TraceDatabase

def main():
    try:
        input_data = json.load(sys.stdin)
        
        # 获取工具输出
        tool_output = input_data.get("tool_output", "")
        error = input_data.get("error")
        
        # 从环境变量获取call_id (需要在PreToolUse传递)
        # 或者从input_data中获取
        call_id = input_data.get("call_id")  # 需要Hook间通信机制
        
        if call_id:
            db = TraceDatabase()
            db.complete_tool_call(call_id, str(tool_output)[:1000], error)
        
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
```

### 3.3 UserPromptSubmit Hook

```python
#!/usr/bin/env python3
# ~/.claude/opentrace/hooks/user_prompt.py
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from storage.trace_db import TraceDatabase

def main():
    try:
        input_data = json.load(sys.stdin)
        prompt_text = input_data.get("user_prompt", "")
        session_id = os.getenv("CLAUDE_SESSION_ID", "unknown")
        
        db = TraceDatabase()
        db.record_user_prompt(session_id, prompt_text)
        
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## 四、MCP服务器 (可选扩展)

### 4.1 暴露查询工具

```python
# mcp-server/trace_server.py
from mcp.server import Server
from storage.trace_db import TraceDatabase

app = Server("opentrace-server")

@app.tool("get_trace_session")
async def get_trace_session(session_id: str) -> dict:
    """获取会话的追踪数据"""
    db = TraceDatabase()
    return {
        "session_id": session_id,
        "traces": db.get_session_traces(session_id)
    }

@app.tool("get_recent_traces")
async def get_recent_traces(limit: int = 10) -> list:
    """获取最近的追踪记录"""
    db = TraceDatabase()
    return db.get_recent_sessions(limit)

if __name__ == "__main__":
    app.run()
```

### 4.2 MCP配置

```json
{
  "mcpServers": {
    "opentrace": {
      "command": "python",
      "args": ["~/.claude/opentrace/mcp-server/trace_server.py"]
    }
  }
}
```

---

## 五、前端可视化 (可选)

### 5.1 简易Dashboard

```html
<!-- frontend/dashboard.html -->
<!DOCTYPE html>
<html>
<head>
    <title>OpenTrace Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/react-flow@11.10.1/dist/umd/index.js"></script>
</head>
<body>
    <div id="root"></div>
    <script>
        const { useState, useEffect } = React;
        const { ReactFlow, Controls } = ReactFlow;

        function TraceDashboard() {
            const [traces, setTraces] = useState([]);
            
            useEffect(() => {
                // Poll for traces
                const interval = setInterval(async () => {
                    const res = await fetch('/api/traces');
                    const data = await res.json();
                    setTraces(data);
                }, 1000);
                return () => clearInterval(interval);
            }, []);

            const nodes = traces.map((t, i) => ({
                id: t.id,
                data: { label: `${t.tool_name} (${t.duration_ms}ms)` },
                position: { x: i * 200, y: 0 }
            }));

            return (
                <div style={{height: '80vh'}}>
                    <ReactFlow nodes={nodes} edges={[]}>
                        <Controls />
                    </ReactFlow>
                </div>
            );
        }

        ReactDOM.render(<TraceDashboard />, document.getElementById('root'));
    </script>
</body>
</html>
```

### 5.2 后端API

```python
# api/server.py
from flask import Flask, jsonify
from storage.trace_db import TraceDatabase

app = Flask(__name__)
db = TraceDatabase()

@app.route('/api/traces')
def get_traces():
    session_id = request.args.get('session')
    if session_id:
        return jsonify(db.get_session_traces(session_id))
    return jsonify(db.get_recent_sessions(20))

if __name__ == '__main__':
    app.run(port=5678)
```

---

## 六、部署清单

### 6.1 文件结构

```
~/.claude/opentrace/
├── hooks/
│   ├── pre_tool_use.py
│   ├── post_tool_use.py
│   └── user_prompt.py
├── storage/
│   ├── __init__.py
│   └── trace_db.py
├── mcp-server/
│   └── trace_server.py (可选)
├── traces.db (自动创建)
└── config.json
```

### 6.2 安装步骤

```bash
# 1. 创建目录
mkdir -p ~/.claude/opentrace/{hooks,storage,mcp-server}

# 2. 复制文件
cp -r hooks/* ~/.claude/opentrace/hooks/
cp -r storage/* ~/.claude/opentrace/storage/

# 3. 更新settings.json
# 添加hooks配置 (见1.2)

# 4. 测试
# 在Claude Code中执行任意工具
sqlite3 ~/.claude/opentrace/traces.db "SELECT * FROM tool_calls"
```

### 6.3 依赖要求

```bash
# Python依赖
pip install mcp  # 如果使用MCP服务器
pip install flask  # 如果需要Web界面
```

---

## 七、故障排查

### 7.1 Hook未触发

- 检查 `settings.json` 中的hooks配置
- 确认Python可执行路径 (`which python3`)
- 查看Hook脚本的执行权限 (`chmod +x hooks/*.py`)

### 7.2 数据未写入

- 检查 `~/.claude/opentrace/` 目录权限
- 确认SQLite数据库可写
- 查看stderr输出 (`2>/tmp/hook.log`)

### 7.3 性能问题

- 减少Hook超时时间 (从5s降到2s)
- 使用异步写入
- 限制输出截断长度

---

*本指南提供了完整实现路径，可根据需求选择性实现*
