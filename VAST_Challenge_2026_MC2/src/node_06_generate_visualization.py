"""
MC2 Analysis - Node 06: Generate Visualization
读取 node_05_final_report.json 并基于 OpenTrace PROV 数据生成可视化文本。
注意：visualize_prov_dag 的 output_file 是相对当前工作目录写入，所以这里显式写入 src 和 session 目录。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server
from opentrace.prov_visualizer import visualize_prov_dag


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def main():
    print("=" * 60)
    print("Node 06: Generate Visualization")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)
    session_dir = Path(server.base_dir) / session_id

    input_file = work_dir / "node_05_final_report.json"
    with open(input_file, "r", encoding="utf-8") as f:
        report = json.load(f)

    # 先生成可视化文本（不依赖 visualize_prov_dag 的相对路径写入行为）
    visualization = visualize_prov_dag(str(session_dir), None)

    output_file = work_dir / "node_06_data_flow_visualization.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(visualization)

    session_output_file = session_dir / "node_06_data_flow_visualization.txt"
    with open(session_output_file, "w", encoding="utf-8") as f:
        f.write(visualization)

    print(f"Input: {input_file}")
    print(f"Output(src): {output_file}")
    print(f"Output(session): {session_output_file}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node06_input_report", "entity_type": "report", "location": str(input_file),
             "attributes": {"from_node": "node_05", "target_event": report.get("executive_summary", {}).get("anomalous_post", {}).get("event_id")}},
            {"id": "node06_output_visualization", "entity_type": "visualization", "location": str(output_file),
             "attributes": {"from_node": "node_06", "format": "text+mermaid", "session_copy": str(session_output_file)}}
        ],
        activities=[
            {"id": "node06_visualize", "activity_type": "visualize",
             "description": "基于OpenTrace PROV数据生成数据血缘可视化",
             "attributes": {"session_dir": str(session_dir), "output_format": "txt"}}
        ],
        agents=[
            {"id": "node06_agent", "agent_type": "python_code", "name": "node_06_generate_visualization",
             "attributes": {"script": "node_06_generate_visualization.py"}}
        ],
        relations=[
            ("node06_visualize", "node06_input_report", "used"),
            ("node06_output_visualization", "node06_visualize", "wasGeneratedBy"),
            ("node06_visualize", "node06_agent", "wasAssociatedWith"),
            ("node06_output_visualization", "node06_input_report", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_06",
        step_name="generate_visualization",
        description="读取最终报告并生成OpenTrace PROV数据血缘可视化，同时保存到src和session目录",
        code_generated=[
            "visualization = visualize_prov_dag(str(session_dir), None)",
            "with open(output_file, 'w', encoding='utf-8') as f: f.write(visualization)"
        ],
        code_files=["src/node_06_generate_visualization.py"],
        commands_run=["python src/node_06_generate_visualization.py"],
        input_files=[str(input_file)],
        output_files=[str(output_file), str(session_output_file)],
        parameters={
            "session_id": session_id,
            "session_dir": str(session_dir),
            "visualization_length": len(visualization),
            "output_saved_in_src": True,
            "output_saved_in_session": True
        }
    )

    print("[OK] Node 06 completed")
    return session_id


if __name__ == "__main__":
    main()
