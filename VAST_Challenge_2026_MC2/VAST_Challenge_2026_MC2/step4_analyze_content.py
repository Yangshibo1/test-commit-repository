"""
Step 4: 分析内容质量和历史异常模式
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
print("Step 4: 分析内容质量和历史异常模式")
print("=" * 70)

# 1. 查找所有文件创建事件（检测是否有类似的问题）
file_creation_events = []
for e in events:
    if e['short_name'] in ['create_file', 'write_file', 'generate_file']:
        details = e.get('details', {})
        if isinstance(details, dict) and 'filename' in details:
            file_creation_events.append(e)

print(f"\n文件创建事件总数: {len(file_creation_events)}")

# 2. 查找大文件（可能包含乱码）
large_files = []
for e in file_creation_events:
    details = e.get('details', {})
    if isinstance(details, dict):
        size = details.get('size_hint', 0)
        if size > 10000:  # 大于 10KB
            large_files.append({
                'id': e['id'],
                'when': e['when'],
                'datetime': str(datetime.fromtimestamp(e['when'])),
                'filename': details.get('filename', 'unknown'),
                'size': size,
                'creator': e.get('parties', ['unknown'])[0]
            })

large_files.sort(key=lambda x: x['size'], reverse=True)

print(f"\n=== 大文件（>10KB）分析 ===")
for f in large_files[:20]:
    print(f"  {f['filename']:30s} | {f['size']:6d} bytes | {f['datetime']} | {f['creator']}")

# 3. 查找 emma_harbor 的所有活动（SwiftWren.txt 创建者）
emma_events = []
for e in events:
    parties_str = str(e.get('parties', []))
    if 'emma_harbor' in parties_str.lower():
        emma_events.append(e)

print(f"\n=== Emma Harbor 的活动 ===")
print(f"总事件数: {len(emma_events)}")

# 查看 Emma 的文件创建活动
emma_files = []
for e in emma_events:
    if e['short_name'] in ['create_file', 'write_file']:
        details = e.get('details', {})
        if isinstance(details, dict) and 'filename' in details:
            emma_files.append({
                'when': e['when'],
                'datetime': str(datetime.fromtimestamp(e['when'])),
                'filename': details.get('filename', ''),
                'size': details.get('size_hint', 0),
                'action': e['short_name']
            })

emma_files.sort(key=lambda x: x['when'])

print(f"\nEmma Harbor 创建的文件:")
for f in emma_files[:10]:
    print(f"  {f['datetime']} | {f['filename']:30s} | {f['size']:6d} bytes")

# 4. 查找所有 SaidIT 帖子事件
saidit_posts = []
for e in events:
    if 'saidit' in e['short_name'].lower() and 'post' in e['short_name'].lower():
        details = e.get('details', {})
        if isinstance(details, dict) and 'content_source' in details:
            saidit_posts.append({
                'id': e['id'],
                'when': e['when'],
                'datetime': str(datetime.fromtimestamp(e['when'])),
                'poster': str(e.get('parties', ['unknown'])[0]),
                'content_source': details.get('content_source', ''),
                'forum': details.get('forum', '')
            })

print(f"\n=== SaidIT 帖子事件（带内容来源）===")
print(f"总数: {len(saidit_posts)}")

# 统计内容来源
content_sources = {}
for post in saidit_posts:
    source = post['content_source']
    content_sources[source] = content_sources.get(source, 0) + 1

print(f"\n内容来源统计:")
for source, count in sorted(content_sources.items(), key=lambda x: x[1], reverse=True):
    print(f"  {source:30s}: {count}")

# 5. 查找删除文件事件（在异常帖子后）
delete_events = []
for e in events:
    if e['short_name'] == 'delete_file':
        details = e.get('details', {})
        delete_events.append({
            'id': e['id'],
            'when': e['when'],
            'datetime': str(datetime.fromtimestamp(e['when'])),
            'deleter': str(e.get('parties', ['unknown'])[0]),
            'filename': details.get('filename', '') if isinstance(details, dict) else ''
        })

# 查找异常帖子后10秒内的删除事件
TARGET_TIME = datetime(2046, 5, 17, 19, 21, 15).timestamp()
suspicious_deletes = []
for e in delete_events:
    if abs(e['when'] - TARGET_TIME) <= 10:
        suspicious_deletes.append(e)

print(f"\n=== 可疑删除事件（异常帖子后10秒内）===")
for e in suspicious_deletes:
    print(f"  {e['datetime']} | {e['deleter']} | {e['filename']}")

# 6. 检查历史是否有类似模式（大文件+级联传播+SaidIT发布）
# 查找所有 create_file 后跟着大量 queue_subordinate_task 的模式
print(f"\n=== 检查历史上的类似模式 ===")

potential_anomalies = []

# 对每个大文件，检查是否有后续传播
for file_event in large_files[:20]:
    file_time = file_event['when']
    filename = file_event['filename']

    # 查找后续24小时内的相关事件
    related_count = 0
    for e in events:
        if 0 < (e['when'] - file_time) <= 86400:  # 24小时内
            search_str = str(e.get('parties', [])) + str(e.get('details', {}))
            if filename.lower() in search_str.lower():
                related_count += 1

    if related_count > 50:  # 超过50个相关事件
        potential_anomalies.append({
            'filename': filename,
            'created': file_time,
            'related_events': related_count
        })

print(f"\n潜在的异常模式（大文件+大量后续事件）:")
for a in potential_anomalies[:5]:
    print(f"  {a['filename']:30s} | 创建于 {datetime.fromtimestamp(a['created']).strftime('%Y-%m-%d %H:%M')} | 后续事件: {a['related_events']}")

# 保存结果
output_data = {
    'large_files': large_files[:30],
    'emma_harbor_files': emma_files,
    'saidit_posts': saidit_posts,
    'content_sources': content_sources,
    'suspicious_deletes': suspicious_deletes,
    'potential_anomalies': potential_anomalies,
    'key_findings': {
        'swiftwren_creator': 'emma_harbor',
        'swiftwren_size': 30615,
        'swiftwren_created': '2046-05-09 23:02:01',
        'cascade_duration_days': 7.8,
        'final_post_date': '2046-05-17 19:21:15'
    }
}

output_file = session_dir / "step4_content_analysis.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

# 记录 PROV 关系
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_data", "entity_type": "dataset", "location": str(data_path)},
        {"id": "step3_output", "entity_type": "dataset", "location": str(session_dir / "step3_swiftwren_origin.json")},
        {"id": "step4_output", "entity_type": "dataset", "location": str(output_file)}
    ],
    activities=[
        {"id": "step4_act", "activity_type": "analyze", "description": "分析内容质量和历史异常模式"}
    ],
    agents=[
        {"id": "step4_agent", "agent_type": "script", "name": "step4_analyze_content"}
    ],
    relations=[
        ("step4_act", "raw_data", "used"),
        ("step4_act", "step3_output", "used"),
        ("step4_output", "step4_act", "wasGeneratedBy"),
        ("step4_act", "step4_agent", "wasAssociatedWith"),
        ("step4_output", "raw_data", "wasDerivedFrom")
    ]
)

print(f"\n输出文件: {output_file}")
print("\nStep 4 完成!")
