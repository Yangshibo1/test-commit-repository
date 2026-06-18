"""
VAST Challenge 2026 MC2 - 详细分析脚本
分析SaidIT帖子的具体内容和来源
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
print("SaidIT帖子详细分析")
print("="*80)

# 查找所有SaidIT相关帖子
saidit_events = events_df[
    events_df['short_name'].str.contains('saidit', case=False, na=False) |
    events_df['parties'].apply(lambda x: any('saidit' in str(p).lower() for p in x))
]

print(f"\n找到 {len(saidit_events)} 个SaidIT相关事件")

# 查找John Windward的SaidIT帖子
john_saidit = saidit_events[
    saidit_events['parties'].apply(lambda x: any('john_windward' in str(p).lower() for p in x))
]

print(f"John Windward的SaidIT事件: {len(john_saidit)}")

# 输出所有John Windward的SaidIT帖子详情
print("\n=== John Windward的SaidIT帖子详情 ===")
for idx, event in john_saidit.iterrows():
    print(f"\n时间: {event['datetime']}")
    print(f"动作: {event['short_name']}")
    print(f"参与方: {event['parties']}")
    if event['details']:
        print(f"详情: {json.dumps(event['details'], indent=2, ensure_ascii=False)[:800]}")

# 查找关键时间点的帖子
key_time_posts = saidit_events[
    (saidit_events['when'] >= KEY_EVENT_TIME - 3600) &
    (saidit_events['when'] <= KEY_EVENT_TIME + 3600)
]

print(f"\n=== 关键时间附近(±1小时)的SaidIT帖子 ===")
for idx, event in key_time_posts.iterrows():
    print(f"\n时间: {event['datetime']}")
    print(f"动作: {event['short_name']}")
    print(f"参与方: {event['parties']}")
    if event['details']:
        print(f"详情: {json.dumps(event['details'], indent=2, ensure_ascii=False)[:800]}")

# 查找所有包含帖子内容的事件
print("\n=== 查找所有可能包含帖子内容的事件 ===")
content_events = []
for idx, event in events_df.iterrows():
    details = event['details']
    if details and isinstance(details, dict):
        # 查找可能包含内容的字段
        for key in details:
            if any(keyword in key.lower() for keyword in ['content', 'text', 'message', 'body', 'post', 'title']):
                content_events.append({
                    'time': event['datetime'],
                    'action': event['short_name'],
                    'field': key,
                    'value': str(details[key])[:200],
                    'parties': event['parties']
                })

print(f"找到 {len(content_events)} 个包含内容的事件")
print("\n前20个内容事件:")
for i, ce in enumerate(content_events[:20]):
    print(f"\n{i+1}. 时间: {ce['time']}")
    print(f"   动作: {ce['action']}")
    print(f"   字段: {ce['field']}")
    print(f"   值: {ce['value']}")
    print(f"   参与方: {ce['parties'][:3]}")

# 分析异常帖子的产生过程
print("\n" + "="*80)
print("异常帖子产生过程分析")
print("="*80)

# 获取关键事件前48小时的John Windward相关事件
window_start = KEY_EVENT_TIME - 48 * 3600
window_end = KEY_EVENT_TIME + 3600

john_window = events_df[
    (events_df['when'] >= window_start) &
    (events_df['when'] <= window_end) &
    (events_df['parties'].apply(lambda x: any('john_windward' in str(p).lower() for p in x)))
].sort_values('when')

print(f"\n关键时间48小时内John Windward的事件: {len(john_window)}")
print("\n事件序列:")
for idx, event in john_window.iterrows():
    print(f"{event['datetime']} | {event['short_name']:25s} | {event['parties'][:2]}")

# 查找Agent相关活动
print("\n=== Agent相关活动 ===")
agent_events = events_df[
    (events_df['when'] >= window_start) &
    (events_df['when'] <= window_end) &
    (events_df['parties'].apply(lambda x: any('agent' in str(p).lower() for p in x)))
].sort_values('when')

print(f"关键时间48小时内Agent相关事件: {len(agent_events)}")
print("\n前30个Agent事件:")
for idx, event in agent_events.head(30).iterrows():
    print(f"{event['datetime']} | {event['short_name']:25s} | {event['parties'][:2]}")

# 保存结果
results = {
    'john_windward_saidit_posts': len(john_saidit),
    'key_time_posts': len(key_time_posts),
    'content_events_found': len(content_events),
    'john_window_events': len(john_window),
    'agent_window_events': len(agent_events)
}

with open('detailed_analysis_results.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n详细分析完成，结果已保存。")
