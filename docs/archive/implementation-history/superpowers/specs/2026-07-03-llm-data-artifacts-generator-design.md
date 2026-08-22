# LLM 数据产物生成系统设计

## 概述

设计一个离线 Python 脚本，调用 LLM API 将 `VAST_Challenge_2026_MC2/src/` 中的脚本、数据集、报告文件转换为结构化数据产物（`.analysis.json`），供前端使用。

## 核心功能

- 扫描输入目录中的脚本（`.py`）、数据集（`.json`）、报告（`.json`, `.txt`）文件
- 对每个文件调用 LLM API，生成结构化分析产物
- 智能增量处理：跳过已存在 `.analysis.json` 的文件
- 支持强制覆盖、类型过滤、并发控制

## 设计要点

| 维度 | 选择 | 说明 |
|------|------|------|
| 执行模式 | 离线生成脚本 | 运行一次生成所有产物 |
| 输出目录 | `artifacts_llm/` | 保持源文件相对目录结构 |
| LLM API | `https://hk.coin.hhm.moe` + `gpt-5.5` | 通过环境变量配置 |
| 上下文传递 | 全上下文重传 | 每次调用传入完整上下文 |
| 可视化格式 | ECharts 配置 JSON | 前端用 ECharts 渲染 |
| Schema | 统一结构 + 类型字段 | 三种类型共用基础字段 |
| 执行流程 | 智能增量处理 | 跳过已存在文件 |
| 配置管理 | 环境变量 | `.env` 或直接设置 |
| Prompt 模板 | 外部文件 | `templates/*.txt` |
| 错误处理 | 指数退避 + 失败记录 | `failed_files.txt` |
| 命令行参数 | 完整参数集 | 支持多种控制选项 |

## 目录结构

```
VAST_Challenge_2026_MC2/
├── src/                        # 输入源文件
│   ├── node_01_load_data.py
│   ├── node_01_loaded.json
│   └── ...
├── artifacts_llm/              # 输出产物
│   ├── node_01_load_data.analysis.json
│   ├── node_01_loaded.analysis.json
│   └── ...
├── templates/                  # Prompt 模板
│   ├── script_prompt.txt
│   ├── dataset_prompt.txt
│   └── report_prompt.txt
├── context/                    # 全局上下文（可选）
│   ├── background.md
│   └── step_details.json
└── generate_artifacts.py       # 主脚本
```

## 统一 JSON Schema

### 基础字段（所有类型共享）

```json
{
  "version": "1.0",
  "type": "script | dataset | report",
  "source_file": "node_01_load_data.py",
  "generated_at": "2026-07-03T10:30:00Z",
  "context": {
    "background": "VAST Challenge 2026 MC2 数据分析...",
    "problem": ["问题1", "问题2", "..."],
    "step_details": {...}
  }
}
```

### Script 类型

```json
{
  "type": "script",
  "content": {
    "algorithm_purpose": "算法目标/作用描述",
    "algorithm_logic": {
      "description": "算法逻辑说明",
      "parameters": [
        {"name": "input_path", "description": "...", "type": "string"}
      ],
      "data_flow": "处理数据流程描述"
    }
  }
}
```

### Dataset 类型

```json
{
  "type": "dataset",
  "content": {
    "description": "数据内容简介",
    "input_datasets": [...],    // 这一步的输入数据集
    "output_datasets": [...],   // 这一步的输出数据集
    "visualization": {
      "design_choice": "result_visualization | process_visualization",
      "choice_reasoning": "选择此可视化形式的理由",
      "echarts_config": {...}   // ECharts 配置 JSON
    }
  }
}
```

### Report 类型

```json
{
  "type": "report",
  "content": {
    "problems": [
      {
        "problem": "问题描述",
        "answer": "基于数据的答案",
        "evidence_from_data": [...]  // 引用的具体数据证据
      }
    ],
    "summary": "整体分析摘要"
  }
}
```

## 命令行接口

```bash
python generate_artifacts.py \
  --input src/ \
  --output artifacts_llm/ \
  [--force] \
  [--type script|dataset|report] \
  [--concurrency N] \
  [--context-dir context/]
```

### 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input` | 输入源目录 | `src/` |
| `--output` | 输出产物目录 | `artifacts_llm/` |
| `--force` | 强制覆盖已存在的 `.analysis.json` | `False` |
| `--type` | 只处理特定类型文件 | 全部 |
| `--concurrency` | 并发处理数量 | `4` |
| `--context-dir` | 全局上下文目录 | `context/` |

## 环境变量配置

```bash
LLM_API_BASE_URL=https://hk.coin.hhm.moe
LLM_MODEL=gpt-5.5
LLM_API_KEY=your_api_key_here
```

## Prompt 模板结构

### script_prompt.txt

```
你是一个数据分析专家。请分析以下脚本文件，提取算法信息。

背景：{background}
问题：{problem}
步骤详情：{step_details}

脚本文件：{file_path}
内容：
{file_content}

请生成结构化的算法描述，包括：
1. 算法目标/作用
2. 算法逻辑（参数、数据流）

输出 JSON 格式...
```

### dataset_prompt.txt

```
你是一个数据可视化专家。请分析以下数据集，生成可视化配置。

背景：{background}
问题：{problem}
步骤详情：{step_details}

数据集文件：{file_path}
输入数据集：{input_datasets}
输出数据集：{output_datasets}

数据内容：
{file_content}

请生成：
1. 数据集描述
2. 输入输出数据集内容
3. 可视化配置（ECharts）

注意：
- 优先选择结果数据可视化
- 如需展示数据处理流程，选择流程可视化
- 禁止想象，基于真实数据

输出 JSON 格式...
```

### report_prompt.txt

```
你是一个数据分析报告专家。请分析以下报告，提取关键发现。

背景：{background}
问题：{problem}
步骤详情：{step_details}

报告文件：{file_path}

内容：
{file_content}

请生成：
1. 每个问题的答案
2. 支持答案的数据证据
3. 整体摘要

重要：所有答案必须基于报告内容，禁止添加未支持的推断。

输出 JSON 格式...
```

## 错误处理

1. **指数退避重试**：失败后按 1s、2s、4s、8s 间隔重试，最多 4 次
2. **失败记录**：失败的文件记录到 `failed_files.txt`
3. **部分失败处理**：继续处理其他文件，最终报告失败列表
4. **API 错误分类**：
   - 网络错误：重试
   - 认证错误：立即停止
   - 限流错误：延长退避时间
   - 解析错误：记录失败，跳过

## 执行流程

```
1. 加载配置（环境变量、命令行参数）
2. 扫描输入目录，识别待处理文件
3. 加载全局上下文（background.md, step_details.json）
4. 对每个文件：
   a. 检查是否存在 .analysis.json（未启用 --force 时跳过）
   b. 确定文件类型，选择对应 prompt 模板
   c. 组合完整 prompt（上下文 + 文件内容）
   d. 调用 LLM API
   e. 解析响应，写入 .analysis.json
5. 输出处理报告（成功/失败统计）
```

## 依赖

- `httpx` 或 `requests`：HTTP 请求
- `python-dotenv`：环境变量加载
- `jinja2`：模板渲染（可选）
- `click` 或 `argparse`：命令行参数解析

## 安全考虑

- API Key 不应硬编码在代码中
- 支持通过环境变量或配置文件注入
- 输出文件不应包含敏感信息
- 限制并发数避免过载

## 扩展性

- 支持添加新的文件类型
- 支持自定义 prompt 模板
- 支持不同 LLM provider（通过配置切换）
- 支持插件化的可视化后端
