# AgentVAST 文档索引

完整的产品文档体系，帮助Agent快速上手AgentVAST。

---

## 🚀 快速开始

| 文档 | 用途 | 适合人群 |
|------|------|----------|
| [README.md](../../README.md) | 项目概述和最简示例 | 所有人 |
| [AGENT_GUIDE.md](AGENT_GUIDE.md) | **Agent专用指南** - 检查清单、代码模板、速查表 | ⭐ Agent首先阅读 |
| [QUICKSTART.md](QUICKSTART.md) | 5分钟快速开始 | 快速上手 |

## 📖 详细文档

| 文档 | 内容 | 何时查阅 |
|------|------|----------|
| [API_REFERENCE.md](API_REFERENCE.md) | API速查手册 - 函数、参数、返回值 | 编写代码时 |
| [BEST_PRACTICES.md](BEST_PRACTICES.md) | 最佳实践 - 正确模式、常见错误 | 遇到问题时 |
| [AGENTVAST_GUIDE.md](../../AGENTVAST_GUIDE.md) | 完整使用指南 - 详细说明和示例 | 深入了解时 |

## 🔮 开发规划

| 文档 | 内容 | 适合人群 |
|------|------|----------|
| [development-roadmap.md](../../docs/development-roadmap.md) | **后续开发规划** - 三大重点方向总览 | 开发者、贡献者 |
| [data-recording-design.md](../../docs/data-recording-design.md) | 数据记录方式设计 - API优化、自动化 | 开发者 |
| [agent-guidance-design.md](../../docs/agent-guidance-design.md) | Agent使用引导设计 - 渐进式系统、实时验证 | 开发者、产品设计 |
| [visualization-design.md](../../docs/visualization-design.md) | 可视化系统设计 - 多层次视图、交互探索 | 开发者、前端设计 |

## 🔧 配置和工具

| 文档 | 内容 |
|------|------|
| [.claude/workflows/trace-analysis.yaml](../../.claude/workflows/trace-analysis.yaml) | 工作流定义 |
| [.claude/workflows/trace-analysis-guide.md](../../.claude/workflows/trace-analysis-guide.md) | 工作流指南 |
| [.claude/skills/agentvast-data-analysis.md](../../.claude/skills/agentvast-data-analysis.md) | Skill定义 |

## 💡 示例代码

| 目录 | 内容 |
|------|------|
| [examples/](../../examples/) | 逐步处理示例脚本 |

## 📋 Agent使用流程

1. **阅读** [AGENT_GUIDE.md](AGENT_GUIDE.md)
2. **复制** 代码模板
3. **查阅** [API_REFERENCE.md](API_REFERENCE.md) 了解参数
4. **参考** [BEST_PRACTICES.md](BEST_PRACTICES.md) 避免错误
5. **验证** 使用 `validate_session()` 检查结果

---

## 文档结构图

```
AgentVAST 文档体系
│
├── 🚀 快速开始
│   ├── README.md              - 项目概述
│   ├── agentvast/doc/AGENT_GUIDE.md    - Agent专用指南 ⭐
│   └── agentvast/doc/QUICKSTART.md    - 快速开始
│
├── 📖 详细文档
│   ├── agentvast/doc/API_REFERENCE.md  - API速查手册
│   ├── agentvast/doc/BEST_PRACTICES.md - 最佳实践
│   └── AGENTVAST_GUIDE.md              - 完整指南
│
├── 🔧 配置和工具
│   ├── .claude/workflows/     - 工作流定义
│   └── .claude/skills/        - Skill定义
│
└── 💡 示例代码
    └── examples/               - 示例脚本
```

---

## 常见问题快速解答

| 问题 | 查看文档 |
|------|----------|
| 如何快速开始？ | [AGENT_GUIDE.md](AGENT_GUIDE.md) 或 [QUICKSTART.md](QUICKSTART.md) |
| API参数是什么？ | [API_REFERENCE.md](API_REFERENCE.md) |
| 为什么验证失败？ | [BEST_PRACTICES.md](BEST_PRACTICES.md) |
| 关系方向怎么写？ | [AGENT_GUIDE.md](AGENT_GUIDE.md) #速查表 |
| 完整示例在哪里？ | [examples/](../../examples/) |

---

## 反馈和改进

如果文档有任何不清楚或遗漏的地方，请通过以下方式反馈：
- GitHub Issues
- 更新文档并提交PR
