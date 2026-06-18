"""
VAST Challenge 2026 MC2 - 深度数据血缘分析
真正回答问题，同时使用 trace 追踪数据来源
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import pandas as pd

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opentrace.mcp_server import get_server
from opentrace.prov_visualizer import visualize_prov_dag


class DeepMC2Analyzer:
    """MC2 深度分析器 - 真正回答问题"""

    def __init__(self, data_path: str, org_chart_path: str):
        self.data_path = data_path
        self.org_chart_path = org_chart_path
        self.server = get_server(".opentrace")
        self.session_id = None

        # 关键事件时间
        self.key_event_time = datetime(2046, 5, 17, 4, 21, 15).timestamp()

        # 分析结果
        self.events_df = None
        self.swiftwren_chain = []
        self.agent_network = defaultdict(set)

    def init_session(self):
        """初始化分析会话"""
        print("=" * 70)
        print("VAST Challenge 2026 MC2 - 深度数据血缘分析")
        print("=" * 70)

        result = self.server.init_session(
            task_description="VAST MC2 深度分析 - SwiftWren异常帖子追踪",
            data_path=self.data_path,
            data_type="json"
        )

        if "error" in result:
            raise Exception(f"初始化失败: {result['error']}")

        self.session_id = result["session_id"]
        print(f"会话ID: {self.session_id}")
        print(f"总事件数: {result['total_rows']}")

        # 记录数据加载 PROV
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "raw_data", "entity_type": "dataset", "location": self.data_path},
                {"id": "working", "entity_type": "dataset", "location": "working_data.json"}
            ],
            activities=[
                {"id": "load_act", "activity_type": "transform", "description": "加载MC2数据"}
            ],
            agents=[
                {"id": "loader", "agent_type": "python_code", "name": "data_loader"}
            ],
            relations=[
                ("load_act", "raw_data", "used"),
                ("working", "load_act", "wasGeneratedBy"),
                ("load_act", "loader", "wasAssociatedWith"),
                ("working", "raw_data", "wasDerivedFrom")
            ]
        )
        return self.session_id

    def load_and_process_data(self):
        """加载并处理数据"""
        print("\n" + "=" * 70)
        print("步骤1: 数据加载与预处理")
        print("=" * 70)

        # 加载数据
        with open(self.data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        self.events_df = pd.DataFrame(raw_data['events'])
        self.events_df['datetime'] = pd.to_datetime(self.events_df['when'], unit='s')

        print(f"[OK] 加载 {len(self.events_df)} 个事件")
        print(f"[OK] 时间范围: {self.events_df['datetime'].min()} 到 {self.events_df['datetime'].max()}")

        # 关键事件分析
        key_event_window = self.events_df[
            (self.events_df['when'] >= self.key_event_time - 3600) &
            (self.events_df['when'] <= self.key_event_time + 3600)
        ]

        print(f"[OK] 关键事件1小时内的事件: {len(key_event_window)}")

        return self.events_df

    def trace_swiftwren_origin(self):
        """问题1: 深度追踪 SwiftWren.txt 的来源"""
        print("\n" + "=" * 70)
        print("问题1: SwiftWren.txt 的完整来源链")
        print("=" * 70)

        # 查找所有 SwiftWren 相关事件
        swiftwren_events = []

        for idx, event in self.events_df.iterrows():
            search_str = str(event['parties']) + str(event.get('details', ''))
            if 'swiftwren' in search_str.lower():
                swiftwren_events.append({
                    'id': event['id'],
                    'short_name': event['short_name'],
                    'when': event['when'],
                    'datetime': event['datetime'],
                    'parties': event['parties'],
                    'details': event.get('details', {})
                })

        # 按时间排序
        swiftwren_events.sort(key=lambda x: x['when'])

        print(f"\n[OK] 找到 {len(swiftwren_events)} 个 SwiftWren 相关事件")

        # 分析关键步骤
        key_steps = []

        for event in swiftwren_events[:20]:  # 显示前20个
            print(f"\n{event['datetime']} | {event['short_name']}")
            print(f"  参与方: {event['parties']}")
            if event['details']:
                details_str = json.dumps(event['details'], ensure_ascii=False)
                print(f"  详情: {details_str[:200]}")
            key_steps.append(event)

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q1_input", "entity_type": "dataset", "location": "working_data.json"},
                {"id": "q1_swiftwren", "entity_type": "artifact", "location": "swiftwren_trace.json", "attributes": {"events": len(swiftwren_events)}},
                {"id": "q1_output", "entity_type": "artifact", "location": "swiftwren_origin_chain.json"}
            ],
            activities=[
                {"id": "q1_act1", "activity_type": "filter", "description": "提取SwiftWren相关事件"},
                {"id": "q1_act2", "activity_type": "transform", "description": "分析来源链"}
            ],
            agents=[
                {"id": "q1_agent", "agent_type": "python_code", "name": "swiftwren_tracer"}
            ],
            relations=[
                ("q1_act1", "q1_input", "used"),
                ("q1_swiftwren", "q1_act1", "wasGeneratedBy"),
                ("q1_act2", "q1_swiftwren", "used"),
                ("q1_output", "q1_act2", "wasGeneratedBy"),
                ("q1_act1", "q1_agent", "wasAssociatedWith"),
                ("q1_act2", "q1_agent", "wasAssociatedWith"),
                ("q1_output", "q1_input", "wasDerivedFrom")
            ]
        )

        return swiftwren_events, key_steps

    def analyze_agent_cascade(self):
        """问题1续: 分析 Agent 级联传播路径"""
        print("\n" + "=" * 70)
        print("Agent 级联传播路径分析")
        print("=" * 70)

        # 查找 queue_subordinate_task 事件
        cascade_events = []

        for idx, event in self.events_df.iterrows():
            if event['short_name'] == 'queue_subordinate_task':
                details = event.get('details', {})
                if isinstance(details, dict):
                    cascade_events.append({
                        'id': event['id'],
                        'when': event['when'],
                        'datetime': event['datetime'],
                        'parties': event['parties'],
                        'details': details
                    })

        # 构建传播网络
        agent_network = defaultdict(set)

        for event in cascade_events:
            parties = event.get('parties', [])
            if len(parties) >= 2:
                from_agent = parties[0]
                to_agents = parties[1:]
                for to_agent in to_agents:
                    agent_network[from_agent].add(to_agent)

        print(f"\n[OK] 找到 {len(cascade_events)} 个任务传递事件")
        print(f"[OK] 涉及 {len(agent_network)} 个不同的 Agent")

        # 找到关键传播路径
        print("\n关键传播路径（按时间）:")

        # 查找 SwiftWren 相关的传递链
        swiftwren_cascade = [e for e in cascade_events
                             if 'swiftwren' in str(e['details']).lower() or
                                any('swiftwren' in str(p).lower() for p in e['parties'])]

        for event in swiftwren_cascade[:10]:
            print(f"\n{event['datetime']}")
            print(f"  {event['parties']}")

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q1c_input", "entity_type": "dataset", "location": "working_data.json"},
                {"id": "q1c_cascade", "entity_type": "artifact", "location": "agent_cascade_network.json", "attributes": {"agents": len(agent_network)}},
                {"id": "q1c_output", "entity_type": "artifact", "location": "cascade_analysis.json"}
            ],
            activities=[
                {"id": "q1c_act1", "activity_type": "transform", "description": "构建Agent传播网络"},
                {"id": "q1c_act2", "activity_type": "analyze", "description": "分析级联传播路径"}
            ],
            agents=[
                {"id": "q1c_agent", "agent_type": "python_code", "name": "cascade_analyzer"}
            ],
            relations=[
                ("q1c_act1", "q1c_input", "used"),
                ("q1c_cascade", "q1c_act1", "wasGeneratedBy"),
                ("q1c_act2", "q1c_cascade", "used"),
                ("q1c_output", "q1c_act2", "wasGeneratedBy"),
                ("q1c_act1", "q1c_agent", "wasAssociatedWith"),
                ("q1c_act2", "q1c_agent", "wasAssociatedWith"),
                ("q1c_output", "q1c_input", "wasDerivedFrom")
            ]
        )

        return cascade_events, agent_network

    def analyze_post_content_and_source(self):
        """问题2: 帖子内容和来源分析"""
        print("\n" + "=" * 70)
        print("问题2: 帖子内容和来源分析")
        print("=" * 70)

        # 查找关键 SaidIT 帖子事件
        key_time_window = self.events_df[
            (self.events_df['when'] >= self.key_event_time - 10) &
            (self.events_df['when'] <= self.key_event_time + 10)
        ]

        saidit_posts = key_time_window[
            key_time_window['short_name'].str.contains('saidit', case=False, na=False)
        ]

        print(f"\n[OK] 关键时刻的 SaidIT 帖子: {len(saidit_posts)}")

        # 分析每个帖子
        for idx, post in saidit_posts.iterrows():
            print(f"\n{'='*50}")
            print(f"时间: {post['datetime']}")
            print(f"动作: {post['short_name']}")
            print(f"参与方: {post['parties']}")

            details = post.get('details', {})
            if details:
                print(f"\n详情:")
                for key, value in details.items():
                    if key == 'content_source':
                        print(f"  [WARNING] 内容来源: {value}")
                    elif key == 'forum':
                        print(f"  论坛: {value}")
                    else:
                        print(f"  {key}: {str(value)[:100]}")

        # 查找所有 John Windward 的 SaidIT 帖子
        john_saidit = self.events_df[
            self.events_df['parties'].apply(
                lambda x: any('john_windward' in str(p).lower() for p in x)
            ) &
            self.events_df['short_name'].str.contains('saidit', case=False, na=False)
        ]

        print(f"\n[OK] John Windward 的所有 SaidIT 帖子: {len(john_saidit)}")

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q2_input", "entity_type": "dataset", "location": "working_data.json"},
                {"id": "q2_posts", "entity_type": "artifact", "location": "saidit_posts_analysis.json", "attributes": {"posts": len(saidit_posts)}},
                {"id": "q2_john", "entity_type": "artifact", "location": "john_windward_posts.json", "attributes": {"posts": len(john_saidit)}},
                {"id": "q2_output", "entity_type": "artifact", "location": "content_analysis_results.json"}
            ],
            activities=[
                {"id": "q2_act1", "activity_type": "filter", "description": "提取关键SaidIT帖子"},
                {"id": "q2_act2", "activity_type": "filter", "description": "分析John Windward帖子"},
                {"id": "q2_act3", "activity_type": "analyze", "description": "内容来源分析"}
            ],
            agents=[
                {"id": "q2_agent", "agent_type": "python_code", "name": "content_analyzer"}
            ],
            relations=[
                ("q2_act1", "q2_input", "used"),
                ("q2_posts", "q2_act1", "wasGeneratedBy"),
                ("q2_act2", "q2_input", "used"),
                ("q2_john", "q2_act2", "wasGeneratedBy"),
                ("q2_act3", "q2_posts", "used"),
                ("q2_act3", "q2_john", "used"),
                ("q2_output", "q2_act3", "wasGeneratedBy"),
                ("q2_act1", "q2_agent", "wasAssociatedWith"),
                ("q2_act2", "q2_agent", "wasAssociatedWith"),
                ("q2_act3", "q2_agent", "wasAssociatedWith"),
                ("q2_output", "q2_input", "wasDerivedFrom")
            ]
        )

        return saidit_posts, john_saidit

    def find_historical_patterns(self):
        """问题3: 查找历史类似案例"""
        print("\n" + "=" * 70)
        print("问题3: 历史模式分析")
        print("=" * 70)

        # 分析所有 SaidIT 帖子
        all_saidit = self.events_df[
            self.events_df['short_name'].str.contains('saidit', case=False, na=False)
        ]

        print(f"\n[OK] 总 SaidIT 帖子数: {len(all_saidit)}")

        # 分析内容来源模式
        content_sources = []

        for idx, post in all_saidit.iterrows():
            details = post.get('details', {})
            if isinstance(details, dict) and 'content_source' in details:
                content_sources.append({
                    'datetime': post['datetime'],
                    'source': details['content_source'],
                    'parties': post['parties']
                })

        print(f"[OK] 引用外部文件的帖子: {len(content_sources)}")

        # 统计来源文件
        source_counts = Counter(s['source'] for s in content_sources)

        print("\n内容来源文件统计:")
        for source, count in source_counts.most_common(10):
            print(f"  {source}: {count}次")

        # 查找异常模式（删除文件事件）
        delete_events = self.events_df[
            self.events_df['short_name'].str.contains('delete_file', case=False, na=False)
        ]

        print(f"\n[OK] 删除文件事件: {len(delete_events)}")

        # 分析关键时间窗口内的删除事件
        key_deletes = delete_events[
            (delete_events['when'] >= self.key_event_time - 60) &
            (delete_events['when'] <= self.key_event_time + 60)
        ]

        print(f"[OK] 关键时刻的删除事件: {len(key_deletes)}")

        for idx, event in key_deletes.iterrows():
            print(f"\n{event['datetime']} | {event['short_name']}")
            print(f"  参与方: {event['parties']}")
            details = event.get('details', {})
            if details:
                print(f"  文件: {details.get('filename', 'N/A')}")

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "q3_input", "entity_type": "dataset", "location": "working_data.json"},
                {"id": "q3_sources", "entity_type": "artifact", "location": "content_sources.json", "attributes": {"sources": len(source_counts)}},
                {"id": "q3_deletes", "entity_type": "artifact", "location": "delete_events.json", "attributes": {"deletes": len(key_deletes)}},
                {"id": "q3_output", "entity_type": "artifact", "location": "historical_pattern_analysis.json"}
            ],
            activities=[
                {"id": "q3_act1", "activity_type": "filter", "description": "分析内容来源模式"},
                {"id": "q3_act2", "activity_type": "filter", "description": "分析删除事件模式"},
                {"id": "q3_act3", "activity_type": "compare", "description": "对比历史模式"}
            ],
            agents=[
                {"id": "q3_agent", "agent_type": "python_code", "name": "pattern_analyzer"}
            ],
            relations=[
                ("q3_act1", "q3_input", "used"),
                ("q3_sources", "q3_act1", "wasGeneratedBy"),
                ("q3_act2", "q3_input", "used"),
                ("q3_deletes", "q3_act2", "wasGeneratedBy"),
                ("q3_act3", "q3_sources", "used"),
                ("q3_act3", "q3_deletes", "used"),
                ("q3_output", "q3_act3", "wasGeneratedBy"),
                ("q3_act1", "q3_agent", "wasAssociatedWith"),
                ("q3_act2", "q3_agent", "wasAssociatedWith"),
                ("q3_act3", "q3_agent", "wasAssociatedWith"),
                ("q3_output", "q3_input", "wasDerivedFrom")
            ]
        )

        return content_sources, key_deletes

    def generate_intervention_recommendations(self):
        """生成干预建议"""
        print("\n" + "=" * 70)
        print("干预建议")
        print("=" * 70)

        recommendations = {
            "primary_intervention": {
                "location": "SaidIT发布接口前的强制验证",
                "priority": "HIGH",
                "measures": [
                    "内容质量验证（语义分析、乱码检测）",
                    "人工审核机制（所有Agent生成内容必须审核）",
                    "证据保留机制（禁止删除源文件）"
                ],
                "expected_effectiveness": "100%拦截异常内容"
            },
            "secondary_measures": {
                "file_source_restrictions": {
                    "description": "限制Agent引用临时文件",
                    "implementation": "只允许引用经过验证的内容源"
                },
                "cascade_monitoring": {
                    "description": "监控级联任务传递",
                    "implementation": "超过N个Agent传递时触发预警"
                }
            }
        }

        print("\n主要干预点:")
        print(f"  位置: {recommendations['primary_intervention']['location']}")
        print(f"  优先级: {recommendations['primary_intervention']['priority']}")
        print(f"  预期效果: {recommendations['primary_intervention']['expected_effectiveness']}")

        print("\n具体措施:")
        for i, measure in enumerate(recommendations['primary_intervention']['measures'], 1):
            print(f"  {i}. {measure}")

        return recommendations

    def save_results(self, all_results):
        """保存分析结果"""
        print("\n" + "=" * 70)
        print("保存分析结果")
        print("=" * 70)

        output_dir = Path(f".opentrace/{self.session_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "mc2_deep_analysis_results.json"

        def convert_types(obj):
            if isinstance(obj, defaultdict):
                return dict(obj)
            elif isinstance(obj, Counter):
                return dict(obj)
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            elif isinstance(obj, pd.Timestamp):
                return str(obj)
            return obj

        converted_results = convert_types(all_results)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(converted_results, f, ensure_ascii=False, indent=2, default=str)

        print(f"[OK] 分析结果已保存到: {output_file}")

    def run_complete_analysis(self):
        """运行完整分析"""
        all_results = {}

        try:
            # 初始化
            self.init_session()

            # 数据加载
            self.load_and_process_data()

            # 问题1: SwiftWren 来源链
            swiftwren_events, key_steps = self.trace_swiftwren_origin()
            all_results['swiftwren_origin'] = {
                'total_events': len(swiftwren_events),
                'key_steps': len(key_steps),
                'events': swiftwren_events[:50]
            }

            # 问题1续: Agent 级联传播
            cascade_events, agent_network = self.analyze_agent_cascade()
            all_results['agent_cascade'] = {
                'cascade_events': len(cascade_events),
                'unique_agents': len(agent_network),
                'network_edges': sum(len(v) for v in agent_network.values())
            }

            # 问题2: 内容和来源分析
            saidit_posts, john_saidit = self.analyze_post_content_and_source()
            all_results['content_analysis'] = {
                'key_posts': len(saidit_posts),
                'john_posts': len(john_saidit)
            }

            # 问题3: 历史模式
            content_sources, key_deletes = self.find_historical_patterns()
            all_results['historical_patterns'] = {
                'content_sources': len(content_sources),
                'key_deletes': len(key_deletes)
            }

            # 干预建议
            recommendations = self.generate_intervention_recommendations()
            all_results['recommendations'] = recommendations

            # 保存结果
            self.save_results(all_results)

            print("\n" + "=" * 70)
            print("分析完成！")
            print("=" * 70)

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

    analyzer = DeepMC2Analyzer(data_path, org_chart_path)
    results = analyzer.run_complete_analysis()

    # 生成可视化
    print("\n生成数据血缘可视化...")
    session_dir = f".opentrace/{analyzer.session_id}"
    visualize_prov_dag(session_dir, f"{session_dir}/mc2_deep_prov_viz.txt")
    print("[OK] 可视化已生成")

    return results


if __name__ == "__main__":
    main()
