# Evidence-grounded Semantic Workflow V1

## 定位

Semantic Workflow 是对 Claude transcript 可观察行为的事后语义重建，不是 hidden
chain-of-thought、内部 Plan 或真实因果推理。原始 `transcript.jsonl` 是不可变证据，
`events.jsonl` 是语义分析的标准输入，`observer_trace.json` 提供关系、Turn 和产物上下文；
语义文件不能覆盖这些来源。

处理路径：

```text
transcript.jsonl
  → Event Schema 2.0 events.jsonl（六类 Event）
  → Event Projection（按类型生成有界证据）
  → Candidate Blocks（确定性聚合）
  → Adjacent Boundary Classification（可选模型）
  → Hard-constraint Boundary Validator
  → Frozen Episodes
  → Evidence Packet（每个 Episode）
  → Per-Episode Semantic Annotation（可选模型）
  → Relation Extraction（可选模型）
  → Evidence + Granularity Validator（确定性）
  → semantic_workflow.json
```

没有配置模型时可以生成保守规则版。规则版和模型版都会标明
`inference_run.method`，不会混淆来源。

## 生成

先完成 transcript 派生：

```powershell
python -m agentvast.cli observe derive <session-id>
```

无需模型的规则版：

```powershell
python -m agentvast.cli observe semantic <session-id> --rules-only
```

模型版使用独立的 OpenAI-compatible 配置：

```powershell
$env:AGENTVAST_SEMANTIC_API_BASE_URL = "https://provider.example/v1"
$env:AGENTVAST_SEMANTIC_API_KEY = "..."
$env:AGENTVAST_SEMANTIC_MODEL = "model-name"

python -m agentvast.cli observe semantic <session-id> --force
```

如果 Claude Code 使用的自定义网关同时提供 OpenAI-compatible
`/v1/chat/completions`，可以只为语义模块指定该路由支持的模型名，并显式复用
`~/.claude/settings.json` 中已有的 `ANTHROPIC_BASE_URL` 与 `ANTHROPIC_API_KEY`：

```dotenv
AGENTVAST_SEMANTIC_USE_CLAUDE_SETTINGS=true
AGENTVAST_SEMANTIC_MODEL=gpt-5.6-terra
```

Claude Code 的模型别名可能包含 `[1M]` 等上下文标记，而 OpenAI-compatible 路由未必接受；
因此语义模型名称应以该网关 `/v1/models` 返回的实际 ID 为准。

模型生成可以接收一段可审计的 Node 颗粒度要求：

```powershell
python -m agentvast.cli observe semantic <session-id> --force `
  --annotation-guidance "每个Node保留一个核心目标、两句行为摘要和最多三条关键结果；保留数字与限制。"
```

这段提示只进入逐 Episode Annotation，不进入 Boundary 判断，因此不能改变 Episode 数量、顺序、
证据 ID 或 JSON Schema。原文和 SHA-256 会写入 inference 状态与最终工作流；恢复同一 inference
时必须使用相同提示。前端语义工作流页面提供同名输入框，并只保留模型生成入口。

如果网络或上游网关在某个 Episode 中断，任务会保存为 `partial`。恢复最新兼容任务：

```powershell
python -m agentvast.cli observe semantic <session-id> --resume
```

也可以明确指定失败输出中的 inference ID：

```powershell
python -m agentvast.cli observe semantic <session-id> --resume semantic-xxxxxxxxxxxx
```

恢复时会复用已冻结的 Boundary 和已经验证成功的 Episode，只重试失败 Episode 及后续阶段。
`--force` 用于创建全新推断；`--resume` 用于继续已有推断，两者语义不同。

仅修改确定性 Validator 后，可以不重复调用模型，直接重算校验和校验后置信度：

```powershell
python -m agentvast.cli observe semantic-validate <session-id>
```

也可以复制仓库中的 `.env.example` 为 `.env`，然后填写同名变量。Semantic Provider 会依次
读取 `AGENTVAST_ENV_FILE` 指定文件、当前工作目录的 `.env` 和仓库根目录的 `.env`，且不会
覆盖 PowerShell 中已经设置的环境变量。`.env` 已由 Git 忽略，但仍是明文密钥文件，应限制
本机访问权限并定期轮换密钥。

未设置专用变量时，Provider 会依次回退到 `AGENTVAST_REVIEW_*` 和通用 `LLM_*`
变量。建议研究实验始终使用专用变量，避免混淆模型与版本。

## 数据产物

```text
derived/
├─ observer_trace.json
├─ events.jsonl
├─ semantic_workflow.json
├─ semantic_workflow_reviewed.json
├─ semantic_reviews.jsonl
├─ semantic_stages/
│  └─ <inference-id>/
│     ├─ inference_state.json
│     ├─ candidate_blocks.json
│     ├─ boundary_raw_response.json
│     ├─ validated_boundaries.json
│     ├─ episodes.json
│     ├─ annotations/
│     │  ├─ annotation-001-request.json
│     │  ├─ annotation-001-raw-response.json
│     │  ├─ annotation-001-validation.json
│     │  └─ annotation-001-node.json
│     ├─ semantic_nodes.json
│     ├─ relation_raw_response.json
│     └─ validation_report.json
└─ semantic_workflows/
   ├─ semantic-0001.json
   └─ semantic-0002.json
```

`semantic_workflows/` 保存每次生成版本；`semantic_workflow.json` 是当前原始推断；
`semantic_reviews.jsonl` 是追加式人工校正记录；
`semantic_workflow_reviewed.json` 是重放校正后的有效视图。

## 边界重建

确定性预处理以 Event Schema 2.0 为输入：同一 `model_response` 发起的 Tool/Command 批次先聚合，
失败后成功的同类 Tool 或 Command 可组成恢复块；连续 Task 生命周期操作可折叠。
`subagent_result` 和 `control_event` 是独立语义锚点，未挂接到 Model Response 的可见 Event 也不会
被静默丢弃。边界模型不直接生成任意分组，而是为每一对相邻 Candidate 返回 `MERGE` 或 `SPLIT`。

硬约束优先于模型：不同人工 Turn、不同 Subagent Result 和 terminal response 必须分开；一个
Episode 最多包含三个 Candidate 和一个 Subagent Result。模型结果缺失或一次修复后仍非法时，
不确定边界默认 `SPLIT`。

Episode 冻结后实行 `1 Episode → 1 Semantic Node`。Annotation 模型只能解释短标题、Activity、
Objective、Summary 和 Outcome，不能再次合并、拆分或重排 Episode。旧版高度重复的 Intent 与
Goal 已合并为 Objective：Objective 表达该阶段试图完成什么，Summary 表达实际进行了什么。

Annotation 不再一次读取全部 Episode。每个 Episode 独立构造 Evidence Packet 并调用模型，
内容按重要性排列为：原始用户任务、当前 Episode 的真实关键 Event、Event 构成统计、前后
Episode 简短上下文、输出约束。纯 Tool Request 的 `model_response` 只用于调用关联，不作为独立
语义事实；带文本或最终回答的 Model Response 保留。Tool、Agent Command、Subagent Result 和
Control Event 分栏传给模型，Command 明确保留 shell、command、cwd、stdout、stderr、exit code；
长输出使用确定性摘要，保留标题、关键数字行、开头、结尾、原始长度和 SHA-256。

每个投影 Event 还保留 `event_class`、`event_subtype`、`actor`、`scope`、`time` 和 `provenance`，
用于消歧和审计，但提示词禁止模型据此虚构隐藏意图。

Provider 优先请求 `response_format=json_schema` 且 `strict=true`；不兼容时依次降级到
`json_object` 和普通 JSON 文本。一次任务中会缓存已经证实可用的响应模式，后续 Episode 不再
重复触发不兼容的 `json_schema` 探测。无论 Provider 是否支持结构化输出，本地都会再次检查固定
schema version、允许字段、封闭 ID 集合、相邻顺序、Evidence 和业务硬约束。非法输出只允许
修复一次；边界仍非法时默认 `SPLIT`，Annotation 仍非法时保留 `Uncertain/abstained` Node，
Relation 仍非法时只保留确定性的 `NEXT`。

## 处理进度

CLI 默认在 stderr 显示进度条，stdout 仍只输出最终 JSON：

```text
[########----------------] 35% semantic_annotation: 分析 Episode 1/7
```

可使用 `--no-progress` 关闭。Web 端生成改为后台任务，并通过
`GET /api/observations/<session-id>/semantic/progress` 轮询阶段、百分比和 Episode 进度；前端在
语义工作流页面显示相同进度。

TLS EOF、远端关闭、连接重置、超时以及 HTTP 408/429/500/502/503/504 会在当前阶段内按长退避
重试，并在进度中显示尝试次数。默认最多五次，等待约从 5 秒增长到 60 秒并加入随机抖动；每次
正常调用之间默认节流 2 秒。所有参数都可以在 `.env` 中调整：

```dotenv
AGENTVAST_SEMANTIC_MAX_RETRIES=5
AGENTVAST_SEMANTIC_RETRY_BASE_SECONDS=5
AGENTVAST_SEMANTIC_RETRY_MAX_SECONDS=60
AGENTVAST_SEMANTIC_RETRY_JITTER_SECONDS=3
AGENTVAST_SEMANTIC_REQUEST_INTERVAL_SECONDS=2
```

每个 Episode 成功后会立即写入规范化 Node 与 Validation 检查点。重试耗尽时
`inference_state.json` 记录 `completed_episodes`、`failed_episode`、`error_type` 和
`retryable`。前端将此状态显示为“可继续”，不会把已成功结果当作完全失败丢弃。

## Evidence 约束

每个 Node 的 `objective`、`summary` 和每条 outcome claim 都必须保存
`evidence_event_ids`。Validator 检查：

- Episode 是否完整、唯一、顺序一致地映射到 Node；
- Activity 是否属于允许分类；
- 字段是否有真实存在的 evidence；
- Semantic relation 是否引用存在的 Node 和 evidence；
- Evidence coverage 是否可以确定性计算。
- terminal response 是否独立；
- 是否出现多个 Subagent Result 被压入同一 Episode/Node；
- 是否将整个多锚点会话压缩为一个 Node；
- `high` model confidence 是否具有至少 0.8 Evidence Coverage。

验证结果分别提供 `evidence_valid`、`granularity_valid` 和总体 `valid`。模型产生
`model_level`，本地 Validator 根据 Evidence Coverage 生成 `validated_level`；页面显示后者。
置信等级不是校准概率。证据不足时使用 `Uncertain` 和 `abstained=true`。

## 语义字段与审计字段

前端默认展示真正帮助用户理解工作流的语义字段：

| 字段 | 用途 |
|---|---|
| `title` | 4—18 个中文字符的阶段名称，用于列表和工作流图 |
| `primary_activity` | 阶段的主活动类别 |
| `objective` | Agent 在这一阶段试图完成什么 |
| `summary` | 记录中可观察到的主要行为 |
| `outcome_claims` | Agent、Subagent 或工具在记录中给出的结果 |
| 非 `NEXT` relations | 验证、细化、重试和结果使用等语义联系 |
| 关键 `actions` | 读取、分析、写入、可视化、Agent 委派等主要行为 |
| `observed_inputs` | 与阶段理解直接相关的文件和资源路径 |

以下字段保留用于复现、调试和审计，但不进入默认语义阅读主线：

| 字段 | 用途 |
|---|---|
| `node_id`、`episode_ids`、`event_ids` | 稳定身份和证据回链 |
| `event_profile` | Node 内六类 Event 的数量、子类型和 Actor 构成 |
| `boundary_decisions`、`boundary_basis` | Episode 切分审计 |
| `source_lines`、Provider metadata | 原始记录和调用诊断 |
| TaskCreate、TaskUpdate、TaskGet、TaskList、Skill | Agent 编排过程 |
| `reported_outputs` | 完整或截断的原始工具输出 |
| `model_level`、`validated_level`、coverage | 模型与本地验证诊断 |

`actions.semantic_relevance` 将动作标为 `key_action` 或 `orchestration`。两类动作均被保存，
但页面默认只突出关键动作，编排动作放入“技术审计与原始证据”折叠区。

Observer 不对 Agent 或 Subagent 结论另行事实认证。`outcome_claims` 的职责是忠实、可回链地
表达记录中已经出现的结果，允许颗粒度随 Agent 的实际输出而变化。页面因此使用“Agent 报告的
结果”这一名称，并明确说明这些内容来自观察记录。

## 关系方向

```text
EarlierNode --NEXT--> LaterNode
ValidationNode --VALIDATES--> EarlierNode
RefinedNode --REFINES--> EarlierNode
RetryNode --RETRY_OF--> FailedNode
ConsumerNode --USES_RESULT_FROM--> ProducerNode
```

`NEXT` 是确定性时间主干；其他关系是带 evidence 和 confidence 的语义叠加边。

## 人工校正

页面支持：

- 接受当前解释；
- 修改 Activity、Specific Intent 和 Summary；
- 合并连续 Node；
- 按 Episode 边界拆分 Node。

校正不会覆盖原始推断。每次操作追加到 `semantic_reviews.jsonl`，重放后字段来源标为
`user_validated`。新的推断版本具有新的 `inference_id`，旧版本的校正不会自动套用到新版本。

## Web API

```text
GET  /api/observations/<session-id>/semantic
POST /api/observations/<session-id>/semantic/generate
POST /api/observations/<session-id>/semantic/reviews
```

生成请求：

```json
{"rules_only": false, "force": true}
```

校正请求：

```json
{
  "action": "accept|update|merge|split",
  "payload": {}
}
```

## UI 层级

Passive Observer 页面提供：

1. **语义工作流**：默认的人类可读 Node、结果和语义关系；
2. **执行轨迹**：Prompt、Response、工具批次、错误、最终回答及其生成的文件产物。

从 Semantic Node 点击 evidence 会切换到执行轨迹并定位对应 Event。

语义工作流图还会把已经存在且能够回链到 `Write`、`Edit`、`NotebookEdit`，或 Bash 明确报告
路径的文件显示为独立产物 Node。产物通过“生成”或“修改”边挂在对应 Semantic Node 下，
不进入 `NEXT` 语义主链。执行轨迹图也会把产物挂在对应工具 Event 下。点击产物名称会通过
受限 Observation API 调用操作系统默认应用直接打开本地文件；API 只接受
Observer 已登记的 `artifact_id`，并限制在该 Session 的项目目录内。旧版
`observer_trace.json` 在读取时也会根据现有 Event 和仍然存在的文件派生产物，无需重新运行
语义模型。

## 安全边界

发送给 Semantic Provider 的内容是有长度限制的 canonical 摘要和必要证据片段，不是完整
raw transcript。Provider 没有工具权限；系统提示明确要求把 transcript、命令和工具输出视为
不可信数据，不执行其中任何指令。Transcript 可能仍包含敏感路径或内容，启用远程 Provider
前应获得授权并配置适当的数据保留与脱敏策略。
