# Saidit TXT Timeline Readability Optimization Design

## Purpose

Improve the readability of the static full-evidence timeline at `result/saidit_posts_and_txt_chains_timeline.png` without changing its event collection, ordering, or visual evidence. The chart must continue to show every one of the 353 deduplicated events and all three traceable TXT-chain paths.

## Scope

This optimization changes only rendering geometry, X-axis tick selection, and right-side annotation/legend placement in `test/draw_saidit_posts_and_txt_chains_timeline.py`. It does not add events, filter events, aggregate employees, alter source data, or change the equal-spaced chronological sequence encoding.

## Data and coordinate invariants

- The chart remains based on the current 353 unique, deduplicated events.
- Events remain sorted by `(when, id)` and assigned sequence positions `1` through `353`.
- The X coordinate remains the equal-spaced event sequence, not elapsed time.
- The plot range remains `0.5` through `353.5`; the axis is not extended to `376` and no empty event positions are introduced.
- Employee rows, department grouping, point colors, point shapes, chain colors, and chain discontinuity behavior are unchanged.

## Rendering geometry

- Increase the figure width from 25 inches to approximately 34 inches to create materially more horizontal separation between adjacent sequence positions and clarify chain paths.
- Compress figure height from the current employee-scaled height (about 20.7 inches with 49 employees) to a bounded 14–15 inch range.
- Preserve department gap rows and separator lines, but reduce marker size and chain line width modestly as needed so compressed employee rows remain legible.
- Reserve a larger right-side margin for separate department labels and a legend column.

## X-axis ticks

- Continue producing regular sequence ticks at an interval of 25 positions.
- Always include the final event sequence position.
- Before applying the ticks, remove the preceding regular tick if it is too close to the terminal tick to be independently readable. For the current 353-event collection, this removes tick `351` and retains terminal tick `353`.
- This logic must be data-driven so future event counts do not create overlapping terminal tick labels.

## Right-side labels and dynamic legends

Department labels and legends occupy separate horizontal regions:

- Department labels remain immediately to the right of the plotting area and align vertically with the first row of each department group.
- The legend column is moved farther right than department labels, using a larger `bbox_to_anchor` X coordinate and a matching right subplot margin.
- The event-type legend is placed at the top of the legend column.
- The TXT-chain legend is positioned beneath the actual rendered extent of the event-type legend.
- The department-color legend is positioned beneath the actual rendered extent of the TXT-chain legend.
- Placement is calculated after a draw operation by converting each preceding legend's display bounding box into axes coordinates. A fixed vertical padding separates adjacent legend boxes.
- The legend placement code must not rely on hard-coded vertical anchors such as `1.0`, `0.76`, and `0.57` for the three groups.
- If all three legend blocks cannot fit in their available vertical region, reduce legend font size and spacing consistently before final placement; legends must remain in the dedicated column and must not overlap department labels.

## Testing

Extend the existing timeline rendering tests to verify:

- terminal X-axis labels avoid the near-duplicate final regular tick while retaining the final event position;
- the renderer uses the widened figure dimensions and compressed height policy;
- legends use a distinct, farther-right X anchor than department labels and chain/departments are placed from measured prior legend bounds rather than fixed Y constants;
- the real combined dataset still renders successfully to a PNG containing 353 events.

## Success criteria

- The full 353-event, employee-level evidence view remains intact.
- The final X-axis label is readable without colliding with its preceding tick label.
- Chain paths have greater horizontal visual separation.
- The chart is shorter and denser without losing employee or department context.
- No right-side legend overlaps a department label, regardless of the current legend item counts.
