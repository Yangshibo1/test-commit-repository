"""
Step 4b: 比较 SwiftWren、HiddenOrca、MellowOtter 三个异常案例
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
print("Step 4b: 比较三个异常案例")
print("=" * 70)

# 目标文件
target_files = ['SwiftWren.txt', 'HiddenOrca.txt', 'MellowOtter.txt']

# 对每个文件，追踪其生命周期
file_analyses = {}

for filename in target_files:
    print(f"\n{'=' * 60}")
    print(f"分析: {filename}")
    print(f"{'=' * 60}")

    # 查找所有相关事件
    related_events = []
    for e in events:
        search_str = str(e.get('parties', [])) + str(e.get('short_name', '')) + str(e.get('details', {}))
        if filename.lower() in search_str.lower():
            related_events.append(e)

    related_events.sort(key=lambda x: x['when'])

    print(f"相关事件总数: {len(related_events)}")

    if not related_events:
        continue

    # 第一个事件
    first_event = related_events[0]
    print(f"\n首次出现: {datetime.fromtimestamp(first_event['when'])}")
    print(f"操作: {first_event['short_name']}")
    print(f"参与方: {first_event.get('parties', [])}")

    # 查找创建者
    creator = None
    for e in related_events:
        if 'create' in e['short_name'].lower() or 'write' in e['short_name'].lower():
            creator = e.get('parties', ['unknown'])[0]
            break
        if e['short_name'] == 'file_created':
            creator = e.get('parties', ['unknown'])[0]
            break

    if not creator and related_events:
        creator = related_events[0].get('parties', ['unknown'])[0]

    print(f"创建者: {creator}")

    # 查找级联传播
    cascade_events = [e for e in related_events if e['short_name'] == 'queue_subordinate_task']
    print(f"级联传播事件: {len(cascade_events)}")

    # 构建传播网络
    agents_involved = set()
    for e in related_events:
        for party in e.get('parties', []):
            if 'agent' in str(party).lower() or 'person' in str(party).lower():
                agents_involved.add(party)

    print(f"涉及的 Agent: {len(agents_involved)}")

    # 查找最终 SaidIT 发布
    saidit_post = None
    for e in related_events:
        if 'saidit' in e['short_name'].lower() and 'post' in e['short_name'].lower():
            saidit_post = e
            break

    if saidit_post:
        post_time = datetime.fromtimestamp(saidit_post['when'])
        first_time = datetime.fromtimestamp(first_event['when'])
        duration = (saidit_post['when'] - first_event['when']) / 86400  # 天
        print(f"最终发布: {post_time}")
        print(f"传播时长: {duration:.1f} 天")
        print(f"发布者: {saidit_post.get('parties', ['unknown'])[0]}")

    # 查找发布后的删除事件
    if saidit_post:
        post_time = saidit_post['when']
        deletes_after = []
        for e in related_events:
            if e['short_name'] == 'delete_file' and 0 < (e['when'] - post_time) <= 60:
                deletes_after.append(e)
        if deletes_after:
            print(f"发布后删除事件: {len(deletes_after)}")
            for d in deletes_after:
                print(f"  {datetime.fromtimestamp(d['when'])} | {d.get('parties', ['unknown'])[0]}")

    # 显示事件流（前20个）
    print(f"\n事件流（前20个）:")
    for i, e in enumerate(related_events[:20]):
        time_str = datetime.fromtimestamp(e['when']).strftime('%m-%d %H:%M')
        print(f"  {i+1:2d}. {time_str} | {e['short_name']:30s} | {str(e.get('parties', []))[:40]}")

    file_analyses[filename] = {
        'events_count': len(related_events),
        'first_event': {
            'when': first_event['when'],
            'datetime': str(datetime.fromtimestamp(first_event['when'])),
            'short_name': first_event['short_name'],
            'creator': str(creator)
        },
        'cascade_events_count': len(cascade_events),
        'agents_involved': len(agents_involved),
        'saidit_post': {
            'when': saidit_post['when'],
            'datetime': str(datetime.fromtimestamp(saidit_post['when'])) if saidit_post else None,
            'poster': str(saidit_post.get('parties', ['unknown'])[0]) if saidit_post else None
        } if saidit_post else None,
        'duration_days': (saidit_post['when'] - first_event['when']) / 86400 if saidit_post else None,
        'event_sample': [
            {
                'when': e['when'],
                'datetime': str(datetime.fromtimestamp(e['when'])),
                'short_name': e['short_name'],
                'parties': e.get('parties', [])
            }
            for e in related_events[:30]
        ]
    }

# 比较分析
print(f"\n{'=' * 70}")
print("三个案例对比")
print(f"{'=' * 70}")

print(f"\n{'文件':20s} {'创建时间':20s} {'传播天数':10s} {'事件数':10s} {'Agent数':10s}")
print("-" * 80)

for filename in target_files:
    if filename in file_analyses:
        analysis = file_analyses[filename]
        create_time = analysis['first_event']['datetime']
        duration = analysis.get('duration_days', 0)
        events = analysis['events_count']
        agents = analysis['agents_involved']

        print(f"{filename:20s} {create_time:20s} {duration:9.1f} {events:10d} {agents:10d}")

# 保存结果
output_data = {
    'file_analyses': file_analyses,
    'summary': {
        'total_anomalies': len(file_analyses),
        'pattern': '文件创建 -> Agent级联传播 -> SaidIT发布 -> 删除文件'
    }
}

output_file = session_dir / "step4b_anomaly_comparison.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

# 记录 PROV 关系
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_data", "entity_type": "dataset", "location": str(data_path)},
        {"id": "step4a_output", "entity_type": "dataset", "location": str(session_dir / "step4_content_analysis.json")},
        {"id": "step4b_output", "entity_type": "dataset", "location": str(output_file)}
    ],
    activities=[
        {"id": "step4b_act", "activity_type": "compare", "description": "比较三个异常案例的模式"}
    ],
    agents=[
        {"id": "step4b_agent", "agent_type": "script", "name": "step4b_compare_anomalies"}
    ],
    relations=[
        ("step4b_act", "raw_data", "used"),
        ("step4b_act", "step4a_output", "used"),
        ("step4b_output", "step4b_act", "wasGeneratedBy"),
        ("step4b_act", "step4b_agent", "wasAssociatedWith"),
        ("step4b_output", "raw_data", "wasDerivedFrom")
    ]
)

print(f"\n输出文件: {output_file}")
print("\nStep 4b 完成!")
