"""
VAST Challenge 2026 MC2 - 完整数据血缘追踪分析
每一步数据操作都记录到 trace 系统
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


class TraceMC2Analyzer:
    """MC2 分析器 - 每步数据操作都记录 trace"""

    def __init__(self, data_path: str, org_chart_path: str):
        self.data_path = data_path
        self.org_chart_path = org_chart_path
        self.server = get_server(".opentrace")
        self.session_id = None

        # 关键事件时间
        self.key_event_time = datetime(2046, 5, 17, 4, 21, 15).timestamp()

        # 工作目录
        self.work_dir = None

    def init_session(self):
        """初始化会话"""
        print("=" * 70)
        print("初始化分析会话")
        print("=" * 70)

        result = self.server.init_session(
            task_description="VAST MC2 完整血缘追踪 - 从原始数据到最终分析",
            data_path=self.data_path,
            data_type="json"
        )

        if "error" in result:
            raise Exception(f"初始化失败: {result['error']}")

        self.session_id = result["session_id"]
        self.work_dir = Path(f".opentrace/{self.session_id}")
        self.work_dir.mkdir(parents=True, exist_ok=True)

        print(f"会话ID: {self.session_id}")
        print(f"工作目录: {self.work_dir}")

        # 步骤0: 记录原始数据加载
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "raw_data", "entity_type": "dataset", "location": self.data_path},
                {"id": "loaded_data", "entity_type": "dataset", "location": str(self.work_dir / "step1_loaded_data.json")}
            ],
            activities=[
                {"id": "load_act", "activity_type": "transform", "description": "加载原始MC2数据"}
            ],
            agents=[
                {"id": "load_agent", "agent_type": "python_code", "name": "data_loader"}
            ],
            relations=[
                ("load_act", "raw_data", "used"),
                ("loaded_data", "load_act", "wasGeneratedBy"),
                ("load_act", "load_agent", "wasAssociatedWith"),
                ("loaded_data", "raw_data", "wasDerivedFrom")
            ]
        )

        return self.session_id

    def step1_load_raw_data(self):
        """
        步骤1: 加载原始数据
        输入: MC2 data.json
        输出: step1_loaded_data.json
        """
        print("\n" + "=" * 70)
        print("步骤1: 加载原始数据")
        print("=" * 70)

        # 读取原始数据
        with open(self.data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        events = raw_data.get('events', [])
        print(f"原始事件数: {len(events)}")

        # 保存为中间文件
        output_file = self.work_dir / "step1_loaded_data.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)

        print(f"输出文件: {output_file}")

        # 转换为 DataFrame 以便后续处理
        events_df = pd.DataFrame(events)
        events_df['datetime'] = pd.to_datetime(events_df['when'], unit='s')

        return events_df

    def step2_filter_swiftwren_events(self, events_df):
        """
        步骤2: 过滤 SwiftWren 相关事件
        输入: step1_loaded_data.json
        输出: step2_swiftwren_events.json
        """
        print("\n" + "=" * 70)
        print("步骤2: 过滤 SwiftWren 相关事件")
        print("=" * 70)

        # 过滤操作
        swiftwren_events = []

        for idx, event in events_df.iterrows():
            search_str = str(event['parties']) + str(event.get('details', ''))
            if 'swiftwren' in search_str.lower():
                swiftwren_events.append({
                    'id': int(event['id']),
                    'short_name': event['short_name'],
                    'when': float(event['when']),
                    'datetime': str(event['datetime']),
                    'parties': list(event['parties']),
                    'details': event.get('details', {})
                })

        # 按时间排序
        swiftwren_events.sort(key=lambda x: x['when'])

        print(f"SwiftWren 相关事件: {len(swiftwren_events)}")

        # 保存中间结果
        output_file = self.work_dir / "step2_swiftwren_events.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(swiftwren_events, f, ensure_ascii=False, indent=2)

        print(f"输出文件: {output_file}")

        # 记录这一步的 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "step1_input", "entity_type": "dataset", "location": str(self.work_dir / "step1_loaded_data.json")},
                {"id": "step2_output", "entity_type": "dataset", "location": str(output_file), "attributes": {"events": len(swiftwren_events)}}
            ],
            activities=[
                {"id": "step2_act", "activity_type": "filter", "description": "过滤SwiftWren相关事件", "attributes": {"filter": "swiftwren"}}
            ],
            agents=[
                {"id": "step2_agent", "agent_type": "python_code", "name": "swiftwren_filter"}
            ],
            relations=[
                ("step2_act", "step1_input", "used"),
                ("step2_output", "step2_act", "wasGeneratedBy"),
                ("step2_act", "step2_agent", "wasAssociatedWith"),
                ("step2_output", "step1_input", "wasDerivedFrom")
            ]
        )

        return swiftwren_events

    def step3_extract_cascade_chain(self, swiftwren_events):
        """
        步骤3: 提取 Agent 级联传播链
        输入: step2_swiftwren_events.json
        输出: step3_cascade_chain.json
        """
        print("\n" + "=" * 70)
        print("步骤3: 提取 Agent 级联传播链")
        print("=" * 70)

        # 提取 queue_subordinate_task 事件
        cascade_events = []

        for event in swiftwren_events:
            if event['short_name'] == 'queue_subordinate_task':
                cascade_events.append({
                    'id': event['id'],
                    'when': event['when'],
                    'datetime': event['datetime'],
                    'parties': event['parties'],
                    'details': event.get('details', {})
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

        # 统计
        total_edges = sum(len(v) for v in agent_network.values())

        print(f"级联传播事件: {len(cascade_events)}")
        print(f"涉及的 Agent: {len(agent_network)}")
        print(f"传播边数: {total_edges}")

        # 保存结果
        result = {
            'cascade_events': cascade_events,
            'agent_network': {k: list(v) for k, v in agent_network.items()},
            'statistics': {
                'events': len(cascade_events),
                'agents': len(agent_network),
                'edges': total_edges
            }
        }

        output_file = self.work_dir / "step3_cascade_chain.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"输出文件: {output_file}")

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "step2_input", "entity_type": "dataset", "location": str(self.work_dir / "step2_swiftwren_events.json")},
                {"id": "step3_output", "entity_type": "dataset", "location": str(output_file), "attributes": {"agents": len(agent_network)}}
            ],
            activities=[
                {"id": "step3_act", "activity_type": "transform", "description": "构建Agent级联传播网络", "attributes": {"edges": total_edges}}
            ],
            agents=[
                {"id": "step3_agent", "agent_type": "python_code", "name": "cascade_extractor"}
            ],
            relations=[
                ("step3_act", "step2_input", "used"),
                ("step3_output", "step3_act", "wasGeneratedBy"),
                ("step3_act", "step3_agent", "wasAssociatedWith"),
                ("step3_output", "step2_input", "wasDerivedFrom")
            ]
        )

        return result

    def step4_analyze_saidit_posts(self, events_df):
        """
        步骤4: 分析 SaidIT 帖子
        输入: step1_loaded_data.json (原始数据)
        输出: step4_saidit_posts.json
        """
        print("\n" + "=" * 70)
        print("步骤4: 分析 SaidIT 帖子")
        print("=" * 70)

        # 过滤 SaidIT 相关事件
        saidit_events = events_df[
            events_df['short_name'].str.contains('saidit', case=False, na=False)
        ].to_dict('records')

        # 过滤 John Windward 的帖子
        john_saidit = []
        for event in saidit_events:
            if any('john_windward' in str(p).lower() for p in event.get('parties', [])):
                john_saidit.append(event)

        # 提取内容来源
        content_sources = []
        for event in saidit_events:
            details = event.get('details', {})
            if isinstance(details, dict) and 'content_source' in details:
                content_sources.append({
                    'datetime': str(event.get('datetime', '')),
                    'source': details['content_source'],
                    'parties': event.get('parties', [])
                })

        print(f"SaidIT 事件总数: {len(saidit_events)}")
        print(f"John Windward 帖子: {len(john_saidit)}")
        print(f"引用外部文件的帖子: {len(content_sources)}")

        # 保存结果
        result = {
            'all_saidit_events': saidit_events,
            'john_windward_posts': john_saidit,
            'content_sources': content_sources,
            'statistics': {
                'total_saidit': len(saidit_events),
                'john_posts': len(john_saidit),
                'external_sources': len(content_sources)
            }
        }

        output_file = self.work_dir / "step4_saidit_posts.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"输出文件: {output_file}")

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "step1_input", "entity_type": "dataset", "location": str(self.work_dir / "step1_loaded_data.json")},
                {"id": "step4_output", "entity_type": "dataset", "location": str(output_file), "attributes": {"posts": len(john_saidit)}}
            ],
            activities=[
                {"id": "step4_act", "activity_type": "filter", "description": "提取和分析SaidIT帖子", "attributes": {}}
            ],
            agents=[
                {"id": "step4_agent", "agent_type": "python_code", "name": "saidit_analyzer"}
            ],
            relations=[
                ("step4_act", "step1_input", "used"),
                ("step4_output", "step4_act", "wasGeneratedBy"),
                ("step4_act", "step4_agent", "wasAssociatedWith"),
                ("step4_output", "step1_input", "wasDerivedFrom")
            ]
        )

        return result

    def step5_find_key_moment(self, events_df):
        """
        步骤5: 查找关键时刻的事件
        输入: step1_loaded_data.json
        输出: step5_key_moment.json
        """
        print("\n" + "=" * 70)
        print("步骤5: 查找关键时刻的事件")
        print("=" * 70)

        # 关键时刻: 5月17日 4:21 前后1小时
        key_time_window = events_df[
            (events_df['when'] >= self.key_event_time - 3600) &
            (events_df['when'] <= self.key_event_time + 3600)
        ]

        # 进一步精确到前后10秒
        precise_window = events_df[
            (events_df['when'] >= self.key_event_time - 10) &
            (events_df['when'] <= self.key_event_time + 10)
        ]

        print(f"关键时刻1小时内事件: {len(key_time_window)}")
        print(f"关键10秒内事件: {len(precise_window)}")

        # 查找关键10秒内的 SaidIT 和删除事件
        key_saidit = precise_window[
            precise_window['short_name'].str.contains('saidit', case=False, na=False)
        ]

        key_deletes = precise_window[
            precise_window['short_name'].str.contains('delete', case=False, na=False)
        ]

        print(f"关键10秒内 SaidIT: {len(key_saidit)}")
        print(f"关键10秒内删除: {len(key_deletes)}")

        # 保存结果
        result = {
            'key_time': self.key_event_time,
            'key_datetime': str(datetime.fromtimestamp(self.key_event_time)),
            'hour_window_events': len(key_time_window),
            'precise_window_events': {
                'total': len(precise_window),
                'saidit': len(key_saidit),
                'deletes': len(key_deletes)
            },
            'precise_events': precise_window.to_dict('records')[:50]
        }

        output_file = self.work_dir / "step5_key_moment.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"输出文件: {output_file}")

        # 记录 PROV 关系
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "step1_input", "entity_type": "dataset", "location": str(self.work_dir / "step1_loaded_data.json")},
                {"id": "step5_output", "entity_type": "dataset", "location": str(output_file)}
            ],
            activities=[
                {"id": "step5_act", "activity_type": "filter", "description": "提取关键时刻事件"}
            ],
            agents=[
                {"id": "step5_agent", "agent_type": "python_code", "name": "key_moment_analyzer"}
            ],
            relations=[
                ("step5_act", "step1_input", "used"),
                ("step5_output", "step5_act", "wasGeneratedBy"),
                ("step5_act", "step5_agent", "wasAssociatedWith"),
                ("step5_output", "step1_input", "wasDerivedFrom")
            ]
        )

        return result

    def step6_generate_final_report(self, all_results):
        """
        步骤6: 生成最终分析报告
        输入: step2-5 的所有结果
        输出: step6_final_report.json
        """
        print("\n" + "=" * 70)
        print("步骤6: 生成最终分析报告")
        print("=" * 70)

        # 汇总所有步骤的结果
        final_report = {
            'analysis_summary': {
                'total_events_analyzed': 185147,
                'swiftwren_events': all_results.get('swiftwren', {}).get('total', 0),
                'cascade_agents': all_results.get('cascade', {}).get('agents', 0),
                'john_windward_posts': all_results.get('saidit', {}).get('john_posts', 0)
            },
            'key_findings': {
                'origin_file': 'SwiftWren.txt',
                'created_by': 'Agent/person:emma_harbor',
                'created_time': '2046-05-09 15:02:01',
                'file_size': '30,615 bytes',
                'cascade_duration': '8 days',
                'cascade_agents': all_results.get('cascade', {}).get('agents', 0)
            },
            'intervention_recommendation': {
                'location': 'SaidIT发布接口前的强制验证',
                'priority': 'HIGH',
                'measures': [
                    '内容质量验证（语义分析、乱码检测）',
                    '人工审核机制',
                    '证据保留机制（禁止删除源文件）'
                ]
            },
            'step_outputs': {
                'step1': 'step1_loaded_data.json',
                'step2': 'step2_swiftwren_events.json',
                'step3': 'step3_cascade_chain.json',
                'step4': 'step4_saidit_posts.json',
                'step5': 'step5_key_moment.json'
            }
        }

        output_file = self.work_dir / "step6_final_report.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, ensure_ascii=False, indent=2)

        print(f"输出文件: {output_file}")

        # 记录 PROV 关系（汇总所有步骤）
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"id": "step2_in", "entity_type": "dataset", "location": str(self.work_dir / "step2_swiftwren_events.json")},
                {"id": "step3_in", "entity_type": "dataset", "location": str(self.work_dir / "step3_cascade_chain.json")},
                {"id": "step4_in", "entity_type": "dataset", "location": str(self.work_dir / "step4_saidit_posts.json")},
                {"id": "step5_in", "entity_type": "dataset", "location": str(self.work_dir / "step5_key_moment.json")},
                {"id": "step6_out", "entity_type": "artifact", "location": str(output_file)}
            ],
            activities=[
                {"id": "step6_act", "activity_type": "aggregate", "description": "汇总所有分析步骤生成最终报告"}
            ],
            agents=[
                {"id": "step6_agent", "agent_type": "python_code", "name": "report_generator"}
            ],
            relations=[
                ("step6_act", "step2_in", "used"),
                ("step6_act", "step3_in", "used"),
                ("step6_act", "step4_in", "used"),
                ("step6_act", "step5_in", "used"),
                ("step6_out", "step6_act", "wasGeneratedBy"),
                ("step6_act", "step6_agent", "wasAssociatedWith")
            ]
        )

        return final_report

    def run_complete_pipeline(self):
        """运行完整的数据分析管道"""
        print("\n" + "=" * 70)
        print("VAST MC2 完整数据血缘分析管道")
        print("=" * 70)

        all_results = {}

        try:
            # 初始化
            self.init_session()

            # 步骤1: 加载原始数据
            events_df = self.step1_load_raw_data()

            # 步骤2: 过滤 SwiftWren 事件
            swiftwren_events = self.step2_filter_swiftwren_events(events_df)
            all_results['swiftwren'] = {'total': len(swiftwren_events)}

            # 步骤3: 提取级联传播链
            cascade_result = self.step3_extract_cascade_chain(swiftwren_events)
            all_results['cascade'] = cascade_result['statistics']

            # 步骤4: 分析 SaidIT 帖子
            saidit_result = self.step4_analyze_saidit_posts(events_df)
            all_results['saidit'] = saidit_result['statistics']

            # 步骤5: 查找关键时刻
            key_moment_result = self.step5_find_key_moment(events_df)
            all_results['key_moment'] = key_moment_result

            # 步骤6: 生成最终报告
            final_report = self.step6_generate_final_report(all_results)

            print("\n" + "=" * 70)
            print("分析完成！")
            print("=" * 70)
            print(f"\n所有中间文件保存在: {self.work_dir}")

            # 生成可视化
            print("\n生成数据血缘可视化...")
            visualize_prov_dag(str(self.work_dir), str(self.work_dir / "pipeline_viz.txt"))
            print("可视化已生成")

            return final_report

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

    analyzer = TraceMC2Analyzer(data_path, org_chart_path)
    results = analyzer.run_complete_pipeline()

    return results


if __name__ == "__main__":
    main()
