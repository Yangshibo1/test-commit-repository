"""
Step 5: 生成最终分析报告和可视化
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opentrace.mcp_server import get_server
from opentrace.prov_visualizer import visualize_prov_dag

# 获取服务器和会话
server = get_server(".opentrace")

# 读取最新会话
import glob
session_dirs = sorted(Path(".opentrace").glob("session_*"), key=lambda x: x.stat().st_mtime, reverse=True)
session_dir = session_dirs[0]
session_id = session_dir.name

print("=" * 70)
print("Step 5: 生成最终分析报告和可视化")
print("=" * 70)

# 汇总所有发现
final_report = {
    "task": "VAST Challenge MC2 - 异常 SaidIT 帖子追踪",
    "key_event": {
        "description": "John Windward 发布异常 SaidIT 帖子",
        "reported_time": "2046-05-17 04:21:15",
        "actual_time": "2046-05-17 19:21:15",
        "note": "时间可能存在12小时制记录错误"
    },
    "findings": {
        "how_post_was_made": {
            "summary": "异常帖子由 Agent 级联传播链导致",
            "origin_file": "SwiftWren.txt",
            "file_creator": "Agent/person:emma_harbor",
            "file_created": "2046-05-09 23:02:01",
            "file_size": "30,615 bytes",
            "cascade_duration": "7.8 天",
            "cascade_events": 186,
            "agents_involved": 18,
            "final_poster": "Agent/person:john_windward"
        },
        "content_origin": {
            "summary": "帖子内容来自 SwiftWren.txt 文件",
            "likely_content": "大文件（30KB）可能包含自动生成的或处理过的数据",
            "file_characteristics": "文本文件，大小异常大，可能是机器生成内容"
        },
        "prior_occurrences": {
            "summary": "发现2个类似的历史案例",
            "cases": [
                {
                    "file": "HiddenOrca.txt",
                    "post_date": "2046-05-10 20:45:42",
                    "cascade_events": 39,
                    "agents": 16
                },
                {
                    "file": "MellowOtter.txt",
                    "file_creator": "Agent/person:noah_mariner",
                    "file_size": "44,879 bytes",
                    "created": "2046-05-10 23:02:01",
                    "post_date": "2046-05-11 08:56:04",
                    "cascade_events": 10,
                    "agents": 11
                }
            ],
            "pattern": "文件创建 → Agent级联传播 → SaidIT发布 → 删除文件"
        }
    },
    "intervention_recommendation": {
        "location": "SaidIT 发布接口前的内容验证",
        "priority": "HIGH",
        "measures": [
            "内容质量验证（语义分析、乱码检测）",
            "大文件内容检查（>10KB 需要人工审核）",
            "证据保留机制（禁止删除源文件）",
            "Agent 任务传播监控（异常级联检测）"
        ],
        "justification": "所有异常案例都通过 SaidIT 发布，在此处拦截可防止问题内容发布"
    },
    "data_lineage": {
        "raw_data": "MC2 data.json",
        "steps": [
            "step1: 加载原始数据",
            "step2: 查找关键 SaidIT 事件",
            "step3: 追踪 SwiftWren.txt 起源和级联传播",
            "step4: 分析内容质量和历史异常模式",
            "step5: 生成最终报告"
        ]
    }
}

# 保存报告
report_file = session_dir / "final_report.json"
with open(report_file, 'w', encoding='utf-8') as f:
    json.dump(final_report, f, ensure_ascii=False, indent=2)

print(f"\n最终报告已保存: {report_file}")

# 记录 PROV 关系（最终报告汇总了所有步骤）
server.record_prov_relation(
    session_id=session_id,
    entities=[
        {"id": "step1_out", "entity_type": "dataset", "location": str(session_dir / "loaded_data.json")},
        {"id": "step2_out", "entity_type": "dataset", "location": str(session_dir / "step2_suspect_event.json")},
        {"id": "step3_out", "entity_type": "dataset", "location": str(session_dir / "step3_swiftwren_origin.json")},
        {"id": "step4a_out", "entity_type": "dataset", "location": str(session_dir / "step4_content_analysis.json")},
        {"id": "step4b_out", "entity_type": "dataset", "location": str(session_dir / "step4b_anomaly_comparison.json")},
        {"id": "step4c_out", "entity_type": "dataset", "location": str(session_dir / "step4c_full_trace.json")},
        {"id": "final_report", "entity_type": "artifact", "location": str(report_file)}
    ],
    activities=[
        {"id": "step5_act", "activity_type": "aggregate", "description": "汇总所有分析结果生成最终报告"}
    ],
    agents=[
        {"id": "step5_agent", "agent_type": "script", "name": "step5_final_report"}
    ],
    relations=[
        ("step5_act", "step1_out", "used"),
        ("step5_act", "step2_out", "used"),
        ("step5_act", "step3_out", "used"),
        ("step5_act", "step4a_out", "used"),
        ("step5_act", "step4b_out", "used"),
        ("step5_act", "step4c_out", "used"),
        ("final_report", "step5_act", "wasGeneratedBy"),
        ("step5_act", "step5_agent", "wasAssociatedWith")
    ]
)

# 生成可视化
print("\n生成数据血缘可视化...")
viz_file = session_dir / "pipeline_visualization.txt"
visualize_prov_dag(str(session_dir), str(viz_file))

print("\n" + "=" * 70)
print("分析完成！")
print("=" * 70)
print(f"\n会话目录: {session_dir}")
print(f"最终报告: {report_file}")
print(f"可视化文件: {viz_file}")

# 打印关键发现摘要
print(f"\n=== 关键发现摘要 ===")
print(f"1. 异常帖子来源: SwiftWren.txt")
print(f"2. 文件创建者: Agent/person:emma_harbor (2046-05-09 23:02:01)")
print(f"3. 级联传播: 186 次任务传递，涉及 18 个 Agent")
print(f"4. 传播时长: 7.8 天")
print(f"5. 发布者: Agent/person:john_windward (2046-05-17 19:21:15)")
print(f"6. 发现2个类似历史案例: HiddenOrca.txt, MellowOtter.txt")
print(f"7. 建议干预点: SaidIT 发布接口前的内容验证")

print("\nStep 5 完成!")
