# AgentVAST Frontend

基于 React + React Flow + Dagre 的 AgentVAST 数据血缘可视化前端。

## 技术栈

- **Vite** - 快速构建工具
- **React 18** - UI框架
- **TypeScript** - 类型安全
- **React Flow** - DAG交互组件
- **Dagre** - 自动布局算法
- **Tailwind CSS** - 样式
- **ECharts** - 图表可视化

## 安装

```bash
cd frontend
npm install
```

## 开发

```bash
npm run dev
```

访问 http://localhost:3000

## 构建

```bash
npm run build
```

## 功能

- 加载 AgentVAST session 文件夹
- 显示 PROV DAG（使用 Dagre 自动布局）
- Timeline 展示分析步骤
- Inspector 查看节点详情
- Follow-up 生成 Claude 继续问答命令
- ECharts 数据集可视化
- Passive Observer 独立页面：展示 transcript 派生的 Turn、工具批次、错误恢复和最终回答

Passive Observer 页面读取后端只读 Observation API，或离线加载
`derived/observer_trace.json`。它不会直接解析原始 transcript，也不会把执行轨迹伪装成带 Plan
约束的 `workflow.json`。

生成 `derived/semantic_workflow.json` 后，被动观察页面默认显示证据约束的语义工作流，并提供
“语义工作流 / 执行轨迹 / 原始证据”三级切换。人工接受、字段修正、连续 Node 合并和按 Episode
拆分会写入追加式 review sidecar，不会覆盖模型或规则生成的原始语义文件。

模型模式使用相邻 Candidate 的 `MERGE/SPLIT` JSON 决策；前端分别显示 Evidence Validity、
Granularity Validity、模型置信度、校验后置信度，以及模型边界被硬约束覆盖的原因。

Semantic Annotation 采用逐 Episode 模型调用。点击模型生成后，页面轮询后端进度，显示候选块、
边界判断、当前 Episode、关系提取和最终验证等阶段，不再让一个长同步请求无反馈地等待。

## 设计原则

参考 `agentvast/visualization/vis-guide.md`：
- 不重新实现 DAG 绘制
- 专注将执行过程转换为具有语义的可解释 Provenance Graph
- 使用现成的布局库（Dagre/ELK）
