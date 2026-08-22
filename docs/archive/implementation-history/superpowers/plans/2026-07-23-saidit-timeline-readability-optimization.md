# Saidit Timeline Readability Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the full 353-event Saidit/TXT-chain timeline wider, shorter, free of terminal X-axis label collisions, and readable on the right side through dynamically stacked legends that do not overlap department labels.

**Architecture:** Keep the existing source loading, deduplication, employee-coordinate mapping, and plot encodings unchanged. Extract two small rendering helpers into `test/draw_saidit_posts_and_txt_chains_timeline.py`: one constructs collision-safe sequence ticks and one positions already-created legends by measuring their rendered extents in axes coordinates. `render_timeline` consumes those helpers and uses new geometry constants; existing `unittest` coverage is extended with focused helper tests and renderer-call assertions.

**Tech Stack:** Python 3.14, standard library, Matplotlib, `unittest`, `unittest.mock`

---

## File structure

- Modify: `test/draw_saidit_posts_and_txt_chains_timeline.py`
  - Define named layout constants.
  - Add `build_sequence_ticks` for regular ticks plus a non-overlapping final tick.
  - Add `stack_legends` to calculate each next legend's top anchor using the previous legend's measured bottom edge.
  - Update the existing renderer to use a wider/shorter figure, separated right-side regions, and the new helpers.
- Modify: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`
  - Test terminal tick de-duplication and normal terminal tick inclusion.
  - Test measured legend stacking independently from data loading.
  - Update the existing mocked renderer test to assert the new tick and geometry behavior.
- Create at runtime: `result/saidit_posts_and_txt_chains_timeline.png`
  - Regenerated visualization only; no source-data changes.

### Task 1: Add collision-safe sequence tick construction

**Files:**
- Modify: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`
- Modify: `test/draw_saidit_posts_and_txt_chains_timeline.py`

- [ ] **Step 1: Add a failing tick-helper test and import**

In `test/test_draw_saidit_posts_and_txt_chains_timeline.py`, add `build_sequence_ticks` to the import list beginning at line 8. Append the following test class before the existing `TimelineOutputTests` class:

```python
class SequenceTickTests(unittest.TestCase):
    def test_keeps_terminal_tick_and_removes_nearby_regular_tick(self):
        self.assertEqual(
            build_sequence_ticks(event_count=353, interval=25),
            [1, 26, 51, 76, 101, 126, 151, 176, 201, 226, 251, 276, 301, 326, 353],
        )

    def test_keeps_regular_tick_when_terminal_tick_is_not_nearby(self):
        self.assertEqual(
            build_sequence_ticks(event_count=375, interval=25),
            [1, 26, 51, 76, 101, 126, 151, 176, 201, 226, 251, 276, 301, 326, 351, 375],
        )

    def test_handles_empty_and_single_event_collections(self):
        self.assertEqual(build_sequence_ticks(event_count=0, interval=25), [])
        self.assertEqual(build_sequence_ticks(event_count=1, interval=25), [1])
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline.SequenceTickTests -v
```

Expected: an import failure stating `build_sequence_ticks` cannot be imported from `draw_saidit_posts_and_txt_chains_timeline`.

- [ ] **Step 3: Define the tick helper and rendering constants**

In `test/draw_saidit_posts_and_txt_chains_timeline.py`, place these constants immediately below `CHAIN_COLORS`:

```python
SEQUENCE_TICK_INTERVAL = 25
FIGURE_WIDTH = 34
FIGURE_HEIGHT = 14.5
DEPARTMENT_LABEL_X = 1.005
LEGEND_COLUMN_X = 1.16
LEGEND_VERTICAL_PADDING = 0.025
```

Then add this function immediately after `department_color_map`:

```python
def build_sequence_ticks(event_count: int, interval: int = SEQUENCE_TICK_INTERVAL) -> List[int]:
    """Return regular sequence ticks and a readable terminal event tick."""
    if event_count <= 0:
        return []

    ticks = list(range(1, event_count + 1, interval))
    if ticks[-1] == event_count:
        return ticks

    if event_count - ticks[-1] < interval:
        ticks.pop()
    ticks.append(event_count)
    return ticks
```

This policy removes `351` from the current 353-event plot and retains `353`, while preserving `351` in a 375-event plot because the final gap is a full interval minus one event.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline.SequenceTickTests -v
```

Expected: `Ran 3 tests ... OK`.

- [ ] **Step 5: Commit the tick helper**

```bash
git add test/draw_saidit_posts_and_txt_chains_timeline.py test/test_draw_saidit_posts_and_txt_chains_timeline.py
git commit -m "feat: prevent Saidit timeline terminal tick overlap"
```

### Task 2: Add measured dynamic legend stacking

**Files:**
- Modify: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`
- Modify: `test/draw_saidit_posts_and_txt_chains_timeline.py`

- [ ] **Step 1: Add a failing real-Matplotlib legend-layout test and imports**

At the top of `test/test_draw_saidit_posts_and_txt_chains_timeline.py`, add:

```python
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
```

Add `LEGEND_COLUMN_X`, `LEGEND_VERTICAL_PADDING`, and `stack_legends` to the imports from `draw_saidit_posts_and_txt_chains_timeline`. Append this test class after `SequenceTickTests`:

```python
class LegendLayoutTests(unittest.TestCase):
    def test_stacks_legends_from_measured_bounds_in_a_separate_column(self):
        figure, axis = plt.subplots(figsize=(8, 5))
        try:
            event_legend = axis.legend(
                handles=[Line2D([0], [0], label="event")],
                loc="upper left",
            )
            axis.add_artist(event_legend)
            chain_legend = axis.legend(
                handles=[Line2D([0], [0], label="chain")],
                loc="upper left",
            )
            axis.add_artist(chain_legend)
            department_legend = axis.legend(
                handles=[Line2D([0], [0], label="department")],
                loc="upper left",
            )

            stack_legends(axis, [event_legend, chain_legend, department_legend])
            figure.canvas.draw()
            renderer = figure.canvas.get_renderer()
            boxes = [
                axis.transAxes.inverted().transform_bbox(legend.get_window_extent(renderer))
                for legend in [event_legend, chain_legend, department_legend]
            ]

            self.assertGreater(LEGEND_COLUMN_X, 1.005)
            self.assertAlmostEqual(boxes[0].x0, LEGEND_COLUMN_X, delta=0.03)
            self.assertGreaterEqual(boxes[0].y0 - boxes[1].y1, LEGEND_VERTICAL_PADDING - 0.01)
            self.assertGreaterEqual(boxes[1].y0 - boxes[2].y1, LEGEND_VERTICAL_PADDING - 0.01)
        finally:
            plt.close(figure)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline.LegendLayoutTests -v
```

Expected: an import failure stating `stack_legends` cannot be imported from `draw_saidit_posts_and_txt_chains_timeline`.

- [ ] **Step 3: Implement the measured legend stacker**

In `test/draw_saidit_posts_and_txt_chains_timeline.py`, add this function immediately after `build_sequence_ticks`:

```python
def stack_legends(axis: Any, legends: List[Any]) -> None:
    """Stack upper-left legends using each rendered legend's measured bottom edge."""
    next_top = 1.0
    for legend in legends:
        legend.set_bbox_to_anchor(
            (LEGEND_COLUMN_X, next_top), transform=axis.transAxes
        )
        axis.figure.canvas.draw()
        renderer = axis.figure.canvas.get_renderer()
        bounds = axis.transAxes.inverted().transform_bbox(
            legend.get_window_extent(renderer)
        )
        next_top = bounds.y0 - LEGEND_VERTICAL_PADDING
```

The renderer draw happens after each anchor change because the next anchor must be calculated from the preceding legend's actual rendered height, not a hard-coded Y coordinate.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline.LegendLayoutTests -v
```

Expected: `Ran 1 test ... OK`.

- [ ] **Step 5: Commit the dynamic legend layout helper**

```bash
git add test/draw_saidit_posts_and_txt_chains_timeline.py test/test_draw_saidit_posts_and_txt_chains_timeline.py
git commit -m "feat: dynamically stack Saidit timeline legends"
```

### Task 3: Apply the optimized geometry and helper-based rendering

**Files:**
- Modify: `test/test_draw_saidit_posts_and_txt_chains_timeline.py`
- Modify: `test/draw_saidit_posts_and_txt_chains_timeline.py`

- [ ] **Step 1: Strengthen the existing mocked renderer test**

In `TimelineOutputTests.test_uses_event_sequence_positions_for_points_lines_and_axis`, retain the current assertions and append these assertions after the existing `axis.scatter` assertions:

```python
        self.assertEqual(figure.set_size_inches.call_args.args, (FIGURE_WIDTH, FIGURE_HEIGHT))
        self.assertEqual(axis.set_xticks.call_args.args[0], [1, 2])
        self.assertEqual(axis.set_xlim.call_args.args, (0.5, 2.5))
```

Add `FIGURE_HEIGHT` and `FIGURE_WIDTH` to the test file's generator imports.

- [ ] **Step 2: Run the renderer unit test and verify it fails**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline.TimelineOutputTests.test_uses_event_sequence_positions_for_points_lines_and_axis -v
```

Expected: FAIL because the renderer still creates its fixed-size `(25, height)` figure and uses inlined tick construction.

- [ ] **Step 3: Replace the geometry and tick code in `render_timeline`**

In `test/draw_saidit_posts_and_txt_chains_timeline.py`, make these exact replacements within `render_timeline`:

1. Replace the current `plt.subplots` call:

```python
    fig, axis = plt.subplots(figsize=(25, max(14, len(rows) * 0.32 + 5)))
```

with:

```python
    fig, axis = plt.subplots(figsize=(FIGURE_WIDTH, FIGURE_HEIGHT))
```

2. In the point rendering call, replace the size expression:

```python
                marker=marker, s=58 if event_type == "saidit_post" else 38,
```

with:

```python
                marker=marker, s=46 if event_type == "saidit_post" else 30,
```

3. In the chain-line rendering call, replace `linewidth=1.25` with `linewidth=1.0`.

4. Replace the complete inline tick block:

```python
    event_count = len(events)
    tick_interval = 25
    sequence_ticks = list(range(1, event_count + 1, tick_interval))
    if event_count and sequence_ticks[-1] != event_count:
        sequence_ticks.append(event_count)
    axis.set_xticks(sequence_ticks)
```

with:

```python
    event_count = len(events)
    axis.set_xticks(build_sequence_ticks(event_count))
```

5. Replace the department-label X coordinate `1.005` with `DEPARTMENT_LABEL_X`:

```python
            axis.text(DEPARTMENT_LABEL_X, y, department, transform=axis.get_yaxis_transform(), va="center", ha="left", fontsize=8, weight="bold", color=department_colors[department])
```

6. Replace all three fixed-anchor legend creation lines with these six lines, preserving the existing handle variables:

```python
    event_legend = axis.legend(handles=event_handles, title="Event type", loc="upper left", fontsize=8)
    axis.add_artist(event_legend)
    chain_legend = axis.legend(handles=chain_handles, title="TXT chain", loc="upper left", fontsize=8)
    axis.add_artist(chain_legend)
    department_legend = axis.legend(handles=department_handles, title="Department", loc="upper left", fontsize=8)
    stack_legends(axis, [event_legend, chain_legend, department_legend])
```

7. Replace the subplot adjustment:

```python
    fig.subplots_adjust(left=0.20, right=0.80, top=0.92, bottom=0.07)
```

with:

```python
    fig.subplots_adjust(left=0.15, right=0.68, top=0.92, bottom=0.08)
```

The narrower plot fraction is intentional: it creates a dedicated right-side region in which department labels sit at `DEPARTMENT_LABEL_X` and legends sit farther right at `LEGEND_COLUMN_X`.

- [ ] **Step 4: Run the renderer unit test and verify it passes**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline.TimelineOutputTests.test_uses_event_sequence_positions_for_points_lines_and_axis -v
```

Expected: `Ran 1 test ... OK`.

- [ ] **Step 5: Run the full timeline test module**

Run:

```bash
python -m unittest test.test_draw_saidit_posts_and_txt_chains_timeline -v
```

Expected: all tests pass, including organization mapping, merge/segmentation, sequence positions, tick construction, legend stacking, mocked rendering, and the real PNG integration test.

- [ ] **Step 6: Regenerate the visualization**

Run:

```bash
PYTHONIOENCODING=utf-8 python test/draw_saidit_posts_and_txt_chains_timeline.py
```

Expected: `Saved 353 merged events to:` followed by `result/saidit_posts_and_txt_chains_timeline.png`.

- [ ] **Step 7: Inspect the generated artifact against the approved criteria**

Open `result/saidit_posts_and_txt_chains_timeline.png` and confirm:

- The X-axis includes `353` but not `351`.
- All 353 events remain shown in their original sequence order.
- The chart is materially wider and visibly shorter than the previous artifact.
- Department labels are adjacent to the plot boundary.
- Event-type, TXT-chain, and department legends are vertically stacked farther to the right than department labels.
- No legend covers a department label.

- [ ] **Step 8: Commit renderer, tests, and regenerated artifact**

```bash
git add test/draw_saidit_posts_and_txt_chains_timeline.py test/test_draw_saidit_posts_and_txt_chains_timeline.py result/saidit_posts_and_txt_chains_timeline.png
git commit -m "feat: improve Saidit timeline readability"
```

## Plan self-review

- **Spec coverage:** Task 1 covers data-preserving terminal tick logic. Task 2 implements renderer-measured legend placement and a separate legend column. Task 3 applies the 34×14.5-inch geometry, reduced mark density, right-side spacing, helper integration, full regression testing, and artifact review. No source data, event ordering, or encoding changes are proposed.
- **Placeholder scan:** The plan contains no TBDs, deferred implementation labels, or unspecified test instructions.
- **Type consistency:** `build_sequence_ticks(event_count: int, interval: int) -> List[int]` is defined before its tests and renderer use. `stack_legends(axis: Any, legends: List[Any]) -> None` is defined before its test and renderer use. The test imports match those exact names.
