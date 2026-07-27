# Q1 Chain Visualization Design

## Time Zone
- **Data timezone**: UTC (Unix timestamp)
- **Display timezone**: MST/MDT (UTC-7) - Mountain Time
- **Conversion**: `display_time = utc_time - 7 hours`
- **Format**: "May 17, 2046 at 4:21am"

## Node Design (事件节点)

### Layout
```
┌─────────────────────────────┐
│      JOHN WINDWARD          │  ← Large uppercase name
│   queue_subordinate_task    │  ← Small task description
│   373893                    │  ← Event ID
│ May 17 at 4:21am            │  ← Converted time
└─────────────────────────────┘
```

### Visual Encoding
- **Shape**: Rectangular with rounded corners
- **Border color**: Department (see department colors below)
- **Border width**: 2px
- **Background**: White (#fff) or light variant based on department
- **Shadow**: Subtle drop shadow for depth

## Edge Design (有向边)

### Visual Elements
- **Direction**: Left to right with arrow
- **Label**: Shortened action name above arrow
- **Full description**: Small text below/aside arrow

### Examples
```
   read_file                 queue_subordinate_task
[Node A] ────────────────────────────────────> [Node B]
   read SwiftWren_further_instructions.md
```

### Edge Label Abbreviations
- `queue_subordinate_task` → `queue` or `→`
- `read_file` → `read`
- `saidit_post_check` → `check`
- `saidit_post` → `post`
- `create_file` → `create`
- `delete_file` → `delete`

## Department Color Scheme

| Department | Border Color | Background |
|-------------|--------------|-------------|
| Executive Suite | #d97745 (Orange) | #fff7ed |
| Customer Support | #2563eb (Blue) | #eff8ff |
| Products | #7c3aed (Purple) | #f5f3ff |
| Human Resources | #db2777 (Pink) | #fdf2f8 |
| Legal | #ca8a04 (Yellow) | #fefce8 |
| Information Technologies | #16a34a (Green) | #f0fdf4 |
| SaidIT System | #dc2626 (Red) | #fef2f2 |
| File System | #64748b (Slate) | #f8fafc |

## Layout Structure

### Grid Layout
- **Direction**: Left to right, then top to bottom
- **Nodes per row**: 5
- **Default view**: 2 rows (10 nodes)
- **Expanded view**: All 193 nodes (39 rows)

### Row Spacing
- Horizontal gap between nodes: 16px
- Vertical gap between rows: 40px
- Arrow size: 60-80px width

### Interaction
- **Default**: Show first 5 + last 5 nodes (similar to current 189-view)
- **Expand button**: "Show all 193 events"
- **Collapse button**: "Show first + last only"
- **Filter options**: By department, by task type

## Stage-Based Highlighting

Different stages can have subtle visual cues:
- **file_creation**: Green border accent
- **task_delegation**: Blue border accent
- **key_actions**: Red border accent (saidit_post, saidit_post_check)
- **cleanup**: Gray/dimmed (delete_file)

## Reference Implementation

Based on: `q_full_189_transfer_chain.html`

Key features to retain:
- Dark gradient background
- Paper-like container
- Department-based color coding
- Interactive filtering
- Clean, readable typography

## Data Structure

Input: `result/complete_swiftwren_chain.json`

Required transformations:
1. Convert Unix timestamp to MST (UTC-7)
2. Format time as "Month day, year at hour:am/pm"
3. Extract department info from person metadata
4. Generate node/edge relationships

## Next Steps

1. ✅ Time zone conversion logic
2. ⏳ Create visualization generator script
3. ⏳ Implement HTML/CSS/JS rendering
4. ⏳ Test with 193 events
5. ⏳ Optimize for performance
