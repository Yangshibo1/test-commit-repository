# OpenTrace Frontend (English Version)

OpenTrace data lineage visualization frontend based on React + React Flow + Dagre.

## Tech Stack

- **Vite** - Fast build tool
- **React 18** - UI framework
- **TypeScript** - Type safety
- **React Flow** - DAG interaction component
- **Dagre** - Automatic layout algorithm
- **Tailwind CSS** - Styling
- **ECharts** - Chart visualization

## Installation

```bash
cd frontend-en
npm install
```

## Development

```bash
npm run dev
```

Visit http://localhost:3000

## Build

```bash
npm run build
```

## Features

- Load OpenTrace session folder
- Display PROV DAG (using Dagre automatic layout)
- Timeline showing analysis steps
- Inspector for viewing node details
- Follow-up for generating Claude continuation Q&A commands
- ECharts dataset visualization

## Design Principles

Refer to `opentrace/visualization/vis-guide.md`:
- Don't reimplement DAG rendering
- Focus on converting execution process into semantic, explainable Provenance Graph
- Use existing layout libraries (Dagre/ELK)
