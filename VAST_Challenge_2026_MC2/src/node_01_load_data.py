"""
MC2 Analysis - Node 01: Load Data
加载原始数据并保存
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server

def main():
    print("=" * 60)
    print("Node 01: Load Data")
    print("=" * 60)

    server = get_server()
    result = server.init_session(
        task_description="MC2 Analysis - Correct Data Flow",
        data_path="VAST_Challenge_2026_MC2/MC2 data.json",
        data_type="json"
    )

    session_id = result.get("session_id")
    work_dir = Path(__file__).parent
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"Session ID: {session_id}")
    print(f"Work directory: {work_dir}")

    # 加载数据
    data_path = Path(__file__).parent.parent / "MC2 data.json"
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    events = data.get('events', [])
    print(f"Total events: {len(events):,}")

    # 保存产物
    output_file = work_dir / "node_01_loaded.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 记录 PROV - 详细颗粒度
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "raw_mc2_data", "entity_type": "dataset", "location": str(data_path),
             "attributes": {"file_size": data_path.stat().st_size, "events": len(events)}},
            {"id": "node01_output", "entity_type": "dataset", "location": str(output_file),
             "attributes": {"events": len(events), "description": "MC2原始数据完整加载"}}
        ],
        activities=[
            {"id": "node01_load", "activity_type": "load", "description": "加载MC2原始数据",
             "attributes": {"operation": "json.load", "encoding": "utf-8", "preserve_structure": True}}
        ],
        agents=[
            {"id": "node01_agent", "agent_type": "python_code", "name": "node_01_load_data",
             "attributes": {"script": "node_01_load_data.py", "purpose": "数据加载"}}
        ],
        relations=[
            ("node01_load", "raw_mc2_data", "used"),
            ("node01_output", "node01_load", "wasGeneratedBy"),
            ("node01_load", "node01_agent", "wasAssociatedWith"),
            ("node01_output", "raw_mc2_data", "wasDerivedFrom")
        ]
    )

    # 记录步骤详情 - 详细颗粒度
    server.record_step_details(
        session_id=session_id,
        step_id="node_01",
        step_name="load_data",
        description="加载MC2原始数据，保留完整结构",
        code_generated=[
            "with open(data_path, 'r', encoding='utf-8') as f:",
            "    data = json.load(f)",
            "events = data.get('events', [])"
        ],
        code_files=["src/node_01_load_data.py"],
        commands_run=["python src/node_01_load_data.py"],
        input_files=[str(data_path)],
        output_files=[str(output_file)],
        parameters={
            "input_file_size": data_path.stat().st_size,
            "total_events": len(events),
            "data_structure": "{'description': str, 'events': list}",
            "encoding": "utf-8",
            "preserve_structure": True,
            "next_step": "探索数据结构，筛选SaidIT事件"
        }
    )

    # 保存会话信息，供后续节点读取
    session_file = work_dir / "current_session.json"
    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump({"session_id": session_id, "work_dir": str(work_dir)}, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Node 01 completed")
    print(f"  Output: {output_file.name}")
    print(f"  Events: {len(events):,}")

    return session_id

if __name__ == "__main__":
    main()
