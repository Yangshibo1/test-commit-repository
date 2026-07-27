# Three TXT Saidit Posting Chains Dataset Design

## Goal

Create one reusable JSON dataset containing the complete observable lifecycle for the three Saidit posts published from TXT files: `SwiftWren.txt`, `HiddenOrca.txt`, and `MellowOtter.txt`.

## Source and inclusion rules

The source is `VAST_Challenge_2026_MC2/MC2 data.json`, specifically its `events` array. The extractor must retain every event that directly references either a chain's primary TXT file or its matching instruction file:

- `SwiftWren.txt` and `SwiftWren_further_instructions.md`
- `HiddenOrca.txt` and `HiddenOrca_further_instructions.md`
- `MellowOtter.txt` and `MellowOtter_further_instructions.md`

An event directly references a file when the filename appears in one of these original fields:

- `details.target`
- `details.args.path`
- `details.task`
- `details.content_source`

The result must not infer or fabricate lifecycle events absent from source data. In particular, `HiddenOrca.txt` has no directly recorded create/read event and begins at its first observable delegation event.

## Dataset structure

The extractor writes `result/three_txt_posting_chains_dataset.json` with:

```json
{
  "metadata": {
    "description": "Complete observable lifecycle chains for all TXT-based Saidit posts",
    "source": "VAST_Challenge_2026_MC2/MC2 data.json",
    "chain_count": 3,
    "total_events": 248
  },
  "chains": {
    "SwiftWren.txt": {
      "post_id": 373902,
      "instruction_file": "SwiftWren_further_instructions.md",
      "events": []
    }
  },
  "all_events_chronological": []
}
```

Each retained event preserves all original fields and includes:

- `chain_file`: the corresponding primary TXT filename
- `related_file`: the specific primary or instruction filename referenced by the event
- `lifecycle_stage`: one of `create`, `read`, `delegate`, `post`, `delete`
- `is_post_event`: `true` only for the chain's final `saidit_post`

`chains` holds chronologically sorted per-file chains. `all_events_chronological` contains the same events combined and sorted ascending by `when`; it is intended for cross-chain temporal analysis.

## Expected coverage

The output must contain exactly the source event IDs directly associated with the two filenames for each chain:

| Chain | Expected events | Saidit post ID |
|---|---:|---:|
| `SwiftWren.txt` | 191 | 373902 |
| `HiddenOrca.txt` | 42 | 27290 |
| `MellowOtter.txt` | 15 | 98591 |

The merged chronological collection must contain 248 unique events. Every chain must contain its one Saidit post and its two file-deletion events. SwiftWren and MellowOtter must each contain their source-recorded creation events.
