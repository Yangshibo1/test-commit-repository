"""
MC2 Analysis - Node 15: Refresh Visualization and Validate After John Analysis
记录 John Windward 完整分析后的最终可视化刷新和 session 验证。
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
    print("Node 15: Refresh Visualization and Validate After John Analysis")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)
    session_dir = Path(server.base_dir) / session_id
    if not session_dir.exists():
        backup_session_dir = Path(server.base_dir) / f"{session_id}备份"
        if backup_session_dir.exists():
            session_dir = backup_session_dir
        else:
            session_dir.mkdir(parents=True, exist_ok=True)

    input_report = work_dir / "node_14_final_john_analysis_report.json"
    previous_viz = work_dir / "node_11_final_similarity_data_flow_visualization.txt"
    output_viz = work_dir / "node_15_final_john_analysis_visualization.txt"
    session_output_viz = session_dir / "node_15_final_john_analysis_visualization.txt"
    validation_file = work_dir / "node_15_validation_result.json"

    with open(input_report, "r", encoding="utf-8") as f:
        report = json.load(f)

    previous_viz_size = previous_viz.stat().st_size if previous_viz.exists() else 0

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node15_input_report", "entity_type": "report", "location": str(input_report),
             "attributes": {"from_node": "node_14", "abnormal_posts": 3}},
            {"id": "node15_input_previous_viz", "entity_type": "visualization", "location": str(previous_viz),
             "attributes": {"from_node": "node_11", "size_bytes": previous_viz_size}},
            {"id": "node15_output_viz", "entity_type": "visualization", "location": str(output_viz),
             "attributes": {"from_node": "node_15", "format": "text+mermaid"}},
            {"id": "node15_output_validation", "entity_type": "artifact", "location": str(validation_file),
             "attributes": {"from_node": "node_15", "artifact_type": "validation_result"}}
        ],
        activities=[
            {"id": "node15_refresh_validate", "activity_type": "validate_visualize",
             "description": "John Windward 完整分析后刷新PROV可视化并验证会话",
             "attributes": {"session_id": session_id, "session_dir": str(session_dir)}}
        ],
        agents=[
            {"id": "node15_agent", "agent_type": "python_code", "name": "node_15_refresh_visualization_validate",
             "attributes": {"script": "node_15_refresh_visualization_validate.py"}}
        ],
        relations=[
            ("node15_refresh_validate", "node15_input_report", "used"),
            ("node15_refresh_validate", "node15_input_previous_viz", "used"),
            ("node15_output_viz", "node15_refresh_validate", "wasGeneratedBy"),
            ("node15_output_validation", "node15_refresh_validate", "wasGeneratedBy"),
            ("node15_refresh_validate", "node15_agent", "wasAssociatedWith"),
            ("node15_output_viz", "node15_input_report", "wasDerivedFrom"),
            ("node15_output_validation", "node15_input_report", "wasDerivedFrom")
        ]
    )

    visualization = visualize_prov_dag(str(session_dir), None)
    with open(output_viz, "w", encoding="utf-8") as f:
        f.write(visualization)
    with open(session_output_viz, "w", encoding="utf-8") as f:
        f.write(visualization)

    is_valid, errors = validate_session(str(session_dir))
    validation_result = {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "is_valid": is_valid,
        "errors": errors,
        "final_visualization_src": str(output_viz),
        "final_visualization_session": str(session_output_viz),
        "visualization_length": len(visualization),
        "john_analysis_report": str(input_report)
    }
    with open(validation_file, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, ensure_ascii=False, indent=2)

    server.record_step_details(
        session_id=session_id,
        step_id="node_15",
        step_name="refresh_john_analysis_visualization_validate",
        description="John Windward 完整分析后刷新最终可视化并验证OpenTrace会话完整性",
        code_generated=[
            "server.record_prov_relation(... node15_refresh_validate ...)",
            "visualization = visualize_prov_dag(str(session_dir), None)",
            "is_valid, errors = validate_session(str(session_dir))"
        ],
        code_files=["src/node_15_refresh_visualization_validate.py"],
        commands_run=["python src/node_15_refresh_visualization_validate.py"],
        input_files=[str(input_report), str(previous_viz)],
        output_files=[str(output_viz), str(session_output_viz), str(validation_file)],
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
    print(f"Final visualization(src): {output_viz}")
    print(f"Final visualization(session): {session_output_viz}")
    print(f"Validation result: {validation_file}")
    print(f"Validation passed: {is_valid}")
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
    print("[OK] Node 15 completed")
    return session_id


if __name__ == "__main__":
    main()
