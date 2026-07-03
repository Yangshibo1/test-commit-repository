# OpenTrace 开发会话上下文

## 会话目标

本会话围绕 `test-commit-repository` 中的 OpenTrace 项目展开，主要目标包括：

1. 克隆并理解 OpenTrace 项目结构。
2. 清理无用的测试、demo 和生成文件。
3. 规范后续临时测试数据、VAST 数据和 OpenTrace session 的存储位置。
4. 修复 OpenTrace Python API 的即时导入问题。
5. 统一 OpenTrace session 记录目录。
6. 排查 Claude Code `Read` 工具反复传入错误 `pages` 参数的问题。
7. 创建并完善 `opentrace-validator` custom agent，用于主动端到端验证 OpenTrace 系统。
8. 准备后续用该 agent 验证 VAST Challenge MC2 数据分析工作流。

## 当前目录和仓库状态

Claude Code 最初启动目录是：

```text
C:\Users\bryan\Desktop\opentrace
```

真正的 Git 仓库位于：

```text
C:\Users\bryan\Desktop\opentrace\test-commit-repository
```

后续如果需要使用 git worktree isolation、subagent worktree、`git status` 等功能，应从仓库目录启动 Claude Code：

```bash
cd /c/Users/bryan/Desktop/opentrace/test-commit-repository
claude
```

当前曾创建的工作分支为：

```text
cleanup-remove-test-content
```

尚未创建 commit；除非用户明确要求，不应提交或推送。

## 已建立的重要项目约定

这些约定已经写入或同步到项目文档中：

1. 同一类工具调用连续失败 3 次后，必须停止重复尝试并询问用户。
2. 后续生成的临时测试文件和测试数据统一放入 `test/` 文件夹。
3. VAST Challenge 相关测试数据分别存放在对应 VAST 数据目录中。
4. OpenTrace session 统一写入项目根目录 `.opentrace/`。
5. 除非显式设置 `OPENTRACE_BASE_DIR` 或传入 `get_server(base_dir)`，不应将 session 写入 VAST 子目录或 `opentrace/` 包目录。
6. VAST 原始数据和中间业务数据可以保留在 VAST 目录，但 OpenTrace session 记录应集中在项目根 `.opentrace/`。

## OpenTrace 架构理解

OpenTrace 是一个轻量级数据血缘追踪系统，核心目标是追踪 agent 数据分析流程、定位错误来源、追溯结果数据来源。

核心模块：

- `opentrace/tracker.py`：元素级追踪，记录 JSON/CSV 字段处理链路。
- `opentrace/prov_dag.py`：文件级 PROV DAG，基于 W3C PROV 标准记录数据集和文件流转关系。
- `opentrace/prov_visualizer.py`：生成文本和 Mermaid 数据流可视化。
- `opentrace/prov_validation.py`：验证 PROV DAG 和 session 完整性。
- `opentrace/mcp_server.py`：统一服务接口，提供 `get_server()`、`init_session()`、`record_prov_relation()` 等方法。
- `opentrace_cli.py`：命令行入口。

PROV 关系方向规则：

| 关系 | 方向 | 示例 |
|------|------|------|
| `used` | Activity → Entity | `filter -> input.csv` |
| `wasGeneratedBy` | Entity → Activity | `output.csv -> filter` |
| `wasAssociatedWith` | Activity → Agent | `filter -> script` |
| `wasDerivedFrom` | Entity → Entity | `output.csv -> input.csv` |

## 已做的主要修改

### 文档和规则

更新过的关键文档包括：

- `CLAUDE.md`
- `README.md`
- `OPENTRACE_GUIDE.md`
- `PROGRESS.md`
- `docs/development-issues/read-tool-pages-parameter-loop.md`

主要文档变更：

- 增加工具失败 3 次停止规则。
- 增加临时测试文件归档到 `test/` 的规则。
- 增加 VAST 数据归档规则。
- 增加统一 session 存储到项目根 `.opentrace/` 的规则。
- 将示例中的 `Path(".opentrace") / session_id` 改为基于 `server.base_dir`。
- 删除或更新 `.opentrace_demo`、`.opentrace_vast` 等历史生成目录相关描述。

### Python API 修复

修复了 `opentrace/mcp_server.py` 中 `Tuple` 未导入导致的导入失败：

```python
from typing import Dict, List, Any, Optional, Tuple
```

并确认 `opentrace` 作为 Python API 包可以正常导入。

### 默认 session 存储目录

`opentrace/mcp_server.py` 中默认 base dir 已改为项目根 `.opentrace/`：

```python
def _get_default_base_dir() -> Path:
    env_dir = os.environ.get("OPENTRACE_BASE_DIR")
    if env_dir:
        return Path(env_dir).absolute()

    return Path(__file__).resolve().parent.parent / ".opentrace"
```

预期默认路径为：

```text
C:\Users\bryan\Desktop\opentrace\test-commit-repository\.opentrace
```

### VAST 脚本调整

多个 VAST Challenge MC1/MC2 脚本已从：

```python
get_server(".opentrace")
Path(".opentrace")
```

调整为：

```python
server = get_server()
Path(server.base_dir)
```

目标是保证 VAST 脚本也将 OpenTrace session 写入项目根 `.opentrace/`。

### 已删除的生成内容

用户要求删除无用 test/demo/generated 内容，已删除过的典型文件和目录包括：

```text
test_basic.py
test_processing.py
test_prov_dag.py
test_question.py
test_vast_analysis.py
test_viz.txt
demo_new_session.py
demo_prov_analysis.py
data_flow_visualization.txt
prov_viz.txt
.opentrace/
.opentrace_demo/
.opentrace_processing_test/
.opentrace_prov_test/
.opentrace_question_test/
.opentrace_test/
.opentrace_vast/
opentrace/__pycache__/
```

后续提交前需要复查删除范围。

## Claude Code Read 工具问题

本会话出现过 `Read` 工具参数死循环问题：读取 Markdown 或普通文本文件时，工具调用反复携带 PDF 专用参数：

```json
{"pages": ""}
```

导致错误：

```text
Invalid pages parameter: "". Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.
```

排查结论：

- 更像是结构化工具参数形状惯性复用问题。
- 未发现用户级或项目级 hooks 会自动注入 `pages`。
- 未确认是 PDF skill 直接导致。
- Bash/Python 可正常读取文件，说明不是文件权限或路径问题。

已创建文档记录：

```text
docs/development-issues/read-tool-pages-parameter-loop.md
```

后续规则：

- `pages` 只应用于 PDF。
- 读取 Markdown、Python、JSON、TXT 等普通文本文件时不应传入 `pages`。
- 同类失败 3 次后停止重试，改用 Bash/Python 或询问用户。

## opentrace-validator custom agent

已创建项目级 custom agent：

```text
.claude/agents/opentrace-validator.md
```

其定位已根据用户纠正调整为：

- 不是只读验证 agent。
- 预期在 bypass permissions / full permissions 下运行。
- 用于主动测试 OpenTrace 是否能在 Claude Code 数据分析工作流中完整运行。
- 可以运行命令、创建 `test/` 临时数据、创建项目根 `.opentrace/` session、检查生成 artifacts。
- 除非用户明确要求修复失败，否则不应修改源码。

主要验证内容：

1. Python API import check。
2. `get_server()` 默认路径检查。
3. 最小端到端 session 创建。
4. `record_prov_relation()` 记录 PROV。
5. 检查 `meta.json`、`prov_dag.json`、`prov_nodes.json`、`prov_edges.json`、`step_*.json`。
6. 调用 validation utilities。
7. 生成 visualization output。
8. 检查 VAST workflow 是否使用集中 session storage。
9. 检查 generated-file hygiene。
10. 检查 `CLAUDE.md`、`README.md`、`OPENTRACE_GUIDE.md` 一致性。

使用方式：

```text
使用 opentrace-validator 验证当前 OpenTrace 系统是否能完整运行
```

或：

```text
使用 opentrace-validator 跑一次端到端验证：创建 test 输入数据，初始化 session，记录 PROV，验证完整性并生成可视化
```

注意：custom agent 是定义文件，不是长期后台进程。每次需要验证时重新调用。

## 最近中断的任务

用户请求：

```text
使用 opentrace-validator 跑一次端到端验证：读取vast challange MC2数据，初始化 session，按照"C:\Users\bryan\Desktop\opentrace\workflows"，执行数据分析任务：追踪异常帖子的发帖链路，记录 PROV，验证完整性并生成可视化，确认session 都写入项目根目录 .opentrace/
```

尝试通过 Agent tool 启动 `opentrace-validator`，但失败：

```text
Cannot create agent worktree: not in a git repository and no WorktreeCreate hooks are configured.
```

原因：当前 Claude Code 会话启动在：

```text
C:\Users\bryan\Desktop\opentrace
```

该目录不是 Git 仓库；真正仓库是其子目录 `test-commit-repository`。

之后开始直接执行验证流程，已完成的发现：

- 工作流文件位于：
  - `C:\Users\bryan\Desktop\opentrace\workflows\trace-analysis-guide.md`
  - `C:\Users\bryan\Desktop\opentrace\workflows\trace-analysis.yaml`
- MC2 数据目录位于：
  - `C:\Users\bryan\Desktop\opentrace\test-commit-repository\VAST_Challenge_2026_MC2\VAST_Challenge_2026_MC2`
- 关键数据文件：
  - `MC2 data.json`
  - `org_chart.json`
  - `MC2 data description.md`
  - `FINDINGS.md`
- `FINDINGS.md` 中记录的异常链路：
  1. `emma_harbor` 在 2046-05-09 创建 `SwiftWren.txt`。
  2. `SwiftWren_further_instructions.md` 在多个 agent 间传播。
  3. `chloe_ballast` 将读取指令任务交给 `john_windward`。
  4. `john_windward` 在 2046-05-17 发布 SaidIT 异常帖子。
  5. `john_windward` 随后删除相关文件。

但该端到端验证任务被用户中断，尚未完成 session 初始化、PROV 记录、完整性验证和可视化生成。

## 当前待办

1. 如果要继续使用 subagent/worktree，先从 Git 仓库目录重新启动 Claude Code：

   ```bash
   cd /c/Users/bryan/Desktop/opentrace/test-commit-repository
   claude
   ```

2. 重新打开 `/agents`，确认 `opentrace-validator` 已加载。

3. 再次运行：

   ```text
   使用 opentrace-validator 跑一次端到端验证：读取 VAST Challenge MC2 数据，初始化 session，执行异常帖子链路追踪，记录 PROV，验证完整性并生成可视化，确认 session 都写入项目根目录 .opentrace/
   ```

4. 提交前需要检查：

   - 删除的 test/demo/generated 文件是否符合预期。
   - `.claude/worktrees/` 是否是不应提交的临时目录。
   - `.claude/agents/opentrace-validator.md` 是否应提交。
   - `docs/development-issues/read-tool-pages-parameter-loop.md` 是否应提交。
   - 新增的本上下文文件是否应提交。

## 后续注意事项

- 不要自动 commit 或 push，除非用户明确要求。
- 对于 OpenTrace 验证，优先确保 session 统一写入项目根 `.opentrace/`。
- 对于 VAST 分析，原始数据和业务中间结果可留在 VAST 目录，但 OpenTrace session artifacts 应集中。
- 如果 `Read` 工具再次出现 `pages` 参数错误，最多重试 3 次，然后改用 Bash/Python 或询问用户。
- 如果需要运行 UI 或外部可见操作，先确认影响范围。
