"""
Step 3: 追踪 SwiftWren.txt 的起源和级联传播链
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
print("Step 3: 追踪 SwiftWren.txt 起源和级联传播链")
print("=" * 70)

# 查找所有 SwiftWren 相关事件
swiftwren_events = []
for e in events:
    search_str = str(e.get('parties', [])) + str(e.get('short_name', '')) + str(e.get('details', {}))
    if 'swiftwren' in search_str.lower():
        swiftwren_events.append(e)

# 按时间排序
swiftwren_events.sort(key=lambda x: x['when'])

print(f"\nSwiftWren 相关事件总数: {len(swiftwren_events)}")

# 查找 SwiftWren.txt 的创建事件
swiftwren_creation = None
swiftwren_file_events = []

for e in swiftwren_events:
    details = e.get('details', {})
    if isinstance(details, dict):
        if 'filename' in details and 'swiftwren' in details['filename'].lower():
            swiftwren_file_events.append(e)
        if e['short_name'] in ['create_file', 'write_file', 'generate_file']:
            swiftwren_creation = e
            break

# 查找第一个 SwiftWren 相关事件
first_swiftwren = min(swiftwren_events, key=lambda x: x['when'])

print(f"\n=== 第一个 SwiftWren 事件 ===")
print(f"时间: {datetime.fromtimestamp(first_swiftwren['when'])}")
print(f"操作: {first_swiftwren['short_name']}")
print(f"参与方: {first_swiftwren.get('parties', [])}")
print(f"详情: {json.dumps(first_swiftwren.get('details', {}), indent=2)}")

# 查找 queue_subordinate_task 事件（级联传播）
cascade_events = []
for e in swiftwren_events:
    if e['short_name'] == 'queue_subordinate_task':
        cascade_events.append(e)

print(f"\n=== 级联传播事件 (queue_subordinate_task) ===")
print(f"总数: {len(cascade_events)}")

# 构建传播网络
propagation_chain = []
for e in cascade_events:
    parties = e.get('parties', [])
    if len(parties) >= 2:
        from_agent = parties[0]
        to_agents = parties[1:]
        propagation_chain.append({
            'when': e['when'],
            'datetime': str(datetime.fromtimestamp(e['when'])),
            'from': from_agent,
            'to': to_agents,
            'id': e['id']
        })

# 显示传播链
print(f"\n=== Agent 级联传播链 ===")
visited = set()
current_level = [first_swiftwren.get('parties', ['unknown'])[0]]
level = 0

# 简化的传播图
propagation_map = {}
for e in propagation_chain:
    from_agent = e['from']
    to_agents = e['to']
    if from_agent not in propagation_map:
        propagation_map[from_agent] = set()
    for to_agent in to_agents:
        propagation_map[from_agent].add(to_agent)

# 打印传播路径
print(f"\n传播路径（按时间顺序）:")
for i, link in enumerate(propagation_chain[:30]):
    print(f"{i+1}. {datetime.fromtimestamp(link['when']).strftime('%m-%d %H:%M')} | {link['from']} -> {link['to']}")

# 统计涉及的 Agent
all_agents = set()
for e in propagation_chain:
    all_agents.add(e['from'])
    all_agents.update(e['to'])

print(f"\n涉及的 Agent 数量: {len(all_agents)}")

# 查找最后一个事件（john_windward）
final_event = None
for e in swiftwren_events:
    if 'john_windward' in str(e.get('parties', [])).lower():
        if e['short_name'] == 'saidit_post':
            final_event = e
            break

print(f"\n=== 最终事件（John Windward 发布帖子）===")
print(f"时间: {datetime.fromtimestamp(final_event['when'])}")
print(f"操作: {final_event['short_name']}")
print(f"内容来源: {final_event.get('details', {}).get('content_source', 'N/A')}")

# 计算传播时长
duration_hours = (final_event['when'] - first_swiftwren['when']) / 3600
print(f"\n传播时长: {duration_hours:.1f} 小时 ({duration_hours/24:.1f} 天)")

# 保存结果
output_data = {
    'swiftwren_events_count': len(swiftwren_events),
    'first_event': {
        'when': first_swiftwren['when'],
        'datetime': str(datetime.fromtimestamp(first_swiftwren['when'])),
        'short_name': first_swiftwren['short_name'],
        'parties': first_swiftwren.get('parties', []),
        'details': first_swiftwren.get('details', {})
    },
    'final_event': {
        'when': final_event['when'],
        'datetime': str(datetime.fromtimestamp(final_event['when'])),
        'short_name': final_event['short_name'],
        'parties': final_event.get('parties', []),
        'details': final_event.get('details', {})
    },
    'cascade_events_count': len(cascade_events),
    'agents_involved': len(all_agents),
    'propagation_chain': propagation_chain[:50],
    'duration_hours': duration_hours,
    'all_swiftwren_events': [
        {
            'id': e['id'],
            'when': e['when'],
            'datetime': str(datetime.fromtimestamp(e['when'])),
            'short_name': e['short_name'],
            'parties': e.get('parties', []),
            'details': e.get('details', {})
        }
        for e in swiftwren_events[:100]
    ]
}

output_file = session_dir / "step3_swiftwren_origin.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

# 记录 PROV 关系
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_data", "entity_type": "dataset", "location": str(data_path)},
        {"id": "step2_output", "entity_type": "dataset", "location": str(session_dir / "step2_suspect_event.json")},
        {"id": "step3_output", "entity_type": "dataset", "location": str(output_file), "attributes": {"events": len(swiftwren_events), "agents": len(all_agents)}}
    ],
    activities=[
        {"id": "step3_act", "activity_type": "trace", "description": "追踪SwiftWren.txt起源和Agent级联传播链", "attributes": {"duration_hours": duration_hours}}
    ],
    agents=[
        {"id": "step3_agent", "agent_type": "script", "name": "step3_trace_swiftwren"}
    ],
    relations=[
        ("step3_act", "raw_data", "used"),
        ("step3_act", "step2_output", "used"),
        ("step3_output", "step3_act", "wasGeneratedBy"),
        ("step3_act", "step3_agent", "wasAssociatedWith"),
        ("step3_output", "raw_data", "wasDerivedFrom")
    ]
)

print(f"\n输出文件: {output_file}")
print("\nStep 3 完成!")
