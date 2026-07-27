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
    return { eventId: event.id, chainFile, when: Number(event.when), shortName: event.short_name ?? "", source: people[0], target: people[1], isPost: false };
  }
  if (people.length === 1 && people[0] === "john_windward" && event.short_name === "saidit_post") {
    return { eventId: event.id, chainFile, when: Number(event.when), shortName: "saidit_post", source: "john_windward", target: GATE_ID, isPost: true };
  }
  return null;
}

export function buildGraph(dataset) {
  const people = new Set();
  const edges = [];
  const edgesByChain = new Map(CHAIN_ORDER.map((chain) => [chain, []]));
  const omittedEvents = [];
  const memberships = new Map();
  for (const chainFile of CHAIN_ORDER) {
    const ordered = [...(dataset.chains?.[chainFile]?.events ?? [])].sort((left, right) =>
      (left.when ?? Number.POSITIVE_INFINITY) - (right.when ?? Number.POSITIVE_INFINITY) || (left.id ?? 0) - (right.id ?? 0));
    for (const event of ordered) {
      const edge = deriveEventEdge(chainFile, event);
      if (!edge) {
        omittedEvents.push({ eventId: event.id, chainFile, shortName: event.short_name ?? "", personCount: personIds(event.parties).length });
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

const BAND_Y = { upper: -250, middle: 0, lower: 250 };
const BAND_BY_SINGLE_MEMBERSHIP = { "HiddenOrca.txt": "upper", "SwiftWren.txt": "middle", "MellowOtter.txt": "lower" };

export function displayName(id) {
  return id.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" ");
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

export function formatEdgeTooltip(edge) {
  const source = displayName(edge.source);
  const target = edge.target === GATE_ID ? "Validation gate" : displayName(edge.target);
  const timestamp = new Date(Number(edge.when) * 1000).toISOString();
  return `<strong>${escapeHtml(edge.chainFile)}</strong><br>Event ${escapeHtml(edge.sequence)} · ${escapeHtml(edge.shortName)}<br>${escapeHtml(source)} → ${escapeHtml(target)}<br>${escapeHtml(timestamp)}`;
}

export function formatEdgeDetailsText(edge) {
  const source = displayName(edge.source);
  const target = edge.target === GATE_ID ? "Validation gate" : displayName(edge.target);
  const timestamp = new Date(Number(edge.when) * 1000).toISOString();
  return `${edge.chainFile} · Event ${edge.sequence} · ${edge.shortName}: ${source} → ${target} · ${timestamp}`;
}

export function detailEdges(graph, state) {
  const selectedNodeId = state.selectedNodeId ?? null;
  return graph.edges.filter((edge) => (
    (!state.activeChain || edge.chainFile === state.activeChain)
    && (!state.hoveredNodeId || edge.source === state.hoveredNodeId || edge.target === state.hoveredNodeId)
    && (!selectedNodeId || edge.source === selectedNodeId || edge.target === selectedNodeId)
  ));
}

export function toggleSelectedNode(selectedNodeId, nodeId) {
  return selectedNodeId === nodeId ? null : nodeId;
}

export function buildNodeModel(graph) {
  return [...graph.people].sort().map((id, index) => {
    const chains = graph.memberships.get(id) ?? new Set();
    const band = chains.size === 1 ? BAND_BY_SINGLE_MEMBERSHIP[[...chains][0]] : "middle";
    const fixed = id === "emma_harbor";
    const isJohn = id === "john_windward";
    const targetX = fixed ? 0 : (isJohn ? 520 : 100 + (index % 6) * 85);
    const targetY = fixed ? 0 : BAND_Y[band];
    return {
      id, label: displayName(id), chains: [...chains], band,
      targetX,
      targetY,
      x: targetX,
      y: targetY,
      fx: fixed ? targetX : null,
      fy: fixed ? targetY : null,
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
    return { edge, kind: "loop", pairIndex, start: { x: start.x - 16, y: start.y - 8 }, control: { x: start.x, y: start.y - loopHeight }, end: { x: start.x + 16, y: start.y - 8 }, label: { x: start.x, y: start.y - loopHeight - 8 } };
  }
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const normal = { x: -dy / length, y: dx / length };
  const signedOffset = (pairIndex - 1) * 18;
  const control = { x: (start.x + end.x) / 2 + normal.x * signedOffset, y: (start.y + end.y) / 2 + normal.y * signedOffset };
  return { edge, kind: "quadratic", pairIndex, start, control, end, label: { x: 0.25 * start.x + 0.5 * control.x + 0.25 * end.x, y: 0.25 * start.y + 0.5 * control.y + 0.25 * end.y } };
}

export function visibleEdgeIds(graph, state) {
  const visible = new Set(graph.edges.filter((edge) => edge.isPost).map((edge) => edge.eventId));
  if (state.activeChain) for (const edge of graph.edges) if (edge.chainFile === state.activeChain) visible.add(edge.eventId);
  for (const nodeId of [state.hoveredNodeId, state.selectedNodeId]) {
    if (nodeId) for (const edge of graph.edges) if (edge.source === nodeId || edge.target === nodeId) visible.add(edge.eventId);
  }
  if (state.hoveredEdgeId !== null) visible.add(state.hoveredEdgeId);
  return new Set([...visible].sort((left, right) => left - right));
}

function quadraticPoint(route, t) {
  const oneMinusT = 1 - t;
  return { x: oneMinusT ** 2 * route.start.x + 2 * oneMinusT * t * route.control.x + t ** 2 * route.end.x, y: oneMinusT ** 2 * route.start.y + 2 * oneMinusT * t * route.control.y + t ** 2 * route.end.y };
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
      if (distance <= smallestDistance) { closest = route; smallestDistance = distance; }
      previous = current;
    }
  }
  return closest;
}

export function originAnchor(viewport) {
  return { x: 32, y: viewport.height / 2 };
}

function emmaAnchorX(node, origin) {
  const labelHalfWidth = Math.max(42, node.label.length * 4.8);
  const safeMargin = 12;
  return Math.max(0, safeMargin + labelHalfWidth - origin.x);
}

export function interventionAnchor(viewport, origin) {
  const gateOffset = 90;
  const gateLabelReservation = 178;
  const rightMargin = 12;
  const preferredJohnX = 620;
  const maximumJohnX = viewport.width - origin.x - gateOffset - gateLabelReservation - rightMargin;
  const johnX = Math.min(preferredJohnX, maximumJohnX);
  return { johnX, gateX: johnX + gateOffset, gateLabelReservation };
}

export function clampNodeToViewport(node, viewport, origin) {
  if (node.fixed) return node;
  const labelHalfWidth = Math.max(42, node.label.length * 4.8);
  const labelHalfHeight = 16;
  const horizontalOverflow = Math.max(260, viewport.width * 0.35);
  const minX = labelHalfWidth - origin.x - horizontalOverflow;
  const maxX = viewport.width - labelHalfWidth - origin.x + horizontalOverflow;
  const minY = labelHalfHeight - origin.y;
  const maxY = viewport.height - labelHalfHeight - origin.y;
  node.x = Math.max(minX, Math.min(maxX, node.x));
  node.y = Math.max(minY, Math.min(maxY, node.y));
  return node;
}

export function dragEventWorldPosition(event) {
  return { x: event.x, y: event.y };
}

export function resetNodePins(nodes) {
  for (const node of nodes) {
    if (!node.fixed) {
      node.fx = null;
      node.fy = null;
    }
  }
  return nodes;
}

export function syncGateToJohn(gate, john) {
  gate.x = john.x + 90;
  gate.y = john.y;
  gate.fx = gate.x;
  gate.fy = gate.y;
  return gate;
}

function reportMountError(root, message) {
  const status = root?.querySelector?.(".network-status");
  if (status) { status.textContent = message; status.hidden = false; }
}

function isValidDataset(dataset) {
  return Boolean(dataset && typeof dataset === "object" && dataset.chains && typeof dataset.chains === "object" && CHAIN_ORDER.every((chain) => Array.isArray(dataset.chains[chain]?.events)));
}

function routePath(route) {
  return `M${route.start.x},${route.start.y} Q${route.control.x},${route.control.y} ${route.end.x},${route.end.y}`;
}

function routesFor(graph, nodesById) {
  const occurrenceByPair = new Map();
  return graph.edges.map((edge) => {
    const key = `${edge.source}→${edge.target}`;
    const pairIndex = occurrenceByPair.get(key) ?? 0;
    occurrenceByPair.set(key, pairIndex + 1);
    return buildRoute(edge, nodesById, pairIndex);
  });
}

export async function mountNetwork({ d3, root, datasetUrl }) {
  if (!root) throw new Error("Q6 network root element is required");
  if (!d3) throw new Error("D3 is required to mount the Q6 network");
  let dataset;
  try { dataset = await d3.json(datasetUrl); } catch (error) {
    const message = "Unable to load Q6 network data.";
    reportMountError(root, message);
    throw new Error(message, { cause: error });
  }
  if (!isValidDataset(dataset)) {
    const message = "Q6 network dataset is malformed.";
    reportMountError(root, message);
    throw new Error(message);
  }
  const stage = root.querySelector(".network-stage");
  const canvas = root.querySelector(".edge-canvas");
  const svgElement = root.querySelector(".network-svg");
  const tooltip = root.querySelector(".tooltip");
  const eventDetailList = root.querySelector(".event-detail-list");
  if (!stage || !canvas || !svgElement || !tooltip || !eventDetailList) {
    const message = "Q6 network shell is incomplete.";
    reportMountError(root, message);
    throw new Error(message);
  }
  const svg = d3.select(svgElement);
  const detailList = d3.select(eventDetailList);
  const state = { activeChain: null, hoveredNodeId: null, hoveredEdgeId: null, selectedNodeId: null };
  const graph = buildGraph(dataset);
  const nodes = buildNodeModel(graph);
  const initialViewport = { width: stage.getBoundingClientRect().width, height: stage.getBoundingClientRect().height };
  const initialOrigin = originAnchor(initialViewport);
  const emma = nodes.find((node) => node.id === "emma_harbor");
  if (emma) {
    const x = emmaAnchorX(emma, initialOrigin);
    Object.assign(emma, { targetX: x, targetY: 0, x, y: 0, fx: x, fy: 0 });
  }
  const john = nodes.find((node) => node.id === "john_windward");
  const initialAnchor = interventionAnchor(initialViewport, initialOrigin);
  if (john) Object.assign(john, { targetX: initialAnchor.johnX, x: initialAnchor.johnX, targetY: 0, y: 0 });
  const gate = { id: GATE_ID, label: "saidit_post validation gate", x: initialAnchor.gateX, y: 0, fx: initialAnchor.gateX, fy: 0, fixed: true };
  const nodesById = new Map([...nodes, gate].map((node) => [node.id, node]));
  let viewport = { width: 0, height: 0, pixelRatio: 1 };

  function resize() {
    const { width, height } = stage.getBoundingClientRect();
    const pixelRatio = globalThis.devicePixelRatio || 1;
    viewport = { width, height, pixelRatio };
    canvas.width = Math.round(width * pixelRatio);
    canvas.height = Math.round(height * pixelRatio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    svg.attr("width", width).attr("height", height).attr("viewBox", `0 0 ${width} ${height}`);
    const origin = originAnchor(viewport);
    const emma = nodesById.get("emma_harbor");
    if (emma) {
      const x = emmaAnchorX(emma, origin);
      emma.x = x;
      emma.y = 0;
      emma.fx = x;
      emma.fy = 0;
      emma.targetX = x;
      emma.targetY = 0;
    }
    const john = nodesById?.get("john_windward");
    if (john && john.fx === null && john.fy === null) {
      john.targetX = interventionAnchor(viewport, origin).johnX;
    }
    if (john) syncGateToJohn(gate, john);
  }
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(stage);
  resize();

  // Lightweight fake DOM/D3 objects are intentionally supported by the pure Node tests.
  if (typeof canvas.getContext !== "function" || typeof d3.forceSimulation !== "function") return { dataset, graph, nodes, gate };

  if (graph.people.size !== nodes.length) throw new Error("Each person must map to exactly one node");
  if (graph.edges.length !== 238) console.warn(`Expected 238 viable edges, received ${graph.edges.length}`);
  if (graph.edges.filter((edge) => edge.isPost).length !== 3) throw new Error("Expected three John-to-gate post edges");

  const context = canvas.getContext("2d");
  const defs = svg.append("defs");
  for (const chainFile of CHAIN_ORDER) {
    defs.append("marker").attr("id", `post-arrow-${chainFile.replace(/[^a-z]/gi, "")}`)
      .attr("viewBox", "0 -5 10 10").attr("refX", 9).attr("refY", 0)
      .attr("markerWidth", 6).attr("markerHeight", 6).attr("orient", "auto")
      .append("path").attr("d", "M0,-5L10,0L0,5Z").attr("fill", CHAIN_COLORS[chainFile]);
  }
  const world = svg.append("g").attr("class", "world");
  const postLayer = world.append("g").attr("class", "post-routes");
  const labelLayer = world.append("g").attr("class", "edge-labels");
  const nodeLayer = world.append("g").attr("class", "person-nodes");
  const gateLayer = world.append("g").attr("class", "validation-gate");
  let transform = d3.zoomIdentity;

  const linkEdges = graph.edges.filter((edge) => !edge.isPost).map((edge) => ({ ...edge }));
  const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(linkEdges).id((node) => node.id).distance(118).strength(0.28))
    .force("charge", d3.forceManyBody().strength(-360))
    .force("collide", d3.forceCollide().radius((node) => Math.max(48, node.label.length * 4.4)).iterations(2))
    .force("x", d3.forceX((node) => node.targetX).strength((node) => node.fixed ? 1 : 0.13))
    .force("y", d3.forceY((node) => node.targetY).strength((node) => node.fixed ? 1 : 0.18));

  function render() {
    const john = nodesById.get("john_windward");
    syncGateToJohn(gate, john);
    const routes = routesFor(graph, nodesById);
    const highlighted = visibleEdgeIds(graph, state);
    const offsetX = 32;
    const offsetY = viewport.height / 2;
    context.setTransform(viewport.pixelRatio, 0, 0, viewport.pixelRatio, 0, 0);
    context.clearRect(0, 0, viewport.width, viewport.height);
    context.save();
    context.translate(offsetX + transform.x, offsetY + transform.y);
    context.scale(transform.k, transform.k);
    for (const route of routes) {
      context.beginPath(); context.moveTo(route.start.x, route.start.y); context.quadraticCurveTo(route.control.x, route.control.y, route.end.x, route.end.y);
      context.globalAlpha = 0.13; context.lineWidth = 1; context.strokeStyle = CHAIN_COLORS[route.edge.chainFile]; context.stroke();
    }
    for (const route of routes) {
      if (route.edge.isPost || !highlighted.has(route.edge.eventId)) continue;
      context.beginPath(); context.moveTo(route.start.x, route.start.y); context.quadraticCurveTo(route.control.x, route.control.y, route.end.x, route.end.y);
      context.globalAlpha = 0.8; context.lineWidth = 2.3; context.strokeStyle = CHAIN_COLORS[route.edge.chainFile]; context.stroke();
    }
    context.restore();
    context.globalAlpha = 1;

    world.attr("transform", `translate(${offsetX + transform.x},${offsetY + transform.y}) scale(${transform.k})`);
    const postRoutes = routes.filter((route) => route.edge.isPost);
    postLayer.selectAll("path").data(postRoutes, (route) => route.edge.eventId).join("path")
      .attr("d", routePath).attr("fill", "none").attr("stroke", (route) => CHAIN_COLORS[route.edge.chainFile])
      .attr("stroke-width", 3).attr("marker-end", (route) => `url(#post-arrow-${route.edge.chainFile.replace(/[^a-z]/gi, "")})`);

    const labelRoutes = routes.filter((route) => highlighted.has(route.edge.eventId));
    const labels = labelLayer.selectAll("g.edge-label").data(labelRoutes, (route) => route.edge.eventId).join((enter) => {
      const group = enter.append("g").attr("class", "edge-label");
      group.append("rect").attr("rx", 4).attr("ry", 4);
      group.append("text").attr("text-anchor", "middle").attr("dominant-baseline", "central");
      return group;
    });
    labels.attr("transform", (route) => `translate(${route.label.x},${route.label.y})`);
    labels.select("text").text((route) => String(route.edge.sequence)).attr("fill", "#172033").attr("font-size", 11).attr("font-weight", 700);
    labels.select("rect").attr("x", (route) => -(String(route.edge.sequence).length * 3.2 + 7)).attr("y", -9).attr("width", (route) => String(route.edge.sequence).length * 6.4 + 14).attr("height", 18).attr("fill", "rgba(255,255,255,.88)").attr("stroke", "#d7dfeb");

    const people = nodeLayer.selectAll("g.person-node").data(nodes, (node) => node.id).join((enter) => {
      const group = enter.append("g").attr("class", "person-node");
      group.append("rect").attr("rx", 10).attr("ry", 10);
      group.append("text").attr("text-anchor", "middle").attr("dominant-baseline", "central");
      return group;
    });
    people.on("pointerenter", personPointerEnter).on("pointerleave", personPointerLeave)
      .on("focus", personPointerEnter).on("blur", personPointerLeave)
      .on("click", personActivate).on("keydown", personKeydown);
    attachDrag();
    people.attr("tabindex", 0).attr("role", "button").attr("aria-label", (node) => node.fixed
      ? `${node.label}, fixed origin anchor`
      : `Show events connected to ${node.label}`)
      .attr("aria-pressed", (node) => String(state.selectedNodeId === node.id))
      .attr("transform", (node) => `translate(${node.x},${node.y})`)
      .attr("opacity", (node) => {
        if (!state.hoveredNodeId) return 1;
        const related = graph.edges.some((edge) => (edge.source === state.hoveredNodeId && edge.target === node.id) || (edge.target === state.hoveredNodeId && edge.source === node.id));
        return node.id === state.hoveredNodeId || related ? 1 : 0.32;
      });
    people.select("rect").attr("x", (node) => -Math.max(42, node.label.length * 4.8)).attr("y", -16).attr("width", (node) => Math.max(84, node.label.length * 9.6)).attr("height", 32)
      .attr("fill", (node) => node.id === "john_windward" ? "#dcecff" : (node.fixed ? "#dcecff" : "#ffffff")).attr("stroke", (node) => node.isFocused ? "#172033" : (node.id === "john_windward" ? "#0b63ce" : (node.fixed ? "#0b63ce" : "#9daabd"))).attr("stroke-width", (node) => node.isFocused ? 3 : (node.fixed || node.id === "john_windward" ? 2.4 : 1.25));
    people.select("text").text((node) => node.label).attr("fill", "#172033").attr("font-size", 12).attr("font-weight", (node) => node.fixed || node.id === "john_windward" ? 800 : 650);

    gateLayer.attr("transform", `translate(${gate.x},${gate.y})`);
    gateLayer.selectAll("polygon").data([gate]).join("polygon").attr("points", "0,-20 20,0 0,20 -20,0").attr("fill", "#fff7df").attr("stroke", "#8c6400").attr("stroke-width", 1.8);
    gateLayer.selectAll("text").data([gate]).join("text").attr("x", 26).attr("y", 4).attr("fill", "#172033").attr("font-size", 12).attr("font-weight", 750).text(gate.label);

    const detailItems = detailList.selectAll("li").data(detailEdges(graph, state), (edge) => edge.eventId).join("li");
    const detailButtons = detailItems.selectAll("button").data((edge) => [edge]).join("button").attr("type", "button");
    detailButtons.text((edge) => formatEdgeDetailsText(edge))
      .on("focus", (event, edge) => { state.hoveredEdgeId = edge.eventId; render(); })
      .on("blur", () => { state.hoveredEdgeId = null; render(); });
  }

  simulation.on("tick", () => {
    const origin = originAnchor(viewport);
    nodes.filter((node) => node.id !== "john_windward").forEach((node) => clampNodeToViewport(node, viewport, origin));
    render();
  });

  function personPointerEnter(event, node) {
    state.hoveredNodeId = node.id;
    if (event.type === "focus") {
      node.isFocused = true;
      d3.select(event.currentTarget).classed("is-focused", true);
    }
    render();
  }
  function personPointerLeave(event, node) {
    state.hoveredNodeId = null;
    if (event.type === "blur") {
      node.isFocused = false;
      d3.select(event.currentTarget).classed("is-focused", false);
    }
    render();
  }
  function personActivate(event, node) {
    state.selectedNodeId = toggleSelectedNode(state.selectedNodeId, node.id);
    render();
  }
  function personKeydown(event, node) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    personActivate(event, node);
  }

  const zoom = d3.zoom().scaleExtent([0.45, 3.5]).on("zoom", (event) => {
    transform = event.transform;
    render();
  });
  svg.call(zoom);


  function attachDrag() {
    if (typeof d3.drag !== "function") return;
    const drag = d3.drag()
      .on("start", (event, node) => {
        if (node.fixed) return;
        if (!event.active) simulation.alphaTarget(0.25).restart();
        const position = dragEventWorldPosition(event);
        node.x = position.x;
        node.y = position.y;
        node.fx = position.x;
        node.fy = position.y;
        if (node.id === "john_windward") syncGateToJohn(gate, node);
        render();
      })
      .on("drag", (event, node) => {
        if (node.fixed) return;
        const position = dragEventWorldPosition(event);
        node.x = position.x;
        node.y = position.y;
        node.fx = position.x;
        node.fy = position.y;
        if (node.id === "john_windward") syncGateToJohn(gate, node);
        render();
      })
      .on("end", (event, node) => {
        if (node.fixed) return;
        if (!event.active) simulation.alphaTarget(0);
      });
    nodeLayer.selectAll("g.person-node").filter((node) => !node.fixed).call(drag);
  }

  stage.addEventListener("pointermove", (event) => {
    const [screenX, screenY] = d3.pointer(event, stage);
    const [worldX, worldY] = transform.invert([screenX - 32, screenY - viewport.height / 2]);
    const route = nearestEdge(routesFor(graph, nodesById), { x: worldX, y: worldY }, 10 / transform.k);
    state.hoveredEdgeId = route?.edge.eventId ?? null;
    if (route) {
      tooltip.hidden = false;
      tooltip.style.left = `${screenX + 14}px`;
      tooltip.style.top = `${screenY + 14}px`;
      tooltip.innerHTML = formatEdgeTooltip(route.edge);
    } else {
      tooltip.hidden = true;
    }
    render();
  });
  stage.addEventListener("pointerleave", () => {
    state.hoveredEdgeId = null;
    tooltip.hidden = true;
    render();
  });

  for (const button of root.querySelectorAll("[data-chain]")) {
    button.addEventListener("click", () => {
      state.activeChain = state.activeChain === button.dataset.chain ? null : button.dataset.chain;
      root.querySelectorAll("[data-chain]").forEach((control) => {
        control.setAttribute("aria-pressed", String(control.dataset.chain === state.activeChain));
      });
      render();
    });
  }
  root.querySelector("[data-action=\"reset\"]").addEventListener("click", () => {
    state.activeChain = null;
    state.hoveredNodeId = null;
    state.hoveredEdgeId = null;
    state.selectedNodeId = null;
    tooltip.hidden = true;
    resetNodePins(nodes);
    root.querySelectorAll("[data-chain]").forEach((button) => button.setAttribute("aria-pressed", "false"));
    svg.transition().duration(250).call(zoom.transform, d3.zoomIdentity);
    simulation.alpha(0.75).restart();
  });
  root.querySelectorAll("[data-chain], [data-action=\"reset\"]").forEach((control) => { control.disabled = false; });

  render();
  return { dataset, graph, nodes, gate, state, simulation, zoom };
}
