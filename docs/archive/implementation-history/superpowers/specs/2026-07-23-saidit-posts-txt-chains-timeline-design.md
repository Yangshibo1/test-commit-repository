# Saidit Posts and TXT Chain Timeline Design

## Purpose

Create one interactive point-and-line timeline that places all Saidit posting activity in the same chronological and organizational context as the three traceable TXT-file posting chains. The visualization supports comparison between routine direct posts and the propagation paths associated with `SwiftWren.txt`, `HiddenOrca.txt`, and `MellowOtter.txt`.

## Inputs

- `result/all_posts_dataset.json`: 108 Saidit posting events.
- `result/three_txt_posting_chains_dataset.json`: 248 observable events from the three TXT-file chains.
- `VAST_Challenge_2026_MC2/org_chart.json`: authoritative employee list and department assignments.

Records shared by the post and chain datasets are deduplicated by event `id`. The expected combined collection contains 353 unique events: 108 Saidit posts plus 245 non-post chain events.

## Visual encoding

### Coordinates

- The horizontal axis uses chronological **event sequence**, not continuous elapsed time. All 353 deduplicated events are sorted by `(when, id)` and assigned equal-spaced sequence positions from 1 to 353.
- The event timestamp determines only the order of points. It does not affect horizontal distance between them.
- The X-axis title is `Event sequence (chronological order)` and labeled ticks occur at a fixed sequence interval.
- The vertical axis has one row for every employee present in the organization chart.
- Employees are grouped by department from top to bottom. Department blocks have labels and extra vertical separation.
- Unmatched `Agent/person:*` values, `system:*` values, and other non-organization entities are excluded from the vertical axis.

### Event points

Each event is located at its sequence position and the row of its primary actor. For multi-party events, the primary actor is the first party in the source `parties` list. This identifies the delegator for `queue_subordinate_task` events and the active operator for other recorded actions.

- Point color encodes the primary actor's department.
- Point shape encodes event type:
  - circle: `saidit_post`
  - square: `create_file`
  - diamond: `read_file`
  - triangle: `queue_subordinate_task`
  - cross: `delete_file`

### Chain lines

For each TXT chain, events are ordered by sequence position and their visible employee points are connected. A chain line breaks when an event belongs to an actor not represented in the organization chart. Lines are drawn below points with partial transparency.

- SwiftWren: fixed line color A
- HiddenOrca: fixed line color B
- MellowOtter: fixed line color C

Line color identifies the file chain and never replaces the department color carried by point marks.

## Interaction

Hovering any visible point reveals timestamp, employee, department, event type, related file, chain file when present, and source event ID. Filters allow the reader to show all events, only Saidit posts, or one of the three TXT chains. The default is all posts plus all three chains.

The chart contains separate legends for department colors, event shapes, and chain-line colors.

## Interpretation limits

The visual display distinguishes recorded links from inferred relationships. Direct-content Saidit posts are placed in organizational and sequence context but are not connected by a line because they have no explicit `content_source` chain. Likewise, source events whose primary actor cannot be matched to the organization chart are omitted from the Y axis and cause a visible chain discontinuity rather than being assigned to an inferred department.

The equal-spaced X axis emphasizes event ordering and propagation structure. It must not be interpreted as a scale of elapsed duration; original timestamps remain available in event details for duration analysis.
