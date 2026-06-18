"""
VAST Challenge 2026 MC2 - 数据分析脚本
使用 OpenTrace 记录分析流程

背景：John Windward 在 2046年5月17日凌晨4:21am 在 SaidIT 发布了异常帖子
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opentrace.mcp_server import get_server


class MC2Analyzer:
    """MC2 数据分析器"""

    # 关键事件时间戳
    KEY_EVENT_TIMESTAMP = datetime(2046, 5, 17, 4, 21).timestamp()

    def __init__(self, data_path: str, org_chart_path: str):
        self.data_path = data_path
        self.org_chart_path = org_chart_path
        self.server = get_server(".opentrace")
        self.session_id = None
        self.data = None
        self.org_chart = None

    def init_session(self):
        """初始化 OpenTrace 会话"""
        print("=" * 60)
        print("初始化 OpenTrace 会话")
        print("=" * 60)

        result = self.server.init_session(
            task_description="VAST Challenge 2026 MC2 - 异常帖子发布分析",
            data_path=self.data_path,
            data_type="json"
        )

        if "error" in result:
            raise Exception(f"初始化失败: {result['error']}")

        self.session_id = result["session_id"]
        print(f"会话ID: {self.session_id}")
        print()

        # 记录初始 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "input", "entity_type": "dataset", "location": self.data_path, "attributes": {"type": "MC2 data.json"}},
                {"id": "org_chart", "entity_type": "dataset", "location": self.org_chart_path, "attributes": {"type": "organization chart"}},
                {"id": "output", "entity_type": "dataset", "location": "working_data.json", "attributes": {"status": "loaded"}}
            ],
            activities=[
                {"id": "activity", "activity_type": "transform", "description": "加载MC2数据和组织架构", "attributes": {"operation": "json_load"}}
            ],
            agents=[
                {"id": "agent", "agent_type": "python_code", "name": "init_session", "attributes": {"step": "data_loading"}}
            ],
            relations=[
                ("activity", "input", "used"),
                ("activity", "org_chart", "used"),
                ("output", "activity", "wasGeneratedBy"),
                ("activity", "agent", "wasAssociatedWith"),
                ("output", "input", "wasDerivedFrom")
            ]
        )
        print(f"PROV 初始记录: {prov_result.get('status', 'unknown')}")

        return self.session_id

    def load_data(self):
        """加载数据"""
        print("=" * 60)
        print("加载数据")
        print("=" * 60)

        with open(self.data_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        with open(self.org_chart_path, 'r', encoding='utf-8') as f:
            self.org_chart = json.load(f)

        events = self.data.get('events', [])
        print(f"总事件数: {len(events)}")
        print(f"组织架构节点数: {len(self.org_chart.get('nodes', []))}")

        # 记录数据加载步骤
        self.server.record_step(
            session_id=self.session_id,
            step_name="数据加载",
            operation="load_mc2_data",
            description="加载MC2事件数据和组织架构",
            metadata={"total_events": len(events), "org_nodes": len(self.org_chart.get('nodes', []))}
        )

        return events

    def analyze_question1(self, events):
        """
        问题1: 异常帖子是如何产生的？
        - 追踪导致帖子产生的事件序列
        - 识别关键的人员和系统交互
        """
        print("=" * 60)
        print("问题1分析: 异常帖子的产生过程")
        print("=" * 60)

        # 记录分析步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="问题1分析",
            operation="analyze_anomalous_post",
            description="追踪导致异常帖子产生的事件序列",
            metadata={"question": "how_was_post_made"}
        )

        results = {
            "key_event_chain": [],
            "john_windward_events": [],
            "saidit_events": [],
            "agent_interactions": [],
            "timeline_analysis": {}
        }

        # 找到关键事件附近的时间窗口（前后24小时）
        key_time = self.KEY_EVENT_TIMESTAMP
        time_window = 24 * 3600  # 24小时

        # 分析关键事件附近的事件
        for event in events:
            event_time = event.get('when', 0)
            time_diff = abs(event_time - key_time)

            # 收集关键事件附近的事件
            if time_diff < time_window:
                results["key_event_chain"].append({
                    "id": event.get('id'),
                    "short_name": event.get('short_name'),
                    "parties": event.get('parties', []),
                    "when": event_time,
                    "time_diff_hours": time_diff / 3600,
                    "details": str(event.get('details', {}))[:200]
                })

            # 识别 John Windward 相关事件
            parties = event.get('parties', [])
            if any('john_windward' in str(p).lower() for p in parties):
                results["john_windward_events"].append({
                    "id": event.get('id'),
                    "short_name": event.get('short_name'),
                    "when": event_time,
                    "details": str(event.get('details', {}))[:200]
                })

            # 识别 SaidIT 相关事件
            short_name = event.get('short_name', '')
            if 'saidit' in short_name.lower() or 'post' in short_name.lower():
                results["saidit_events"].append({
                    "id": event.get('id'),
                    "short_name": short_name,
                    "when": event_time,
                    "parties": parties,
                    "details": str(event.get('details', {}))[:200]
                })

            # 识别 agent 交互事件
            if 'a2a' in str(event.get('details', {})):
                results["agent_interactions"].append({
                    "id": event.get('id'),
                    "short_name": event.get('short_name'),
                    "when": event_time,
                    "details": str(event.get('details', {}))[:300]
                })

        # 按时间排序
        results["key_event_chain"].sort(key=lambda x: x['time_diff_hours'])
        results["john_windward_events"].sort(key=lambda x: x['when'])
        results["saidit_events"].sort(key=lambda x: x['when'])

        print(f"关键事件链事件数: {len(results['key_event_chain'])}")
        print(f"John Windward 相关事件数: {len(results['john_windward_events'])}")
        print(f"SaidIT 相关事件数: {len(results['saidit_events'])}")
        print(f"Agent 交互事件数: {len(results['agent_interactions'])}")

        # 记录数据处理
        self.server.record_processing(
            session_id=self.session_id,
            step_id=step_id,
            input_spec={
                "source": "working_data.json",
                "source_type": "json_timeline",
                "total_events": len(events),
                "key_timestamp": key_time
            },
            algorithm_spec={
                "type": "temporal_analysis",
                "language": "python",
                "logic_description": "分析关键事件时间窗口内的事件序列"
            },
            result_data={
                "key_event_chain_count": len(results['key_event_chain']),
                "john_windward_events_count": len(results['john_windward_events']),
                "saidit_events_count": len(results['saidit_events']),
                "agent_interactions_count": len(results['agent_interactions'])
            }
        )

        # 记录 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q1_input", "entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"id": "q1_events", "entity_type": "artifact", "location": "key_event_chain.json", "attributes": {"count": len(results['key_event_chain'])}},
                {"id": "q1_john", "entity_type": "artifact", "location": "john_windward_events.json", "attributes": {"count": len(results['john_windward_events'])}},
                {"id": "q1_saidit", "entity_type": "artifact", "location": "saidit_events.json", "attributes": {"count": len(results['saidit_events'])}},
                {"id": "q1_output", "entity_type": "artifact", "location": "question1_results.json", "attributes": {}}
            ],
            activities=[
                {"id": "q1_activity1", "activity_type": "filter", "description": "提取关键事件链", "attributes": {"events": len(results['key_event_chain'])}},
                {"id": "q1_activity2", "activity_type": "filter", "description": "识别John Windward事件", "attributes": {"events": len(results['john_windward_events'])}},
                {"id": "q1_activity3", "activity_type": "aggregate", "description": "汇总问题1结果", "attributes": {}}
            ],
            agents=[
                {"id": "q1_agent", "agent_type": "python_code", "name": "analyze_q1", "attributes": {"step": "q1_analysis"}}
            ],
            relations=[
                ("q1_activity1", "q1_input", "used"),
                ("q1_events", "q1_activity1", "wasGeneratedBy"),
                ("q1_activity2", "q1_input", "used"),
                ("q1_john", "q1_activity2", "wasGeneratedBy"),
                ("q1_activity3", "q1_events", "used"),
                ("q1_activity3", "q1_john", "used"),
                ("q1_output", "q1_activity3", "wasGeneratedBy"),
                ("q1_activity1", "q1_agent", "wasAssociatedWith"),
                ("q1_activity2", "q1_agent", "wasAssociatedWith"),
                ("q1_activity3", "q1_agent", "wasAssociatedWith"),
                ("q1_output", "q1_input", "wasDerivedFrom")
            ]
        )
        print(f"问题1 PROV 记录: {prov_result.get('status', 'unknown')}")

        return results

    def analyze_question2(self, events):
        """
        问题2: 帖子"意味着"什么？内容的来源是什么？
        - 分析帖子内容的含义
        - 追踪内容来源
        """
        print("=" * 60)
        print("问题2分析: 帖子内容和来源分析")
        print("=" * 60)

        # 记录分析步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="问题2分析",
            operation="analyze_content_origin",
            description="分析异常帖子的内容和来源",
            metadata={"question": "post_meaning_and_origin"}
        )

        results = {
            "content_analysis": [],
            "source_tracing": [],
            "pattern_analysis": {},
            "gibberish_indicators": []
        }

        # 分析事件中的内容
        content_keywords = ['content', 'text', 'message', 'post', 'body', 'data']
        gibberish_indicators = ['gibberish', 'random', 'garbled', 'nonsense', 'corrupt']

        for event in events:
            details = event.get('details', {})
            details_str = str(details).lower()

            # 检查内容相关字段
            for keyword in content_keywords:
                if keyword in details_str:
                    results["content_analysis"].append({
                        "id": event.get('id'),
                        "short_name": event.get('short_name'),
                        "keyword_found": keyword,
                        "details": str(details)[:300]
                    })
                    break

            # 检查乱码指标
            for indicator in gibberish_indicators:
                if indicator in details_str:
                    results["gibberish_indicators"].append({
                        "id": event.get('id'),
                        "short_name": event.get('short_name'),
                        "indicator": indicator,
                        "when": event.get('when'),
                        "details": str(details)[:200]
                    })
                    break

        # 统计模式
        results["pattern_analysis"] = {
            "total_content_events": len(results["content_analysis"]),
            "gibberish_indicators_count": len(results["gibberish_indicators"]),
            "event_types": Counter(e["short_name"] for e in results["content_analysis"])
        }

        print(f"内容相关事件数: {len(results['content_analysis'])}")
        print(f"乱码指标数: {len(results['gibberish_indicators'])}")
        print(f"事件类型分布: {dict(results['pattern_analysis']['event_types'])}")

        # 记录数据处理
        self.server.record_processing(
            session_id=self.session_id,
            step_id=step_id,
            input_spec={
                "source": "working_data.json",
                "source_type": "json_timeline",
                "total_events": len(events)
            },
            algorithm_spec={
                "type": "content_analysis",
                "language": "python",
                "logic_description": "分析事件中的内容和乱码指标"
            },
            result_data={
                "content_events": len(results['content_analysis']),
                "gibberish_indicators": len(results['gibberish_indicators'])
            }
        )

        # 记录 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q2_input", "entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"id": "q2_content", "entity_type": "artifact", "location": "content_analysis.json", "attributes": {"count": len(results['content_analysis'])}},
                {"id": "q2_gibberish", "entity_type": "artifact", "location": "gibberish_indicators.json", "attributes": {"count": len(results['gibberish_indicators'])}},
                {"id": "q2_output", "entity_type": "artifact", "location": "question2_results.json", "attributes": {}}
            ],
            activities=[
                {"id": "q2_activity1", "activity_type": "filter", "description": "提取内容相关事件", "attributes": {"events": len(results['content_analysis'])}},
                {"id": "q2_activity2", "activity_type": "filter", "description": "识别乱码指标", "attributes": {"indicators": len(results['gibberish_indicators'])}},
                {"id": "q2_activity3", "activity_type": "aggregate", "description": "汇总问题2结果", "attributes": {}}
            ],
            agents=[
                {"id": "q2_agent", "agent_type": "python_code", "name": "analyze_q2", "attributes": {"step": "q2_analysis"}}
            ],
            relations=[
                ("q2_activity1", "q2_input", "used"),
                ("q2_content", "q2_activity1", "wasGeneratedBy"),
                ("q2_activity2", "q2_input", "used"),
                ("q2_gibberish", "q2_activity2", "wasGeneratedBy"),
                ("q2_activity3", "q2_content", "used"),
                ("q2_activity3", "q2_gibberish", "used"),
                ("q2_output", "q2_activity3", "wasGeneratedBy"),
                ("q2_activity1", "q2_agent", "wasAssociatedWith"),
                ("q2_activity2", "q2_agent", "wasAssociatedWith"),
                ("q2_activity3", "q2_agent", "wasAssociatedWith"),
                ("q2_output", "q2_input", "wasDerivedFrom")
            ]
        )
        print(f"问题2 PROV 记录: {prov_result.get('status', 'unknown')}")

        return results

    def analyze_question3(self, events):
        """
        问题3: 这种行为会重复吗？
        - 查找历史行为中的类似案例
        - 对比当前案例和历史案例
        - 建议干预措施
        """
        print("=" * 60)
        print("问题3分析: 历史行为对比和干预建议")
        print("=" * 60)

        # 记录分析步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="问题3分析",
            operation="analyze_historic_behavior",
            description="查找类似的历史案例并建议干预措施",
            metadata={"question": "behavior_recurrence"}
        )

        results = {
            "prior_incidents": [],
            "behavior_patterns": {},
            "anomaly_indicators": [],
            "intervention_suggestions": []
        }

        # 关键事件时间
        key_time = self.KEY_EVENT_TIMESTAMP

        # 分析不同时间段的行为
        time_periods = {
            "before_may17": [2409400000, key_time - 86400],  # 5月17日之前
            "after_may17": [key_time + 86400, 2410000000]   # 5月17日之后
        }

        # 乱码/异常相关关键词
        anomaly_keywords = [
            'error', 'fail', 'crash', 'gibberish', 'corrupt',
            'malfunction', 'anomalous', 'unexpected', 'unusual',
            'agent_malfunction', 'system_error'
        ]

        for period_name, (start_time, end_time) in time_periods.items():
            period_events = []
            for event in events:
                event_time = event.get('when', 0)
                if start_time <= event_time <= end_time:
                    # 检查异常关键词
                    details_str = str(event.get('details', '')).lower()
                    short_name = event.get('short_name', '').lower()

                    if any(kw in details_str or kw in short_name for kw in anomaly_keywords):
                        period_events.append({
                            "id": event.get('id'),
                            "short_name": event.get('short_name'),
                            "when": event_time,
                            "period": period_name,
                            "details": str(event.get('details', {}))[:200]
                        })

            results["prior_incidents"].extend(period_events)

        # 分析行为模式
        results["behavior_patterns"] = {
            "total_prior_incidents": len(results["prior_incidents"]),
            "incident_distribution": Counter(inc["period"] for inc in results["prior_incidents"]),
            "incident_types": Counter(inc["short_name"] for inc in results["prior_incidents"])
        }

        # 识别异常指标
        for event in events:
            details = event.get('details', {})
            # 检查 agent-to-agent 通信中的异常
            if 'a2a' in str(details):
                results["anomaly_indicators"].append({
                    "id": event.get('id'),
                    "short_name": event.get('short_name'),
                    "when": event.get('when'),
                    "a2a_details": str(details)[:300]
                })

        # 干预建议（基于发现的模式）
        if results["behavior_patterns"]["total_prior_incidents"] > 0:
            results["intervention_suggestions"].append({
                "type": "monitoring",
                "description": "增强 agent 间通信监控",
                "priority": "high",
                "reason": f"发现 {len(results['prior_incidents'])} 个历史异常案例"
            })

        if len(results["anomaly_indicators"]) > 100:
            results["intervention_suggestions"].append({
                "type": "validation",
                "description": "添加 agent 输出验证层",
                "priority": "medium",
                "reason": f"检测到 {len(results['anomaly_indicators'])} 个 agent 交互事件"
            })

        results["intervention_suggestions"].append({
            "type": "alert",
            "description": "为 SaidIT 发布添加人工审核",
            "priority": "high",
            "reason": "防止异常内容公开发布"
        })

        print(f"历史异常事件数: {len(results['prior_incidents'])}")
        print(f"Agent 交互事件数: {len(results['anomaly_indicators'])}")
        print(f"干预建议数: {len(results['intervention_suggestions'])}")

        # 记录数据处理
        self.server.record_processing(
            session_id=self.session_id,
            step_id=step_id,
            input_spec={
                "source": "working_data.json",
                "source_type": "json_timeline",
                "total_events": len(events),
                "key_timestamp": key_time
            },
            algorithm_spec={
                "type": "temporal_pattern_analysis",
                "language": "python",
                "logic_description": "分析历史行为模式并识别异常"
            },
            result_data={
                "prior_incidents": len(results['prior_incidents']),
                "anomaly_indicators": len(results['anomaly_indicators']),
                "intervention_suggestions": len(results['intervention_suggestions'])
            }
        )

        # 记录 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q3_input", "entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"id": "q3_prior", "entity_type": "artifact", "location": "prior_incidents.json", "attributes": {"count": len(results['prior_incidents'])}},
                {"id": "q3_anomaly", "entity_type": "artifact", "location": "anomaly_indicators.json", "attributes": {"count": len(results['anomaly_indicators'])}},
                {"id": "q3_output", "entity_type": "artifact", "location": "question3_results.json", "attributes": {}}
            ],
            activities=[
                {"id": "q3_activity1", "activity_type": "filter", "description": "查找历史异常事件", "attributes": {"incidents": len(results['prior_incidents'])}},
                {"id": "q3_activity2", "activity_type": "transform", "description": "分析行为模式", "attributes": {}},
                {"id": "q3_activity3", "activity_type": "aggregate", "description": "汇总问题3结果和建议", "attributes": {"suggestions": len(results['intervention_suggestions'])}}
            ],
            agents=[
                {"id": "q3_agent", "agent_type": "python_code", "name": "analyze_q3", "attributes": {"step": "q3_analysis"}}
            ],
            relations=[
                ("q3_activity1", "q3_input", "used"),
                ("q3_prior", "q3_activity1", "wasGeneratedBy"),
                ("q3_activity2", "q3_input", "used"),
                ("q3_anomaly", "q3_activity2", "wasGeneratedBy"),
                ("q3_activity3", "q3_prior", "used"),
                ("q3_activity3", "q3_anomaly", "used"),
                ("q3_output", "q3_activity3", "wasGeneratedBy"),
                ("q3_activity1", "q3_agent", "wasAssociatedWith"),
                ("q3_activity2", "q3_agent", "wasAssociatedWith"),
                ("q3_activity3", "q3_agent", "wasAssociatedWith"),
                ("q3_output", "q3_input", "wasDerivedFrom")
            ]
        )
        print(f"问题3 PROV 记录: {prov_result.get('status', 'unknown')}")

        return results

    def save_results(self, all_results):
        """保存分析结果"""
        print("\n" + "=" * 60)
        print("保存分析结果")
        print("=" * 60)

        output_dir = Path(f".opentrace/{self.session_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "mc2_analysis_results.json"

        # 转换 Counter 为普通 dict
        def convert_types(obj):
            if isinstance(obj, Counter):
                return dict(obj)
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            return obj

        converted_results = convert_types(all_results)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(converted_results, f, ensure_ascii=False, indent=2, default=str)

        print(f"分析结果已保存到: {output_file}")

    def run_analysis(self):
        """运行完整分析"""
        print("\n" + "=" * 60)
        print("VAST Challenge 2026 MC2 - 数据分析")
        print("=" * 60)
        print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        all_results = {}

        try:
            # 初始化会话
            self.init_session()

            # 加载数据
            events = self.load_data()

            # 问题1分析
            all_results["question1"] = self.analyze_question1(events)

            # 问题2分析
            all_results["question2"] = self.analyze_question2(events)

            # 问题3分析
            all_results["question3"] = self.analyze_question3(events)

            # 保存结果
            self.save_results(all_results)

            print("\n" + "=" * 60)
            print("分析完成！")
            print("=" * 60)

            return all_results

        except Exception as e:
            print(f"\n分析出错: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """主函数"""
    data_dir = "C:/Users/83734/Desktop/opentrace/VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2"
    data_path = f"{data_dir}/MC2 data.json"
    org_chart_path = f"{data_dir}/org_chart.json"

    analyzer = MC2Analyzer(data_path, org_chart_path)
    results = analyzer.run_analysis()

    return results


if __name__ == "__main__":
    main()
