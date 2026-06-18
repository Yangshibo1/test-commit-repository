"""
VAST Challenge 2026 MC2 - 追踪异常帖子的来源
查找SwiftWren.txt文件的创建过程和内容
"""

import json
import pandas as pd
from datetime import datetime

# 加载数据
print("Loading data...")
with open('MC2 data.json', 'r', encoding='utf-8') as f:
    events_data = json.load(f)

# 关键事件时间
KEY_EVENT_TIME = datetime(2046, 5, 17, 4, 21).timestamp()

# 创建DataFrame
events_list = []
for event in events_data['events']:
    events_list.append({
        'id': event['id'],
        'short_name': event['short_name'],
        'parties': event['parties'],
        'when': event['when'],
        'datetime': pd.to_datetime(event['when'], unit='s'),
        'details': event.get('details')
    })

events_df = pd.DataFrame(events_list)

print("\n" + "="*80)
print("追踪SwiftWren.txt文件的来源")
print("="*80)

# 查找所有涉及SwiftWren的事件
swiftwren_events = []
for idx, event in events_df.iterrows():
    search_str = str(event['parties']) + str(event['details'])
    if 'swiftwren' in search_str.lower() or 'SwiftWren' in search_str:
        swiftwren_events.append(event)

print(f"\n找到 {len(swiftwren_events)} 个涉及SwiftWren的事件")
print("\n=== SwiftWren相关事件 ===")
for event in sorted(swiftwren_events, key=lambda x: x['when']):
    print(f"\n时间: {event['datetime']}")
    print(f"动作: {event['short_name']}")
    print(f"参与方: {event['parties']}")
    if event['details']:
        print(f"详情: {json.dumps(event['details'], indent=2, ensure_ascii=False)[:600]}")

# 查找所有创建文件的事件
print("\n" + "="*80)
print("查找所有文件创建事件（可能在48小时窗口内）")
print("="*80)

window_start = KEY_EVENT_TIME - 48 * 3600
window_end = KEY_EVENT_TIME + 3600

create_file_events = events_df[
    (events_df['when'] >= window_start) &
    (events_df['when'] <= window_end) &
    (events_df['short_name'].str.contains('create_file|write_file|save_file', case=False, na=False))
]

print(f"\n关键时间48小时内文件创建事件: {len(create_file_events)}")
for idx, event in create_file_events.iterrows():
    print(f"\n时间: {event['datetime']}")
    print(f"动作: {event['short_name']}")
    print(f"参与方: {event['parties']}")
    if event['details']:
        print(f"详情: {json.dumps(event['details'], indent=2, ensure_ascii=False)[:400]}")

# 查找所有包含.txt文件的引用
print("\n" + "="*80)
print("查找所有涉及.txt文件的事件")
print("="*80)

txt_events = []
for idx, event in events_df.iterrows():
    search_str = str(event['parties']) + str(event['details'])
    if '.txt' in search_str:
        txt_events.append(event)

print(f"\n找到 {len(txt_events)} 个涉及.txt文件的事件")
print("\n前30个.txt文件相关事件:")
for event in sorted(txt_events, key=lambda x: x['when'])[:30]:
    print(f"\n时间: {event['datetime']}")
    print(f"动作: {event['short_name']}")
    if event['details']:
        # 尝试提取文件名
        details_str = str(event['details'])
        if '.txt' in details_str:
            start = details_str.find('.txt') - 20
            if start < 0:
                start = 0
            end = details_str.find('.txt') + 4
            print(f"文件引用: ...{details_str[start:end]}...")

# 分析异常内容
print("\n" + "="*80)
print("异常帖子分析")
print("="*80)

print("\n关键发现:")
print("1. John Windward的Agent在5月17日11:21:14发布了SaidIT帖子")
print("2. 帖子内容来源是: SwiftWren.txt")
print("3. 这是一个Agent自动发布的帖子，没有人工审核")
print("4. 需要查找SwiftWren.txt是如何创建的")

# 查找所有内容来源文件
content_sources = set()
for event in events_df[events_df['short_name'].str.contains('saidit', case=False, na=False)].iterrows():
    details = event[1]['details']
    if details and isinstance(details, dict):
        if 'content_source' in details:
            content_sources.add(details['content_source'])

print(f"\n所有SaidIT帖子的内容来源文件:")
for source in sorted(content_sources):
    print(f"  - {source}")

# 保存结果
results = {
    'swiftwren_events_count': len(swiftwren_events),
    'content_sources': list(content_sources),
    'txt_files_count': len(txt_events)
}

with open('trace_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n追踪完成，结果已保存。")
