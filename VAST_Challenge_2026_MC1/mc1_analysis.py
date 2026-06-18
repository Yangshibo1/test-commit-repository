"""
VAST Challenge 2026 MC1 - 数据分析脚本
使用 OpenTrace 记录分析流程
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from opentrace.mcp_server import get_server

class MC1Analyzer:
    """MC1 数据分析器"""

    def __init__(self, data_path: str):
        self.data_path = data_path
        self.server = get_server(".opentrace")
        self.session_id = None
        self.data = None

    def init_session(self):
        """初始化 OpenTrace 会话"""
        print("=" * 60)
        print("初始化 OpenTrace 会话")
        print("=" * 60)

        result = self.server.init_session(
            task_description="VAST Challenge 2026 MC1 - 多Agent危机数据分析",
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
                {"id": "input", "entity_type": "dataset", "location": self.data_path, "attributes": {"type": "MC1_final_00.json"}},
                {"id": "output", "entity_type": "dataset", "location": "working_data.json", "attributes": {"status": "loaded"}}
            ],
            activities=[
                {"id": "activity", "activity_type": "transform", "description": "加载MC1数据", "attributes": {"operation": "json_load"}}
            ],
            agents=[
                {"id": "agent", "agent_type": "python_code", "name": "init_session", "attributes": {"step": "data_loading"}}
            ],
            relations=[
                ("activity", "input", "used"),
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

        rounds = self.data.get('rounds', [])
        print(f"总轮数: {len(rounds)}")

        # 记录数据加载步骤
        self.server.record_step(
            session_id=self.session_id,
            step_name="数据加载",
            operation="load_mc1_data",
            description="加载MC1数据（轮次格式）",
            metadata={"total_rounds": len(rounds)}
        )

        return rounds

    def analyze_question1(self, rounds):
        """
        问题1: 导致不当发布的关键事件和关系
        - 关键行动
        - 因果关系
        - 决策点和参与者
        - 通过禁令执行的重要决策和系统元素
        """
        print("=" * 60)
        print("问题1分析: 导致不当发布的关键事件和关系")
        print("=" * 60)

        # 记录分析步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="问题1分析",
            operation="analyze_key_events",
            description="分析导致不当发布的关键事件",
            metadata={"question": "key_events_and_relationships"}
        )

        results = {
            "key_events": [],
            "agent_actions": defaultdict(list),
            "communications": [],
            "decision_points": [],
            "critical_timeline": []
        }

        # 分析每一轮
        for round_idx, round_data in enumerate(rounds):
            hour = round_data.get('hour', '')
            env_context = round_data.get('environment_context', {})
            event_narrative = env_context.get('event_narrative', '')
            event_headline = env_context.get('event_headline', '')

            # 记录关键环境事件
            if event_narrative:
                results["key_events"].append({
                    "round": round_idx + 1,
                    "hour": hour,
                    "type": "environment_event",
                    "headline": event_headline,
                    "narrative": event_narrative
                })

            # 分析通信
            communications = round_data.get('communications', [])
            print(f"轮次 {round_idx + 1}: {hour} - {len(communications)} 条通信")

            for comm in communications:
                agent_id = comm.get('agent_id', 'unknown')
                agent_role = comm.get('agent_role', '')
                agent_label = comm.get('agent_label', '')
                channel = comm.get('channel', '')
                content = comm.get('content', '')
                internal_state = comm.get('internal_state', {})
                message_type = comm.get('message_type', '')

                # 记录通信
                results["communications"].append({
                    "round": round_idx + 1,
                    "hour": hour,
                    "agent_id": agent_id,
                    "agent_role": agent_role,
                    "agent_label": agent_label,
                    "channel": channel,
                    "content": content[:300] if len(content) > 300 else content,
                    "message_type": message_type
                })

                # 记录agent行动
                results["agent_actions"][agent_id].append({
                    "round": round_idx + 1,
                    "hour": hour,
                    "role": agent_role,
                    "channel": channel,
                    "action_type": message_type
                })

                # 记录决策点（内部状态中的关键信息）
                if internal_state and isinstance(internal_state, dict):
                    for state_type, state_value in internal_state.items():
                        if state_value and isinstance(state_value, str) and len(state_value) > 50:
                            results["decision_points"].append({
                                "round": round_idx + 1,
                                "hour": hour,
                                "agent_id": agent_id,
                                "agent_role": agent_role,
                                "state_type": state_type,
                                "decision": state_value[:200]
                            })

            # 检查禁令相关的关键事件
            if any(keyword in event_narrative.lower() for keyword in ['embargo', 'merger', 'civicloom', 'harborcrest', 'publish', 'announcement']):
                results["critical_timeline"].append({
                    "round": round_idx + 1,
                    "hour": hour,
                    "event": event_headline,
                    "narrative": event_narrative[:300]
                })

        print(f"\n关键事件数量: {len(results['key_events'])}")
        print(f"通信数量: {len(results['communications'])}")
        print(f"决策点数量: {len(results['decision_points'])}")
        print(f"关键时间线事件: {len(results['critical_timeline'])}")

        # 记录数据处理
        self.server.record_processing(
            session_id=self.session_id,
            step_id=step_id,
            input_spec={
                "source": "working_data.json",
                "source_type": "json_array",
                "total_rounds": len(rounds)
            },
            algorithm_spec={
                "type": "event_extraction",
                "language": "python",
                "logic_description": "遍历所有轮次，提取关键事件、通信、决策点"
            },
            result_data={
                "key_events_count": len(results['key_events']),
                "communications_count": len(results['communications']),
                "decision_points_count": len(results['decision_points']),
                "critical_timeline_count": len(results['critical_timeline'])
            }
        )

        # 记录 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q1_input", "entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"id": "q1_events", "entity_type": "artifact", "location": "key_events.json", "attributes": {"count": len(results['key_events'])}},
                {"id": "q1_comms", "entity_type": "artifact", "location": "communications.json", "attributes": {"count": len(results['communications'])}},
                {"id": "q1_output", "entity_type": "artifact", "location": "question1_results.json", "attributes": {}}
            ],
            activities=[
                {"id": "q1_activity1", "activity_type": "filter", "description": "提取关键事件", "attributes": {"events_found": len(results['key_events'])}},
                {"id": "q1_activity2", "activity_type": "transform", "description": "分析通信模式", "attributes": {"communications": len(results['communications'])}},
                {"id": "q1_activity3", "activity_type": "aggregate", "description": "汇总问题1结果", "attributes": {}}
            ],
            agents=[
                {"id": "q1_agent", "agent_type": "python_code", "name": "analyze_q1", "attributes": {"step": "q1_analysis"}}
            ],
            relations=[
                ("q1_activity1", "q1_input", "used"),
                ("q1_events", "q1_activity1", "wasGeneratedBy"),
                ("q1_activity2", "q1_input", "used"),
                ("q1_comms", "q1_activity2", "wasGeneratedBy"),
                ("q1_activity3", "q1_events", "used"),
                ("q1_activity3", "q1_comms", "used"),
                ("q1_output", "q1_activity3", "wasGeneratedBy"),
                ("q1_activity1", "q1_agent", "wasAssociatedWith"),
                ("q1_activity2", "q1_agent", "wasAssociatedWith"),
                ("q1_activity3", "q1_agent", "wasAssociatedWith"),
                ("q1_output", "q1_input", "wasDerivedFrom")
            ]
        )
        print(f"问题1 PROV 记录: {prov_result.get('status', 'unknown')}")

        return results

    def analyze_question2(self, rounds):
        """
        问题2: 规避禁令是一种新行为
        - 发现和说明典型行为
        - 与之前行为对比
        """
        print("=" * 60)
        print("问题2分析: 典型行为与新行为对比")
        print("=" * 60)

        # 记录分析步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="问题2分析",
            operation="analyze_typical_behavior",
            description="分析典型行为与新行为对比",
            metadata={"question": "typical_vs_new_behavior"}
        )

        results = {
            "agent_behavior_patterns": defaultdict(lambda: {"actions": [], "channels": Counter()}),
            "communication_patterns": Counter(),
            "action_distribution": Counter(),
            "typical_behavior": {},
            "crisis_behavior": {},
            "comparison": {}
        }

        # 分割正常期和危机期
        split_point = len(rounds) // 2
        normal_rounds = rounds[:split_point]
        crisis_rounds = rounds[split_point:]

        print(f"正常期轮数: {len(normal_rounds)}")
        print(f"危机期轮数: {len(crisis_rounds)}")

        # 分析正常期行为
        normal_communications = []
        for round_data in normal_rounds:
            communications = round_data.get('communications', [])
            normal_communications.extend(communications)

        # 分析危机期行为
        crisis_communications = []
        for round_data in crisis_rounds:
            communications = round_data.get('communications', [])
            crisis_communications.extend(communications)

        print(f"正常期通信数: {len(normal_communications)}")
        print(f"危机期通信数: {len(crisis_communications)}")

        # 统计正常期模式
        for comm in normal_communications:
            agent_id = comm.get('agent_id')
            channel = comm.get('channel')
            message_type = comm.get('message_type')

            results["agent_behavior_patterns"][agent_id]["actions"].append(message_type)
            results["agent_behavior_patterns"][agent_id]["channels"][channel] += 1
            results["communication_patterns"][channel] += 1
            results["action_distribution"][message_type] += 1

        # 统计危机期模式
        crisis_action_dist = Counter()
        crisis_comm_patterns = Counter()
        crisis_agent_patterns = defaultdict(lambda: {"actions": [], "channels": Counter()})

        for comm in crisis_communications:
            agent_id = comm.get('agent_id')
            channel = comm.get('channel')
            message_type = comm.get('message_type')

            crisis_agent_patterns[agent_id]["actions"].append(message_type)
            crisis_agent_patterns[agent_id]["channels"][channel] += 1
            crisis_comm_patterns[channel] += 1
            crisis_action_dist[message_type] += 1

        # 汇总结果
        results["typical_behavior"] = {
            "total_communications": len(normal_communications),
            "action_distribution": dict(results["action_distribution"]),
            "communication_patterns": dict(results["communication_patterns"]),
            "agent_patterns": {
                k: {
                    "actions": v["actions"],
                    "channels": dict(v["channels"])
                }
                for k, v in results["agent_behavior_patterns"].items()
            }
        }

        results["crisis_behavior"] = {
            "total_communications": len(crisis_communications),
            "action_distribution": dict(crisis_action_dist),
            "communication_patterns": dict(crisis_comm_patterns),
            "agent_patterns": {
                k: {
                    "actions": v["actions"],
                    "channels": dict(v["channels"])
                }
                for k, v in crisis_agent_patterns.items()
            }
        }

        # 对比分析
        typical_actions = set(results["action_distribution"].keys())
        crisis_actions = set(crisis_action_dist.keys())
        new_actions = crisis_actions - typical_actions

        results["comparison"] = {
            "new_actions_in_crisis": list(new_actions),
            "communication_volume_change": len(crisis_communications) - len(normal_communications),
            "action_type_change": len(crisis_actions) - len(typical_actions)
        }

        print(f"\n危机期新增行动类型: {new_actions}")
        print(f"通信量变化: {results['comparison']['communication_volume_change']}")

        # 记录数据处理
        self.server.record_processing(
            session_id=self.session_id,
            step_id=step_id,
            input_spec={
                "source": "working_data.json",
                "source_type": "json_array",
                "split_point": split_point
            },
            algorithm_spec={
                "type": "behavior_comparison",
                "language": "python",
                "logic_description": "对比正常期和危机期的agent行为模式"
            },
            result_data={
                "typical_comms": len(normal_communications),
                "crisis_comms": len(crisis_communications),
                "new_actions": list(new_actions)
            }
        )

        # 记录 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q2_input", "entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"id": "q2_typical", "entity_type": "artifact", "location": "typical_behavior.json", "attributes": {"comms": len(normal_communications)}},
                {"id": "q2_crisis", "entity_type": "artifact", "location": "crisis_behavior.json", "attributes": {"comms": len(crisis_communications)}},
                {"id": "q2_comparison", "entity_type": "artifact", "location": "behavior_comparison.json", "attributes": {}},
                {"id": "q2_output", "entity_type": "artifact", "location": "question2_results.json", "attributes": {}}
            ],
            activities=[
                {"id": "q2_activity1", "activity_type": "filter", "description": "提取正常期数据", "attributes": {}},
                {"id": "q2_activity2", "activity_type": "filter", "description": "提取危机期数据", "attributes": {}},
                {"id": "q2_activity3", "activity_type": "transform", "description": "对比行为差异", "attributes": {"new_actions": len(new_actions)}}
            ],
            agents=[
                {"id": "q2_agent", "agent_type": "python_code", "name": "analyze_q2", "attributes": {"step": "q2_analysis"}}
            ],
            relations=[
                ("q2_activity1", "q2_input", "used"),
                ("q2_typical", "q2_activity1", "wasGeneratedBy"),
                ("q2_activity2", "q2_input", "used"),
                ("q2_crisis", "q2_activity2", "wasGeneratedBy"),
                ("q2_activity3", "q2_typical", "used"),
                ("q2_activity3", "q2_crisis", "used"),
                ("q2_output", "q2_activity3", "wasGeneratedBy"),
                ("q2_activity1", "q2_agent", "wasAssociatedWith"),
                ("q2_activity2", "q2_agent", "wasAssociatedWith"),
                ("q2_activity3", "q2_agent", "wasAssociatedWith"),
                ("q2_output", "q2_input", "wasDerivedFrom")
            ]
        )
        print(f"问题2 PROV 记录: {prov_result.get('status', 'unknown')}")

        return results

    def analyze_question3(self, rounds):
        """
        问题3: 是否有领先指标表明这种发布可能发生？
        - agent实际行为与预期行为不同的先前情况
        - 系统表现出类似导致发布的行为的情况
        - 为什么先前情况没有导致明显行动
        """
        print("=" * 60)
        print("问题3分析: 领先指标和先前情况")
        print("=" * 60)

        # 记录分析步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="问题3分析",
            operation="analyze_leading_indicators",
            description="分析领先指标和先前异常情况",
            metadata={"question": "leading_indicators"}
        )

        results = {
            "behavior_deviations": [],
            "warning_signs": [],
            "prior_incidents": [],
            "escalation_failures": [],
            "suppression_indicators": []
        }

        # 警告关键词列表
        warning_keywords = [
            'uncertain', 'concern', 'risk', 'unusual', 'unprecedented',
            'escalat', 'warn', 'caution', 'alert', 'crisi',
            'embargo', 'breach', 'violat', 'publish', 'leak',
            'conflict', 'disagree', 'oppose', 'reject',
            'silence', 'delay', 'hesitat', 'unclear'
        ]

        # 分析每一轮
        for round_idx, round_data in enumerate(rounds):
            hour = round_data.get('hour', '')
            env_context = round_data.get('environment_context', {})
            event_narrative = env_context.get('event_narrative', '')

            communications = round_data.get('communications', [])

            # 检查环境事件中的警告信号
            for keyword in warning_keywords:
                if keyword in event_narrative.lower():
                    results["warning_signs"].append({
                        "round": round_idx + 1,
                        "hour": hour,
                        "type": "environment_event",
                        "keyword": keyword,
                        "context": event_narrative[:200]
                    })
                    break

            # 检查通信中的异常
            for comm in communications:
                agent_id = comm.get('agent_id')
                content = comm.get('content', '')
                internal_state = comm.get('internal_state', {})
                channel = comm.get('channel', '')

                # 检查内容中的警告关键词
                for keyword in warning_keywords:
                    if keyword in content.lower() or (internal_state and keyword in str(internal_state).lower()):
                        results["behavior_deviations"].append({
                            "round": round_idx + 1,
                            "hour": hour,
                            "agent": agent_id,
                            "channel": channel,
                            "keyword": keyword,
                            "context": content[:150]
                        })
                        break

                # 检查内部状态中的犹豫或担忧
                if internal_state and isinstance(internal_state, dict):
                    for state_type, state_value in internal_state.items():
                        if state_value and isinstance(state_value, str):
                            # 检查是否有担忧、犹豫等情绪
                            concern_keywords = ['concern', 'worri', 'hesitat', 'uncertain', 'uncomfortable', 'reluctant']
                            if any(kw in state_value.lower() for kw in concern_keywords):
                                results["suppression_indicators"].append({
                                    "round": round_idx + 1,
                                    "hour": hour,
                                    "agent": agent_id,
                                    "state_type": state_type,
                                    "indicator": "agent_concern",
                                    "context": state_value[:150]
                                })

                # 检查是否有公开发布相关的行动
                if channel == 'social_media' or channel == 'external':
                    results["prior_incidents"].append({
                        "round": round_idx + 1,
                        "hour": hour,
                        "agent": agent_id,
                        "channel": channel,
                        "content_preview": content[:100]
                    })

        # 分析升级失败的原因
        results["escalation_failures"] = {
            "lack_of_escalation_count": len([w for w in results["warning_signs"] if "escalat" in str(w.get("keyword", "")).lower()]),
            "agent_concerns_suppressed": len([w for w in results["suppression_indicators"] if w.get("indicator") == "agent_concern"]),
            "total_warning_signs": len(results["warning_signs"]),
            "total_behavior_deviations": len(results["behavior_deviations"])
        }

        print(f"\n警告信号数量: {len(results['warning_signs'])}")
        print(f"行为偏差数量: {len(results['behavior_deviations'])}")
        print(f"先前事件数量: {len(results['prior_incidents'])}")
        print(f"抑制指标数量: {len(results['suppression_indicators'])}")

        # 记录数据处理
        self.server.record_processing(
            session_id=self.session_id,
            step_id=step_id,
            input_spec={
                "source": "working_data.json",
                "source_type": "json_array",
                "warning_keywords": len(warning_keywords)
            },
            algorithm_spec={
                "type": "warning_detection",
                "language": "python",
                "logic_description": "检测通信和环境事件中的警告关键词"
            },
            result_data={
                "warning_signs": len(results['warning_signs']),
                "behavior_deviations": len(results['behavior_deviations']),
                "prior_incidents": len(results['prior_incidents']),
                "suppression_indicators": len(results['suppression_indicators'])
            }
        )

        # 记录 PROV 关系
        prov_result = self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q3_input", "entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"id": "q3_warnings", "entity_type": "artifact", "location": "warning_signs.json", "attributes": {"count": len(results['warning_signs'])}},
                {"id": "q3_deviations", "entity_type": "artifact", "location": "behavior_deviations.json", "attributes": {"count": len(results['behavior_deviations'])}},
                {"id": "q3_suppression", "entity_type": "artifact", "location": "suppression_indicators.json", "attributes": {"count": len(results['suppression_indicators'])}},
                {"id": "q3_output", "entity_type": "artifact", "location": "question3_results.json", "attributes": {}}
            ],
            activities=[
                {"id": "q3_activity1", "activity_type": "filter", "description": "检测警告信号", "attributes": {"warnings": len(results['warning_signs'])}},
                {"id": "q3_activity2", "activity_type": "filter", "description": "识别行为偏差", "attributes": {"deviations": len(results['behavior_deviations'])}},
                {"id": "q3_activity3", "activity_type": "aggregate", "description": "汇总升级失败分析", "attributes": {}}
            ],
            agents=[
                {"id": "q3_agent", "agent_type": "python_code", "name": "analyze_q3", "attributes": {"step": "q3_analysis"}}
            ],
            relations=[
                ("q3_activity1", "q3_input", "used"),
                ("q3_warnings", "q3_activity1", "wasGeneratedBy"),
                ("q3_activity2", "q3_input", "used"),
                ("q3_deviations", "q3_activity2", "wasGeneratedBy"),
                ("q3_activity3", "q3_warnings", "used"),
                ("q3_activity3", "q3_deviations", "used"),
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
        output_file = output_dir / "mc1_analysis_results.json"

        # 转换 defaultdict 和 Counter 为普通 dict
        def convert_types(obj):
            if isinstance(obj, defaultdict) or isinstance(obj, Counter):
                return dict(obj)
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            elif isinstance(obj, set):
                return list(obj)
            return obj

        converted_results = convert_types(all_results)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(converted_results, f, ensure_ascii=False, indent=2, default=str)

        print(f"分析结果已保存到: {output_file}")

    def run_analysis(self):
        """运行完整分析"""
        print("\n" + "=" * 60)
        print("VAST Challenge 2026 MC1 - 数据分析")
        print("=" * 60)
        print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        all_results = {}

        try:
            # 初始化会话
            self.init_session()

            # 加载数据
            rounds = self.load_data()

            # 问题1分析
            all_results["question1"] = self.analyze_question1(rounds)

            # 问题2分析
            all_results["question2"] = self.analyze_question2(rounds)

            # 问题3分析
            all_results["question3"] = self.analyze_question3(rounds)

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
    data_path = "C:/Users/83734/Desktop/opentrace/VAST_Challenge_2026_MC1/MC1_final_00.json"

    analyzer = MC1Analyzer(data_path)
    results = analyzer.run_analysis()

    return results


if __name__ == "__main__":
    main()
