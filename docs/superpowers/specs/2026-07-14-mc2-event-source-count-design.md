# MC2 Event Source Count Design

## Goal

Provide a small Python utility that counts MC2 events by their source entity and saves a compact, reusable JSON summary.

## Source Rule

For every event in `MC2 data.json`, the source entity is exactly the first element of `parties` (`parties[0]`). Events with a missing or empty `parties` field are counted separately as unresolved rather than assigned to a node.

Literal identity strings remain distinct. In particular, `person:john_windward`, `Agent/person:john_windward`, and `agent:person:john_windward` are separate nodes and are not normalized or merged.

## Inputs

- `VAST_Challenge_2026_MC2/MC2 data.json`: MC2 event log.
- `VAST_Challenge_2026_MC2/org_chart.json`: organization nodes used to add labels and types to matching source identities.

## Implementation

Create `test/vast_challenge_2026_mc2/count_event_sources.py`.

The script reads both inputs, linearly scans the event list once, and uses a counter keyed by the literal source string. It joins each count to the organization chart where an exact node ID match exists. It does not alter either input file.

## Output

Write `test/vast_challenge_2026_mc2/event_source_counts.json` with:

- input paths;
- total event count;
- resolved and unresolved source-event counts;
- an `organization_nodes` array containing every organization-chart node, including zero-count nodes;
- an `external_or_unmapped_nodes` array for source strings that are not exact organization-node IDs;
- per-node source ID, optional organization label/type, event count, and percentage of total events;
- arrays sorted by descending event count and then source ID.

This is an aggregate-only result: it intentionally excludes per-node event ID lists to keep the generated file small and the operation fast.

## Error Handling

The script should fail with a clear message if an input JSON file cannot be loaded or does not contain the expected event/node arrays. Malformed event records or empty `parties` arrays should be counted as unresolved and not terminate the complete run.

## Verification

Run the script against the included MC2 data. Confirm that the sum of all node counts plus unresolved events equals the total event count, all 75 organization nodes appear in the output, and the output JSON parses successfully.

## Scope

This work only produces the counting script and saved JSON summary. It does not create a chart, modify raw VAST data, normalize person/agent identities, or record event-level provenance.
