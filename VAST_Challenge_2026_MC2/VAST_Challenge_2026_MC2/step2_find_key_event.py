"""
Step 2: 查找关键时刻的异常 SaidIT 帖子
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
if not session_dirs:
    print("错误: 没有找到会话")
    sys.exit(1)

session_dir = session_dirs[0]
session_id = session_dir.name
print(f"使用会话: {session_id}")

# 加载上一步的数据
loaded_data_file = session_dir / "loaded_data.json"
with open(loaded_data_file, 'r', encoding='utf-8') as f:
    loaded_data = json.load(f)

events = loaded_data['events']
KEY_TIMESTAMP = loaded_data['key_timestamp']

print("=" * 70)
print("Step 2: 查找关键时刻的异常 SaidIT 帖子")
print("=" * 70)

# 关键时刻前后10秒的事件
time_window = 10  # 秒
key_events = []

for event in events:
    time_diff = abs(event['when'] - KEY_TIMESTAMP)
    if time_diff <= time_window:
        key_events.append({
            'id': event['id'],
            'short_name': event['short_name'],
            'when': event['when'],
            'datetime': str(datetime.fromtimestamp(event['when'])),
            'time_diff': time_diff,
            'parties': event.get('parties', []),
            'details': event.get('details', {})
        })

# 按时间排序
key_events.sort(key=lambda x: x['time_diff'])

print(f"\n关键10秒内的事件数: {len(key_events)}")

# 查找 John Windward 相关的 SaidIT 事件
john_windward_saidit = []
for event in key_events:
    parties_str = ' '.join(str(p) for p in event.get('parties', []))
    if ('saidit' in event['short_name'].lower() and
        'john_windward' in parties_str.lower()):
        john_windward_saidit.append(event)

print(f"John Windward 的 SaidIT 事件: {len(john_windward_saidit)}")

if john_windward_saidit:
    print("\n=== John Windward SaidIT 事件详情 ===")
    for event in john_windward_saidit:
        print(f"ID: {event['id']}")
        print(f"时间: {event['datetime']} (相差 {event['time_diff']:.2f} 秒)")
        print(f"操作: {event['short_name']}")
        print(f"参与方: {event['parties']}")
        print(f"详情: {event['details']}")
        print()

# 保存结果
output_data = {
    'key_timestamp': KEY_TIMESTAMP,
    'key_datetime': str(datetime.fromtimestamp(KEY_TIMESTAMP)),
    'time_window_seconds': time_window,
    'total_key_events': len(key_events),
    'john_windward_saidit_events': john_windward_saidit,
    'all_key_events': key_events
}

output_file = session_dir / "step2_key_events.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"输出文件: {output_file}")

# 记录 PROV 关系
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "step1_input", "entity_type": "dataset", "location": str(loaded_data_file)},
        {"id": "step2_output", "entity_type": "dataset", "location": str(output_file), "attributes": {"events": len(key_events), "john_saidit": len(john_windward_saidit)}}
    ],
    activities=[
        {"id": "step2_act", "activity_type": "filter", "description": "查找关键时刻的John Windward SaidIT事件"}
    ],
    agents=[
        {"id": "step2_agent", "agent_type": "script", "name": "step2_find_key_event"}
    ],
    relations=[
        ("step2_act", "step1_input", "used"),
        ("step2_output", "step2_act", "wasGeneratedBy"),
        ("step2_act", "step2_agent", "wasAssociatedWith"),
        ("step2_output", "step1_input", "wasDerivedFrom")
    ]
)

print("\nStep 2 完成!")
