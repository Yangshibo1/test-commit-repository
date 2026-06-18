"""
VAST Challenge 2026 MC2 - Data Analysis
直接分析异常帖子的起因和内容
"""

import json
import pandas as pd
from datetime import datetime
from collections import defaultdict, Counter

# 加载数据
print("Loading data...")
with open('MC2 data.json', 'r', encoding='utf-8') as f:
    events_data = json.load(f)

with open('org_chart.json', 'r', encoding='utf-8') as f:
    org_data = json.load(f)

# 关键事件时间
KEY_EVENT_TIME = datetime(2046, 5, 17, 4, 21).timestamp()
print(f"Key event timestamp: {KEY_EVENT_TIME}")
print(f"Key event datetime: {datetime.fromtimestamp(KEY_EVENT_TIME)}")

# 创建DataFrame
events_list = []
for event in events_data['events']:
    events_list.append({
        'id': event['id'],
        'short_name': event['short_name'],
        'parties': event['parties'],
        'when': event['when'],
        'datetime': pd.to_datetime(event['when'], unit='s'),
        'details': event.get('details', {})
    })

events_df = pd.DataFrame(events_list)
print(f"\nTotal events: {len(events_df)}")
print(f"Date range: {events_df['datetime'].min()} to {events_df['datetime'].max()}")

# ============================================================================
# 问题1: 找到John Windward异常发帖的事件链
# ============================================================================
print("\n" + "="*80)
print("问题1: 异常帖子的产生过程")
print("="*80)

# 查找John Windward的所有事件
john_events = events_df[events_df['parties'].apply(
    lambda x: any('john_windward' in str(p).lower() for p in x)
)]
print(f"\nJohn Windward相关事件数: {len(john_events)}")

# 查找SaidIT相关帖子
saidit_posts = events_df[
    events_df['short_name'].isin(['post', 'posted', 'create_post', 'send_post', 'publish']) |
    events_df['parties'].apply(lambda x: any('saidit' in str(p).lower() for p in x))
]
print(f"SaidIT相关帖子数: {len(saidit_posts)}")

# 查找关键时间附近的事件
window_hours = 48
window_start = KEY_EVENT_TIME - window_hours * 3600
window_end = KEY_EVENT_TIME + 3600

chain_events = events_df[
    (events_df['when'] >= window_start) &
    (events_df['when'] <= window_end)
].sort_values('when')

print(f"\n关键时间48小时内的事件数: {len(chain_events)}")

# 输出事件链
print("\n=== 关键事件链（按时间顺序）===")
for idx, event in chain_events.head(50).iterrows():
    print(f"{event['datetime']} | {event['short_name']:20s} | {event['parties'][:3]}")

# ============================================================================
# 问题2: 分析帖子内容和来源
# ============================================================================
print("\n" + "="*80)
print("问题2: 帖子内容和来源分析")
print("="*80)

# 查找包含帖子内容的事件
print("\n查找帖子内容...")
post_content_events = []
for event in events_data['events']:
    details = event.get('details')
    if details and isinstance(details, dict):
        if any(key in details for key in ['content', 'text', 'message', 'body', 'post']):
            if KEY_EVENT_TIME - 86400 <= event['when'] <= KEY_EVENT_TIME + 3600:
                post_content_events.append(event)
                print(f"\n时间: {datetime.fromtimestamp(event['when'])}")
                print(f"动作: {event['short_name']}")
                print(f"参与方: {event['parties']}")
                print(f"详情: {json.dumps(details, indent=2)[:500]}")

# ============================================================================
# 问题3: 查找相似的历史模式
# ============================================================================
print("\n" + "="*80)
print("问题3: 相似历史模式查找")
print("="*80)

# 分析John Windward的所有活动模式
print("\nJohn Windward的活动模式:")
john_activity = john_events['short_name'].value_counts()
print(john_activity.head(20))

# 查找所有涉及Agent的帖子
agent_posts = events_df[
    events_df['parties'].apply(lambda x: any('agent:' in str(p) or 'Agent' in str(p) for p in x))
]
print(f"\n涉及Agent的事件数: {len(agent_posts)}")

# ============================================================================
# 问题4: 系统改进建议
# ============================================================================
print("\n" + "="*80)
print("问题4: 系统改进建议")
print("="*80)

# 分析关键事件链中的模式
print("\n关键事件链分析:")
print(f"1. 事件总数: {len(chain_events)}")
print(f"2. 参与方数量: {len(set([p for event in chain_events['parties'] for p in event]))}")

# 统计事件类型
event_types = chain_events['short_name'].value_counts()
print(f"\n3. 主要事件类型:")
for event_type, count in event_types.head(10).items():
    print(f"   {event_type}: {count}")

# 分析Agent相关活动
agent_activities = chain_events[
    chain_events['parties'].apply(lambda x: any('agent:' in str(p).lower() or 'Agent' in str(p) for p in x))
]
print(f"\n4. Agent相关活动: {len(agent_activities)}")

# 保存详细分析结果
analysis_results = {
    'key_event_time': datetime.fromtimestamp(KEY_EVENT_TIME).isoformat(),
    'john_windward_events': len(john_events),
    'saidit_posts': len(saidit_posts),
    'chain_events_48h': len(chain_events),
    'event_types': event_types.to_dict(),
    'agent_activities': len(agent_activities)
}

with open('analysis_results.json', 'w', encoding='utf-8') as f:
    json.dump(analysis_results, f, indent=2, ensure_ascii=False)

print("\n分析结果已保存到 analysis_results.json")
