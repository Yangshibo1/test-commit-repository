# Claude Code Read 工具参数死循环问题

## 问题概述

在 Windows 11 环境下使用 Claude Code 进行 AI 辅助开发时，曾出现 `Read` 工具调用反复失败的问题。故障表现为：读取普通 Markdown 文本文件时，AI 多次把 PDF 专用参数 `pages` 传入 `Read` 工具，并将其赋值为空字符串 `""`，导致工具持续返回参数校验错误。

典型错误：

```text
Invalid pages parameter: "". Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.
```

## 根因判断

该问题更符合“结构化工具参数惯性复用”问题，而不是项目代码或文件权限问题。

具体表现为：

1. 第一次错误工具调用生成了包含 `pages: ""` 的坏参数结构。
2. 后续即使语言层面已经识别到 `pages` 只适用于 PDF，工具调用层仍继续复用旧参数形状。
3. 用户明确要求停止后，AI 仍多次生成相同错误字段，形成“承诺修正但工具层继续复现”的割裂状态。
4. 通过 Bash/Python 读取文件可以正常工作，说明文件本身、路径和权限不是根因。

## 已排查项

- 用户级 `C:\Users\bryan\.claude\settings.json` 未发现 hooks 或插件配置会改写 `Read` 参数。
- 项目级 `.claude/settings.json` / `.claude/settings.local.json` 不存在。
- 未发现通过 `PreToolUse` / `updatedInput` 自动注入 `pages` 参数的 hook。
- `~/.claude/skills` 不存在。
- `~/.claude/plugins` 中存在官方 marketplace 缓存，但未发现当前项目启用 PDF skill 或相关插件配置。

因此，问题更可能来自当前对话上下文中的坏工具调用模板复用，而不是项目配置或 PDF skill 直接影响。

## 临时绕过方案

当 `Read` 工具出现类似参数死循环时：

1. 不要继续重复调用同一种失败工具参数。
2. 连续失败 3 次后停止重试并询问用户。
3. 改用 Bash/Python 读取普通文本文件，例如：

```bash
PYTHONIOENCODING=utf-8 python - <<'PY'
from pathlib import Path
print(Path('README.md').read_text(encoding='utf-8'))
PY
```

4. 如果必须恢复 `Read` 工具，建议重启 Claude Code 会话，让坏参数模板从上下文中消失。

## 防复发规则

- `pages` 参数只应用于 PDF 文件读取。
- 读取 Markdown、Python、JSON、TXT 等普通文本文件时，不应传入 `pages`。
- 同类工具调用连续失败 3 次后，必须停止重复尝试并向用户确认下一步。
- 对于工具参数校验错误，应改变工具调用形状，而不是只在自然语言中承诺修正。
- 如果工具层无法生成正确参数，应立即切换到等价的 Bash/Python 方案。

## 工程启示

该问题说明，AI Agent 在结构化工具调用阶段可能出现参数形状的惯性复现。自然语言提示并不总能可靠约束工具参数生成，因此工具框架需要更强的状态机、参数校验和负反馈机制，避免同一类 `InputValidationError` 反复触发。

核心结论：Claude Code 的参数死循环暴露了 AI 编程工具在结构化调用鲁棒性上的短板；仅靠模型自纠不足以保证复杂工程场景下的稳定性。
