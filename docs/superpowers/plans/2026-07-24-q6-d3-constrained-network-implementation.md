# Q6 D3 Constrained Personnel Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one interactive D3 HTML visualization that renders the three observed TXT personnel chains as a readable constrained-force network with progressive edge-detail disclosure.

**Architecture:** A small browser module owns pure graph derivation, constrained node initialization, deterministic route geometry, Canvas edge drawing, SVG foreground drawing, and interaction state. The HTML file supplies layout, controls, tooltip styling, and loads the existing JSON dataset. Canvas renders every viable event edge; SVG renders nodes, the gate, labels, annotations, controls, and the three always-prominent post arrows under one shared D3 zoom transform.

**Tech Stack:** HTML/CSS, vanilla ES modules, D3 v7 from `https://cdn.jsdelivr.net/npm/d3@7/+esm`, Canvas 2D, SVG, Node.js built-in test runner.

---

## File structure

- **Create:** `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html`
  - Primary user-facing page: controls, legend, canvas/SVG layers, tooltip, and module bootstrap.
- **Create:** `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
  - Pure event/route helpers plus D3 constrained-force layout, canvas/SVG rendering, interaction state, hit testing, zoom, and dragging.
- **Create:** `test/test_q6_john_posting_intervention_network.mjs`
  - Node built-in unit tests for data derivation, sequencing, memberships/bands, route offsets, interaction-state filtering, and nearest-edge hit testing.
- **Modify:** `docs/superpowers/specs/2026-07-24-q6-d3-constrained-network-design.md`
  - Add the exact chosen module, D3 CDN, and Node test command once implementation confirms them.

The existing Python renderer and PNG are intentionally out of scope: retain them but do not modify or regenerate them.

## Shared contracts

The JavaScript module must export these pure helpers for tests:

```js
export const GATE_ID = "__validation_gate__";
export const CHAIN_ORDER = ["SwiftWren.txt", "HiddenOrca.txt", "MellowOtter.txt"];
export const CHAIN_COLORS = {
  "SwiftWren.txt": "#C33C54",
  "HiddenOrca.txt": "#246EB9",
  "MellowOtter.txt": "#1F2937",
};

export function personId(party) { /* returns normalized id or null */ }
export function deriveEventEdge(chainFile, event) { /* edge or null */ }
export function buildGraph(dataset) { /* graph contract below */ }
export function buildNodeModel(graph) { /* unique nodes with bands */ }
export function buildRoute(edge, nodesById, occurrenceByPair) { /* route geometry */ }
export function visibleEdgeIds(graph, state) { /* disclosure policy */ }
export function nearestEdge(edges, point, tolerance) { /* edge hit test */ }
```

`buildGraph(dataset)` returns:

```js
{
  people: Set<string>,
  edges: Array<{
    eventId: number,
    chainFile: string,
    when: number,
    shortName: string,
    source: string,
    target: string,
    sequence: number,
    isPost: boolean,
  }>,
  edgesByChain: Map<string, Array<Edge>>,
  omittedEvents: Array<{ eventId: number, chainFile: string, shortName: string, personCount: number }>,
  memberships: Map<string, Set<string>>,
}
```

An edge's route is a deterministic object:

```js
{
  edge,
  kind: "quadratic" | "loop",
  start: {x, y},
  control: {x, y},
  end: {x, y},
  label: {x, y},
  pairIndex: number,
}
```

The interaction state is:

```js
{
  activeChain: null | string,
  hoveredNodeId: null | string,
  hoveredEdgeId: null | string,
}
```

### Task 1: Add the pure data-derivation module and its red tests

**Files:**
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Create: `test/test_q6_john_posting_intervention_network.mjs`

- [ ] **Step 1: Create a Node test fixture and failing data-derivation tests.**

Write `test/test_q6_john_posting_intervention_network.mjs` with the following test setup and assertions:

```js
import assert from "node:assert/strict";
import test from "node:test";
import {
  GATE_ID,
  buildGraph,
  deriveEventEdge,
  personId,
} from "../VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js";

const event = (id, when, shortName, parties) => ({ id, when, short_name: shortName, parties });

test("normalizes person prefixes without removing duplicate parties", () => {
  assert.equal(personId("Agent/person:emma_harbor"), "emma_harbor");
  assert.equal(personId("person:emma_harbor"), "emma_harbor");
  assert.equal(personId("system:file_system"), null);
});

test("derives two-person edges and projects John posts to the gate", () => {
  assert.deepEqual(
    deriveEventEdge("SwiftWren.txt", event(1, 10, "handoff", [
      "system:file_system", "Agent/person:emma_harbor", "person:chloe_ballast",
    ])),
    {
      eventId: 1, chainFile: "SwiftWren.txt", when: 10, shortName: "handoff",
      source: "emma_harbor", target: "chloe_ballast", isPost: false,
    },
  );
  assert.deepEqual(
    deriveEventEdge("SwiftWren.txt", event(2, 20, "saidit_post", ["person:john_windward"])),
    {
      eventId: 2, chainFile: "SwiftWren.txt", when: 20, shortName: "saidit_post",
      source: "john_windward", target: GATE_ID, isPost: true,
    },
  );
  assert.equal(deriveEventEdge("SwiftWren.txt", event(3, 30, "read_file", ["person:emma_harbor"])), null);
  assert.equal(deriveEventEdge("SwiftWren.txt", event(4, 40, "handoff", ["person:a", "person:b", "person:c"])), null);
});
```

- [ ] **Step 2: Run the test and verify it fails because the module does not exist.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: failure with `ERR_MODULE_NOT_FOUND` for `q6_john_posting_intervention_network.js`.

- [ ] **Step 3: Implement the minimal normalization and edge-derivation exports.**

Create the module with these exact starting definitions:

```js
export const GATE_ID = "__validation_gate__";
export const CHAIN_ORDER = ["SwiftWren.txt", "HiddenOrca.txt", "MellowOtter.txt"];
export const CHAIN_COLORS = {
  "SwiftWren.txt": "#C33C54",
  "HiddenOrca.txt": "#246EB9",
  "MellowOtter.txt": "#1F2937",
};

export function personId(party) {
  const value = String(party);
  for (const prefix of ["Agent/person:", "person:"]) {
    if (value.startsWith(prefix)) return value.slice(prefix.length);
  }
  return null;
}

function personIds(parties = []) {
  return parties.map(personId).filter((id) => id !== null);
}

export function deriveEventEdge(chainFile, event) {
  const people = personIds(event.parties);
  if (people.length === 2) {
    return {
      eventId: event.id,
      chainFile,
      when: Number(event.when),
      shortName: event.short_name ?? "",
      source: people[0],
      target: people[1],
      isPost: false,
    };
  }
  if (people.length === 1 && people[0] === "john_windward" && event.short_name === "saidit_post") {
    return {
      eventId: event.id,
      chainFile,
      when: Number(event.when),
      shortName: "saidit_post",
      source: "john_windward",
      target: GATE_ID,
      isPost: true,
    };
  }
  return null;
}
```

- [ ] **Step 4: Run the data-derivation tests and verify they pass.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: 2 passing tests, 0 failures.

### Task 2: Build chain-local graph state, membership bands, and real-data contract tests

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `test/test_q6_john_posting_intervention_network.mjs`

- [ ] **Step 1: Add failing graph-contract tests using a compact unsorted fixture and the real dataset.**

Append these tests:

```js
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("orders each chain independently, retains duplicates, and records omissions", () => {
  const dataset = {
    chains: {
      "SwiftWren.txt": { events: [
        event(5, 50, "saidit_post", ["person:john_windward"]),
        event(4, 40, "read_file", ["person:alpha"]),
        event(3, 30, "handoff", ["person:beta", "person:beta"]),
        event(2, 20, "handoff", ["person:alpha", "person:beta"]),
        event(1, 10, "handoff", ["person:alpha", "person:beta"]),
      ] },
      "HiddenOrca.txt": { events: [event(7, 70, "saidit_post", ["person:john_windward"])] },
      "MellowOtter.txt": { events: [event(8, 80, "saidit_post", ["person:john_windward"])] },
    },
  };
  const graph = buildGraph(dataset);
  assert.deepEqual(graph.edgesByChain.get("SwiftWren.txt").map((edge) => edge.eventId), [1, 2, 3, 5]);
  assert.deepEqual(graph.edgesByChain.get("SwiftWren.txt").map((edge) => edge.sequence), [1, 2, 3, 4]);
  assert.equal(graph.edges.filter((edge) => edge.source === "alpha" && edge.target === "beta").length, 2);
  assert.equal(graph.edges.filter((edge) => edge.isPost).length, 3);
  assert.equal(graph.omittedEvents[0].eventId, 4);
  assert.deepEqual([...graph.memberships.get("alpha")], ["SwiftWren.txt"]);
});

test("matches the observed dataset graph contract", () => {
  const dataset = JSON.parse(fs.readFileSync(path.join(root, "result/three_txt_posting_chains_dataset.json"), "utf8"));
  const graph = buildGraph(dataset);
  assert.equal(graph.people.size, 19);
  assert.equal(graph.edges.length, 238);
  assert.equal(graph.omittedEvents.length, 10);
  assert.deepEqual(
    Object.fromEntries(CHAIN_ORDER.map((chain) => [chain, graph.edgesByChain.get(chain).length])),
    { "SwiftWren.txt": 187, "HiddenOrca.txt": 40, "MellowOtter.txt": 11 },
  );
  assert.deepEqual(
    Object.fromEntries(CHAIN_ORDER.map((chain) => [chain, graph.edgesByChain.get(chain).at(-1).sequence])),
    { "SwiftWren.txt": 187, "HiddenOrca.txt": 40, "MellowOtter.txt": 11 },
  );
});
```

Add `CHAIN_ORDER` and `buildGraph` to the import list.

- [ ] **Step 2: Run tests and verify the new graph tests fail because `buildGraph` is not exported.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: failure mentioning missing export `buildGraph`.

- [ ] **Step 3: Implement `buildGraph(dataset)` with chain-local ordering and memberships.**

Add this implementation:

```js
export function buildGraph(dataset) {
  const people = new Set();
  const edges = [];
  const edgesByChain = new Map(CHAIN_ORDER.map((chain) => [chain, []]));
  const omittedEvents = [];
  const memberships = new Map();

  for (const chainFile of CHAIN_ORDER) {
    const events = dataset.chains?.[chainFile]?.events ?? [];
    const ordered = [...events].sort((left, right) =>
      (left.when ?? Number.POSITIVE_INFINITY) - (right.when ?? Number.POSITIVE_INFINITY)
      || (left.id ?? 0) - (right.id ?? 0));
    for (const event of ordered) {
      const edge = deriveEventEdge(chainFile, event);
      if (!edge) {
        omittedEvents.push({
          eventId: event.id,
          chainFile,
          shortName: event.short_name ?? "",
          personCount: personIds(event.parties).length,
        });
        continue;
      }
      edge.sequence = edgesByChain.get(chainFile).length + 1;
      edges.push(edge);
      edgesByChain.get(chainFile).push(edge);
      for (const person of [edge.source, edge.target]) {
        if (person === GATE_ID) continue;
        people.add(person);
        if (!memberships.has(person)) memberships.set(person, new Set());
        memberships.get(person).add(chainFile);
      }
    }
  }
  return { people, edges, edgesByChain, omittedEvents, memberships };
}
```

- [ ] **Step 4: Run tests and verify all graph contract assertions pass.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: 4 passing tests, 0 failures.

### Task 3: Add constrained node model and deterministic edge route geometry

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `test/test_q6_john_posting_intervention_network.mjs`

- [ ] **Step 1: Add failing node-band and route-geometry tests.**

Append:

```js
import { buildNodeModel, buildRoute } from "../VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js";

test("assigns one constrained node per person with chain-story bands", () => {
  const graph = {
    people: new Set(["john_windward", "swift", "hidden", "mellow", "shared"]),
    memberships: new Map([
      ["john_windward", new Set(["SwiftWren.txt", "HiddenOrca.txt", "MellowOtter.txt"])],
      ["swift", new Set(["SwiftWren.txt"])],
      ["hidden", new Set(["HiddenOrca.txt"])],
      ["mellow", new Set(["MellowOtter.txt"])],
      ["shared", new Set(["SwiftWren.txt", "HiddenOrca.txt"])],
    ]),
  };
  const nodes = buildNodeModel(graph);
  assert.equal(new Set(nodes.map((node) => node.id)).size, 5);
  assert.equal(nodes.find((node) => node.id === "john_windward").fixed, true);
  assert.equal(nodes.find((node) => node.id === "hidden").band, "upper");
  assert.equal(nodes.find((node) => node.id === "mellow").band, "lower");
  assert.equal(nodes.find((node) => node.id === "swift").band, "middle");
  assert.equal(nodes.find((node) => node.id === "shared").band, "middle");
});

test("gives parallel routes separate labels and gives self transfers a loop", () => {
  const nodes = new Map([
    ["alpha", { x: 0, y: 0 }], ["beta", { x: 100, y: 0 }], ["john_windward", { x: 200, y: 0 }],
    [GATE_ID, { x: 270, y: 0 }],
  ]);
  const samePair = [0, 1, 2].map((pairIndex) => buildRoute(
    { eventId: pairIndex, chainFile: "SwiftWren.txt", source: "alpha", target: "beta", sequence: pairIndex + 1 }, nodes, pairIndex,
  ));
  assert.equal(new Set(samePair.map((route) => route.control.y)).size, 3);
  assert.equal(new Set(samePair.map((route) => `${route.label.x},${route.label.y}`)).size, 3);
  const loop = buildRoute(
    { eventId: 9, chainFile: "MellowOtter.txt", source: "alpha", target: "alpha", sequence: 1 }, nodes, 0,
  );
  assert.equal(loop.kind, "loop");
  assert.notDeepEqual(loop.start, loop.end);
});
```

- [ ] **Step 2: Run the tests and verify failure because the node and route helpers are missing.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: failure mentioning missing exports `buildNodeModel` and `buildRoute`.

- [ ] **Step 3: Implement band targets, node initialization, and route calculations.**

Add the following constants and helpers. `displayName` is used in later rendering tasks.

```js
const BAND_Y = { upper: -250, middle: 0, lower: 250 };
const BAND_BY_SINGLE_MEMBERSHIP = {
  "HiddenOrca.txt": "upper",
  "SwiftWren.txt": "middle",
  "MellowOtter.txt": "lower",
};

export function displayName(id) {
  return id.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

export function buildNodeModel(graph) {
  return [...graph.people].sort().map((id, index) => {
    const chains = graph.memberships.get(id) ?? new Set();
    const band = chains.size === 1 ? BAND_BY_SINGLE_MEMBERSHIP[[...chains][0]] : "middle";
    const fixed = id === "john_windward";
    return {
      id,
      label: displayName(id),
      chains: [...chains],
      band,
      targetX: fixed ? 620 : 100 + (index % 6) * 85,
      targetY: fixed ? 0 : BAND_Y[band],
      x: fixed ? 620 : 100 + (index % 6) * 85,
      y: fixed ? 0 : BAND_Y[band],
      fx: fixed ? 620 : null,
      fy: fixed ? 0 : null,
      fixed,
    };
  });
}

export function buildRoute(edge, nodesById, pairIndex) {
  const startNode = nodesById.get(edge.source);
  const endNode = nodesById.get(edge.target);
  const start = { x: startNode.x, y: startNode.y };
  const end = { x: endNode.x, y: endNode.y };
  if (edge.source === edge.target) {
    const loopHeight = 42 + pairIndex * 16;
    return {
      edge, kind: "loop", pairIndex,
      start: { x: start.x - 16, y: start.y - 8 },
      control: { x: start.x, y: start.y - loopHeight },
      end: { x: start.x + 16, y: start.y - 8 },
      label: { x: start.x, y: start.y - loopHeight - 8 },
    };
  }
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const normal = { x: -dy / length, y: dx / length };
  const signedOffset = (pairIndex - 1) * 18;
  const control = {
    x: (start.x + end.x) / 2 + normal.x * signedOffset,
    y: (start.y + end.y) / 2 + normal.y * signedOffset,
  };
  return {
    edge, kind: "quadratic", pairIndex, start, control, end,
    label: {
      x: 0.25 * start.x + 0.5 * control.x + 0.25 * end.x,
      y: 0.25 * start.y + 0.5 * control.y + 0.25 * end.y,
    },
  };
}
```

- [ ] **Step 4: Run all pure tests and verify they pass.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: 6 passing tests, 0 failures.

### Task 4: Add progressive-disclosure state and Canvas hit testing

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `test/test_q6_john_posting_intervention_network.mjs`

- [ ] **Step 1: Add failing interaction-state and hit-test tests.**

Append:

```js
import { nearestEdge, visibleEdgeIds } from "../VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js";

test("reveals only final post labels by default and expands detail by context", () => {
  const graph = {
    edges: [
      { eventId: 1, source: "a", target: "b", chainFile: "SwiftWren.txt", isPost: false },
      { eventId: 2, source: "b", target: "john_windward", chainFile: "HiddenOrca.txt", isPost: false },
      { eventId: 3, source: "john_windward", target: GATE_ID, chainFile: "MellowOtter.txt", isPost: true },
    ],
  };
  assert.deepEqual([...visibleEdgeIds(graph, { activeChain: null, hoveredNodeId: null, hoveredEdgeId: null })], [3]);
  assert.deepEqual([...visibleEdgeIds(graph, { activeChain: "SwiftWren.txt", hoveredNodeId: null, hoveredEdgeId: null })], [1, 3]);
  assert.deepEqual([...visibleEdgeIds(graph, { activeChain: null, hoveredNodeId: "b", hoveredEdgeId: null })], [1, 2, 3]);
});

test("returns the closest route only inside a screen-space tolerance", () => {
  const routes = [
    { edge: { eventId: 1 }, kind: "quadratic", start: { x: 0, y: 0 }, control: { x: 50, y: 0 }, end: { x: 100, y: 0 } },
    { edge: { eventId: 2 }, kind: "quadratic", start: { x: 0, y: 50 }, control: { x: 50, y: 50 }, end: { x: 100, y: 50 } },
  ];
  assert.equal(nearestEdge(routes, { x: 52, y: 4 }, 8).edge.eventId, 1);
  assert.equal(nearestEdge(routes, { x: 52, y: 30 }, 8), null);
});
```

- [ ] **Step 2: Run tests and verify failure because disclosure and hit-testing helpers are missing.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: failure mentioning missing exports `visibleEdgeIds` and `nearestEdge`.

- [ ] **Step 3: Implement disclosure policy and sampled quadratic route hit testing.**

Add:

```js
export function visibleEdgeIds(graph, state) {
  const visible = new Set(graph.edges.filter((edge) => edge.isPost).map((edge) => edge.eventId));
  if (state.activeChain) {
    for (const edge of graph.edges) if (edge.chainFile === state.activeChain) visible.add(edge.eventId);
  }
  if (state.hoveredNodeId) {
    for (const edge of graph.edges) {
      if (edge.source === state.hoveredNodeId || edge.target === state.hoveredNodeId) visible.add(edge.eventId);
    }
  }
  if (state.hoveredEdgeId !== null) visible.add(state.hoveredEdgeId);
  return visible;
}

function quadraticPoint(route, t) {
  const oneMinusT = 1 - t;
  return {
    x: oneMinusT ** 2 * route.start.x + 2 * oneMinusT * t * route.control.x + t ** 2 * route.end.x,
    y: oneMinusT ** 2 * route.start.y + 2 * oneMinusT * t * route.control.y + t ** 2 * route.end.y,
  };
}

export function nearestEdge(routes, point, tolerance) {
  let closest = null;
  let smallestDistance = tolerance;
  for (const route of routes) {
    let previous = route.start;
    for (let index = 1; index <= 24; index += 1) {
      const current = quadraticPoint(route, index / 24);
      const dx = current.x - previous.x;
      const dy = current.y - previous.y;
      const spanSquared = dx * dx + dy * dy || 1;
      const projection = Math.max(0, Math.min(1, ((point.x - previous.x) * dx + (point.y - previous.y) * dy) / spanSquared));
      const closestPoint = { x: previous.x + projection * dx, y: previous.y + projection * dy };
      const distance = Math.hypot(point.x - closestPoint.x, point.y - closestPoint.y);
      if (distance < smallestDistance) {
        closest = route;
        smallestDistance = distance;
      }
      previous = current;
    }
  }
  return closest;
}
```

- [ ] **Step 4: Run all pure tests and verify they pass.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: 8 passing tests, 0 failures.

### Task 5: Build the HTML shell and D3 bootstrap

**Files:**
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html`
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`

- [ ] **Step 1: Add a browser bootstrap export with an explicit missing-container error.**

Append a failing-testable guard to the module:

```js
export async function mountNetwork({ d3, root, datasetUrl }) {
  if (!root) throw new Error("Q6 network root element is required");
  if (!d3) throw new Error("D3 is required to mount the Q6 network");
  const dataset = await d3.json(datasetUrl);
  return { dataset, graph: buildGraph(dataset) };
}
```

- [ ] **Step 2: Create the primary HTML page with the required controls and layers.**

Create a complete page containing this required markup structure:

```html
<body>
  <main class="page-shell">
    <header class="page-header">
      <p class="eyebrow">VAST Challenge 2026 · MC2 · Question 6</p>
      <h1>Three observed TXT posting chains converge at John Windward</h1>
      <p class="summary">All 238 directionally viable event routes remain available. The default view emphasizes the three observed publication paths that reach the proposed validation gate.</p>
    </header>
    <section class="network-card" id="q6-network" aria-label="Interactive personnel intervention network">
      <div class="toolbar" role="group" aria-label="Network controls">
        <button type="button" data-chain="SwiftWren.txt" aria-pressed="false">SwiftWren.txt</button>
        <button type="button" data-chain="HiddenOrca.txt" aria-pressed="false">HiddenOrca.txt</button>
        <button type="button" data-chain="MellowOtter.txt" aria-pressed="false">MellowOtter.txt</button>
        <button type="button" data-action="reset">Reset view</button>
      </div>
      <div class="legend" aria-label="Legend">
        <span><i class="swatch swift"></i>SwiftWren.txt</span>
        <span><i class="swatch hidden"></i>HiddenOrca.txt</span>
        <span><i class="swatch mellow"></i>MellowOtter.txt</span>
        <span>Numbers appear for highlighted event routes and mean event order within that chain.</span>
      </div>
      <div class="network-stage">
        <canvas class="edge-canvas" aria-hidden="true"></canvas>
        <svg class="network-svg" role="img" aria-label="Personnel graph with three TXT chains converging at John Windward and a validation gate"></svg>
        <aside class="tooltip" hidden></aside>
      </div>
      <p class="rule"><strong>Proposed gate:</strong> <code>content_source exists + content empty → block + audit</code></p>
      <p class="scope-note">The gate covers all three observed TXT-derived anomalous posting chains. This observed pattern does not establish that every future anomaly will reach John Windward’s publication workflow.</p>
    </section>
  </main>
  <script type="module">
    import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";
    import { mountNetwork } from "./q6_john_posting_intervention_network.js";
    mountNetwork({ d3, root: document.querySelector("#q6-network"), datasetUrl: "../../result/three_txt_posting_chains_dataset.json" });
  </script>
</body>
```

Add responsive CSS that gives `.network-stage` a minimum height of `760px`, clips overflow, stacks controls on small screens, makes buttons keyboard-focusable, and uses visible focus outlines. Set the page to light surfaces with near-black text; do not reuse red/blue/black as text colors.

- [ ] **Step 3: Expand `mountNetwork` to create shared Canvas/SVG dimensions and fetch the dataset.**

Inside `mountNetwork`, create the viewport state and layers:

```js
const stage = root.querySelector(".network-stage");
const canvas = root.querySelector(".edge-canvas");
const svg = d3.select(root.querySelector(".network-svg"));
const tooltip = root.querySelector(".tooltip");
const state = { activeChain: null, hoveredNodeId: null, hoveredEdgeId: null };
const graph = buildGraph(dataset);
const nodes = buildNodeModel(graph);
const gate = { id: GATE_ID, label: "saidit_post validation gate", x: 710, y: 0, fx: 710, fy: 0, fixed: true };
const nodesById = new Map([...nodes, gate].map((node) => [node.id, node]));
```

Define a `resize()` function that sets the Canvas backing-store dimensions with `devicePixelRatio`, sets CSS dimensions to the stage dimensions, and applies the same `viewBox` width/height to SVG. Install `ResizeObserver` on `stage` and invoke `resize()` immediately.

- [ ] **Step 4: Manually load the page from a local static server and verify the shell.**

Run from repository root:

```bash
python -m http.server 8000
```

Open `http://localhost:8000/VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html` in a browser.

Expected: title, legend, three chain controls, reset button, empty stage, rule, and scope note display without browser-console module or dataset-fetch errors. Stop the server after the check.

### Task 6: Implement constrained D3 simulation and shared Canvas/SVG rendering

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html`

- [ ] **Step 1: Add a render contract assertion to the browser bootstrap.**

After graph creation, add this runtime invariant before any rendering:

```js
if (graph.people.size !== nodes.length) throw new Error("Each person must map to exactly one node");
if (graph.edges.length !== 238) console.warn(`Expected 238 viable edges, received ${graph.edges.length}`);
if (graph.edges.filter((edge) => edge.isPost).length !== 3) throw new Error("Expected three John-to-gate post edges");
```

- [ ] **Step 2: Create the constrained force simulation.**

Use the D3 forces below, keeping John pinned and gate outside the simulation:

```js
const simulation = d3.forceSimulation(nodes)
  .force("link", d3.forceLink(graph.edges.filter((edge) => !edge.isPost))
    .id((node) => node.id)
    .distance(118)
    .strength(0.28))
  .force("charge", d3.forceManyBody().strength(-360))
  .force("collide", d3.forceCollide().radius((node) => Math.max(48, node.label.length * 4.4)).iterations(2))
  .force("x", d3.forceX((node) => node.targetX).strength((node) => node.fixed ? 1 : 0.13))
  .force("y", d3.forceY((node) => node.targetY).strength((node) => node.fixed ? 1 : 0.18));
```

On each tick, keep `gate.x = john.x + 90` and `gate.y = john.y`, then call `render()`.

- [ ] **Step 3: Implement Canvas edge drawing and SVG foreground nodes.**

Inside `render()`:

1. Obtain routes by grouping `graph.edges` by `source + "→" + target`, assigning each edge a deterministic index, and calling `buildRoute`.
2. Clear Canvas in screen coordinates, apply the D3 zoom transform, and draw all routes.
3. Draw ordinary edges using `globalAlpha = 0.13`, `lineWidth = 1`, and their chain color.
4. Draw active-chain, hovered-node, or hovered-edge routes again using `globalAlpha = 0.8`, `lineWidth = 2.3`.
5. Create an SVG `<g class="world">` transformed by the same zoom transform.
6. In `world`, draw the three post routes as SVG quadratic paths with `stroke-width="3"`, the appropriate chain colors, arrowhead marker ends, and no Canvas-only dependence.
7. Bind person nodes to `<g class="person-node">`, render a rounded SVG `rect` and neutral-ink `<text>`, and give John a stronger fill/border.
8. Draw the validation gate as a diamond polygon at the gate coordinate and label it `saidit_post validation gate`.
9. Draw labels for the `visibleEdgeIds(graph, state)` set, including the three post labels in default view. Labels use neutral ink inside a white translucent rectangle; they must not use chain color as text.

- [ ] **Step 4: Implement D3 zoom and node dragging.**

Attach zoom to the SVG:

```js
const zoom = d3.zoom()
  .scaleExtent([0.45, 3.5])
  .on("zoom", (event) => {
    transform = event.transform;
    render();
  });
svg.call(zoom);
```

Attach `d3.drag()` to person node groups. On drag start set `simulation.alphaTarget(0.25).restart()`. During drag set `node.fx` and `node.fy` from `transform.invert([event.x, event.y])`. On drag end set `simulation.alphaTarget(0)` and retain `fx`/`fy` so the chosen position persists for the current page session. Do not attach drag behavior to John.

- [ ] **Step 5: Manually verify render and layout behavior without exporting an image.**

Run:

```bash
python -m http.server 8000
```

Open the Q6 page and verify:

- it loads 19 unique person nodes, John, and one gate;
- SwiftWren-only nodes settle around the middle, HiddenOrca-only nodes upper, and MellowOtter-only nodes lower;
- Canvas contains low-emphasis background routes;
- the three colored John-to-gate arrows are SVG foreground paths with readable sequence labels;
- no ordinary labels appear by default;
- pan, zoom, and dragging an ordinary person work; John is not draggable; gate follows John.

Stop the server after checking.

### Task 7: Implement controls, hover disclosure, tooltip, reset, and final verification

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html`
- Modify: `docs/superpowers/specs/2026-07-24-q6-d3-constrained-network-design.md`

- [ ] **Step 1: Wire chain controls and reset behavior.**

Implement event listeners for `[data-chain]` controls:

```js
for (const button of root.querySelectorAll("[data-chain]")) {
  button.addEventListener("click", () => {
    state.activeChain = state.activeChain === button.dataset.chain ? null : button.dataset.chain;
    root.querySelectorAll("[data-chain]").forEach((control) => {
      control.setAttribute("aria-pressed", String(control.dataset.chain === state.activeChain));
    });
    render();
  });
}
```

For `[data-action="reset"]`, clear all state fields, clear `fx`/`fy` on non-John nodes, reset the transform with `svg.transition().duration(250).call(zoom.transform, d3.zoomIdentity)`, and call `simulation.alpha(0.75).restart()`.

- [ ] **Step 2: Add node hover disclosure.**

On person node `pointerenter`, assign `state.hoveredNodeId = node.id` and call `render()`. On `pointerleave`, clear it and re-render. Update node class/opacity so unrelated nodes visibly recede while the hovered node and its immediate neighbors remain legible.

- [ ] **Step 3: Add Canvas edge hover and HTML tooltip.**

On stage `pointermove`:

```js
const [screenX, screenY] = d3.pointer(event, stage);
const world = transform.invert([screenX, screenY]);
const route = nearestEdge(routes, { x: world[0], y: world[1] }, 10 / transform.k);
state.hoveredEdgeId = route?.edge.eventId ?? null;
if (route) {
  const edge = route.edge;
  tooltip.hidden = false;
  tooltip.style.left = `${screenX + 14}px`;
  tooltip.style.top = `${screenY + 14}px`;
  tooltip.innerHTML = `<strong>${edge.chainFile}</strong><br>Event ${edge.sequence} · ${edge.shortName}<br>${displayName(edge.source)} → ${edge.target === GATE_ID ? "Validation gate" : displayName(edge.target)}<br>${new Date(edge.when * 1000).toISOString()}`;
} else {
  tooltip.hidden = true;
}
render();
```

On `pointerleave`, clear the hovered edge and hide the tooltip. Use text content construction or escaped values if source data may be untrusted; do not inject raw event strings into `innerHTML` without escaping.

- [ ] **Step 4: Add accessibility and interaction regression checks.**

Extend the pure Node test file with this test to prevent the default disclosure policy from regressing:

```js
test("keeps post edges visible after a chain is cleared", () => {
  const graph = {
    edges: [
      { eventId: 1, source: "a", target: "b", chainFile: "SwiftWren.txt", isPost: false },
      { eventId: 2, source: "john_windward", target: GATE_ID, chainFile: "SwiftWren.txt", isPost: true },
      { eventId: 3, source: "john_windward", target: GATE_ID, chainFile: "HiddenOrca.txt", isPost: true },
      { eventId: 4, source: "john_windward", target: GATE_ID, chainFile: "MellowOtter.txt", isPost: true },
    ],
  };
  assert.deepEqual([...visibleEdgeIds(graph, { activeChain: null, hoveredNodeId: null, hoveredEdgeId: null })], [2, 3, 4]);
});
```

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: all 9 tests pass, 0 failures.

- [ ] **Step 5: Update the design specification with confirmed implementation details.**

In `docs/superpowers/specs/2026-07-24-q6-d3-constrained-network-design.md`, add this implementation note under “Technology and render architecture”:

```markdown
Implementation uses `q6_john_posting_intervention_network.html` and its adjacent ES module, `q6_john_posting_intervention_network.js`. D3 v7 is loaded as an ES module from `https://cdn.jsdelivr.net/npm/d3@7/+esm`; pure data and interaction helpers are checked with `node --test test/test_q6_john_posting_intervention_network.mjs`.
```

- [ ] **Step 6: Perform final browser verification.**

Run:

```bash
python -m http.server 8000
```

Verify all of the following in the browser, without generating or opening any PNG:

- the page loads through HTTP without console errors;
- the default view draws all routes but only labels all three John-to-gate post edges;
- selecting each of the three chain controls reveals its full set of sequence labels and leaves other chains faintly visible;
- selecting an active chain again restores default state;
- hovering a person reveals exactly its incident-edge labels;
- hovering a Canvas route shows its chain, event number, timestamp, type, source, and target;
- tooltip remains visible and correctly placed while panning and zooming;
- reset clears selection, resets zoom, and releases dragged ordinary people;
- legend, validation rule, and observed-case caveat are readable;
- no PNG export control or additional non-person graph node exists.

Stop the server after the check.

- [ ] **Step 7: Run final automated checks and inspect the working diff.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
git diff --check
git status --short
```

Expected: all Node tests pass; `git diff --check` reports no whitespace errors; status shows only intended Q6 HTML, module, test, and specification changes plus any pre-existing unrelated changes.
