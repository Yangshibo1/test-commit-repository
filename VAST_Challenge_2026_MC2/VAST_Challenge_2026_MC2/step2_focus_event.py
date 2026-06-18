"""
深入研究可疑的 SaidIT 事件
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opentrace.mcp_server import get_server

# 获取服务器和会话
server = get_server(".opentrace")

# 读取最新会话
import glob
session_dirs = sorted(Path(".opentrace").glob("session_*"), key=lambda x: x.stat().st_mtime, reverse=True)
session_dir = session_dirs[0]
session_id = session_dir.name

# 加载数据
data_dir = Path(__file__).parent
data_path = data_dir / "MC2 data.json"

with open(data_path, 'r', encoding='utf-8') as f:
    mc2_data = json.load(f)

events = mc2_data.get('events', [])

print("=" * 70)
print("Step 2: 深入研究可疑的 SaidIT 事件")
print("=" * 70)

# 目标事件 ID: 373902 (2046-05-17 19:21:15)
TARGET_EVENT_ID = 373902

# 查找这个事件的完整信息
target_event = None
for e in events:
    if e['id'] == TARGET_EVENT_ID:
        target_event = e
        break

if target_event:
    print(f"\n=== 目标事件 (ID: {TARGET_EVENT_ID}) ===")
    print(f"时间: {datetime.fromtimestamp(target_event['when'])}")
    print(f"操作: {target_event['short_name']}")
    print(f"参与方: {target_event.get('parties', [])}")
    print(f"详情: {json.dumps(target_event.get('details', {}), indent=2)}")

# 查找这个事件前后的相关事件 (前后1小时)
target_time = target_event['when'] if target_event else 0
time_window = 3600  # 1小时

nearby_events = []
for e in events:
    time_diff = abs(e['when'] - target_time)
    if time_diff <= time_window:
        nearby_events.append(e)

print(f"\n=== 前后1小时内的相关事件 ({len(nearby_events)}) ===")

# 按时间排序
nearby_events.sort(key=lambda x: x['when'])

# 显示前50个事件
for i, e in enumerate(nearby_events[:50]):
    time_offset = e['when'] - target_time
    offset_str = f"{time_offset:+.1f}s"
    print(f"{offset_str:10s} | {datetime.fromtimestamp(e['when']).strftime('%H:%M:%S')} | {e['short_name']:30s} | {str(e.get('parties', []))[:50]}")

# 特别关注 SwiftWren 相关的事件
swiftwren_events = []
for e in nearby_events:
    search_str = str(e.get('parties', [])) + str(e.get('short_name', '')) + str(e.get('details', {}))
    if 'swiftwren' in search_str.lower():
        swiftwren_events.append(e)

print(f"\n=== SwiftWren 相关事件 ({len(swiftwren_events)}) ===")
for e in swiftwren_events[:20]:
    time_offset = e['when'] - target_time
    print(f"{time_offset:+8.1f}s | {datetime.fromtimestamp(e['when']).strftime('%H:%M:%S')} | {e['short_name']}")
    print(f"           参与方: {e.get('parties', [])}")

# 保存结果
output_data = {
    'target_event_id': TARGET_EVENT_ID,
    'target_event': target_event,
    'nearby_events_count': len(nearby_events),
    'swiftwren_events_count': len(swiftwren_events),
    'nearby_events_summary': [
        {
            'id': e['id'],
            'when': e['when'],
            'datetime': str(datetime.fromtimestamp(e['when'])),
            'time_offset': e['when'] - target_time,
            'short_name': e['short_name'],
            'parties': e.get('parties', []),
            'details': e.get('details', {})
        }
        for e in nearby_events[:100]
    ],
    'swiftwren_events': [
        {
            'id': e['id'],
            'when': e['when'],
            'datetime': str(datetime.fromtimestamp(e['when'])),
            'time_offset': e['when'] - target_time,
            'short_name': e['short_name'],
            'parties': e.get('parties', []),
            'details': e.get('details', {})
        }
        for e in swiftwren_events
    ]
}

output_file = session_dir / "step2_suspect_event.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

# 记录 PROV 关系
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_data", "entity_type": "dataset", "location": str(data_path)},
        {"id": "step2_output", "entity_type": "dataset", "location": str(output_file), "attributes": {"target_event": TARGET_EVENT_ID}}
    ],
    activities=[
        {"id": "step2_act", "activity_type": "filter", "description": "深入分析可疑SaidIT事件及其前因后果"}
    ],
    agents=[
        {"id": "step2_agent", "agent_type": "script", "name": "step2_focus_event"}
    ],
    relations=[
        ("step2_act", "raw_data", "used"),
        ("step2_output", "step2_act", "wasGeneratedBy"),
        ("step2_act", "step2_agent", "wasAssociatedWith"),
        ("step2_output", "raw_data", "wasDerivedFrom")
    ]
)

print(f"\n输出文件: {output_file}")
print("\nStep 2 完成!")
