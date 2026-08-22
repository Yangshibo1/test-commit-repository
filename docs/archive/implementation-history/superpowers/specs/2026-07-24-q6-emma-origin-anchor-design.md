# Q6 Emma Harbor and Draggable John Anchor Revision

## Purpose

Revise the Q6 D3 constrained personnel network so the stable left-side narrative anchor is **Emma Harbor**, rather than John Windward. John becomes an ordinary draggable personnel node while the proposed validation gate continues to follow John at a fixed right-side offset.

## Layout model

### Emma Harbor: fixed origin anchor

- `emma_harbor` is a fixed, non-draggable person node.
- Emma is anchored on the left side of the SwiftWren middle band.
- The anchor uses a responsive safe margin: it remains visible after stage resize and does not overlap the left edge or its label.
- Emma's initial x/y position becomes the origin-side counterpart to the existing right-side intervention relationship.

### John Windward: draggable convergence node

- `john_windward` is no longer a fixed force-simulation node.
- John remains visually emphasized as the observed convergence point but can be dragged and released using the same behavior as other ordinary people.
- Reset releases John's manual drag position together with other non-Emma personnel nodes, allowing the simulation to return John to its constrained target location.

### Validation gate: follows John

- The gate is not independently draggable.
- On every simulation tick, render update, drag update, and resize, its position is recomputed as a fixed horizontal offset directly right of John:

```text
Gate.x = John.x + 90
Gate.y = John.y
```

- The three distinct John-to-gate post edges remain separate, prominent, and labelled with their chain-local sequence numbers.

## Force and responsive constraints

- The existing band forces continue to bias SwiftWren people to the middle, HiddenOrca-only people to the upper band, and MellowOtter-only people to the lower band.
- Emma is the sole fixed person node and retains its fixed x/y coordinates during simulation and resize.
- John uses middle-band target forces and collision constraints, so a reset produces a readable convergence arrangement without pinning John.
- Responsive resize recomputes Emma's left anchor position. It must not reset a manually dragged John position.
- The wider horizontal overflow and 920px vertical drag workspace remain available for ordinary personnel, including John.

## Interaction and accessibility

- Emma is excluded from the drag behavior and is identified accessibly as the fixed origin anchor.
- John remains a focusable, selectable, draggable SVG button, with the existing click/Enter/Space behavior, visible focus treatment, and incident-edge disclosure.
- The validation gate remains the only non-person graph node and is not keyboard- or pointer-draggable.

## Acceptance criteria

1. Emma Harbor is present once, fixed, non-draggable, and visibly positioned at the responsive left-side SwiftWren anchor location.
2. John Windward is present once, retains convergence emphasis, and is draggable using pointer interaction.
3. The validation gate moves with John and stays exactly 90 world units to John's right at the same y coordinate.
4. Reset releases John but preserves Emma's anchor.
5. Stage resizing reanchors Emma without overwriting John’s manually pinned position.
6. All existing 238 viable event edges, three post edges, chain colors, numbering, accessibility controls, and progressive disclosure behavior remain unchanged.
7. Unit tests cover the new fixed/draggable role assignments, Emma responsive anchoring, John-to-gate following, and reset/resize preservation rules.

Emma Harbor is the sole fixed origin anchor. John Windward is an emphasized draggable convergence node; the validation gate is recomputed as a fixed right-side offset from John during rendering and does not independently participate in dragging.
