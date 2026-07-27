# Q6 D3 Constrained Personnel Network Design

## Purpose

Replace the Q6 Matplotlib PNG as the primary deliverable with one interactive HTML network visualization. The figure must demonstrate that all three observed TXT-derived anomalous posting chains converge at John Windward's `saidit_post` workflow, where a single pre-publication validation gate can cover the observed cases.

The interactive HTML is the only new primary output. No report PNG export is required.

## Evidence boundary

The visualization supports a claim about the three observed anomalous chains only. It must visibly state that the proposed gate covers all three observed chains and does not establish that every future anomaly will reach John Windward's workflow.

## Data contract

Use `result/three_txt_posting_chains_dataset.json`. Derive visible directed edges exactly as follows:

- For a record with exactly two normalized person parties, map the first person to the source and the second to the target.
- For a one-person `saidit_post` by John Windward, map John Windward to the validation gate.
- Omit one-person filesystem records and events with more than two normalized people because they cannot support a directed personnel relationship without inventing an endpoint.
- Preserve every directionally viable event as a distinct edge, including repeated person-to-person transfers, self-transfers, and all three John-to-gate post edges.
- Sort each chain by `(when, id)` and independently assign its visible edges contiguous sequence numbers starting at `1`.

For the current dataset, 238 of 248 raw records are directionally viable: 187 SwiftWren, 40 HiddenOrca, and 11 MellowOtter. Ten unipersonal filesystem records remain omitted.

## Technology and render architecture

Use a standalone HTML page with D3.js. The page may load D3 from a pinned CDN URL and load the existing JSON dataset through a relative path.

Implementation uses `q6_john_posting_intervention_network.html` and its adjacent ES module, `q6_john_posting_intervention_network.js`. D3 v7 is loaded as an ES module from `https://cdn.jsdelivr.net/npm/d3@7/+esm`; pure data and interaction helpers are checked with `node --test test/test_q6_john_posting_intervention_network.mjs`.

Render a single shared world-coordinate graph in three layers:

1. **Canvas edge layer** — all 238 event edges, including duplicate routes and self-loops. Canvas makes dense, low-emphasis paths inexpensive to render during pan, zoom, layout ticks, and highlight changes.
2. **SVG foreground layer** — people, John Windward, validation gate, title, legend, operational rule, scope note, primary post arrows, event-number labels, and interaction hit regions.
3. **HTML tooltip layer** — details for the currently hovered edge or node.

Canvas and SVG must use the same D3 zoom transform and the same final node positions.

## Constrained force layout

All people have exactly one node. John Windward is an anchored node on the right side of the network. The validation gate is an anchored diamond at a fixed offset directly to John's right.

Use a D3 force simulation with:

- link force based on the directionally viable person-to-person edges;
- collision force sized for visible name labels;
- charge force to separate unrelated nodes;
- x/y positioning forces that preserve story bands rather than arbitrary automatic placement.

Band rules:

- SwiftWren-associated people are biased to the middle band.
- HiddenOrca-only people are biased to the upper band.
- MellowOtter-only people are biased to the lower band.
- People shared by multiple chains remain one node and are biased to a middle or transitional position based on their memberships and John connectivity.

Node dragging must pin a person at the user's chosen position for the active page session. Dragging John is not required. The gate remains fixed relative to John.

## Edge routing and encoding

All viable event edges remain visible. The three chain colors are fixed:

- SwiftWren.txt: red;
- HiddenOrca.txt: blue;
- MellowOtter.txt: black.

Background edges are thin and low-opacity. Routes for repeated source/target pairs receive deterministic signed offsets. Self-transfers render as distinct local loops. The three John-to-gate post arrows always render as high-contrast foreground SVG paths with distinct curvatures and their own chain-local sequence labels.

In the default view, ordinary edges have no visible sequence label. This is progressive disclosure, not event removal: each label becomes visible when its edge is relevant through node hover or chain selection.

## Default visual state and interaction

### Default state

- Draw every viable edge in the Canvas background.
- Render all people once, John emphasized, and the sole non-person validation-gate diamond.
- Emphasize the three John-to-gate post arrows and show their sequence labels.
- Do not display ordinary edge numbers.
- Include the gate rule: `content_source exists + content empty → block + audit`.
- Include a legend, title, and observed-cases-only scope note.

### Node hover

Hovering a person highlights incident edges and their chain-local sequence labels. Unrelated nodes and edges recede.

### Chain selection

The legend provides one selectable control per TXT chain. Selecting a chain highlights it and reveals all its sequence labels. The other chains remain faintly visible to preserve the convergence context. Selecting the active chain again or using a reset control restores the default view.

### Edge hover

Canvas hit testing identifies the nearest visible edge within a defined screen-space tolerance. Hovering an edge presents an HTML tooltip with:

- TXT chain;
- chain-local sequence;
- timestamp;
- event type;
- source and target display names.

A selected or hovered edge receives a high-contrast redraw in the foreground and its sequence label becomes visible.

### Navigation

The graph supports mouse-wheel zoom and drag-to-pan. Zooming redraws Canvas edges and transforms SVG graph content in lockstep. A reset-view control restores the initial fitted viewport and removes any active chain selection.

## File scope

- Add or replace `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html` as the primary Q6 deliverable.
- Add a focused JavaScript module beside the page or under `VAST_Challenge_2026_MC2/src/` for data derivation, constrained layout, Canvas rendering, SVG rendering, and interaction state.
- Add browser-facing tests only where the project's established tooling permits them; otherwise add pure-data/unit tests for event derivation, sequence assignment, chain membership, route offsets, and interaction-state reducers.
- The existing Matplotlib renderer and PNG may remain in the repository but are not extended or regenerated for this change.

## Acceptance criteria

1. The HTML loads the three-chain dataset and produces 238 visible viable event routes with no fabricated endpoints.
2. Every person appears exactly once; the validation gate is the only non-person graph node.
3. The force layout preserves the intended upper/middle/lower chain narrative while preventing node-label collisions under its deterministic initial state.
4. SwiftWren, HiddenOrca, and MellowOtter preserve their fixed colors; repeated transfers, self-loops, and all three John-to-gate post arrows remain distinct.
5. Default view shows all edges but only the three final post-edge sequence labels.
6. Node hover, chain selection, and edge hover expose relevant sequence labels and event details without permanently cluttering the graph.
7. John and the gate remain visually prominent, with the gate directly right of John and the operational validation rule nearby.
8. The page supports zoom, pan, node dragging, and reset view.
9. The legend and scope note clearly distinguish chain identity, chain-local event order, the proposed gate, and the limitation to observed cases.
10. No PNG export, HTML dashboard expansion, candidate comparison matrix, or additional technical object nodes are introduced.
