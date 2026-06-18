"""
Step 4c: 完整追踪三个文件的所有相关事件
使用更宽泛的搜索模式
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
print("Step 4c: 完整追踪三个文件的所有相关事件")
print("=" * 70)

# 定义文件名关键词（用于搜索）
file_keywords = {
    'SwiftWren': ['swiftwren', 'swift_wren', 'swift-wren'],
    'HiddenOrca': ['hiddenorca', 'hidden_orca', 'hidden-orca'],
    'MellowOtter': ['mellowotter', 'mellow_otter', 'mellow-otter']
}

# 对每个文件进行完整追踪
for file_name, keywords in file_keywords.items():
    print(f"\n{'=' * 70}")
    print(f"追踪: {file_name}")
    print(f"{'=' * 70}")

    # 查找所有相关事件
    related_events = []
    for e in events:
        # 搜索多个字段
        search_text = ''
        search_text += str(e.get('short_name', '')).lower()
        search_text += str(e.get('parties', [])).lower()
        search_text += str(e.get('details', {})).lower()

        # 检查是否包含任何关键词
        if any(keyword in search_text for keyword in keywords):
            related_events.append(e)

    related_events.sort(key=lambda x: x['when'])

    print(f"相关事件总数: {len(related_events)}")

    if not related_events:
        continue

    # 显示事件类型统计
    event_types = {}
    for e in related_events:
        event_types[e['short_name']] = event_types.get(e['short_name'], 0) + 1

    print(f"\n事件类型统计:")
    for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  {event_type}: {count}")

    # 显示时间线（前30个事件）
    print(f"\n时间线（前30个事件）:")
    print(f"{'时间':20s} {'操作':25s} {'参与方'}")
    print("-" * 80)

    for e in related_events[:30]:
        time_str = datetime.fromtimestamp(e['when']).strftime('%m-%d %H:%M:%S')
        parties = str(e.get('parties', []))[:30]
        print(f"{time_str:20s} {e['short_name']:25s} {parties}")

    # 分析级联传播
    cascade_events = [e for e in related_events if 'queue' in e['short_name'].lower()]
    if cascade_events:
        print(f"\n级联传播事件 ({len(cascade_events)}):")
        for e in cascade_events[:20]:
            time_str = datetime.fromtimestamp(e['when']).strftime('%m-%d %H:%M')
            parties = e.get('parties', [])
            print(f"  {time_str} | {parties[0] if parties else 'unknown'} -> {parties[1:] if len(parties) > 1 else []}")

    # 统计涉及的 Agent
    all_parties = set()
    for e in related_events:
        for party in e.get('parties', []):
            all_parties.add(party)

    # 只统计 Agent/person
    agents = {p for p in all_parties if 'agent' in p.lower() or 'person' in p.lower()}
    print(f"\n涉及的 Agent/Person 数量: {len(agents)}")

    # 查找文件创建事件
    create_events = [e for e in related_events if 'create' in e['short_name'].lower() or 'write' in e['short_name'].lower()]
    if create_events:
        print(f"\n文件创建/写入事件:")
        for e in create_events:
            time_str = datetime.fromtimestamp(e['when']).strftime('%Y-%m-%d %H:%M:%S')
            details = e.get('details', {})
            if isinstance(details, dict):
                filename = details.get('filename', details.get('target', 'unknown'))
                size = details.get('size_hint', 0)
                print(f"  {time_str} | {e['short_name']} | {filename} | {size} bytes")

    # 查找 SaidIT 发布事件
    saidit_events = [e for e in related_events if 'saidit' in e['short_name'].lower() and 'post' in e['short_name'].lower()]
    if saidit_events:
        print(f"\nSaidIT 发布事件:")
        for e in saidit_events:
            time_str = datetime.fromtimestamp(e['when']).strftime('%Y-%m-%d %H:%M:%S')
            details = e.get('details', {})
            if isinstance(details, dict):
                forum = details.get('forum', 'unknown')
                content_source = details.get('content_source', 'unknown')
            print(f"  {time_str} | 论坛: {forum} | 内容来源: {content_source}")

# 保存完整追踪结果
output_data = {
    'analysis_summary': '完整追踪三个文件的级联传播模式'
}

output_file = session_dir / "step4c_full_trace.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

# 记录 PROV 关系
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_data", "entity_type": "dataset", "location": str(data_path)},
        {"id": "step4b_output", "entity_type": "dataset", "location": str(session_dir / "step4b_anomaly_comparison.json")},
        {"id": "step4c_output", "entity_type": "dataset", "location": str(output_file)}
    ],
    activities=[
        {"id": "step4c_act", "activity_type": "trace", "description": "完整追踪三个文件的级联传播"}
    ],
    agents=[
        {"id": "step4c_agent", "agent_type": "script", "name": "step4c_full_trace"}
    ],
    relations=[
        ("step4c_act", "raw_data", "used"),
        ("step4c_act", "step4b_output", "used"),
        ("step4c_output", "step4c_act", "wasGeneratedBy"),
        ("step4c_act", "step4c_agent", "wasAssociatedWith"),
        ("step4c_output", "raw_data", "wasDerivedFrom")
    ]
)

print(f"\n输出文件: {output_file}")
print("\nStep 4c 完成!")
