# AgentVAST Vertical DAG Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current AgentVAST viewer DAG layout with a stable top-to-bottom layered graph that prevents node overlap, routes long dependency edges through side lanes, keeps nodes concise, and preserves details in the Inspector.

**Architecture:** The viewer remains a single static HTML file at `agentvast/visualization/trace_viewer.html`. The graph pipeline is split inside that file into focused functions: build a merged visualization graph from PROV, compute a vertical layered layout, route short and long edges separately, render compact nodes, and expose details through the existing Inspector. Regression coverage stays in `test/test_trace_viewer_frontend.py` using static HTML assertions.

**Tech Stack:** Static HTML/CSS/vanilla JavaScript, SVG for edge rendering, Python pytest for regression checks.

---

## File Structure

- Modify: `agentvast/visualization/trace_viewer.html`
  - CSS: node sizing, graph stage scrolling, zoom controls, side-lane visual styling, edge label styling.
  - JS: PROV graph merge, vertical layout, side-lane edge routing, compact node title/description, zoom handlers.
- Modify: `test/test_trace_viewer_frontend.py`
  - Add regression tests for non-overlap-oriented layout primitives, side-lane routing functions, compact node content, and Inspector detail boundary.
- Do not modify backend tracking APIs for this task.
- Do not change `prov_visualizer.py`; use it only as conceptual reference for entity-by-location and agent-as-processing-node merging.

---

## Design Constraints to Preserve

1. The visual graph is built from `prov_nodes.json` and `prov_edges.json`, not only from `step_details.json`.
2. Entity nodes with the same normalized artifact location are merged.
3. Agent nodes with the same normalized agent name are merged.
4. Edges are deduped by `source + target + relation`.
5. Node boxes use fixed dimensions; content never controls graph geometry.
6. Node display contains only name and short description.
7. Full paths, input/output files, code, commands, parameters, raw PROV, and insights stay in the right Inspector.
8. Short edges connect vertically from bottom-center to top-center.
9. Long cross-layer edges route through left/right side lanes.
10. The canvas may be larger than the viewport; scrolling and zoom are expected.

---

### Task 1: Add Regression Tests for Final DAG Layout Contract

**Files:**
- Modify: `test/test_trace_viewer_frontend.py`

- [ ] **Step 1: Add failing tests for vertical side-lane layout contract**

Append these tests near the existing viewer layout tests:

```python
def test_trace_viewer_declares_no_overlap_layout_constants():
    html = VIEWER.read_text(encoding="utf-8")

    assert "const NODE_W = 220" in html
    assert "const NODE_H = 96" in html
    assert "const ROW_GAP = 84" in html
    assert "const COL_GAP = 96" in html
    assert "const SIDE_LANE_W = 128" in html


def test_trace_viewer_routes_long_edges_through_side_lanes():
    html = VIEWER.read_text(encoding="utf-8")

    assert "routeGraphEdges" in html
    assert "isLongEdge" in html
    assert "side: laneIndex % 2 === 0 ? \"left\" : \"right\"" in html
    assert "renderSideLaneEdge" in html
    assert "renderShortEdge" in html
    assert "long-edge" in html
    assert "side-lane" in html


def test_trace_viewer_nodes_only_render_summary_content():
    html = VIEWER.read_text(encoding="utf-8")

    assert "formatNodeTitle" in html
    assert "formatNodeDescription" in html
    assert "node-desc" in html
    assert "node.location" not in html.split("function renderDAGNode", 1)[1].split("function matchInsightsForNode", 1)[0]
    assert "inputFiles" not in html.split("function renderDAGNode", 1)[1].split("function matchInsightsForNode", 1)[0]
    assert "outputFiles" not in html.split("function renderDAGNode", 1)[1].split("function matchInsightsForNode", 1)[0]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py -q
```

Expected: FAIL because constants/functions such as `routeGraphEdges`, `renderSideLaneEdge`, or exact fixed constants are not implemented yet.

- [ ] **Step 3: Commit not required**

Do not commit unless the user explicitly asks. This repository currently follows the session rule: commit only when requested.

---

### Task 2: Replace Layout Constants and Graph Stage Styling

**Files:**
- Modify: `agentvast/visualization/trace_viewer.html`

- [ ] **Step 1: Update CSS for scrollable, zoomable, side-lane graph stage**

In the `<style>` section, replace the current graph/node sizing block around `.graph-stage`, `.flow-grid`, and `.dag-node` with:

```css
    .graph-stage {
      height: calc(100% - 48px);
      overflow: auto;
      padding: 18px;
      background:
        linear-gradient(90deg, rgba(217,119,69,.055) 0 128px, transparent 128px calc(100% - 128px), rgba(217,119,69,.055) calc(100% - 128px)),
        rgba(255,255,255,.34);
    }
    .graph-toolbar { display: flex; gap: 8px; align-items: center; color: var(--muted); font: 11px Consolas, monospace; }
    .graph-toolbar button { padding: 6px 9px; border-radius: 10px; }
    .flow-grid { position: relative; min-width: 100%; min-height: 100%; transform-origin: top left; }
    .side-lane-label {
      position: absolute;
      top: 10px;
      color: #b08a70;
      font: 10px Consolas, monospace;
      text-transform: uppercase;
      letter-spacing: .08em;
      writing-mode: vertical-rl;
      pointer-events: none;
    }
    .side-lane-label.left { left: 14px; }
    .side-lane-label.right { right: 14px; }
    .dag-svg { position: absolute; inset: 0; pointer-events: none; overflow: visible; }
    .dag-edge { fill: none; stroke: rgba(217, 119, 69, 0.42); stroke-width: 2.2; marker-end: url(#arrow); }
    .dag-edge.generated { stroke: rgba(111, 143, 82, 0.46); }
    .dag-edge.long-edge { stroke: rgba(164, 118, 92, 0.58); stroke-dasharray: 7 5; }

    .dag-node {
      position: absolute;
      width: 220px;
      height: 96px;
      border: 1px solid rgba(184, 165, 143, 0.58);
      border-radius: 14px;
      padding: 10px 12px;
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 16px 35px rgba(76, 55, 32, 0.09);
      cursor: pointer;
      transition: 180ms ease;
      overflow: hidden;
    }

    .dag-node:hover, .dag-node.selected { border-color: var(--accent); box-shadow: 0 18px 42px rgba(217, 119, 69, 0.16); transform: translateY(-1px); }
    .dag-node.entity { border-left: 4px solid var(--green); }
    .dag-node.activity { border-left: 4px solid var(--amber); }
    .dag-node.agent { border-left: 4px solid var(--violet); }
    .dag-node.report { border-left-color: var(--accent); }
    .node-label { font-weight: 800; font-size: 13px; line-height: 1.24; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .node-kind { color: var(--muted); font: 9px Consolas, monospace; margin-bottom: 6px; text-transform: uppercase; letter-spacing: .08em; }
    .node-desc { color: #6b5b4f; font-size: 11px; line-height: 1.32; margin-top: 6px; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
```

- [ ] **Step 2: Run tests and verify expected partial failure**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py -q
```

Expected: still FAIL because JS constants and routing functions are not complete yet.

---

### Task 3: Implement Stable Vertical Layer Layout Constants

**Files:**
- Modify: `agentvast/visualization/trace_viewer.html`

- [ ] **Step 1: Replace `verticalLayout()` implementation**

Find `function verticalLayout(flow, stageWidth) { ... }` and replace the whole function with:

```js
    function verticalLayout(flow, stageWidth) {
      const NODE_W = 220;
      const NODE_H = 96;
      const ROW_GAP = 84;
      const COL_GAP = 96;
      const SIDE_LANE_W = 128;
      const PADDING_X = 32;
      const PADDING_Y = 36;

      const incoming = new Map(flow.nodes.map(n => [n.id, 0]));
      const outgoing = new Map(flow.nodes.map(n => [n.id, []]));
      for (const edge of flow.edges) {
        incoming.set(edge.to, (incoming.get(edge.to) || 0) + 1);
        if (!outgoing.has(edge.from)) outgoing.set(edge.from, []);
        outgoing.get(edge.from).push(edge.to);
      }

      const remainingIncoming = new Map(incoming);
      const layer = new Map(flow.nodes.map(n => [n.id, 0]));
      const queue = flow.nodes.filter(n => !remainingIncoming.get(n.id)).map(n => n.id);
      const visited = new Set();

      while (queue.length) {
        const id = queue.shift();
        visited.add(id);
        const nextLayer = (layer.get(id) || 0) + 1;
        for (const to of outgoing.get(id) || []) {
          if ((layer.get(to) || 0) < nextLayer) layer.set(to, nextLayer);
          remainingIncoming.set(to, remainingIncoming.get(to) - 1);
          if (remainingIncoming.get(to) === 0) queue.push(to);
        }
      }

      // Cycles should not happen in a valid DAG, but if malformed data contains one,
      // place unvisited nodes after their current inferred layer instead of overlapping.
      for (const node of flow.nodes) {
        if (!visited.has(node.id)) {
          const fallbackLayer = Math.max(0, ...[...layer.values()]) + 1;
          layer.set(node.id, fallbackLayer);
        }
      }

      const rows = new Map();
      for (const node of flow.nodes) {
        const row = layer.get(node.id) || 0;
        if (!rows.has(row)) rows.set(row, []);
        rows.get(row).push(node);
      }

      const positions = {};
      const sortedRows = [...rows.keys()].sort((a, b) => a - b);
      let maxRowWidth = 0;

      sortedRows.forEach(rowNo => {
        const rowNodes = rows.get(rowNo);
        const rowWidth = rowNodes.length * NODE_W + Math.max(0, rowNodes.length - 1) * COL_GAP;
        maxRowWidth = Math.max(maxRowWidth, rowWidth);
        const mainAreaWidth = Math.max(rowWidth, (stageWidth || 900) - SIDE_LANE_W * 2 - PADDING_X * 2);
        const startX = SIDE_LANE_W + PADDING_X + Math.max(0, (mainAreaWidth - rowWidth) / 2);
        rowNodes.forEach((node, col) => {
          positions[node.id] = {
            x: startX + col * (NODE_W + COL_GAP),
            y: PADDING_Y + rowNo * (NODE_H + ROW_GAP),
            layer: rowNo,
          };
        });
      });

      return {
        positions,
        width: Math.max((stageWidth || 900), maxRowWidth + SIDE_LANE_W * 2 + PADDING_X * 2),
        height: Math.max(sortedRows.length * (NODE_H + ROW_GAP) + PADDING_Y * 2, 720),
        nodeWidth: NODE_W,
        nodeHeight: NODE_H,
        rowGap: ROW_GAP,
        colGap: COL_GAP,
        sideLaneWidth: SIDE_LANE_W,
      };
    }
```

- [ ] **Step 2: Run the layout tests**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py::test_trace_viewer_declares_no_overlap_layout_constants -q
```

Expected: PASS.

---

### Task 4: Implement Short and Long Edge Routing

**Files:**
- Modify: `agentvast/visualization/trace_viewer.html`

- [ ] **Step 1: Add edge routing helpers before `renderGraph()`**

Insert these functions between `layeredLayout()` and `renderGraph()`:

```js
    function isLongEdge(edge, positions) {
      const from = positions[edge.from];
      const to = positions[edge.to];
      if (!from || !to) return false;
      return Math.abs((to.layer || 0) - (from.layer || 0)) > 1;
    }

    function routeGraphEdges(edges, positions) {
      let laneIndex = 0;
      return edges.map(edge => {
        if (!isLongEdge(edge, positions)) return { ...edge, kind: "short" };
        const routed = {
          ...edge,
          kind: "long",
          laneIndex,
          side: laneIndex % 2 === 0 ? "left" : "right",
        };
        laneIndex += 1;
        return routed;
      });
    }

    function renderShortEdge(edge, positions, layout) {
      const a = positions[edge.from], b = positions[edge.to];
      if (!a || !b) return "";
      const x1 = a.x + layout.nodeWidth / 2;
      const y1 = a.y + layout.nodeHeight;
      const x2 = b.x + layout.nodeWidth / 2;
      const y2 = b.y;
      const labelX = (x1 + x2) / 2;
      const labelY = (y1 + y2) / 2 - 6;
      const bend = Math.max(44, Math.abs(y2 - y1) / 2);
      const path = `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
      return `<path class="dag-edge ${edge.relation === "output" ? "generated" : ""}" d="${path}" /><text class="edge-label" x="${labelX}" y="${labelY}">${escapeHtml(edge.relation)}</text>`;
    }

    function renderSideLaneEdge(edge, positions, layout) {
      const a = positions[edge.from], b = positions[edge.to];
      if (!a || !b) return "";
      const laneOffset = 24 + (edge.laneIndex % 4) * 18;
      const laneX = edge.side === "left"
        ? layout.sideLaneWidth - laneOffset
        : layout.width - layout.sideLaneWidth + laneOffset;
      const x1 = edge.side === "left" ? a.x : a.x + layout.nodeWidth;
      const y1 = a.y + layout.nodeHeight / 2;
      const x2 = edge.side === "left" ? b.x : b.x + layout.nodeWidth;
      const y2 = b.y + layout.nodeHeight / 2;
      const labelX = laneX + (edge.side === "left" ? -6 : 6);
      const labelY = (y1 + y2) / 2;
      const path = `M ${x1} ${y1} C ${laneX} ${y1}, ${laneX} ${y1}, ${laneX} ${(y1 + y2) / 2} C ${laneX} ${y2}, ${laneX} ${y2}, ${x2} ${y2}`;
      return `<path class="dag-edge long-edge" d="${path}" /><text class="edge-label" x="${labelX}" y="${labelY}">${escapeHtml(edge.relation)}</text>`;
    }
```

- [ ] **Step 2: Replace edge rendering inside `renderGraph()`**

Inside `renderGraph()`, replace the current `const svgEdges = flow.edges.map(...).join("");` block with:

```js
      const routedEdges = routeGraphEdges(flow.edges, pos);
      const svgEdges = routedEdges.map(edge => {
        return edge.kind === "long"
          ? renderSideLaneEdge(edge, pos, layout)
          : renderShortEdge(edge, pos, layout);
      }).join("");
```

- [ ] **Step 3: Add side lane labels to graph HTML**

In the `graphStage.innerHTML` template, after `${nodeHtml}` and before closing the scaled inner `<div>`, add:

```html
          <div class="side-lane-label left">long dependencies</div>
          <div class="side-lane-label right">long dependencies</div>
```

The relevant final template should contain:

```js
      $("graphStage").innerHTML = `<div class="flow-grid" style="width:${layout.width * GRAPH_SCALE}px;height:${layout.height * GRAPH_SCALE}px"><div style="position:relative;width:${layout.width}px;height:${layout.height}px;transform:scale(${GRAPH_SCALE});transform-origin:top left;">
        <svg class="dag-svg" width="${layout.width}" height="${layout.height}" viewBox="0 0 ${layout.width} ${layout.height}">
          <defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="rgba(217, 119, 69, 0.55)" /></marker></defs>
          ${svgEdges}
        </svg>${nodeHtml}
          <div class="side-lane-label left">long dependencies</div>
          <div class="side-lane-label right">long dependencies</div>
        </div></div>`;
```

- [ ] **Step 4: Run long-edge routing test**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py::test_trace_viewer_routes_long_edges_through_side_lanes -q
```

Expected: PASS.

---

### Task 5: Restrict Node Rendering to Name and Short Description

**Files:**
- Modify: `agentvast/visualization/trace_viewer.html`

- [ ] **Step 1: Replace `formatNodeTitle()` and `formatNodeDescription()`**

Replace both functions with:

```js
    function formatNodeTitle(node) {
      const raw = node.location ? baseName(node.location) : (node.name || node.description || node.id);
      return String(raw)
        .replace(/^node_0*(\d+)_/, "n$1 · ")
        .replace(/_/g, " ")
        .replace(/\.json$|\.py$|\.txt$/i, "")
        .slice(0, 54);
    }

    function formatNodeDescription(node) {
      if (node.type === "agent") return (node.name || node.agent_type || "processing agent").replace(/_/g, " ").slice(0, 72);
      if (node.type === "activity") return (node.description || node.activity_type || "activity").slice(0, 72);
      if (node.location) return `${node.entity_type || "artifact"} · click for full path`;
      return (node.description || node.name || "PROV node").slice(0, 72);
    }
```

- [ ] **Step 2: Replace `renderDAGNode()`**

Replace the whole function with:

```js
    function renderDAGNode(node, p, trace) {
      const kind = node.merged ? "entity" : (node.type || "node");
      const subtype = node.entity_type || node.activity_type || node.agent_type || kind;
      const title = formatNodeTitle(node);
      const description = formatNodeDescription(node);
      const mergedMeta = node.merged && node.original_ids?.length > 1 ? `merged ${node.original_ids.length}` : "detail in inspector";
      return `<article class="dag-node ${escapeHtml(kind)} ${/report|final/i.test(title) ? "report" : ""} ${node.id === state.selectedProvId ? "selected" : ""}" data-prov-id="${escapeHtml(node.id)}" style="left:${p.x}px;top:${p.y}px">
        <div class="node-kind">${escapeHtml(subtype)} · ${escapeHtml(mergedMeta)}</div>
        <div class="node-label">${escapeHtml(title)}</div>
        <div class="node-desc">${escapeHtml(description)}</div>
      </article>`;
    }
```

- [ ] **Step 3: Run summary-content test**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py::test_trace_viewer_nodes_only_render_summary_content -q
```

Expected: PASS.

---

### Task 6: Verify Inspector Still Carries Full Details

**Files:**
- Modify: `test/test_trace_viewer_frontend.py`
- Inspect: `agentvast/visualization/trace_viewer.html`

- [ ] **Step 1: Add failing test for detail boundary**

Append:

```python
def test_trace_viewer_keeps_full_details_in_inspector():
    html = VIEWER.read_text(encoding="utf-8")

    inspector_section = html.split("function renderInspector", 1)[1]
    assert "input files" in inspector_section
    assert "output files" in inspector_section
    assert "code files" in inspector_section
    assert "commands" in inspector_section
    assert "related_edges" in inspector_section
    assert "trace.insights" in inspector_section
```

- [ ] **Step 2: Run test**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py::test_trace_viewer_keeps_full_details_in_inspector -q
```

Expected: PASS if the current Inspector implementation still includes all detail tabs. If it fails, restore those strings in `renderInspector()` without adding detail back into `renderDAGNode()`.

---

### Task 7: Final Regression Run

**Files:**
- Test: `test/test_trace_viewer_frontend.py`
- Test: `test/test_step_records.py`

- [ ] **Step 1: Run all current regression tests**

Run:

```bash
python -m pytest test/test_trace_viewer_frontend.py test/test_step_records.py
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Manual browser check**

Open:

```text
agentvast/visualization/trace_viewer.html
```

Load session folder:

```text
.agentvast/session_20260630_172421
```

Check:

```text
- Nodes are arranged top-to-bottom.
- Nodes do not visually overlap.
- Node text is name + short description only.
- Full paths and file lists appear only after clicking a node in Inspector.
- Short edges are vertical.
- Long dependency edges use left/right side lanes.
- Zoom buttons change scale.
- Scrolling works for a graph larger than the viewport.
```

- [ ] **Step 3: Report verification evidence**

Report the exact pytest command and pass count. If manual browser checks reveal problems, list them instead of claiming completion.

---

## Self-Review

**Spec coverage:**
- Fixed node dimensions and no-overlap layout constants: Task 3.
- Top-to-bottom layout: Task 3 and Task 4.
- Long dependency edges through left/right lanes: Task 4.
- Nodes show only name + brief description: Task 5.
- Full details in Inspector: Task 6.
- Scrolling/zooming: existing controls preserved and graph canvas remains larger than viewport; verified in Task 7.
- Entity/agent/edge dedupe: preserved from existing `buildProvDAGFlow()` implementation; not changed except routing/layout.

**Placeholder scan:** No TBD/TODO/placeholders remain.

**Type consistency:** Functions referenced in tests (`verticalLayout`, `routeGraphEdges`, `renderSideLaneEdge`, `renderShortEdge`, `formatNodeTitle`, `formatNodeDescription`) are defined in implementation tasks with matching names.
