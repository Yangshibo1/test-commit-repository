# Q6 Personnel-Chain Intervention Visualization Design

## Purpose

Create one static PNG for VAST Challenge 2026 MC2 Question 6. The figure must show why a single pre-publication validation gate at the `saidit_post` workflow is an effective intervention for the three observed TXT-derived anomalous posting chains.

The figure is a personnel transfer network, not an HTML dashboard, chart matrix, or before/after page. It preserves every directionally viable record from the extracted time dataset as a distinct directed edge while keeping each person visible exactly once.

## Evidence boundary

The available data supports a claim about the three observed anomalous chains only. The figure must state that the proposed validation gate covers all three observed chains and must not claim that every future anomaly will route through John Windward’s workflow.

## Input contract

The extracted dataset stores ordered event parties rather than universal explicit `source` and `target` fields. For a record with exactly two normalized people, the first person is the source and the second is the target. A one-person `saidit_post` performed by John Windward is projected as John Windward → Validation Gate. One-person filesystem events and events with more than two people are omitted because no directed personnel relationship can be supported without fabricating an endpoint.

Each directionally viable event yields one visible directed edge. Repeated transfers between the same people remain separate edges. Sequence numbers are contiguous among rendered events within each chain.

For the current dataset, 238 of 248 raw records are directionally viable: 187 SwiftWren, 40 HiddenOrca, and 11 MellowOtter. Ten unipersonal filesystem records are omitted rather than assigning them invented personnel endpoints.

For the three final `saidit_post` events, the target is represented visually by the single validation-gate node rather than by a person. These remain separate edges, one per chain.

## Layout

### Reading direction

The network reads left to right. Time determines the order labels on edges, not a globally shared horizontal time scale.

### Chain placement

- `SwiftWren.txt` is the middle anchor chain.
- `HiddenOrca.txt` occupies the upper band.
- `MellowOtter.txt` occupies the lower band.

People in the SwiftWren chain establish the center-row column ordering from their first appearance in that chain. A person who appears in a supplementary chain but not in the center chain is placed in the upper or lower band beside the column of their first connection to an already placed person. This preserves local attachment order without duplicating shared people.

All person nodes are globally unique. A person shared across chains appears once at the same coordinate and receives edges from every applicable chain.

## Marks and encodings

### Nodes

- Every person is a rounded rectangular node labelled only with the person’s display name.
- A person appears at most once in the figure.
- John Windward appears once and is visually emphasized as the observed convergence point.
- The `saidit_post validation gate` is the sole non-person node. It is a diamond placed directly to the right of John Windward.
- No files, system modules, actions, or intermediate technical objects become graph nodes.

### Edges

- Every source-to-target record is rendered as a directed arrow.
- Each chain has a stable, legend-labelled color:
  - `SwiftWren.txt`: red;
  - `HiddenOrca.txt`: blue;
  - `MellowOtter.txt`: black.
- Multiple edges sharing a source and target must be rendered as distinct, slightly offset curved arrows rather than merged.
- Multiple edges arriving at the validation gate must also remain distinct. The three John-to-gate `saidit_post` arrows use their chain colors and slight curvature offsets.
- Each chain is sorted by its own event timestamp and numbered independently from `1` through its final event.
- The numeric order label is placed near the midpoint of its associated arrow. Edge labels contain only the number; they do not display timestamps, event types, file names, or system-module names.

### Intervention annotation

The validation-gate area includes the concise operational rule:

```text
content_source exists + content empty → block + audit
```

The gate represents a pre-publication check that resolves file-derived content and requires a non-empty body before allowing the post to proceed.

## Supporting labels

The figure includes:

- a descriptive title identifying the three observed TXT posting chains and their convergence at John Windward’s posting workflow;
- a legend mapping each chain color to its TXT file, explaining that edge numbers are event order within a chain, and identifying the diamond as the proposed validation gate;
- a concise scope note stating that the gate covers the three observed anomalous chains but does not establish that all future anomalies will follow the same workflow.

## Exclusions

The deliverable does not add or preserve a complex HTML Q6 page, case matrix, full event-text labels, hover interactions, or separate pre/post panels. The existing HTML visualization is outside the scope of this change unless a later request explicitly changes it.

## Acceptance criteria

1. The generator produces the Q6 PNG successfully from the extracted three-chain time dataset.
2. Every unique person occurs only once in the rendered graph.
3. Every directionally viable event creates exactly one directed arrow, including repeated person-to-person transfers and all three John-to-gate post events.
4. The three chains use stable distinct colors and independent edge numbering beginning at `1`.
5. Every edge number is positioned near its arrow midpoint.
6. SwiftWren is centered, HiddenOrca is above it, and MellowOtter is below it; supplementary-only people are inserted at their first attachment location.
7. The only non-person node is the diamond-shaped validation gate to John Windward’s right.
8. The output has a readable legend, a gate rule, and the observed-case-only caveat.
9. Automated tests verify the graph extraction, ordering, unique-person placement inputs, preservation of duplicate edges, three final post edges, and output generation.
