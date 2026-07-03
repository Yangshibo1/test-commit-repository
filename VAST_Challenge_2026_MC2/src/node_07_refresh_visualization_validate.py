"""
MC2 Analysis - Node 07: Refresh Visualization and Validate Session
记录最终可视化刷新节点，然后重新生成可视化，确保可视化内容包含完整 PROV DAG。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server
from opentrace.prov_visualizer import visualize_prov_dag
from opentrace.prov_validation import validate_session


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def main():
    print("=" * 60)
    print("Node 07: Refresh Visualization and Validate Session")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)
    session_dir = Path(server.base_dir) / session_id

    input_report = work_dir / "node_05_final_report.json"
    input_visualization = work_dir / "node_06_data_flow_visualization.txt"
    output_file = work_dir / "node_07_final_data_flow_visualization.txt"
    session_output_file = session_dir / "node_07_final_data_flow_visualization.txt"
    validation_file = work_dir / "node_07_validation_result.json"

    with open(input_report, "r", encoding="utf-8") as f:
        report = json.load(f)

    previous_viz_size = input_visualization.stat().st_size if input_visualization.exists() else 0

    # 先记录最终可视化刷新活动；随后生成可视化，使输出内容包含本节点的 PROV 记录。
    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node07_input_report", "entity_type": "report", "location": str(input_report),
             "attributes": {"from_node": "node_05", "target_event": report.get("executive_summary", {}).get("anomalous_post", {}).get("event_id")}},
            {"id": "node07_input_previous_viz", "entity_type": "visualization", "location": str(input_visualization),
             "attributes": {"from_node": "node_06", "size_bytes": previous_viz_size}},
            {"id": "node07_output_final_viz", "entity_type": "visualization", "location": str(output_file),
             "attributes": {"from_node": "node_07", "format": "text+mermaid", "session_copy": str(session_output_file)}},
            {"id": "node07_output_validation", "entity_type": "artifact", "location": str(validation_file),
             "attributes": {"from_node": "node_07", "artifact_type": "validation_result"}}
        ],
        activities=[
            {"id": "node07_refresh_validate", "activity_type": "validate_visualize",
             "description": "刷新完整PROV可视化并验证OpenTrace会话完整性",
             "attributes": {"session_id": session_id, "session_dir": str(session_dir)}}
        ],
        agents=[
            {"id": "node07_agent", "agent_type": "python_code", "name": "node_07_refresh_visualization_validate",
             "attributes": {"script": "node_07_refresh_visualization_validate.py"}}
        ],
        relations=[
            ("node07_refresh_validate", "node07_input_report", "used"),
            ("node07_refresh_validate", "node07_input_previous_viz", "used"),
            ("node07_output_final_viz", "node07_refresh_validate", "wasGeneratedBy"),
            ("node07_output_validation", "node07_refresh_validate", "wasGeneratedBy"),
            ("node07_refresh_validate", "node07_agent", "wasAssociatedWith"),
            ("node07_output_final_viz", "node07_input_report", "wasDerivedFrom"),
            ("node07_output_final_viz", "node07_input_previous_viz", "wasDerivedFrom"),
            ("node07_output_validation", "node07_input_report", "wasDerivedFrom")
        ]
    )

    # 生成包含 node_07 PROV 节点的最终可视化。
    visualization = visualize_prov_dag(str(session_dir), None)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(visualization)
    with open(session_output_file, "w", encoding="utf-8") as f:
        f.write(visualization)

    is_valid, errors = validate_session(str(session_dir))
    validation_result = {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "is_valid": is_valid,
        "errors": errors,
        "final_visualization_src": str(output_file),
        "final_visualization_session": str(session_output_file),
        "visualization_length": len(visualization)
    }
    with open(validation_file, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, ensure_ascii=False, indent=2)

    server.record_step_details(
        session_id=session_id,
        step_id="node_07",
        step_name="refresh_visualization_validate",
        description="刷新最终PROV可视化并验证OpenTrace会话完整性，输出保存到src和session目录",
        code_generated=[
            "server.record_prov_relation(... node07_refresh_validate ...)",
            "visualization = visualize_prov_dag(str(session_dir), None)",
            "is_valid, errors = validate_session(str(session_dir))"
        ],
        code_files=["src/node_07_refresh_visualization_validate.py"],
        commands_run=["python src/node_07_refresh_visualization_validate.py"],
        input_files=[str(input_report), str(input_visualization)],
        output_files=[str(output_file), str(session_output_file), str(validation_file)],
        parameters={
            "session_id": session_id,
            "visualization_length": len(visualization),
            "validation_passed": is_valid,
            "validation_errors": errors,
            "output_saved_in_src": True,
            "output_saved_in_session": True
        }
    )

    print(f"Session ID: {session_id}")
    print(f"Final visualization(src): {output_file}")
    print(f"Final visualization(session): {session_output_file}")
    print(f"Validation result: {validation_file}")
    print(f"Validation passed: {is_valid}")
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
    print("[OK] Node 07 completed")
    return session_id


if __name__ == "__main__":
    main()
