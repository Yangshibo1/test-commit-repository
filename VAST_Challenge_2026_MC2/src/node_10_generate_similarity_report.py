"""
MC2 Analysis - Node 10: Generate Supplemental Similarity Report
读取 node_09_instruction_outcome_comparison.json，生成“历史类似实例与为什么只有 John 发帖成功”的补充报告。
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from opentrace.mcp_server import get_server


def load_session_id(work_dir: Path) -> str:
    with open(work_dir / "current_session.json", "r", encoding="utf-8") as f:
        return json.load(f)["session_id"]


def main():
    print("=" * 60)
    print("Node 10: Generate Supplemental Similarity Report")
    print("=" * 60)

    server = get_server()
    work_dir = Path(__file__).parent
    session_id = load_session_id(work_dir)

    input_file = work_dir / "node_09_instruction_outcome_comparison.json"
    with open(input_file, "r", encoding="utf-8") as f:
        comparison = json.load(f)

    summary = comparison["summary"]
    per_target = comparison["per_target_summary"]
    success_sequences = comparison["successful_sequences"]
    examples = comparison["representative_non_success_examples"]

    john = per_target.get("person:john_windward", {})
    checked_examples = examples.get("checked_but_no_swiftwren_post", [])[:5]
    no_attempt_examples = examples.get("no_saidit_post_attempt_observed", [])[:5]

    report = {
        "node_id": "node_10",
        "operation": "generate_supplemental_similarity_report",
        "generated_at": str(datetime.now()),
        "session_id": session_id,
        "input_file": str(input_file),
        "question": "历史系统行为中是否发现其他类似实例？为什么只有 John Windward 的异常帖子发了出来，其他人没有？",
        "answer_summary": {
            "similar_instances_found": True,
            "similar_instance_definition": "收到或传播 SwiftWren_further_instructions.md 读取任务的 queue_subordinate_task。",
            "similar_instruction_tasks": summary["instruction_tasks"],
            "tasks_before_target_post": summary["tasks_before_target_post"],
            "outcome_counts": summary["outcome_counts"],
            "only_successful_swiftwren_poster": "person:john_windward",
            "john_instruction_count": john.get("instruction_count"),
            "john_successful_task_ids": john.get("successful_task_ids"),
            "john_source_agents": john.get("source_agents")
        },
        "core_findings": [
            f"存在历史类似实例：共有 {summary['instruction_tasks']} 条 SwiftWren_further_instructions.md 读取任务，涉及多个目标人员。",
            f"这些类似任务全部发生在目标异常帖子之前；其中 {summary['outcome_counts'].get('no_saidit_post_attempt_observed', 0)} 条后续未观察到 SaidIT 发帖尝试。",
            f"另有 {summary['outcome_counts'].get('checked_saidit_but_no_swiftwren_post', 0)} 条出现了 saidit_post_check，但没有产生 content_source=SwiftWren.txt 的 saidit_post。",
            "只有 1 条任务形成完整异常发布链，目标人员是 John Windward，对应任务事件 ID 373893。",
            "John 的成功链为：Chloe Ballast 指派 John 读取 SwiftWren_further_instructions.md → John 进行 SaidIT 发布检查 → John 发布 content_source=SwiftWren.txt → John 删除指令文件和源文件。"
        ],
        "why_only_john_posted": {
            "evidence_based_explanation": [
                "John Windward 是唯一在收到 SwiftWren 指令后 2 分钟内产生 content_source=SwiftWren.txt 的 saidit_post 的人员。",
                "其他人员虽然有相似的 SwiftWren 指令任务，但后续行为停在两个状态：没有 SaidIT 发布尝试，或只有 saidit_post_check 而没有异常内容发布。",
                "John 的任务链时间极短且连续：19:21:13 收到 Chloe 指令，19:21:14 saidit_post_check，19:21:15 saidit_post，19:21:16/17 删除文件。这个完整序列在其他目标人员中没有出现。",
                "因此，不是没有其他类似实例；而是只有 John 的实例完成了从指令到平台检查、发帖、清理痕迹的完整执行链。"
            ],
            "successful_sequence": success_sequences,
            "representative_non_success_checked_examples": checked_examples,
            "representative_non_success_no_attempt_examples": no_attempt_examples
        },
        "per_target_summary": per_target,
        "conclusion": {
            "other_instances_exist": True,
            "other_instances_nature": "类似传播/尝试实例，而不是成功异常发帖实例。",
            "john_unique_condition": "只有 John 的指令后续产生了 saidit_post_check + saidit_post(content_source=SwiftWren.txt) + 删除源文件的完整链。",
            "final_answer": "历史系统行为中发现了大量相似 SwiftWren 指令实例，但只有 John Windward 的实例完成异常发帖；其他人没有发出异常帖子，是因为他们的后续事件没有进入完整 SaidIT 发布链，最多只出现检查动作或没有任何发帖尝试。"
        }
    }

    output_file = work_dir / "node_10_supplemental_similarity_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Input: {input_file}")
    print(f"Output: {output_file}")
    print(f"Instruction tasks: {summary['instruction_tasks']}")
    print(f"Outcome counts: {summary['outcome_counts']}")

    server.record_prov_relation(
        session_id=session_id,
        entities=[
            {"id": "node10_input_comparison", "entity_type": "dataset", "location": str(input_file),
             "attributes": {"from_node": "node_09", "instruction_tasks": summary["instruction_tasks"]}},
            {"id": "node10_output_report", "entity_type": "report", "location": str(output_file),
             "attributes": {"from_node": "node_10", "other_instances_exist": True, "successful_poster": "person:john_windward"}}
        ],
        activities=[
            {"id": "node10_generate_similarity_report", "activity_type": "aggregate",
             "description": "生成历史类似实例与John唯一成功发帖原因的补充报告",
             "attributes": {"input_node": "node_09", "question": "similar abnormal posting instances"}}
        ],
        agents=[
            {"id": "node10_agent", "agent_type": "python_code", "name": "node_10_generate_similarity_report",
             "attributes": {"script": "node_10_generate_similarity_report.py"}}
        ],
        relations=[
            ("node10_generate_similarity_report", "node10_input_comparison", "used"),
            ("node10_output_report", "node10_generate_similarity_report", "wasGeneratedBy"),
            ("node10_generate_similarity_report", "node10_agent", "wasAssociatedWith"),
            ("node10_output_report", "node10_input_comparison", "wasDerivedFrom")
        ]
    )

    server.record_step_details(
        session_id=session_id,
        step_id="node_10",
        step_name="generate_supplemental_similarity_report",
        description="读取node_09比较结果，回答历史类似实例和为什么只有John发帖成功的问题",
        code_generated=[
            "comparison = json.load(open('node_09_instruction_outcome_comparison.json'))",
            "report = {'answer_summary': ..., 'why_only_john_posted': ..., 'conclusion': ...}"
        ],
        code_files=["src/node_10_generate_similarity_report.py"],
        commands_run=["python src/node_10_generate_similarity_report.py"],
        input_files=[str(input_file)],
        output_files=[str(output_file)],
        parameters={
            "instruction_tasks": summary["instruction_tasks"],
            "outcome_counts": summary["outcome_counts"],
            "successful_poster": "person:john_windward",
            "next_step_basis": "node_11 将刷新可视化并验证session"
        }
    )

    print("[OK] Node 10 completed")
    return session_id


if __name__ == "__main__":
    main()
