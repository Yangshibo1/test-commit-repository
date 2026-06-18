"""
Step 1: 加载原始数据并初始化分析
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opentrace.mcp_server import get_server

# 初始化服务器
server = get_server(".opentrace")

# 数据路径
data_dir = Path(__file__).parent
data_path = data_dir / "MC2 data.json"
org_chart_path = data_dir / "org_chart.json"

# 关键时刻
KEY_TIMESTAMP = datetime(2046, 5, 17, 4, 21, 15).timestamp()

print("=" * 70)
print("Step 1: 加载原始数据")
print("=" * 70)

# 初始化会话
result = server.init_session(
    task_description="MC2 异常帖子追踪 - John Windward SaidIT 事件分析",
    data_path=str(data_path),
    data_type="json"
)

if "error" in result:
    print(f"错误: {result['error']}")
    sys.exit(1)

session_id = result["session_id"]
work_dir = Path(f".opentrace/{session_id}")
work_dir.mkdir(parents=True, exist_ok=True)

print(f"会话ID: {session_id}")
print(f"工作目录: {work_dir}")

# 记录原始数据加载
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "raw_mc2_data", "entity_type": "dataset", "location": str(data_path)},
        {"id": "raw_org_chart", "entity_type": "dataset", "location": str(org_chart_path)},
        {"id": "loaded_data", "entity_type": "dataset", "location": str(work_dir / "loaded_data.json")}
    ],
    activities=[
        {"id": "load_act", "activity_type": "load", "description": "加载MC2原始数据和组织架构"}
    ],
    agents=[
        {"id": "data_loader", "agent_type": "script", "name": "step1_load_data"}
    ],
    relations=[
        ("load_act", "raw_mc2_data", "used"),
        ("load_act", "raw_org_chart", "used"),
        ("loaded_data", "load_act", "wasGeneratedBy"),
        ("load_act", "data_loader", "wasAssociatedWith"),
        ("loaded_data", "raw_mc2_data", "wasDerivedFrom")
    ]
)

# 加载数据
with open(data_path, 'r', encoding='utf-8') as f:
    mc2_data = json.load(f)

with open(org_chart_path, 'r', encoding='utf-8') as f:
    org_chart = json.load(f)

events = mc2_data.get('events', [])
print(f"原始事件总数: {len(events)}")

# 保存加载的数据
loaded_data = {
    'total_events': len(events),
    'events': events,
    'org_chart': org_chart,
    'key_timestamp': KEY_TIMESTAMP,
    'key_datetime': str(datetime.fromtimestamp(KEY_TIMESTAMP))
}

output_file = work_dir / "loaded_data.json"
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(loaded_data, f, ensure_ascii=False, indent=2)

print(f"输出文件: {output_file}")
print(f"关键时间点: {loaded_data['key_datetime']}")
print("\nStep 1 完成!")
