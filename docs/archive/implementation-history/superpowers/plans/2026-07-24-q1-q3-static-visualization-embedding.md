# Q1–Q3 Static Visualization Embedding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the selected Q1–Q3 static visualization images and English captions to the MC2 answer-sheet HTML using portable submission-relative paths.

**Architecture:** Copy the five unique PNG source assets into `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/`; reuse the copied Q1-2 asset in both Q1 and Q3. Add six semantic centered figure blocks into `index.html` after the prose for their respective answers. A lightweight Python regression test will assert asset existence, insertion order, captions, and the deliberate absence of Q3-2.

**Tech Stack:** Static HTML, CSS inline styles compatible with the Word-exported answer sheet, Python `unittest`.

---

## File Structure

- `VAST_Challenge_2026_MC2/index.html` — Word-exported submission answer sheet; receives figure blocks for Q1, Q2, and Q3.
- `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q1-1.png` — copied detailed Q1 visual.
- `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q1-2.png` — copied posting-chain overview reused in Q1 and Q3.
- `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q2.png` — copied Q2 visual.
- `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q3-1.png` — copied historical comparison visual.
- `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q3-3.png` — copied intervention visual.
- `VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py` — regression assertions for the submission document and copied assets.

### Task 1: Write the failing embedding regression test

**Files:**
- Create: `VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py`
- Test: `VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py`

- [ ] **Step 1: Write the failing test for selected figure assets and HTML figure blocks**

```python
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = PROJECT_ROOT / "index.html"
FIGURE_DIR = PROJECT_ROOT / "report_question_visualizations" / "final_graphs"


class IndexVisualizationEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.html = INDEX_HTML.read_text(encoding="windows-1252")

    def test_selected_static_assets_are_included_in_submission(self):
        expected_assets = {
            "Q1-1.png",
            "Q1-2.png",
            "Q2.png",
            "Q3-1.png",
            "Q3-3.png",
        }

        self.assertEqual(
            {path.name for path in FIGURE_DIR.glob("*.png")},
            expected_assets,
        )

    def test_q1_q2_and_q3_figure_blocks_have_expected_order_and_captions(self):
        figures = [
            "Q1-1.png",
            "Q1-2.png",
            "Q2.png",
            "Q1-2.png",
            "Q3-1.png",
            "Q3-3.png",
        ]
        positions = [
            self.html.index(f"report_question_visualizations/final_graphs/{name}")
            for name in figures
        ]

        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "The complete interactive HTML and D3 visualization are provided as supplementary attachments.",
            self.html,
        )
        self.assertIn(
            "John Windward as the common final posting node before SaidIT publication.",
            self.html,
        )
        self.assertNotIn("Q3-2", self.html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails before the assets and figure blocks exist**

Run:

```bash
python -m unittest VAST_Challenge_2026_MC2.test.test_index_visualization_embedding -v
```

Expected: FAIL because `report_question_visualizations/final_graphs` and its five selected images do not exist, and `index.html` has no new figure paths.

- [ ] **Step 3: Commit the failing test**

```bash
git add VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py
git commit -m "test: cover MC2 visualization embedding"
```

### Task 2: Copy the five unique selected figure assets into the submission

**Files:**
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q1-1.png`
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q1-2.png`
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q2.png`
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q3-1.png`
- Create: `VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q3-3.png`
- Test: `VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py`

- [ ] **Step 1: Create the final-graph asset directory and copy only the approved source figures**

Run:

```bash
mkdir -p "VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs"
cp "C:/Users/83734/Desktop/vast 2026 final graph/Q1-1.png" "VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q1-1.png"
cp "C:/Users/83734/Desktop/vast 2026 final graph/Q1-2.png" "VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q1-2.png"
cp "C:/Users/83734/Desktop/vast 2026 final graph/Q2.png" "VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q2.png"
cp "C:/Users/83734/Desktop/vast 2026 final graph/Q3-1.png" "VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q3-1.png"
cp "C:/Users/83734/Desktop/vast 2026 final graph/Q3-3.png" "VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs/Q3-3.png"
```

Do not copy `Q3-2废弃.png`; Q1-2 is intentionally reused from the single copied asset.

- [ ] **Step 2: Run the regression test to confirm the copied asset set is correct**

Run:

```bash
python -m unittest VAST_Challenge_2026_MC2.test.test_index_visualization_embedding.IndexVisualizationEmbeddingTests.test_selected_static_assets_are_included_in_submission -v
```

Expected: PASS for the asset-set assertion, then the overall test still fails because the HTML blocks are not embedded yet.

- [ ] **Step 3: Commit the copied submission assets**

```bash
git add VAST_Challenge_2026_MC2/report_question_visualizations/final_graphs
git commit -m "assets: add selected MC2 answer figures"
```

### Task 3: Add Q1 and Q2 figure blocks to the answer sheet

**Files:**
- Modify: `VAST_Challenge_2026_MC2/index.html:1554` (immediately after Q1 answer prose)
- Modify: `VAST_Challenge_2026_MC2/index.html:1593` (immediately after Q2 answer prose)
- Test: `VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py`

- [ ] **Step 1: Insert Q1 figure blocks immediately after the Q1 narrative**

Insert directly after the paragraph ending with `personnel and organizational relationships rather than remaining within a single individual or department.`:

```html
    <div style='margin:12pt 0;text-align:center'>
      <img src="report_question_visualizations/final_graphs/Q1-1.png"
        alt="Detailed SwiftWren transmission chain from source-file creation through task propagation to the anomalous SaidIT post"
        style="display:block;max-width:100%;height:auto;margin:0 auto">
      <p class=MsoNormal style='margin-top:6pt;text-align:center'><i><span style='font-size:10.0pt;font-family:"Source Sans Pro",sans-serif'>Figure Q1-1. Detailed SwiftWren transmission chain. The complete interactive HTML and D3 visualization are provided as supplementary attachments.</span></i></p>
    </div>

    <div style='margin:12pt 0;text-align:center'>
      <img src="report_question_visualizations/final_graphs/Q1-2.png"
        alt="System overview of SaidIT posting chains contrasting direct-content posts and text-file source paths"
        style="display:block;max-width:100%;height:auto;margin:0 auto">
      <p class=MsoNormal style='margin-top:6pt;text-align:center'><i><span style='font-size:10.0pt;font-family:"Source Sans Pro",sans-serif'>Figure Q1-2. System overview of SaidIT posting chains, contrasting direct-content and .txt-source posting paths.</span></i></p>
    </div>
```

- [ ] **Step 2: Insert the Q2 figure block immediately after the Q2 narrative**

Insert directly after the paragraph ending with `the meeting-derived material was intended for publication but was not successfully transferred to the post.`:

```html
    <div style='margin:12pt 0;text-align:center'>
      <img src="report_question_visualizations/final_graphs/Q2.png"
        alt="SwiftWren content-source evidence connecting Emma Harbor's preceding meeting activity and candidate meeting sources"
        style="display:block;max-width:100%;height:auto;margin:0 auto">
      <p class=MsoNormal style='margin-top:6pt;text-align:center'><i><span style='font-size:10.0pt;font-family:"Source Sans Pro",sans-serif'>Figure Q2. Evidence linking SwiftWren.txt to Emma Harbor's preceding meeting activity and the candidate meeting-content sources.</span></i></p>
    </div>
```

- [ ] **Step 3: Run the regression test to verify Q1 and Q2 paths and captions are present**

Run:

```bash
python -m unittest VAST_Challenge_2026_MC2.test.test_index_visualization_embedding -v
```

Expected: The asset assertion passes. The order/caption test may still fail because the Q3 figure blocks are not embedded yet.

- [ ] **Step 4: Commit Q1 and Q2 figure embedding**

```bash
git add VAST_Challenge_2026_MC2/index.html
git commit -m "feat: embed Q1 and Q2 answer figures"
```

### Task 4: Add Q3 evidence figure blocks and verify the complete answer sheet

**Files:**
- Modify: `VAST_Challenge_2026_MC2/index.html:1661` (immediately after Q3 answer prose)
- Test: `VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py`

- [ ] **Step 1: Insert Q3 figure blocks immediately after the Q3 recommendation paragraph**

Insert directly after the paragraph ending with `preserving the upstream evidence required for investigation.`:

```html
    <div style='margin:12pt 0;text-align:center'>
      <img src="report_question_visualizations/final_graphs/Q1-2.png"
        alt="SaidIT posting-chain overview reused to compare recurring text-file posting cases and their common final posting node"
        style="display:block;max-width:100%;height:auto;margin:0 auto">
      <p class=MsoNormal style='margin-top:6pt;text-align:center'><i><span style='font-size:10.0pt;font-family:"Source Sans Pro",sans-serif'>Figure Q3-1. Posting-chain overview used to compare the recurring .txt-based cases; it shows John Windward as the common final posting node before SaidIT publication.</span></i></p>
    </div>

    <div style='margin:12pt 0;text-align:center'>
      <img src="report_question_visualizations/final_graphs/Q3-1.png"
        alt="Historical comparison of the three text-file based SaidIT posting cases"
        style="display:block;max-width:100%;height:auto;margin:0 auto">
      <p class=MsoNormal style='margin-top:6pt;text-align:center'><i><span style='font-size:10.0pt;font-family:"Source Sans Pro",sans-serif'>Figure Q3-2. Historical comparison of the three .txt-based SaidIT posting cases.</span></i></p>
    </div>

    <div style='margin:12pt 0;text-align:center'>
      <img src="report_question_visualizations/final_graphs/Q3-3.png"
        alt="Intervention analysis supporting a content-validation check immediately before John Windward's agent submits to SaidIT"
        style="display:block;max-width:100%;height:auto;margin:0 auto">
      <p class=MsoNormal style='margin-top:6pt;text-align:center'><i><span style='font-size:10.0pt;font-family:"Source Sans Pro",sans-serif'>Figure Q3-3. Intervention analysis supporting a validation check immediately before John Windward's agent submits content to SaidIT. The complete interactive HTML and D3 visualization are provided as supplementary attachments.</span></i></p>
    </div>
```

- [ ] **Step 2: Run the full regression test**

Run:

```bash
python -m unittest VAST_Challenge_2026_MC2.test.test_index_visualization_embedding -v
```

Expected: PASS; all five unique figure assets exist, the HTML includes six image usages in Q1 → Q2 → Q3 order, the required supplementary-attachment and John Windward captions are present, and no Q3-2 reference exists.

- [ ] **Step 3: Verify exact HTML references and excluded asset with a static check**

Run:

```bash
python -c "from pathlib import Path; html = Path('VAST_Challenge_2026_MC2/index.html').read_text(encoding='windows-1252'); expected = ['Q1-1.png','Q1-2.png','Q2.png','Q1-2.png','Q3-1.png','Q3-3.png']; found = [line.split('final_graphs/', 1)[1].split(chr(34), 1)[0] for line in html.splitlines() if 'final_graphs/' in line]; assert found == expected, found; assert 'Q3-2' not in html; print('Figure references verified:', found)"
```

Expected:

```text
Figure references verified: ['Q1-1.png', 'Q1-2.png', 'Q2.png', 'Q1-2.png', 'Q3-1.png', 'Q3-3.png']
```

- [ ] **Step 4: Commit the Q3 embedding and regression coverage**

```bash
git add VAST_Challenge_2026_MC2/index.html VAST_Challenge_2026_MC2/test/test_index_visualization_embedding.py
git commit -m "feat: embed Q3 answer figures"
```
