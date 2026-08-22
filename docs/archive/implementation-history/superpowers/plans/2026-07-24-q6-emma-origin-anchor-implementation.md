# Q6 Emma Harbor Origin Anchor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Emma Harbor the responsive fixed left-origin anchor, make John Windward draggable, and keep the validation gate fixed relative to John.

**Architecture:** Adjust the Q6 ES module's node-role assignment, responsive anchoring helper, resize behavior, and reset/drag invariants. Preserve the existing Canvas/SVG render layers and all event data logic. Pure helpers make node-role and coordinate rules unit-testable under Node before browser behavior consumes them.

**Tech Stack:** Vanilla ES modules, D3 v7, Canvas/SVG, Node built-in test runner.

---

### Task 1: Test and implement Emma fixed-anchor and draggable-John roles

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `test/test_q6_john_posting_intervention_network.mjs`

- [ ] **Step 1: Add failing tests for the personnel role model.**

Import any new helper needed for role assignment. Add this test:

```js
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
```

- [ ] **Step 2: Run the test and verify it fails under the current John-fixed behavior.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: failure because John is fixed and Emma is not.

- [ ] **Step 3: Make Emma the fixed person in `buildNodeModel`.**

In `buildNodeModel`, replace the fixed-person condition with:

```js
const fixed = id === "emma_harbor";
```

Use a neutral middle-band target for John:

```js
const isJohn = id === "john_windward";
const targetX = fixed ? 0 : (isJohn ? 520 : 100 + (index % 6) * 85);
const targetY = fixed ? 0 : BAND_Y[band];
```

Return `targetX`, `targetY`, `x`, `y`, `fx`, and `fy` based on these values. Only Emma gets non-null `fx` and `fy`.

- [ ] **Step 4: Run the full Node test suite.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: all existing tests plus the new role test pass.

### Task 2: Test and implement responsive Emma anchoring without resetting John

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `test/test_q6_john_posting_intervention_network.mjs`

- [ ] **Step 1: Add failing tests for the left-side Emma anchor.**

Add this test:

```js
test("anchors Emma inside the responsive left edge while preserving a wider stage position", () => {
  const narrow = originAnchor({ width: 640, height: 920 }, { x: 32, y: 460 });
  assert.ok(narrow.emmaX >= 42);
  assert.equal(narrow.emmaY, 0);

  const wide = originAnchor({ width: 1440, height: 920 }, { x: 32, y: 460 });
  assert.equal(wide.emmaX, 0);
  assert.equal(wide.emmaY, 0);
});
```

Add a resize behavior test using the existing fake `ResizeObserver` harness:

```js
test("reanchors fixed Emma on resize without overwriting manually pinned John", async () => {
  // Mount with a valid minimal three-post dataset.
  // Pin John at { x: 310, y: 48 } after mount.
  // Narrow the fake stage to 640px and invoke the observer callback.
  // Assert Emma's x/fx/targetX equal the new originAnchor result.
  // Assert John's x/y/fx/fy remain 310/48/310/48.
  // Assert gate x/y equals John's x+90 / John's y.
});
```

- [ ] **Step 2: Run tests and verify failure because `originAnchor` does not exist and resize still targets John.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: missing-export or failed anchor/resize assertions.

- [ ] **Step 3: Implement `originAnchor` and revise mount/resize behavior.**

Add and export:

```js
export function originAnchor(viewport, origin) {
  const leftMargin = 42;
  const emmaLabelReservation = 92;
  const maximumEmmaX = Math.max(
    0,
    viewport.width - origin.x - emmaLabelReservation - leftMargin,
  );
  return {
    emmaX: Math.min(0, maximumEmmaX),
    emmaY: 0,
  };
}
```

At mount time, use `originAnchor(viewport, origin)` to set only Emma's `x`, `fx`, `targetX`, `y`, and `fy`. Create the gate from John's initial current position:

```js
const john = nodes.find((node) => node.id === "john_windward");
const gate = {
  id: GATE_ID,
  label: "saidit_post validation gate",
  x: john.x + 90,
  y: john.y,
  fixed: true,
};
```

Inside `resize()`, reapply the origin anchor only to Emma. Do not alter John’s `x`, `y`, `fx`, `fy`, `targetX`, or `targetY`. Update the gate coordinate from John during `render()` and every simulation tick.

- [ ] **Step 4: Run all Node tests and verify they pass.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: all tests pass, including responsive Emma anchor and pinned-John resize tests.

### Task 3: Preserve drag/reset accessibility and complete verification

**Files:**
- Modify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js`
- Modify: `test/test_q6_john_posting_intervention_network.mjs`
- Modify: `docs/superpowers/specs/2026-07-24-q6-emma-origin-anchor-design.md`

- [ ] **Step 1: Add failing tests for Emma drag exclusion and reset behavior.**

Add a pure helper if needed, e.g.:

```js
export function resetNodePins(nodes) {
  for (const node of nodes) {
    if (!node.fixed) {
      node.fx = null;
      node.fy = null;
    }
  }
  return nodes;
}
```

Test:

```js
test("reset releases John but retains Emma's fixed anchor", () => {
  const nodes = [
    { id: "emma_harbor", fixed: true, fx: 0, fy: 0 },
    { id: "john_windward", fixed: false, fx: 310, fy: 48 },
  ];
  resetNodePins(nodes);
  assert.deepEqual(nodes[0], { id: "emma_harbor", fixed: true, fx: 0, fy: 0 });
  assert.deepEqual(nodes[1], { id: "john_windward", fixed: false, fx: null, fy: null });
});
```

- [ ] **Step 2: Run tests and verify failure for the missing helper or wrong fixed-role behavior.**

Run:

```bash
node --test test/test_q6_john_posting_intervention_network.mjs
```

Expected: failure mentioning `resetNodePins` or the old fixed John semantics.

- [ ] **Step 3: Implement reset and drag behavior around the new fixed role.**

Add `resetNodePins(nodes)` as specified. Change reset listener to call it:

```js
resetNodePins(nodes);
```

The existing drag filter must continue to exclude `node.fixed`; once Task 1 changes the role model this excludes Emma and permits John without further special casing. Update Emma’s accessible label:

```js
.attr("aria-label", (node) => node.fixed
  ? `${node.label}, fixed origin anchor`
  : `Show events connected to ${node.label}`)
```

Keep John visually emphasized separately from fixed status:

```js
const isJohn = node.id === "john_windward";
.attr("fill", (node) => isJohn ? "#dcecff" : "#ffffff")
.attr("stroke", (node) => node.isFocused ? "#172033" : (isJohn ? "#0b63ce" : "#9daabd"))
.attr("font-weight", (node) => isJohn ? 800 : 650)
```

- [ ] **Step 4: Update the design specification implementation note.**

Append:

```markdown
Emma Harbor is the sole fixed origin anchor. John Windward is an emphasized draggable convergence node; the validation gate is recomputed as a fixed right-side offset from John during rendering and does not independently participate in dragging.
```

- [ ] **Step 5: Run final checks.**

Run:

```bash
node --check VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.js
node --test test/test_q6_john_posting_intervention_network.mjs
python -m http.server 8018 --directory .
```

While the server is running, open:

```text
http://localhost:8018/VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.html
```

Verify without generating or opening image files:

- Emma stays fixed at the left origin and cannot be dragged.
- John can be dragged; Gate moves directly right with John.
- Reset releases John and keeps Emma fixed.
- The three post arrows remain distinct and labelled.
- Resizing preserves Emma’s responsive left anchor and does not move manually pinned John.
- Existing chain controls, focus behavior, tooltips, keyboard event details, zoom, and pan still work.

Stop the server after verification and run:

```bash
git diff --check
git status --short
```

Expected: all tests pass; no whitespace errors; only intended Q6 source/test/spec changes plus pre-existing unrelated working-tree changes.
