# Q6 人员链路单点干预图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成并验证一张 Matplotlib 静态 PNG，以展示三个已观察 TXT 异常发布链在 John Windward 的 `saidit_post` 工作流汇聚，并由唯一的发布前验证门覆盖。

**Architecture:** `draw_john_intervention_network.py` 从 `result/three_txt_posting_chains_dataset.json` 提取可定向的人员事件，建立唯一人员坐标、每事件独立弧形箭头和验证门，再输出 PNG。`test/test_draw_john_intervention_network.py` 验证事件映射、排序、布局输入、路线分离和 PNG 写出；最终通过真实数据重新生成图片并目视检查。

**Tech Stack:** Python 3、Matplotlib、`unittest`、JSON。

---

## File structure

- `VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py`：数据映射、确定性布局、弧形边路由和 PNG 渲染。
- `test/test_draw_john_intervention_network.py`：覆盖数据合同、路线与渲染行为的单元测试。
- `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png`：真实数据生成的报告图。
- `绘图方案.md`：已批准的视觉目标、范围边界和验收标准；不在本计划中改动。

### Task 1: Lock down data-to-edge semantics

**Files:**
- Modify: `test/test_draw_john_intervention_network.py:49-175`
- Modify: `VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py:44-139`

- [ ] **Step 1: Write or retain the data-contract tests**

Ensure tests assert that two ordered personnel IDs become one `source → target` edge; John’s one-person `saidit_post` becomes `john_windward → GATE_ID`; single-person filesystem events and events with more than two people are omitted; chain-local timestamps create consecutive sequence numbers.

```python
self.assertEqual(
    (post["source"], post["target"], post["is_post"]),
    ("john_windward", GATE_ID, True),
)
self.assertEqual(len(graph["edges"]), 238)
self.assertEqual(len(graph["omitted_events"]), 10)
```

- [ ] **Step 2: Run the focused extraction tests**

Run:

```bash
python -m unittest test.test_draw_john_intervention_network.InterventionGraphTests.test_projects_john_post_and_omits_unsupported_events test.test_draw_john_intervention_network.InterventionGraphTests.test_real_dataset_graph_contract -v
```

Expected: both tests pass; the real dataset contains 238 viable edges distributed 187 / 40 / 11 and three final post edges.

- [ ] **Step 3: Implement the minimal extraction behavior if a test fails**

Use the following mapping logic in `_derive_event_edge` and `build_intervention_graph`:

```python
people = _person_ids(event.get("parties"))
if len(people) == 2:
    return {"source": people[0], "target": people[1], "is_post": False, ...}
if len(people) == 1 and people[0] == "john_windward" and event.get("short_name") == "saidit_post":
    return {"source": "john_windward", "target": GATE_ID, "is_post": True, ...}
return None
```

Assign `sequence = len(edges_by_chain[chain_file]) + 1` after sorting each chain by timestamp and event ID.

- [ ] **Step 4: Re-run the focused extraction tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit the data-contract change if this task modified tracked or intended deliverable files**

```bash
git add VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py test/test_draw_john_intervention_network.py
git commit -m "feat: map Q6 personnel events to intervention graph" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

Do not commit unrelated pre-existing worktree changes.

### Task 2: Preserve every viable event with deterministic layout and readable routing

**Files:**
- Modify: `test/test_draw_john_intervention_network.py:177-237`
- Modify: `VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py:142-241`

- [ ] **Step 1: Write or retain layout and route tests**

Verify center / upper / lower bands, globally unique people, repeated edge curvature separation, separate self-loops, and three distinct John-to-Gate routes.

```python
self.assertEqual(set(positions), graph["people"])
self.assertGreater(positions["upper_new"][1], 0)
self.assertLess(positions["lower_new"][1], 0)
self.assertEqual(len({item["curvature"] for item in post_routes}), 3)
```

- [ ] **Step 2: Run the focused layout and routing tests**

Run:

```bash
python -m unittest test.test_draw_john_intervention_network.InterventionGraphTests.test_positions_keep_each_person_unique_and_attach_supplementary_people test.test_draw_john_intervention_network.InterventionGraphTests.test_routes_separate_duplicate_edges_posts_and_loops -v
```

Expected: PASS.

- [ ] **Step 3: Implement deterministic positions and non-merged routes if a test fails**

Place SwiftWren people at `(index * PERSON_COLUMN_SPACING, 0.0)`. For each supplementary event with exactly one known endpoint, attach the new source left of its known target or the new target right of its known source in the upper or lower chain band. Group retained edges by `(source, target)` and apply symmetric curvature offsets:

```python
groups[(str(edge["source"]), str(edge["target"]))].append(edge)
for edge, offset in zip(pair_edges, _symmetric_offsets(len(pair_edges))):
    curvature = CHAIN_CURVATURE[edge["chain_file"]] + offset * 0.09
```

For self-loops, use shifted endpoints and a progressively larger curve radius rather than identical start and end points.

- [ ] **Step 4: Re-run the focused layout and routing tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Commit the layout and routing change if this task modified intended deliverable files**

```bash
git add VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py test/test_draw_john_intervention_network.py
git commit -m "feat: route all Q6 personnel events distinctly" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

### Task 3: Render the approved intervention evidence figure

**Files:**
- Modify: `test/test_draw_john_intervention_network.py:239-269`
- Modify: `VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py:244-395`
- Create/overwrite: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png`

- [ ] **Step 1: Write or retain renderer-output test**

```python
render_intervention_network(dataset, output_path)
self.assertTrue(output_path.exists())
self.assertGreater(output_path.stat().st_size, 0)
self.assertEqual(output_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
self.assertEqual(dataset, original)
self.assertEqual(plt.get_fignums(), [])
```

- [ ] **Step 2: Run the focused renderer test**

Run:

```bash
python -m unittest test.test_draw_john_intervention_network.InterventionGraphTests.test_renderer_writes_closed_png_without_mutating_dataset -v
```

Expected: PASS.

- [ ] **Step 3: Implement the render contract if a test fails**

Render with Matplotlib using `FancyBboxPatch` for unique people, `FancyArrowPatch` for all routes, `RegularPolygon` for the sole gate, and `Line2D` for the legend. The renderer must include the following English text in the figure:

```text
Three Observed TXT Posting Chains Converge at John Windward’s Publication Workflow
content_source exists + content empty → block + audit
The gate covers all three observed TXT-derived anomalous posting chains.
This observed pattern does not establish that every future anomaly will reach John Windward’s publication workflow.
```

Use stable red, blue, and black chain colors; draw the gate to John’s right; save with a high-resolution large canvas and close the figure after `savefig`.

- [ ] **Step 4: Re-run the focused renderer test**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 5: Generate the real-data PNG**

Run:

```bash
python VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py
```

Expected: prints `Saved intervention network to:` followed by `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png`.

- [ ] **Step 6: Visually inspect the generated PNG**

Open `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png` and verify: title is visible; only one John node exists; a diamond gate appears to John’s right; three visible colored arrows point from John to the gate; legend, gate rule, and observed-case caveat do not overlap or clip.

- [ ] **Step 7: Commit the intended deliverables if requested**

```bash
git add VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py test/test_draw_john_intervention_network.py VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png
git commit -m "feat: render Q6 intervention evidence network" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
```

Do not include unrelated worktree changes.

### Task 4: Run end-to-end verification

**Files:**
- Verify: `test/test_draw_john_intervention_network.py`
- Verify: `VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py`
- Verify: `VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png`

- [ ] **Step 1: Run the complete dedicated test module**

Run:

```bash
python -m unittest test.test_draw_john_intervention_network -v
```

Expected: all tests pass.

- [ ] **Step 2: Re-run the generator from the real dataset**

Run:

```bash
python VAST_Challenge_2026_MC2/src/draw_john_intervention_network.py
```

Expected: exits with status 0 and rewrites the report PNG.

- [ ] **Step 3: Inspect output metadata**

Run:

```bash
python -c "from pathlib import Path; p=Path('VAST_Challenge_2026_MC2/report_question_visualizations/q6_john_posting_intervention_network.png'); print(p.exists(), p.stat().st_size, p.read_bytes()[:8])"
```

Expected: `True`, a non-zero file size, and `b'\\x89PNG\\r\\n\\x1a\\n'`.

- [ ] **Step 4: Record verification outcome**

Report the dedicated-test result, generator result, PNG path and visual-inspection conclusion. If a failure occurs, report its exact command and output rather than claiming completion.

## Self-review

- **Spec coverage:** Task 1 covers the truthful directional data mapping, omitted event policy, edge counts and independent order. Task 2 covers global person uniqueness, band placement, duplicate events, self-loops and three distinct post routes. Task 3 covers the static PNG, only one non-person Gate, colors, title, legend, Gate rule and evidence-boundary wording. Task 4 validates all acceptance criteria together.
- **Placeholder scan:** No TBD/TODO items or undefined interfaces remain. All named functions exist in the current generator and are covered by explicit commands.
- **Consistency:** `GATE_ID`, `build_intervention_graph`, `build_person_positions`, `build_edge_routes`, and `render_intervention_network` use the same signatures throughout.
