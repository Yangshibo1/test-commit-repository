"""
探索数据中的实际时间戳分布
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# 加载数据
data_dir = Path(__file__).parent
data_path = data_dir / "MC2 data.json"

with open(data_path, 'r', encoding='utf-8') as f:
    mc2_data = json.load(f)

events = mc2_data.get('events', [])

print("=" * 70)
print("数据时间戳探索")
print("=" * 70)

# 计算时间范围
timestamps = [e['when'] for e in events]
min_time = min(timestamps)
max_time = max(timestamps)

print(f"事件总数: {len(events)}")
print(f"最早时间: {datetime.fromtimestamp(min_time)}")
print(f"最晚时间: {datetime.fromtimestamp(max_time)}")
print(f"时间跨度: {(max_time - min_time) / 86400:.1f} 天")

# 关键时间: 2046-05-17 04:21:15
KEY_TIMESTAMP = datetime(2046, 5, 17, 4, 21, 15).timestamp()
print(f"\n关键时间戳: {KEY_TIMESTAMP}")
print(f"关键时间: {datetime.fromtimestamp(KEY_TIMESTAMP)}")

# 查找 SaidIT 相关事件
saidit_events = []
for e in events:
    if 'saidit' in e['short_name'].lower():
        saidit_events.append(e)

print(f"\nSaidIT 事件总数: {len(saidit_events)}")

# 查找 John Windward 相关事件
john_events = []
for e in events:
    parties_str = ' '.join(str(p) for p in e.get('parties', []))
    if 'john_windward' in parties_str.lower():
        john_events.append(e)

print(f"John Windward 事件总数: {len(john_events)}")

# 交集
john_saidit = []
for e in saidit_events:
    parties_str = ' '.join(str(p) for p in e.get('parties', []))
    if 'john_windward' in parties_str.lower():
        john_saidit.append(e)

print(f"John Windward SaidIT 事件: {len(john_saidit)}")

if john_saidit:
    print("\n=== John Windward SaidIT 事件 ===")
    for e in john_saidit[:10]:
        print(f"ID: {e['id']}, 时间: {datetime.fromtimestamp(e['when'])}")
        print(f"  操作: {e['short_name']}")
        print(f"  参与方: {e.get('parties', [])}")
        print()

# 查找最接近关键时间的事件
time_diffs = [(abs(e['when'] - KEY_TIMESTAMP), e) for e in events]
time_diffs.sort(key=lambda x: x[0])

print("\n=== 最接近关键时间的事件 ===")
for diff, e in time_diffs[:5]:
    print(f"时间差: {diff:.2f} 秒")
    print(f"  时间: {datetime.fromtimestamp(e['when'])}")
    print(f"  操作: {e['short_name']}")
    print(f"  参与方: {e.get('parties', [])}")
    print()
