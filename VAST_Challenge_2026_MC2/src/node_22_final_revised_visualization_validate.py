"""
MC2 Analysis - Node 22: Final Revised Visualization and Validation
修正后调查的最终可视化和验证。
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
    print("Node 22: Final Revised Visualization and Validation")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)
    session_dir = Path(server.base_dir) / session_id
    if not session_dir.exists():
        backup_session_dir = Path(server.base_dir) / f"{session_id}备份"
        if backup_session_dir.exists():
            session_dir = backup_session_dir

    revised_report = work_dir / "node_21_revised_final_report.json"
    output_viz = work_dir / "node_22_final_revised_visualization.txt"
    session_output_viz = session_dir / "node_22_final_revised_visualization.txt"
    validation_file = work_dir / "node_22_validation_result.json"

    with open(revised_report, "r", encoding="utf-8") as f:
        report = json.load(f)

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node22_input_report", "entity_type": "report", "location": str(revised_report),
             "attributes": {"from_node": "node_21", "revised": True}},
            {"id": "node22_output_viz", "entity_type": "visualization", "location": str(output_viz),
             "attributes": {"from_node": "node_22"}},
            {"id": "node22_output_validation", "entity_type": "artifact", "location": str(validation_file),
             "attributes": {"from_node": "node_22"}}
        ],
        activities=[
            {"id": "node22_final_viz_validate", "activity_type": "validate_visualize",
             "description": "修正后调查最终可视化和验证",
             "attributes": {"session_id": session_id}}
        ],
        agents=[
            {"id": "node22_agent", "agent_type": "python_code", "name": "node_22_final_revised_viz_validate",
             "attributes": {"script": "node_22_final_revised_visualization_validate.py"}}
        ],
        relations=[
            ("node22_final_viz_validate", "node22_input_report", "used"),
            ("node22_output_viz", "node22_final_viz_validate", "wasGeneratedBy"),
            ("node22_output_validation", "node22_final_viz_validate", "wasGeneratedBy"),
            ("node22_final_viz_validate", "node22_agent", "wasAssociatedWith"),
            ("node22_output_viz", "node22_input_report", "wasDerivedFrom"),
            ("node22_output_validation", "node22_input_report", "wasDerivedFrom")
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
        "is_valid": is_valid,
        "errors": errors,
        "visualization_src": str(output_viz),
        "visualization_session": str(session_output_viz),
        "revised_report": str(revised_report)
    }
    with open(validation_file, "w", encoding="utf-8") as f:
        json.dump(validation_result, f, ensure_ascii=False, indent=2)

    server.record_step_details(
        session_id=session_id,
        step_id="node_22",
        step_name="final_revised_visualization_validate",
        description="修正后调查最终可视化和验证",
        code_generated=["visualization = visualize_prov_dag()", "is_valid = validate_session()"],
        code_files=["src/node_22_final_revised_visualization_validate.py"],
        commands_run=["python src/node_22_final_revised_visualization_validate.py"],
        input_files=[str(revised_report)],
        output_files=[str(output_viz), str(session_output_viz), str(validation_file)],
        parameters={
            "validation_passed": is_valid,
            "investigation_revised": True,
            "user_observations_validated": 2
        }
    )

    print(f"Validation passed: {is_valid}")
    print(f"[OK] Node 22 completed - Final Revised Investigation Complete")
    return session_id


if __name__ == "__main__":
    main()
