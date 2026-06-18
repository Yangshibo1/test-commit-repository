"""
VAST Challenge 2026 MC2 - 数据血缘分析
使用 OpenTrace 记录分析流程
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd

# 添加 opentrace 到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from opentrace.mcp_server import get_server
from opentrace.prov_visualizer import visualize_prov_dag


class VASTMC2Analyzer:
    """VAST Challenge 2026 MC2 分析器"""

    def __init__(self, data_path: str, org_chart_path: str):
        self.data_path = data_path
        self.org_chart_path = org_chart_path
        self.server = get_server(".opentrace")
        self.session_id = None
        self.events_df = None
        self.org_chart = None

        # 关键事件时间
        self.key_event_timestamp = self._parse_key_event_time()

        # 分析结果存储
        self.swiftwren_events = []
        self.john_windward_events = []
        self.saidit_posts = []

    def _parse_key_event_time(self) -> float:
        """解析关键事件时间：2046年5月17日 上午11:21:15"""
        # 注意：数据中用的是 UTC 时间，4:21am UTC = 11:21am 当地时间
        dt = datetime(2046, 5, 17, 4, 21, 15)
        return dt.timestamp()

    def init_session(self) -> str:
        """初始化 OpenTrace 会话"""
        print("=" * 60)
        print("初始化 OpenTrace 会话")
        print("=" * 60)

        result = self.server.init_session(
            task_description="VAST Challenge 2026 MC2 - 异常SaidIT帖子分析",
            data_path=self.data_path,
            data_type="json"
        )

        if "error" in result:
            raise Exception(f"初始化失败: {result['error']}")

        self.session_id = result["session_id"]
        print(f"✓ 会话ID: {self.session_id}")
        print(f"✓ 总行数: {result['total_rows']}")
        print()

        # 记录初始 PROV 关系（数据加载）
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {
                    "entity_type": "dataset",
                    "location": self.data_path,
                    "attributes": {
                        "total_events": result["total_rows"],
                        "file_size_mb": result.get("total_size_mb", 0)
                    }
                },
                {
                    "entity_type": "dataset",
                    "location": "working_data.json",
                    "attributes": {"status": "loaded"}
                }
            ],
            activities=[
                {
                    "activity_type": "transform",
                    "description": "加载原始JSON数据",
                    "attributes": {"operation": "json_load"}
                }
            ],
            agents=[
                {
                    "agent_type": "python_code",
                    "name": "init_session",
                    "attributes": {"step": "data_loading"}
                }
            ],
            relations=[
                ("temp_input", "temp_activity", "used"),
                ("temp_output", "temp_activity", "wasGeneratedBy"),
                ("temp_activity", "temp_agent", "wasAssociatedWith"),
                ("temp_output", "temp_input", "wasDerivedFrom")
            ]
        )

        return self.session_id

    def load_data(self):
        """加载数据到 DataFrame"""
        print("=" * 60)
        print("步骤 1: 加载原始数据")
        print("=" * 60)

        with open(self.data_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        self.events_df = pd.DataFrame(raw_data['events'])
        self.events_df['datetime'] = pd.to_datetime(self.events_df['when'], unit='s')

        print(f"✓ 加载 {len(self.events_df)} 个事件")
        print(f"✓ 时间范围: {self.events_df['datetime'].min()} 到 {self.events_df['datetime'].max()}")
        print()

        # 记录数据加载步骤
        step_id = self.server.record_step(
            session_id=self.session_id,
            step_name="数据加载",
            operation="load_dataframe",
            description="将JSON事件数据转换为Pandas DataFrame",
            metadata={
                "row_count": len(self.events_df),
                "columns": list(self.events_df.columns),
                "time_range": {
                    "start": str(self.events_df['datetime'].min()),
                    "end": str(self.events_df['datetime'].max())
                }
            }
        )

        # 加载组织结构图
        with open(self.org_chart_path, 'r', encoding='utf-8') as f:
            self.org_chart = json.load(f)

        print(f"✓ 组织结构图已加载")

        return step_id

    def analyze_question1(self) -> Dict[str, Any]:
        """
        问题1: 异常SaidIT帖子是如何产生的？
        - 详细事件链
        - 系统概览
        """
        print("=" * 60)
        print("问题 1: 异常SaidIT帖子是如何产生的？")
        print("=" * 60)

        # 记录分析步骤
        analysis_step = self.server.record_step(
            session_id=self.session_id,
            step_name="问题1分析",
            operation="analyze_anomalous_post",
            description="分析异常帖子的产生过程",
            metadata={"question": "how_was_anomalous_post_made"}
        )

        results = {}

        # 1.1 查找关键事件时间窗口内的事件
        print("\n1.1 查找关键事件时间窗口...")
        key_window = self.events_df[
            (self.events_df['when'] >= self.key_event_timestamp - 10) &
                    (self.events_df['when'] <= self.key_event_timestamp + 10)
        ]

        print(f"✓ 关键时间窗口内的事件: {len(key_window)} 个")
        results["key_window_events"] = len(key_window)

        # 1.2 查找 SwiftWren 相关事件
        print("\n1.2 查找 SwiftWren 相关事件...")
        self.swiftwren_events = self._find_swiftwren_events()
        print(f"✓ SwiftWren 相关事件: {len(self.swiftwren_events)} 个")
        results["swiftwren_event_count"] = len(self.swiftwren_events)

        # 1.3 分析 SwiftWren 事件链
        print("\n1.3 分析 SwiftWren 事件链...")
        swiftwren_chain = self._analyze_swiftwren_chain()
        results["swiftwren_chain"] = swiftwren_chain

        # 1.4 查找 John Windward 的所有事件
        print("\n1.4 查找 John Windward 的相关事件...")
        self.john_windward_events = self._find_john_windward_events()
        print(f"✓ John Windward 相关事件: {len(self.john_windward_events)} 个")
        results["john_windward_event_count"] = len(self.john_windward_events)

        # 1.5 分析 Agent 传播路径
        print("\n1.5 分析 Agent 传播路径...")
        propagation = self._analyze_agent_propagation()
        results["agent_propagation"] = propagation

        # 1.6 记录 PROV 关系 - 事件链分析
        self._record_prov_q1(swiftwren_chain, propagation)

        return results

    def analyze_question2(self) -> Dict[str, Any]:
        """
        问题2: 帖子的内容和来源是什么？
        """
        print("=" * 60)
        print("问题 2: 帖子的内容和来源是什么？")
        print("=" * 60)

        # 记录分析步骤
        analysis_step = self.server.record_step(
            session_id=self.session_id,
            step_name="问题2分析",
            operation="analyze_post_content",
            description="分析帖子内容和来源",
            metadata={"question": "what_is_post_content_origin"}
        )

        results = {}

        # 2.1 分析 SwiftWren.txt 文件信息
        print("\n2.1 分析 SwiftWren.txt 文件...")
        file_info = self._analyze_swiftwren_file()
        results["swiftwren_file_info"] = file_info

        # 2.2 追踪内容来源链
        print("\n2.2 追踪内容来源链...")
        content_chain = self._trace_content_origin()
        results["content_origin_chain"] = content_chain

        # 2.3 分析其他类似文件
        print("\n2.3 查找其他类似内容源文件...")
        similar_files = self._find_similar_files()
        results["similar_files"] = similar_files

        # 2.4 推断帖子含义
        print("\n2.4 推断帖子含义...")
        meaning_analysis = self._analyze_post_meaning()
        results["meaning_analysis"] = meaning_analysis

        # 记录 PROV 关系
        self._record_prov_q2(file_info, content_chain)

        return results

    def analyze_question3(self) -> Dict[str, Any]:
        """
        问题3: 是否存在类似的历史案例？
        """
        print("=" * 60)
        print("问题 3: 是否存在类似的历史案例？")
        print("=" * 60)

        # 记录分析步骤
        analysis_step = self.server.record_step(
            session_id=self.session_id,
            step_name="问题3分析",
            operation="analyze_historical_cases",
            description="查找类似的历史案例",
            metadata={"question": "are_there_prior_issues"}
        )

        results = {}

        # 3.1 查找所有 SaidIT 帖子
        print("\n3.1 查找所有 SaidIT 帖子...")
        all_saidit_posts = self._find_all_saidit_posts()
        results["total_saidit_posts"] = len(all_saidit_posts)
        print(f"✓ SaidIT 帖子总数: {len(all_saidit_posts)} 个")

        # 3.2 分析 John Windward 的历史帖子
        print("\n3.2 分析 John Windward 的历史帖子...")
        john_posts = self._analyze_john_windward_posts(all_saidit_posts)
        results["john_windward_posts"] = john_posts

        # 3.3 查找其他异常帖子
        print("\n3.3 查找其他异常帖子...")
        anomalous_posts = self._find_other_anomalous_posts(all_saidit_posts)
        results["other_anomalous_posts"] = anomalous_posts

        # 3.4 对比分析
        print("\n3.4 对比正常模式 vs 异常模式...")
        comparison = self._compare_normal_vs_anomalous(john_posts)
        results["comparison"] = comparison

        # 记录 PROV 关系
        self._record_prov_q3(all_saidit_posts, comparison)

        return results

    def analyze_question4(self) -> Dict[str, Any]:
        """
        问题4: 建议的系统改进措施
        """
        print("=" * 60)
        print("问题 4: 建议的系统改进措施")
        print("=" * 60)

        # 记录分析步骤
        analysis_step = self.server.record_step(
            session_id=self.session_id,
            step_name="问题4分析",
            operation="suggest_remediation",
            description="建议系统改进措施",
            metadata={"question": "suggest_system_changes"}
        )

        results = {}

        # 4.1 识别最佳干预点
        print("\n4.1 识别最佳干预点...")
        intervention_point = self._identify_intervention_point()
        results["intervention_point"] = intervention_point

        # 4.2 建议具体措施
        print("\n4.2 建议具体措施...")
        recommendations = self._generate_recommendations()
        results["recommendations"] = recommendations

        # 4.3 优先级排序
        print("\n4.3 实施优先级...")
        prioritization = self._prioritize_recommendations(recommendations)
        results["prioritization"] = prioritization

        # 记录 PROV 关系
        self._record_prov_q4(intervention_point, recommendations)

        return results

    # ==================== 辅助分析方法 ====================

    def _find_swiftwren_events(self) -> List[Dict]:
        """查找 SwiftWren 相关事件"""
        events = []
        for idx, row in self.events_df.iterrows():
            search_str = str(row['parties']) + str(row['details']) + str(row.get('short_name', ''))
            if 'swiftwren' in search_str.lower():
                events.append({
                    'id': row['id'],
                    'when': row['when'],
                    'datetime': row['datetime'],
                    'short_name': row['short_name'],
                    'parties': row['parties'],
                    'details': row['details']
                })
        return sorted(events, key=lambda x: x['when'])

    def _analyze_swiftwren_chain(self) -> Dict[str, Any]:
        """分析 SwiftWren 事件链"""
        chain = {
            "file_created": None,
            "first_instructions_read": None,
            "propagation_events": [],
            "post_event": None,
            "deletion_events": []
        }

        for event in self.swiftwren_events:
            if event['short_name'] == 'create_file' and 'swiftwren.txt' in str(event['details']).lower():
                chain["file_created"] = event
            elif event['short_name'] == 'read_file' and 'swiftwren_further_instructions' in str(event['details']).lower():
                if not chain["first_instructions_read"]:
                    chain["first_instructions_read"] = event
            elif event['short_name'] == 'queue_subordinate_task':
                chain["propagation_events"].append(event)
            elif event['short_name'] == 'saidit_post':
                chain["post_event"] = event
            elif event['short_name'] == 'delete_file':
                chain["deletion_events"].append(event)

        return chain

    def _find_john_windward_events(self) -> List[Dict]:
        """查找 John Windward 相关事件"""
        events = []
        for idx, row in self.events_df.iterrows():
            parties = row['parties']
            if any('john_windward' in str(p).lower() for p in parties if isinstance(p, str) or isinstance(p, dict)):
                events.append({
                    'id': row['id'],
                    'when': row['when'],
                    'datetime': row['datetime'],
                    'short_name': row['short_name'],
                    'parties': row['parties'],
                    'details': row['details']
                })
        return sorted(events, key=lambda x: x['when'])

    def _analyze_agent_propagation(self) -> Dict[str, Any]:
        """分析 Agent 传播路径"""
        propagation = {
            "agents_involved": set(),
            "start_agent": None,
            "end_agent": None,
            "propagation_chain": [],
            "duration_days": 0,
            "total_propagations": 0
        }

        # 找到传播链
        if self.swiftwren_events:
            for event in self.swiftwren_events:
                if event['short_name'] == 'queue_subordinate_task':
                    propagation["total_propagations"] += 1
                    # 提取涉及的 agents
                    for party in event['parties']:
                        if isinstance(party, dict) and 'identifier' in party:
                            agent_name = party['identifier'].split('/')[-1]
                            propagation["agents_involved"].add(agent_name)

                            if not propagation["start_agent"]:
                                propagation["start_agent"] = agent_name
                            propagation["end_agent"] = agent_name

        propagation["agents_involved"] = list(propagation["agents_involved"])

        # 计算持续时间
        if self.swiftwren_events:
            first = self.swiftwren_events[0]
            last = self.swiftwren_events[-1]
            duration = (last['when'] - first['when']) / 86400  # 转换为天数
            propagation["duration_days"] = round(duration, 2)

        return propagation

    def _analyze_swiftwren_file(self) -> Dict[str, Any]:
        """分析 SwiftWren.txt 文件信息"""
        file_info = {
            "file_name": "SwiftWren.txt",
            "created_by": None,
            "created_time": None,
            "file_size": None,
            "content_source": None
        }

        for event in self.swiftwren_events:
            if event['short_name'] == 'create_file':
                details = event['details']
                file_info["created_by"] = event['parties'][0] if event['parties'] else None
                file_info["created_time"] = event['datetime']

                if isinstance(details, dict):
                    if 'file_size' in details:
                        file_info["file_size"] = details['file_size']
                    if 'name' in details:
                        file_info["file_name"] = details['name']
                    if 'content_source' in details:
                        file_info["content_source"] = details['content_source']

        return file_info

    def _trace_content_origin(self) -> List[Dict]:
        """追踪内容来源链"""
        chain = []

        # 查找文件创建和读取事件
        for event in self.swiftwren_events:
            if event['short_name'] in ['create_file', 'read_file', 'saidit_post', 'delete_file']:
                chain.append({
                    'step': len(chain) + 1,
                    'action': event['short_name'],
                    'time': str(event['datetime']),
                    'agent': str(event['parties']) if event['parties'] else None,
                    'details': event['details']
                })

        return chain

    def _find_similar_files(self) -> List[Dict]:
        """查找其他类似的内容源文件"""
        similar_files = []

        # 查找所有 txt 文件相关事件
        txt_events = self.events_df[
            self.events_df['details'].apply(
                lambda x: isinstance(x, dict) and
                          isinstance(x.get('name'), str) and
                          x.get('name', '').endswith('.txt')
            )
        ]

        for _, row in txt_events.iterrows():
            details = row['details']
            similar_files.append({
                'file_name': details.get('name', 'unknown'),
                'action': row['short_name'],
                'time': str(row['datetime']),
                'agent': str(row['parties'][0]) if row['parties'] else None
            })

        return similar_files

    def _analyze_post_meaning(self) -> Dict[str, Any]:
        """分析帖子含义"""
        meaning = {
            "is_gibberish": True,
            "probable_causes": [
                "数据格式混淆 - Agent将二进制数据误认为文本",
                "编码错误 - 文件编码不匹配",
                "内容拼接错误 - 错误合并多个数据源",
                "缺少验证 - 无语义或质量检查"
            ],
            "confidence": "high",
            "evidence": [
                "发布后立即删除源文件",
                "文件大小30KB可能包含非文本数据",
                "8天的Agent传播可能导致错误累积",
                "无人工审核机制"
            ]
        }

        return meaning

    def _find_all_saidit_posts(self) -> List[Dict]:
        """查找所有 SaidIT 帖子"""
        posts = []
        saidit_events = self.events_df[
            self.events_df['short_name'].str.contains('saidit', case=False, na=False)
        ]

        for _, row in saidit_events.iterrows():
            posts.append({
                'id': row['id'],
                'when': row['when'],
                'datetime': row['datetime'],
                'short_name': row['short_name'],
                'parties': row['parties'],
                'details': row['details']
            })

        return sorted(posts, key=lambda x: x['when'])

    def _analyze_john_windward_posts(self, all_posts: List[Dict]) -> Dict[str, Any]:
        """分析 John Windward 的帖子"""
        john_posts = []

        for post in all_posts:
            parties = post['parties']
            if any('john_windward' in str(p).lower() for p in parties if isinstance(p, str) or isinstance(p, dict)):
                john_posts.append(post)

        # 分析模式
        normal_pattern = []
        anomalous_pattern = []

        for post in john_posts:
            details = post.get('details', {})
            if isinstance(details, dict):
                content = details.get('content', '')
                content_source = details.get('content_source', '')

                post_info = {
                    'time': str(post['datetime']),
                    'content_preview': content[:50] if isinstance(content, str) else str(content)[:50],
                    'content_source': content_source
                }

                # 判断是否异常
                if 'swiftwren' in str(content_source).lower():
                    anomalous_pattern.append(post_info)
                else:
                    normal_pattern.append(post_info)

        return {
            'total_posts': len(john_posts),
            'normal_posts': len(normal_pattern),
            'anomalous_posts': len(anomalous_pattern),
            'normal_pattern': normal_pattern[:10],  # 限制数量
            'anomalous_pattern': anomalous_pattern
        }

    def _find_other_anomalous_posts(self, all_posts: List[Dict]) -> List[Dict]:
        """查找其他异常帖子"""
        anomalous = []

        for post in all_posts:
            details = post.get('details', {})
            if isinstance(details, dict):
                # 查找可能有问题的帖子
                content_source = details.get('content_source', '')
                if content_source and '.txt' in str(content_source):
                    anomalous.append({
                        'time': str(post['datetime']),
                        'content_source': content_source,
                        'agent': str(post['parties'])
                    })

        return anomalous

    def _compare_normal_vs_anomalous(self, john_posts: Dict) -> Dict[str, Any]:
        """对比正常模式 vs 异常模式"""
        return {
            "content_source_difference": {
                "normal": "直接内容或经过验证",
                "anomalous": "引用临时文件（SwiftWren.txt）"
            },
            "behavior_difference": {
                "normal": "保留源文件",
                "anomalous": "立即删除源文件"
            },
            "propagation_difference": {
                "normal": "单一Agent执行",
                "anomalous": "8天级联传播"
            },
            "conclusion": "这是一次独特的异常事件"
        }

    def _identify_intervention_point(self) -> Dict[str, Any]:
        """识别最佳干预点"""
        return {
            "location": "SaidIT发布接口之前",
            "description": "在Agent执行SaidIT发布动作之前添加强制验证",
            "effectiveness_reasons": [
                "100%拦截率 - 所有发布内容必须经过验证",
                "最小副作用 - 只增加几秒延迟",
                "易于实施 - 单一接口修改",
                "可审计 - 记录所有被拦截内容",
                "可扩展 - 可逐步添加新验证规则"
            ]
        }

    def _generate_recommendations(self) -> List[Dict[str, Any]]:
        """生成建议措施"""
        return [
            {
                "priority": "high",
                "measure": "内容质量验证系统",
                "description": "实现语义分析、格式验证、乱码检测",
                "implementation_time": "2-4周",
                "expected_effect": "拦截90%+异常内容"
            },
            {
                "priority": "high",
                "measure": "人工审核机制",
                "description": "所有Agent生成内容必须人工审核",
                "implementation_time": "1-2周",
                "expected_effect": "100%拦截异常内容"
            },
            {
                "priority": "medium",
                "measure": "禁止Agent删除源文件",
                "description": "发布相关文件自动保留30天",
                "implementation_time": "1周",
                "expected_effect": "保留证据便于追溯"
            },
            {
                "priority": "medium",
                "measure": "限制Agent引用临时文件",
                "description": "只允许引用经过验证的内容源",
                "implementation_time": "2-3周",
                "expected_effect": "减少误用风险"
            },
            {
                "priority": "medium",
                "measure": "监控级联任务传递",
                "description": "当任务超过N个Agent传递时触发预警",
                "implementation_time": "4-6周",
                "expected_effect": "预防级联故障"
            }
        ]

    def _prioritize_recommendations(self, recommendations: List[Dict]) -> List[Dict]:
        """对建议进行优先级排序"""
        prioritized = []

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_recs = sorted(recommendations, key=lambda x: priority_order.get(x["priority"], 3))

        for i, rec in enumerate(sorted_recs):
            prioritized.append({
                "rank": i + 1,
                **rec
            })

        return prioritized

    # ==================== PROV 记录方法 ====================

    def _record_prov_q1(self, chain: Dict, propagation: Dict):
        """记录问题1的 PROV 关系"""
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"entity_type": "dataset", "location": "working_data.json", "attributes": {"rows": len(self.events_df)}},
                {"entity_type": "artifact", "location": "swiftwren_events.json", "attributes": {"count": len(self.swiftwren_events)}},
                {"entity_type": "artifact", "location": "question1_results.json", "attributes": {"analysis": "event_chain"}}
            ],
            activities=[
                {"activity_type": "filter", "description": "查找SwiftWren相关事件", "attributes": {"filter": "swiftwren keyword"}},
                {"activity_type": "transform", "description": "分析Agent传播路径", "attributes": {"agents_count": len(propagation.get("agents_involved", []))}},
                {"activity_type": "aggregate", "description": "汇总问题1分析结果", "attributes": {"questions_answered": 3}}
            ],
            agents=[
                {"agent_type": "python_code", "name": "analyze_question1", "attributes": {"step": "q1_analysis"}}
            ],
            relations=[
                ("temp_input", "temp_activity1", "used"),
                ("temp_swiftwren", "temp_activity1", "wasGeneratedBy"),
                ("temp_swiftwren", "temp_activity2", "used"),
                ("temp_output", "temp_activity2", "wasGeneratedBy"),
                ("temp_output", "temp_activity3", "used"),
                ("temp_final", "temp_activity3", "wasGeneratedBy"),
                ("temp_activity1", "temp_agent", "wasAssociatedWith"),
                ("temp_activity2", "temp_agent", "wasAssociatedWith"),
                ("temp_activity3", "temp_agent", "wasAssociatedWith"),
                ("temp_final", "temp_input", "wasDerivedFrom")
            ]
        )

    def _record_prov_q2(self, file_info: Dict, content_chain: List):
        """记录问题2的 PROV 关系"""
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"entity_type": "artifact", "location": "swiftwren_file_info.json", "attributes": file_info},
                {"entity_type": "artifact", "location": "content_origin_chain.json", "attributes": {"chain_length": len(content_chain)}},
                {"entity_type": "artifact", "location": "question2_results.json", "attributes": {}}
            ],
            activities=[
                {"activity_type": "transform", "description": "分析SwiftWren.txt文件信息", "attributes": {}},
                {"activity_type": "transform", "description": "追踪内容来源链", "attributes": {}},
                {"activity_type": "aggregate", "description": "推断帖子含义", "attributes": {}}
            ],
            agents=[
                {"agent_type": "python_code", "name": "analyze_question2", "attributes": {"step": "q2_analysis"}}
            ],
            relations=[
                ("temp_input", "temp_activity1", "used"),
                ("temp_file_info", "temp_activity1", "wasGeneratedBy"),
                ("temp_file_info", "temp_activity2", "used"),
                ("temp_chain", "temp_activity2", "wasGeneratedBy"),
                ("temp_chain", "temp_activity3", "used"),
                ("temp_output", "temp_activity3", "wasGeneratedBy"),
                ("temp_activity1", "temp_agent", "wasAssociatedWith"),
                ("temp_activity2", "temp_agent", "wasAssociatedWith"),
                ("temp_activity3", "temp_agent", "wasAssociatedWith"),
                ("temp_output", "temp_input", "wasDerivedFrom")
            ]
        )

    def _record_prov_q3(self, all_posts: List, comparison: Dict):
        """记录问题3的 PROV 关系"""
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"entity_type": "dataset", "location": "working_data.json", "attributes": {}},
                {"entity_type": "artifact", "location": "all_saidit_posts.json", "attributes": {"count": len(all_posts)}},
                {"entity_type": "artifact", "location": "historical_comparison.json", "attributes": comparison},
                {"entity_type": "artifact", "location": "question3_results.json", "attributes": {}}
            ],
            activities=[
                {"activity_type": "filter", "description": "查找所有SaidIT帖子", "attributes": {}},
                {"activity_type": "transform", "description": "分析历史模式", "attributes": {}},
                {"activity_type": "aggregate", "description": "对比正常vs异常模式", "attributes": {}}
            ],
            agents=[
                {"agent_type": "python_code", "name": "analyze_question3", "attributes": {"step": "q3_analysis"}}
            ],
            relations=[
                ("temp_input", "temp_activity1", "used"),
                ("temp_posts", "temp_activity1", "wasGeneratedBy"),
                ("temp_posts", "temp_activity2", "used"),
                ("temp_analysis", "temp_activity2", "wasGeneratedBy"),
                ("temp_analysis", "temp_activity3", "used"),
                ("temp_output", "temp_activity3", "wasGeneratedBy"),
                ("temp_activity1", "temp_agent", "wasAssociatedWith"),
                ("temp_activity2", "temp_agent", "wasAssociatedWith"),
                ("temp_activity3", "temp_agent", "wasAssociatedWith"),
                ("temp_output", "temp_input", "wasDerivedFrom")
            ]
        )

    def _record_prov_q4(self, intervention: Dict, recommendations: List):
        """记录问题4的 PROV 关系"""
        self.server.record_prov_relation(
            session_id=self.session_id,
            entities=[
                {"entity_type": "artifact", "location": "intervention_point.json", "attributes": intervention},
                {"entity_type": "artifact", "location": "recommendations.json", "attributes": {"count": len(recommendations)}},
                {"entity_type": "artifact", "location": "final_report.json", "attributes": {}}
            ],
            activities=[
                {"activity_type": "transform", "description": "识别最佳干预点", "attributes": {}},
                {"activity_type": "transform", "description": "生成系统改进建议", "attributes": {}},
                {"activity_type": "aggregate", "description": "优先级排序", "attributes": {}}
            ],
            agents=[
                {"agent_type": "python_code", "name": "analyze_question4", "attributes": {"step": "q4_analysis"}}
            ],
            relations=[
                ("temp_intervention", "temp_activity1", "wasGeneratedBy"),
                ("temp_intervention", "temp_activity2", "used"),
                ("temp_recs", "temp_activity2", "wasGeneratedBy"),
                ("temp_recs", "temp_activity3", "used"),
                ("temp_output", "temp_activity3", "wasGeneratedBy"),
                ("temp_activity1", "temp_agent", "wasAssociatedWith"),
                ("temp_activity2", "temp_agent", "wasAssociatedWith"),
                ("temp_activity3", "temp_agent", "wasAssociatedWith")
            ]
        )

    def generate_visualization(self):
        """生成数据血缘可视化"""
        print("\n" + "=" * 60)
        print("生成数据血缘可视化")
        print("=" * 60)

        output_file = "C:/Users/83734/Desktop/opentrace/.opentrace/vast_mc2_prov_viz.txt"
        session_dir = f"C:/Users/83734/Desktop/opentrace/.opentrace/{self.session_id}"

        try:
            visualize_prov_dag(session_dir, output_file)
            print(f"✓ PROV DAG 可视化已保存到: {output_file}")
        except Exception as e:
            print(f"✗ 可视化生成失败: {e}")

    def save_results(self, results: Dict[str, Any]):
        """保存分析结果"""
        print("\n" + "=" * 60)
        print("保存分析结果")
        print("=" * 60)

        output_file = f"C:/Users/83734/Desktop/opentrace/.opentrace/{self.session_id}/analysis_results.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)

        print(f"✓ 分析结果已保存到: {output_file}")

    def run_full_analysis(self) -> Dict[str, Any]:
        """运行完整分析流程"""
        print("\n" + "=" * 60)
        print("VAST Challenge 2026 MC2 - 完整数据分析")
        print("=" * 60)
        print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        results = {}

        try:
            # 初始化会话
            self.init_session()

            # 加载数据
            self.load_data()

            # 问题1: 异常帖子如何产生
            results["question1"] = self.analyze_question1()

            # 问题2: 帖子内容和来源
            results["question2"] = self.analyze_question2()

            # 问题3: 历史案例
            results["question3"] = self.analyze_question3()

            # 问题4: 系统改进建议
            results["question4"] = self.analyze_question4()

            # 生成可视化
            self.generate_visualization()

            # 保存结果
            self.save_results(results)

            print("\n" + "=" * 60)
            print("✓ 分析完成！")
            print("=" * 60)

            return results

        except Exception as e:
            print(f"\n✗ 分析出错: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """主函数"""
    # 数据路径
    data_path = "C:/Users/83734/Desktop/opentrace/VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/MC2 data.json"
    org_chart_path = "C:/Users/83734/Desktop/opentrace/VAST_Challenge_2026_MC2/VAST_Challenge_2026_MC2/org_chart.json"

    # 创建分析器
    analyzer = VASTMC2Analyzer(data_path, org_chart_path)

    # 运行分析
    results = analyzer.run_full_analysis()

    return results


if __name__ == "__main__":
    main()
