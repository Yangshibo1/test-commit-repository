"""Reviewer task prompts.

The workflow context is evidence and orientation, not content to duplicate in
the derived assets. Each task returns only the user-facing enrichment that the
frontend cannot obtain directly from workflow.json.
"""

from __future__ import annotations

import json
from typing import Any, Dict


SYSTEM_PROMPT = """You are the AgentVAST Artifact Reviewer. You review completed data-analysis artifacts after the real workflow has been recorded. Never rewrite the workflow, invent a Node, or present a new claim without support from the supplied source, deterministic extraction, or recorded conclusions. Return one valid JSON object and no prose outside JSON. Do not include chain-of-thought. Use concise Chinese user-facing text."""


def code_prompt(context: Dict[str, Any], source: Dict[str, Any]) -> str:
    return _prompt(
        "review_code",
        context,
        source,
        {
            "summary": "一句话解释代码实际做什么",
            "logic_steps": [
                {"order": 1, "description": "关键处理逻辑", "related_functions": []}
            ],
            "data_flow": {"inputs": [], "processing": "", "outputs": []},
            "critical_logic": [],
            "implementation_notes": [],
            "potential_issues": [
                {"type": "implementation_risk", "description": "", "impact": ""}
            ],
        },
        "重点解释影响分析结果的筛选、匹配、计算、关联、排序和统计规则；不要逐行解释代码，也不要重复Node目标。",
    )


def dataset_plan_prompt(context: Dict[str, Any], profile: Dict[str, Any]) -> str:
    return _prompt(
        "review_dataset_plan",
        context,
        profile,
        {
            "analysis_requests": [
                {
                    "operation": "count_by|top_n|numeric_summary|time_range|timeline_events",
                    "field": "真实字段名",
                    "limit": 20,
                    "fields": [],
                }
            ]
        },
        "根据原始问题、Node上下文和数据画像，只申请真正有助于理解该中间数据的白名单计算。最多8项；不需要额外计算时返回空数组。",
    )


def dataset_review_prompt(
    context: Dict[str, Any], profile: Dict[str, Any], computed: Any
) -> str:
    source = {"profile": profile, "requested_computations": computed}
    return _prompt(
        "review_dataset",
        context,
        source,
        {
            "dataset_description": "数据集包含什么",
            "role_in_analysis": "它在本次分析中帮助理解什么",
            "key_patterns": [
                {"finding": "", "basis": "引用profile或requested_computations中的事实"}
            ],
            "anomalies": [
                {"finding": "", "basis": "引用profile或requested_computations中的事实"}
            ],
            "quality_notes": [],
            "visualizations": [
                {
                    "chart_type": "table|bar|line|scatter|timeline|network|distribution",
                    "title": "",
                    "purpose": "",
                    "encoding": {
                        "x": "真实字段名",
                        "y": "真实字段名",
                        "category": "真实字段名",
                        "time": "真实字段名",
                        "event": "真实字段名",
                        "detail": "真实字段名",
                        "source": "真实字段名",
                        "target": "真实字段名"
                    },
                }
            ],
        },
        "只报告确定性画像和计算支持的模式。图表必须帮助理解原始问题或该Node结果；无合适图表时返回空数组。encoding只保留该图真正使用的字段。",
    )


def report_prompt(context: Dict[str, Any], report: Dict[str, Any]) -> str:
    return _prompt(
        "review_report",
        context,
        report,
        {
            "core_findings": [
                {"finding": "报告中的核心发现", "importance": "high|medium|low"}
            ],
            "conclusions": [],
            "limitations": [],
            "unresolved_questions": [],
            "relevant_question_aspects": [],
        },
        "只提炼该报告实际包含的发现、结论、限制和未解决问题。不要让单个阶段报告代替整次Run回答全部问题。",
    )


def answer_review_prompt(context: Dict[str, Any], reviews: Dict[str, Any]) -> str:
    return _prompt(
        "review_run_answer",
        context,
        reviews,
        {
            "question_aspects": [
                {"aspect_id": "aspect-001", "question": "原始问题的一个可独立回答方面"}
            ],
            "answer_coverage": [
                {
                    "aspect_id": "aspect-001",
                    "status": "answered|partial|unanswered|not_applicable",
                    "answer": "现有分析能支持的回答",
                    "supporting_nodes": [],
                    "supporting_assets": [],
                    "remaining_gap": None,
                }
            ],
            "analysis_depth": [
                {
                    "dimension": "question_coverage|data_support|method_adequacy|alternative_explanations|uncertainty_handling|reproducibility",
                    "status": "sufficient|partial|insufficient|not_applicable",
                    "assessment": "",
                }
            ],
            "analysis_gaps": [
                {
                    "gap_id": "gap-001",
                    "type": "question_coverage|data_gap|method_gap|unsupported_claim|alternative_explanation|uncertainty_gap|reproducibility_gap",
                    "severity": "high|medium|low",
                    "description": "",
                    "impact": "",
                    "related_aspects": [],
                }
            ],
            "next_analysis_directions": [
                {
                    "direction_id": "next-001",
                    "priority": "high|medium|low",
                    "objective": "",
                    "rationale": "",
                    "suggested_inputs": [],
                    "suggested_method": "",
                    "expected_value": "",
                    "requires_new_data": False,
                }
            ],
        },
        "综合评估现有分析对原始问题的回答程度和分析深度。不要复述完整workflow。回答必须引用现有Node或Reviewer资产；分析不足时明确缺陷和下一步方向。不要使用虚假的精确总分。",
    )


def _prompt(
    task_mode: str,
    context: Dict[str, Any],
    source: Any,
    output_shape: Dict[str, Any],
    instruction: str,
) -> str:
    return "\n\n".join(
        [
            "TASK_MODE: {0}".format(task_mode),
            instruction,
            "上下文摘要（用于理解，不要复制已有workflow字段）：\n{0}".format(
                json.dumps(context, ensure_ascii=False)
            ),
            "待处理内容或确定性提取结果：\n{0}".format(
                json.dumps(source, ensure_ascii=False)
            ),
            "必须返回以下结构的JSON对象：\n{0}".format(
                json.dumps(output_shape, ensure_ascii=False)
            ),
        ]
    )
