# OpenTrace Frontend

基于 React + React Flow + Dagre 的 OpenTrace 数据血缘可视化前端。

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

- 加载 OpenTrace session 文件夹
- 显示 PROV DAG（使用 Dagre 自动布局）
- Timeline 展示分析步骤
- Inspector 查看节点详情
- Follow-up 生成 Claude 继续问答命令
- ECharts 数据集可视化

## 设计原则

参考 `opentrace/visualization/vis-guide.md`：
- 不重新实现 DAG 绘制
- 专注将执行过程转换为具有语义的可解释 Provenance Graph
- 使用现成的布局库（Dagre/ELK）
