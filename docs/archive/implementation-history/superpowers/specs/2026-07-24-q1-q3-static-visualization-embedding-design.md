# Q1–Q3 Static Visualization Embedding Design

## Goal

Embed six selected static visualizations from `C:\Users\83734\Desktop\vast 2026 final graph` into the VAST Challenge MC2 answer sheet, immediately after the prose that each figure supports.

## Scope

Modify only `VAST_Challenge_2026_MC2/index.html` and copy the selected PNG assets into the submission directory so the answer sheet uses portable relative image paths.

### Selected figures

| Answer section | Figure files | Purpose |
| --- | --- | --- |
| Q1 | `Q1-1.png`, `Q1-2.png` | Evidence for the detailed SwiftWren propagation chain and the broader SaidIT posting-chain system overview. |
| Q2 | `Q2.png` | Evidence for the content-source and candidate-meeting analysis. |
| Q3 | `Q1-2.png`, `Q3-1.png`, `Q3-3.png` | Reuse the posting-chain overview to establish John Windward as the common terminal posting node; add historical-pattern and intervention evidence. |

`Q3-2.png` is deliberately excluded.

## Page integration

Create one figure block per image, placed after the existing answer paragraphs for Q1, Q2, and Q3 respectively. Each block will:

- use a submission-relative `src` path;
- constrain the image with `max-width: 100%` and automatic height so it fits the Word-style page layout;
- center the image;
- include descriptive English alternative text;
- add a brief English figure caption below the image.

The Q1-1 caption will state that the complete interactive HTML and D3 visualization are included as supplementary attachments. The Q3 captions will likewise direct reviewers to the supplementary interactive HTML and D3 visualizations. The reused Q1-2 caption in Q3 will explain its role in comparing `.txt`-based posting chains and identifying John Windward as their common final posting node.

## Captions

1. **Q1-1**: Detailed SwiftWren transmission chain. The complete interactive HTML and D3 visualization are provided as supplementary attachments.
2. **Q1-2 (Q1)**: System overview of SaidIT posting chains, contrasting direct-content and `.txt`-source posting paths.
3. **Q2**: Evidence linking SwiftWren.txt to Emma Harbor's preceding meeting activity and the candidate meeting-content sources.
4. **Q1-2 (Q3 reuse)**: Posting-chain overview used to compare the recurring `.txt`-based cases; it shows John Windward as the common final posting node before SaidIT publication.
5. **Q3-1**: Historical comparison of the three `.txt`-based SaidIT posting cases.
6. **Q3-3**: Intervention analysis supporting a validation check immediately before John Windward's agent submits content to SaidIT. The complete interactive HTML and D3 visualization are provided as supplementary attachments.

## Validation

After implementation, verify that all six referenced relative paths resolve, that no `Q3-2.png` reference remains, and that the HTML contains the required figure blocks in the specified Q1 → Q2 → Q3 order.
