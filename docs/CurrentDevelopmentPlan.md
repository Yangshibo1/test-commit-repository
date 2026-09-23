# AgentVAST 当前开发计划与会话交接

更新时间：2026-09-23

## 当前工作基线

- 本地项目：`test-commit-repository-agentvast-9-15-latest`
- Git 分支：`agentvast-9-15-latest`
- Passive Observer 示例 Session：`d04a523c-84b7-474f-a28f-b5b964d59ac9`
- 当前研究范围：优先优化被动观察链路，暂不扩展主动执行或干预能力。
- 原始 transcript 保持不可变；派生数据、语义工作流和前端展示均可重新生成。

## 已确认的数据设计

Event 是系统最小事实单元。Transcript 经过确定性聚合后形成六类 Event：

1. `user_prompt`
2. `model_response`
3. `tool_execution`
4. `command_execution`
5. `subagent_result`
6. `control_event`

约束与取舍：

- `assistant_message` 已合并进 `model_response`。
- 只记录 Agent 发起的命令；用户手动输入的本地命令不进入 Workflow Event。
- 普通系统生命周期记录进入 `telemetry`，只有改变执行流程的记录形成 `control_event`。
- `derived/events.jsonl` 是语义分析、关系推断和可视化的标准 Event 输入。
- `canonical_events.jsonl` 仅作为采集、合并和关联阶段的内部中间文件。
- 旧的 Event 关系暂时保留，本阶段不扩大关系类型集合。

Event Schema 2.0 的公共信息包括：`event_class`、`event_type`、`event_subtype`、
`actor`、`scope`、`time`、`provenance`、状态、摘要、Payload 和 Evidence 回链。

## 当前语义分析链路

语义处理器版本为 `0.6.0`，输出 Schema 为 `semantic-workflow/0.4`。

```text
transcript.jsonl
  -> events.jsonl (Event Schema 2.0)
  -> Event 类型化证据投影
  -> Candidate Blocks
  -> 相邻边界判断
  -> Frozen Episodes
  -> 逐 Episode AI 语义标注
  -> Semantic Node 关系提取
  -> Evidence 与粒度校验
  -> semantic_workflow.json
```

当前实现重点：

- AI 输入严格区分 Tool、Agent Command、Model Response、Subagent Result 和 Control Event。
- Command 证据保留 shell、command、cwd、stdout、stderr 和 exit code。
- 每个 Candidate、Episode 和 Semantic Node 包含 `event_profile`，用于记录 Event 类型构成。
- 未挂接到 Model Response 的可见 Event 不会被静默丢弃。
- Command 重试可以参与失败恢复阶段识别。
- `semantic-workflow/0.2` 和 `0.3` 可在内存中适配到 `0.4`，不重写历史证据。

示例 Session 当前统计：

- 源 Events：110
- 关键语义 Events：62
- Candidate Blocks：38
- Command Candidates：17
- 未覆盖关键 Event：0

## 当前前端设计

- 语义工作流以 Semantic Node 为主干。
- 数据集和中间产物作为侧挂文件节点，不推动主干 Node 横向偏移。
- 文件节点只展示最终文件名，并提供本地打开入口。
- 执行轨迹和语义工作流均能展示数据产物。
- 语义 Node 展示 Event、Tool、Command、Subagent 构成。
- Inspector 区分 Tool Execution、Agent Command、Subagent Result 和 Control Event，并可回到原始 Event 证据。
- 旧语义文件缺少 `event_profile` 时，前端从当前 `observer_trace.json` 回算统计。

## 当前验证状态

- Observer 与 CLI 回归测试：33 项通过。
- 前端 TypeScript 检查与生产构建通过。
- 示例 Session 的 110 条 Event 均进入 Candidate 审计统计，62 条关键 Event 无遗漏。
- 最近一次真实 AI 重建在 Boundary 阶段遭遇上游 HTTP 429；旧的 18 Node 模型结果未被覆盖。

## 下一阶段计划

1. 上游额度恢复后，重新生成并人工检查 `semantic-workflow/0.4` 的真实模型结果。
2. 为不同数据分析任务构造多样化 Transcript/Event 数据集，验证 Episode 颗粒度稳定性。
3. 重点测试循环、失败重试、Fallback、多 Tool 批次和 Subagent 场景。
4. 在 Event 稳定后再扩展条件关系推断，例如 `RETRY_OF`、`RECOVERS_FROM`、
   `FALLBACK_FROM`、`PRODUCES_ARTIFACT`、`CONSUMES_ARTIFACT` 和 `VALIDATES_ARTIFACT`。
5. 关系推断结果必须携带 Evidence、推断来源和置信等级，不能把时间邻接直接解释为因果。
6. 前端在关系丰富后再增加 Loop、Fallback 和跨阶段依赖的专用视觉编码。

## 复现命令

```powershell
python -m agentvast.cli observe derive <session-id>
python -m agentvast.cli observe semantic <session-id> --force
python -m pytest tests/test_observer.py tests/test_prototype_cli.py -q
cd frontend
npm run build
```

