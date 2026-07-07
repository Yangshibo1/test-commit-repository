"""
MC2 Analysis - Node 19: Final Visualization and Validation
完整的 John Windward 数据外泄调查最终可视化刷新和 session 验证。
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
    print("Node 19: Final Visualization and Validation")
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

    final_report = work_dir / "node_18_final_complete_investigation_report.json"
    output_viz = work_dir / "node_19_final_complete_investigation_visualization.txt"
    session_output_viz = session_dir / "node_19_final_complete_investigation_visualization.txt"
    validation_file = work_dir / "node_19_validation_result.json"

    with open(final_report, "r", encoding="utf-8") as f:
        report = json.load(f)

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node19_input_report", "entity_type": "report", "location": str(final_report),
             "attributes": {"from_node": "node_18", "investigation_complete": True}},
            {"id": "node19_output_viz", "entity_type": "visualization", "location": str(output_viz),
             "attributes": {"from_node": "node_19", "format": "text+mermaid"}},
            {"id": "node19_output_validation", "entity_type": "artifact", "location": str(validation_file),
             "attributes": {"from_node": "node_19", "artifact_type": "final_validation"}}
        ],
        activities=[
            {"id": "node19_final_visualize_validate", "activity_type": "validate_visualize",
             "description": "完整数据外泄调查最终可视化刷新和 session 验证",
             "attributes": {"session_id": session_id, "session_dir": str(session_dir)}}
        ],
        agents=[
            {"id": "node19_agent", "agent_type": "python_code", "name": "node_19_final_visualization_validate",
             "attributes": {"script": "node_19_final_visualization_validate.py"}}
        ],
        relations=[
            ("node19_final_visualize_validate", "node19_input_report", "used"),
            ("node19_output_viz", "node19_final_visualize_validate", "wasGeneratedBy"),
            ("node19_output_validation", "node19_final_visualize_validate", "wasGeneratedBy"),
            ("node19_final_visualize_validate", "node19_agent", "wasAssociatedWith"),
            ("node19_output_viz", "node19_input_report", "wasDerivedFrom"),
            ("node19_output_validation", "node19_input_report", "wasDerivedFrom")
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
        "investigation_report": str(final_report)
    }
    with open(validation_file, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, ensure_ascii=False, indent=2)

    server.record_step_details(
        session_id=session_id,
        step_id="node_19",
        step_name="final_visualization_validate",
        description="完整数据外泄调查最终可视化刷新和验证",
        code_generated=[
            "visualization = visualize_prov_dag(str(session_dir), None)",
            "is_valid, errors = validate_session(str(session_dir))"
        ],
        code_files=["src/node_19_final_visualization_validate.py"],
        commands_run=["python src/node_19_final_visualization_validate.py"],
        input_files=[str(final_report)],
        output_files=[str(output_viz), str(session_output_viz), str(validation_file)],
        parameters={
            "session_id": session_id,
            "visualization_length": len(visualization),
            "validation_passed": is_valid,
            "validation_errors": errors,
            "investigation_complete": True
        }
    )

    print(f"Session ID: {session_id}")
    print(f"Final visualization: {output_viz}")
    print(f"Validation: {validation_file}")
    print(f"Validation passed: {is_valid}")
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
    print("[OK] Node 19 completed - Investigation Complete")
    return session_id


if __name__ == "__main__":
    main()
