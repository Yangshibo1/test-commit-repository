import fs from "node:fs";
import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { CHAIN_ORDER, GATE_ID, buildGraph, buildNodeModel, buildRoute, clampNodeToViewport, deriveEventEdge, detailEdges, dragEventWorldPosition, escapeHtml, formatEdgeDetailsText, formatEdgeTooltip, interventionAnchor, mountNetwork, nearestEdge, originAnchor, personId, resetNodePins, syncGateToJohn, toggleSelectedNode, visibleEdgeIds } from "../VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const event = (id, when, shortName, parties) => ({ id, when, short_name: shortName, parties });
const minimalDataset = () => ({ chains: Object.fromEntries(CHAIN_ORDER.map((chain) => [chain, { events: [] }])) });

function fakeMountRoot({ includeStage = true } = {}) {
  const status = { hidden: true, textContent: "", setAttribute() {} };
  const stage = { getBoundingClientRect: () => ({ width: 640, height: 760 }) };
  const canvas = { style: {}, width: 0, height: 0 };
  const svgElement = {};
  const elements = { ".network-stage": includeStage ? stage : null, ".edge-canvas": canvas, ".network-svg": svgElement, ".tooltip": {}, ".event-detail-list": {}, ".network-status": status };
  return { status, stage, canvas, querySelector: (selector) => elements[selector] ?? null };
}

function fakeD3(datasetOrError) {
  return { json: async () => { if (datasetOrError instanceof Error) throw datasetOrError; return datasetOrError; }, select: () => ({ attr() { return this; } }) };
}

test("normalizes person prefixes without removing duplicate parties", () => {
  assert.equal(personId("Agent/person:emma_harbor"), "emma_harbor"); assert.equal(personId("person:emma_harbor"), "emma_harbor"); assert.equal(personId("system:file_system"), null);
});
test("derives two-person edges and projects John posts to the gate", () => {
  assert.deepEqual(deriveEventEdge("SwiftWren.txt", event(1, 10, "handoff", ["system:file_system", "Agent/person:emma_harbor", "person:chloe_ballast"])), { eventId: 1, chainFile: "SwiftWren.txt", when: 10, shortName: "handoff", source: "emma_harbor", target: "chloe_ballast", isPost: false });
  assert.deepEqual(deriveEventEdge("SwiftWren.txt", event(2, 20, "saidit_post", ["person:john_windward"])), { eventId: 2, chainFile: "SwiftWren.txt", when: 20, shortName: "saidit_post", source: "john_windward", target: GATE_ID, isPost: true });
  assert.equal(deriveEventEdge("SwiftWren.txt", event(3, 30, "read_file", ["person:emma_harbor"])), null); assert.equal(deriveEventEdge("SwiftWren.txt", event(4, 40, "handoff", ["person:a", "person:b", "person:c"])), null); assert.equal(deriveEventEdge("SwiftWren.txt", event(5, 50, "create_file", ["system:file_system"])), null);
});
test("orders each chain independently, retains duplicates, and records omissions", () => {
  const dataset = { chains: { "SwiftWren.txt": { events: [event(5, 50, "saidit_post", ["person:john_windward"]), event(4, 40, "read_file", ["person:alpha"]), event(3, 30, "handoff", ["person:beta", "person:beta"]), event(2, 20, "handoff", ["person:alpha", "person:beta"]), event(1, 10, "handoff", ["person:alpha", "person:beta"])] }, "HiddenOrca.txt": { events: [event(7, 70, "saidit_post", ["person:john_windward"])] }, "MellowOtter.txt": { events: [event(8, 80, "saidit_post", ["person:john_windward"])] } } };
  const graph = buildGraph(dataset); assert.deepEqual(graph.edgesByChain.get("SwiftWren.txt").map((edge) => edge.eventId), [1, 2, 3, 5]); assert.deepEqual(graph.edgesByChain.get("SwiftWren.txt").map((edge) => edge.sequence), [1, 2, 3, 4]); assert.equal(graph.edges.filter((edge) => edge.source === "alpha" && edge.target === "beta").length, 2); assert.equal(graph.edges.filter((edge) => edge.isPost).length, 3); assert.equal(graph.omittedEvents[0].eventId, 4); assert.deepEqual([...graph.memberships.get("alpha")], ["SwiftWren.txt"]);
});
test("matches the observed dataset graph contract", () => {
  const graph = buildGraph(JSON.parse(fs.readFileSync(path.join(root, "result/three_txt_posting_chains_dataset.json"), "utf8"))); assert.equal(graph.people.size, 19); assert.equal(graph.edges.length, 238); assert.equal(graph.omittedEvents.length, 10); assert.deepEqual(Object.fromEntries(CHAIN_ORDER.map((chain) => [chain, graph.edgesByChain.get(chain).length])), { "SwiftWren.txt": 187, "HiddenOrca.txt": 40, "MellowOtter.txt": 11 }); assert.deepEqual(Object.fromEntries(CHAIN_ORDER.map((chain) => [chain, graph.edgesByChain.get(chain).at(-1).sequence])), { "SwiftWren.txt": 187, "HiddenOrca.txt": 40, "MellowOtter.txt": 11 });
});
test("assigns one constrained node per person with chain-story bands", () => {
  const nodes = buildNodeModel({ people: new Set(["emma_harbor", "john_windward", "swift", "hidden", "mellow", "shared"]), memberships: new Map([["emma_harbor", new Set(["SwiftWren.txt"])], ["john_windward", new Set(CHAIN_ORDER)], ["swift", new Set(["SwiftWren.txt"])], ["hidden", new Set(["HiddenOrca.txt"])], ["mellow", new Set(["MellowOtter.txt"])], ["shared", new Set(["SwiftWren.txt", "HiddenOrca.txt"])]]) }); assert.equal(new Set(nodes.map((node) => node.id)).size, 6); assert.equal(nodes.find((node) => node.id === "emma_harbor").fixed, true); assert.equal(nodes.find((node) => node.id === "john_windward").fixed, false); assert.equal(nodes.find((node) => node.id === "hidden").band, "upper"); assert.equal(nodes.find((node) => node.id === "mellow").band, "lower"); assert.equal(nodes.find((node) => node.id === "swift").band, "middle"); assert.equal(nodes.find((node) => node.id === "shared").band, "middle");
});
test("uses Emma as the only fixed person anchor and leaves John draggable", () => {
  const graph = {
    people: new Set(["emma_harbor", "john_windward", "other_person"]),
    memberships: new Map([
      ["emma_harbor", new Set(["SwiftWren.txt"])],
      ["john_windward", new Set(CHAIN_ORDER)],
      ["other_person", new Set(["SwiftWren.txt"])],
    ]),
  };
  const nodes = buildNodeModel(graph);
  const emma = nodes.find((node) => node.id === "emma_harbor");
  const john = nodes.find((node) => node.id === "john_windward");
  assert.equal(emma.fixed, true);
  assert.equal(john.fixed, false);
  assert.equal(john.band, "middle");
  assert.equal(john.fx, null);
  assert.equal(john.fy, null);
});
test("gives parallel routes separate labels and gives self transfers a loop", () => {
  const nodes = new Map([["alpha", { x: 0, y: 0 }], ["beta", { x: 100, y: 0 }], [GATE_ID, { x: 270, y: 0 }]]); const samePair = [0, 1, 2].map((pairIndex) => buildRoute({ eventId: pairIndex, source: "alpha", target: "beta" }, nodes, pairIndex)); assert.equal(new Set(samePair.map((route) => route.control.y)).size, 3); assert.equal(new Set(samePair.map((route) => `${route.label.x},${route.label.y}`)).size, 3); const loop = buildRoute({ eventId: 9, source: "alpha", target: "alpha" }, nodes, 0); assert.equal(loop.kind, "loop"); assert.notDeepEqual(loop.start, loop.end);
});
test("reveals only final post labels by default and expands detail by context", () => {
  const graph = { edges: [{ eventId: 1, source: "a", target: "b", chainFile: "SwiftWren.txt", isPost: false }, { eventId: 2, source: "b", target: "john_windward", chainFile: "HiddenOrca.txt", isPost: false }, { eventId: 3, source: "john_windward", target: GATE_ID, chainFile: "MellowOtter.txt", isPost: true }] }; assert.deepEqual([...visibleEdgeIds(graph, { activeChain: null, hoveredNodeId: null, hoveredEdgeId: null })], [3]); assert.deepEqual([...visibleEdgeIds(graph, { activeChain: "SwiftWren.txt", hoveredNodeId: null, hoveredEdgeId: null })], [1, 3]); assert.deepEqual([...visibleEdgeIds(graph, { activeChain: null, hoveredNodeId: "b", hoveredEdgeId: null })], [1, 2, 3]);
});
test("returns the closest route only inside a world-coordinate tolerance", () => { const routes = [{ edge: { eventId: 1 }, kind: "quadratic", start: { x: 0, y: 0 }, control: { x: 50, y: 0 }, end: { x: 100, y: 0 } }, { edge: { eventId: 2 }, kind: "quadratic", start: { x: 0, y: 50 }, control: { x: 50, y: 50 }, end: { x: 100, y: 50 } }]; assert.equal(nearestEdge(routes, { x: 52, y: 4 }, 8).edge.eventId, 1); assert.equal(nearestEdge(routes, { x: 52, y: 30 }, 8), null); });
test("includes hits exactly at the world tolerance, including zero", () => { const route = { edge: { eventId: 1 }, kind: "quadratic", start: { x: 0, y: 0 }, control: { x: 50, y: 0 }, end: { x: 100, y: 0 } }; assert.equal(nearestEdge([route], { x: 50, y: 8 }, 8), route); assert.equal(nearestEdge([route], { x: 50, y: 0 }, 0), route); });
test("hits a curved quadratic route only within the supplied world tolerance", () => { const route = { edge: { eventId: 3 }, kind: "quadratic", start: { x: 0, y: 0 }, control: { x: 50, y: 40 }, end: { x: 100, y: 0 } }; assert.equal(nearestEdge([route], { x: 50, y: 26 }, 6), route); assert.equal(nearestEdge([route], { x: 50, y: 26.1 }, 6), null); });
test("exports a narrow and wide responsive Emma origin anchor", () => {
  assert.deepEqual(originAnchor({ width: 640, height: 760 }), { x: 32, y: 380 });
  assert.deepEqual(originAnchor({ width: 1440, height: 760 }), { x: 32, y: 380 });
});

test("reanchors only Emma on resize while preserving manually pinned John and gate offset", async () => {
  const originalResizeObserver = globalThis.ResizeObserver;
  const observers = [];
  let width = 1440;
  globalThis.ResizeObserver = class { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} };
  try {
    const shell = fakeMountRoot();
    shell.stage.getBoundingClientRect = () => ({ width, height: 760 });
    const posts = CHAIN_ORDER.map((chain, index) => event(index + 1, index + 1, "handoff", ["person:emma_harbor", "person:john_windward"]));
    const dataset = { chains: Object.fromEntries(CHAIN_ORDER.map((chain, index) => [chain, { events: [posts[index]] }])) };
    const result = await mountNetwork({ d3: fakeD3(dataset), root: shell, datasetUrl: "fixture.json" });
    const john = result.nodes.find((node) => node.id === "john_windward");
    john.x = 455; john.y = 77; john.fx = 455; john.fy = 77;
    width = 640;
    observers[0].callback();
    const emma = result.nodes.find((node) => node.id === "emma_harbor");
    const emmaLabelHalfWidth = Math.max(42, emma.label.length * 4.8);
    assert.deepEqual({ y: emma.y, fy: emma.fy }, { y: 0, fy: 0 });
    assert.equal(emma.x, emma.fx);
    assert.equal(emma.targetX, emma.fx);
    assert.ok(originAnchor({ width, height: 760 }).x + emma.x - emmaLabelHalfWidth >= 12);
    assert.deepEqual({ x: john.x, y: john.y, fx: john.fx, fy: john.fy }, { x: 455, y: 77, fx: 455, fy: 77 });
    assert.equal(result.gate.x, john.x + 90);
    assert.equal(result.gate.y, john.y);
  } finally { globalThis.ResizeObserver = originalResizeObserver; }
});
test("mounts narrow-stage Emma, John, and gate within their safe horizontal bounds", async () => {
  const originalResizeObserver = globalThis.ResizeObserver;
  globalThis.ResizeObserver = class { constructor() {} observe() {} };
  try {
    const shell = fakeMountRoot();
    shell.stage.getBoundingClientRect = () => ({ width: 640, height: 760 });
    const posts = CHAIN_ORDER.map((chain, index) => event(index + 10, index + 10, "saidit_post", ["person:john_windward"]));
    const dataset = { chains: Object.fromEntries(CHAIN_ORDER.map((chain, index) => [chain, { events: [event(index + 1, index + 1, "handoff", ["person:emma_harbor", "person:john_windward"]), posts[index]] }])) };
    const result = await mountNetwork({ d3: fakeD3(dataset), root: shell, datasetUrl: "fixture.json" });
    const emma = result.nodes.find((node) => node.id === "emma_harbor");
    const john = result.nodes.find((node) => node.id === "john_windward");
    const emmaLabelHalfWidth = Math.max(42, emma.label.length * 4.8);
    const anchor = interventionAnchor({ width: 640, height: 760 }, originAnchor({ width: 640, height: 760 }));
    assert.ok(originAnchor({ width: 640, height: 760 }).x + emma.x - emmaLabelHalfWidth >= 12);
    assert.equal(john.x, anchor.johnX);
    assert.equal(john.targetX, anchor.johnX);
    assert.equal(result.gate.x, anchor.gateX);
    assert.ok(result.gate.x + anchor.gateLabelReservation <= 640 - 12);
  } finally { globalThis.ResizeObserver = originalResizeObserver; }
});
test("anchors John and the gate inside a narrow stage while preserving right-side emphasis", () => {
  const narrow = interventionAnchor({ width: 640, height: 760 }, { x: 32, y: 380 });
  assert.ok(narrow.johnX < 620);
  assert.equal(narrow.gateX, narrow.johnX + 90);
  assert.ok(narrow.gateX + narrow.gateLabelReservation <= 640 - 12);
  const wide = interventionAnchor({ width: 1440, height: 760 }, { x: 32, y: 380 });
  assert.equal(wide.johnX, 620);
  assert.equal(wide.gateX, 710);
});
test("clamps ordinary nodes to a label-safe stage-derived world boundary", () => {
  const node = { x: -50, y: 500, label: "Long Name", fixed: false };
  clampNodeToViewport(node, { width: 640, height: 760 }, { x: 32, y: 380 });
  assert.equal(node.x, -50);
  assert.equal(node.y, 364);
  const john = { x: 620, y: 0, label: "John Windward", fixed: true };
  clampNodeToViewport(john, { width: 640, height: 760 }, { x: 32, y: 380 });
  assert.deepEqual(john, { x: 620, y: 0, label: "John Windward", fixed: true });
});

test("allows a wider horizontal drag workspace while preserving label safety", () => {
  const node = { x: 2000, y: 0, label: "Person", fixed: false };
  clampNodeToViewport(node, { width: 960, height: 920 }, { x: 32, y: 460 });
  assert.equal(node.x, 1222);
});

test("gives the network a larger vertical drag workspace", () => {
  const html = fs.readFileSync(path.join(root, "VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html"), "utf8");
  assert.match(html, /\.network-stage \{[^}]*min-height:\s*920px;/);
  const node = { x: 0, y: 900, label: "Person", fixed: false };
  clampNodeToViewport(node, { width: 960, height: 920 }, { x: 32, y: 460 });
  assert.equal(node.y, 444);
});


test("mountNetwork requires a root element", async () => { await assert.rejects(mountNetwork({ d3: {}, root: null, datasetUrl: "fixture.json" }), { message: "Q6 network root element is required" }); });
test("mountNetwork requires D3 after validating the root", async () => { await assert.rejects(mountNetwork({ d3: null, root: {}, datasetUrl: "fixture.json" }), { message: "D3 is required to mount the Q6 network" }); });
test("reports a fetch failure in the root-visible status element", async () => { const shell = fakeMountRoot(); await assert.rejects(mountNetwork({ d3: fakeD3(new Error("network unavailable")), root: shell, datasetUrl: "fixture.json" })); assert.equal(shell.status.hidden, false); assert.match(shell.status.textContent, /Unable to load Q6 network data/); });
test("reports a malformed dataset in the root-visible status element", async () => { const shell = fakeMountRoot(); await assert.rejects(mountNetwork({ d3: fakeD3({ chains: null }), root: shell, datasetUrl: "fixture.json" })); assert.equal(shell.status.hidden, false); assert.match(shell.status.textContent, /Q6 network dataset is malformed/); });
test("reports missing required shell elements in the root-visible status element", async () => { const shell = fakeMountRoot({ includeStage: false }); await assert.rejects(mountNetwork({ d3: fakeD3(minimalDataset()), root: shell, datasetUrl: "fixture.json" })); assert.equal(shell.status.hidden, false); assert.match(shell.status.textContent, /Q6 network shell is incomplete/); });
test("keeps John and the gate responsive without treating either as a fixed anchor", async () => {
  const originalResizeObserver = globalThis.ResizeObserver;
  const observers = [];
  let width = 1440;
  globalThis.ResizeObserver = class { constructor(callback) { this.callback = callback; observers.push(this); } observe() {} };
  try {
    const shell = fakeMountRoot();
    shell.stage.getBoundingClientRect = () => ({ width, height: 760 });
    const posts = CHAIN_ORDER.map((chain, index) => event(index + 1, index + 1, "saidit_post", ["person:john_windward"]));
    const dataset = { chains: Object.fromEntries(CHAIN_ORDER.map((chain, index) => [chain, { events: [posts[index]] }])) };
    const result = await mountNetwork({ d3: fakeD3(dataset), root: shell, datasetUrl: "fixture.json" });
    const john = result.nodes.find((node) => node.id === "john_windward");
    assert.equal(john.fixed, false);
    assert.equal(john.fx, null);
    assert.equal(john.fy, null);
    const originalPosition = { x: john.x, y: john.y };
    width = 640;
    observers[0].callback();
    const narrowAnchor = interventionAnchor({ width, height: 760 }, originAnchor({ width, height: 760 }));
    assert.deepEqual({ x: john.x, y: john.y, fx: john.fx, fy: john.fy }, { ...originalPosition, fx: null, fy: null });
    assert.equal(john.targetX, narrowAnchor.johnX);
    assert.equal(result.gate.x, john.x + 90);
    assert.equal(result.gate.y, john.y);
    assert.equal(result.gate.fx, result.gate.x);
  } finally { globalThis.ResizeObserver = originalResizeObserver; }
});


test("keeps exactly the three post labels visible after chain state clears", () => {
  const graph = { edges: [
    { eventId: 1, source: "a", target: "b", chainFile: "SwiftWren.txt", isPost: false },
    { eventId: 2, source: "john_windward", target: GATE_ID, chainFile: "SwiftWren.txt", isPost: true },
    { eventId: 3, source: "john_windward", target: GATE_ID, chainFile: "HiddenOrca.txt", isPost: true },
    { eventId: 4, source: "john_windward", target: GATE_ID, chainFile: "MellowOtter.txt", isPost: true },
  ] };
  assert.deepEqual([...visibleEdgeIds(graph, { activeChain: null, hoveredNodeId: null, hoveredEdgeId: null })], [2, 3, 4]);
});



test("builds safe textual keyboard details for the active chain and focused person", () => {
  const edges = [
    { eventId: 1, chainFile: "SwiftWren.txt", sequence: 1, shortName: "handoff", source: "alice", target: "bob", when: 0, isPost: false },
    { eventId: 2, chainFile: "HiddenOrca.txt", sequence: 4, shortName: "saidit_post", source: "john_windward", target: GATE_ID, when: 1, isPost: true },
  ];
  assert.deepEqual(detailEdges({ edges }, { activeChain: "SwiftWren.txt", hoveredNodeId: null }), [edges[0]]);
  assert.deepEqual(detailEdges({ edges }, { activeChain: null, hoveredNodeId: "john_windward" }), [edges[1]]);
  assert.equal(formatEdgeDetailsText({ ...edges[0], shortName: "<untrusted>" }), "SwiftWren.txt · Event 1 · <untrusted>: Alice → Bob · 1970-01-01T00:00:00.000Z");
});

test("keeps SVG descendants interactive with title and description labelling", () => {
  const html = fs.readFileSync(path.join(root, "VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html"), "utf8");
  assert.match(html, /<svg class="network-svg" aria-labelledby="network-title network-description">/);
  assert.match(html, /<title id="network-title">/);
  assert.match(html, /<desc id="network-description">/);
  assert.doesNotMatch(html, /<svg[^>]*\brole="img"/);
  const module = fs.readFileSync(path.join(root, "VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js"), "utf8");
  assert.match(module, /classed\("is-focused", true\)/);
  assert.match(module, /classed\("is-focused", false\)/);
  assert.match(module, /stroke-width", \(node\) => node\.isFocused \? 3 :/);
});

test("toggles persistent selected-node state for click and keyboard activation", () => {
  assert.equal(toggleSelectedNode(null, "alice"), "alice");
  assert.equal(toggleSelectedNode("alice", "alice"), null);
  assert.equal(toggleSelectedNode("alice", "bob"), "bob");
});

test("reset releases John but retains Emma's fixed anchor", () => {
  const nodes = [
    { id: "emma_harbor", fixed: true, fx: 0, fy: 0 },
    { id: "john_windward", fixed: false, fx: 310, fy: 48 },
  ];
  resetNodePins(nodes);
  assert.deepEqual(nodes[0], { id: "emma_harbor", fixed: true, fx: 0, fy: 0 });
  assert.deepEqual(nodes[1], { id: "john_windward", fixed: false, fx: null, fy: null });
});

test("synchronously positions the fixed gate beside John's current drag position", () => {
  const john = { x: 310, y: 48 };
  const gate = { x: 0, y: 0, fx: 0, fy: 0 };
  assert.equal(syncGateToJohn(gate, john), gate);
  assert.deepEqual(gate, { x: 400, y: 48, fx: 400, fy: 48 });
});
