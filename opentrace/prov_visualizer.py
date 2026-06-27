"""
PROV DAG 可视化工具

生成 PROV DAG 的可视化图表
"""

import json
from pathlib import Path
from typing import Dict, List, Any


class ProvDAGVisualizer:
    """PROV DAG 可视化器"""

    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)

        # 加载 DAG 数据
        self.dag_data = self._load_prov_dag()
        self.nodes = self._load_prov_nodes()
        self.edges = self._load_prov_edges()

    def _load_prov_dag(self) -> Dict:
        """加载 DAG 元数据"""
        dag_file = self.session_dir / "prov_dag.json"
        if dag_file.exists():
            return json.loads(dag_file.read_text(encoding='utf-8'))
        return {}

    def _load_prov_nodes(self) -> Dict:
        """加载节点数据"""
        nodes_file = self.session_dir / "prov_nodes.json"
        if nodes_file.exists():
            return json.loads(nodes_file.read_text(encoding='utf-8')).get('nodes', {})
        return {}

    def _load_prov_edges(self) -> List:
        """加载边数据"""
        edges_file = self.session_dir / "prov_edges.json"
        if edges_file.exists():
            return json.loads(edges_file.read_text(encoding='utf-8')).get('edges', [])
        return []

    def visualize_text(self) -> str:
        """生成文本格式的 DAG 可视化

        Returns:
            文本形式的 DAG 图
        """
        output = []
        output.append("=" * 70)
        output.append("PROV DAG 可视化")
        output.append("=" * 70)

        # 按类型分组节点
        entities = [n for n in self.nodes.values() if n.get('type') == 'entity']
        activities = [n for n in self.nodes.values() if n.get('type') == 'activity']
        agents = [n for n in self.nodes.values() if n.get('type') == 'agent']

        output.append(f"\n节点统计:")
        output.append(f"  实体: {len(entities)}")
        output.append(f"  活动: {len(activities)}")
        output.append(f"  代理: {len(agents)}")
        output.append(f"  边: {len(self.edges)}")

        # 生成数据流图 (新的可视化方式)
        output.append("\n" + "=" * 70)
        output.append("数据流图 (实体→处理→产物)")
        output.append("=" * 70)

        data_flows = self._extract_data_flows()
        self._visualize_data_flows(data_flows, output)

        # 显示节点详情
        output.append("\n" + "=" * 70)
        output.append("节点详情")
        output.append("=" * 70)

        for node_type in ['entity', 'activity', 'agent']:
            output.append(f"\n{node_type.upper()} 节点:")
            for node in [n for n in self.nodes.values() if n.get('type') == node_type]:
                output.append(f"  {self._format_node(node)}")

        # 显示关系详情
        output.append("\n" + "=" * 70)
        output.append("关系详情")
        output.append("=" * 70)

        for edge in self.edges[:10]:  # 只显示前10个关系
            output.append(f"  {edge['from']} --[{edge['relation']}]--> {edge['to']}")

        if len(self.edges) > 10:
            output.append(f"  ... 还有 {len(self.edges) - 10} 个关系")

        # 生成 Mermaid 格式（用于在支持 Mermaid 的平台显示）
        output.append("\n" + "=" * 70)
        output.append("Mermaid 格式 (可在支持 Mermaid 的平台渲染)")
        output.append("=" * 70)

        mermaid = self._generate_mermaid()
        output.append(mermaid)

        return "\n".join(output)

    def _extract_chains(self) -> List[List]:
        """提取处理链"""
        chains = []

        # 找到所有最终产物（没有作为输入的实体）
        input_entities = set(e['to'] for e in self.edges if e['relation'] == 'used')
        all_entities = [n['id'] for n in self.nodes.values() if n.get('type') == 'entity']
        final_entities = [e for e in all_entities if e not in input_entities]

        # 为每个最终产物构建溯源链
        for final_entity in final_entities[:3]:  # 只处理前3个
            chain = self._build_chain(final_entity)
            if chain:
                chains.append(chain)

        return chains

    def _extract_data_flows(self) -> List[Dict]:
        """提取数据流（实体间的处理关系）

        Returns:
            数据流列表: [{input_entity, output_entity, activity, agent}]
        """
        flows = []

        # 遍历所有活动，找到每个活动的输入和输出实体
        activities = [n for n in self.nodes.values() if n.get('type') == 'activity']

        for activity in activities:
            activity_id = activity['id']

            # 找到这个活动使用的输入实体
            # used关系: from=activity, to=entity (活动使用了实体)
            input_edges = [e for e in self.edges
                          if e['from'] == activity_id and e['relation'] == 'used']

            # 找到这个活动生成的输出实体
            # wasGeneratedBy关系: from=entity, to=activity (实体由活动生成)
            output_edges = [e for e in self.edges
                           if e['to'] == activity_id and e['relation'] == 'wasGeneratedBy']

            # 找到关联的代理
            # wasAssociatedWith关系: from=activity, to=agent
            agent_edges = [e for e in self.edges
                          if e['from'] == activity_id and e['relation'] == 'wasAssociatedWith']

            agent_id = agent_edges[0]['to'] if agent_edges else None
            agent = self.nodes.get(agent_id) if agent_id else None

            # 为每个输入-输出对创建数据流
            for input_edge in input_edges:
                input_entity_id = input_edge['to']  # used关系的to是实体
                input_entity = self.nodes.get(input_entity_id)

                for output_edge in output_edges:
                    output_entity_id = output_edge['from']  # wasGeneratedBy关系的from是实体
                    output_entity = self.nodes.get(output_entity_id)

                    if input_entity and output_entity:
                        flows.append({
                            'input_entity': input_entity,
                            'output_entity': output_entity,
                            'activity': activity,
                            'agent': agent
                        })

        return flows

    def _visualize_data_flows(self, flows: List[Dict], output: List):
        """可视化数据流

        Args:
            flows: 数据流列表
            output: 输出列表
        """
        if not flows:
            output.append("  (无数据流)")
            return

        # 按输入实体分组
        flows_by_input = {}
        for flow in flows:
            input_id = flow['input_entity']['id']
            if input_id not in flows_by_input:
                flows_by_input[input_id] = []
            flows_by_input[input_id].append(flow)

        # 显示每个输入实体的流向
        for input_id, input_flows in flows_by_input.items():
            input_entity = input_flows[0]['input_entity']
            input_name = input_entity.get('location', input_id)

            output.append(f"\n【输入】{input_name}")
            if input_entity.get('attributes'):
                attrs = input_entity['attributes']
                attr_str = ', '.join(f"{k}={v}" for k, v in attrs.items())
                output.append(f"      属性: {attr_str}")

            for flow in input_flows:
                activity = flow['activity']
                agent = flow['agent']
                output_entity = flow['output_entity']
                output_name = output_entity.get('location', output_entity['id'])

                # 处理步骤
                activity_desc = activity.get('description', '')
                activity_type = activity.get('activity_type', '')
                output.append(f"      ↓ [{activity_type}] {activity_desc}")

                # 执行者
                if agent:
                    agent_name = agent.get('name', '')
                    output.append(f"      by: {agent_name}")

                # 输出
                output.append(f"      【输出】{output_name}")
                if output_entity.get('attributes'):
                    attrs = output_entity['attributes']
                    attr_str = ', '.join(f"{k}={v}" for k, v in attrs.items())
                    output.append(f"            属性: {attr_str}")

    def _build_chain(self, entity_id: str, visited: set = None) -> List:
        """构建单个实体的溯源链"""
        if visited is None:
            visited = set()

        if entity_id in visited:
            return []

        visited.add(entity_id)

        # 获取实体信息
        entity = self.nodes.get(entity_id)
        if not entity:
            return []

        chain = [{'type': 'entity', 'id': entity_id, 'data': entity}]

        # 找到生成这个实体的活动
        for edge in self.edges:
            if edge['to'] == entity_id and edge['relation'] == 'wasGeneratedBy':
                activity_id = edge['from']
                activity = self.nodes.get(activity_id)
                if activity:
                    chain.insert(0, {'type': 'activity', 'id': activity_id, 'data': activity})

                    # 找到这个活动使用的输入实体
                    for input_edge in self.edges:
                        if input_edge['to'] == activity_id and input_edge['relation'] == 'used':
                            input_entity_id = input_edge['from']
                            input_chain = self._build_chain(input_entity_id, visited)
                            if input_chain:
                                chain = input_chain + chain
                    break

        return chain

    def _visualize_chain(self, chain: List, output: List):
        """可视化处理链"""
        for i, item in enumerate(chain):
            if item['type'] == 'entity':
                entity = item['data']
                location = entity.get('location', '')
                short_name = location.split('/')[-1] if location else item['id']
                output.append(f"  {short_name}")
            elif item['type'] == 'activity':
                activity = item['data']
                desc = activity.get('description', '')
                output.append(f"     ↓ [{desc}]")

    def _format_node(self, node: Dict) -> str:
        """格式化节点信息"""
        node_type = node.get('type', '')
        if node_type == 'entity':
            location = node.get('location', '')
            attrs = node.get('attributes', {})
            return f"- {location} (属性: {attrs})"
        elif node_type == 'activity':
            desc = node.get('description', '')
            attrs = node.get('attributes', {})
            return f"- {desc} (属性: {attrs})"
        elif node_type == 'agent':
            name = node.get('name', '')
            attrs = node.get('attributes', {})
            return f"- {name} (属性: {attrs})"
        return f"- {node.get('id', '')}"

    def _generate_mermaid(self) -> str:
        """生成 Mermaid 格式的图表 - Agent作为边上节点版本

        结构: input_entity --[activity]--> agent --[produces]--> output_entity
        相同文件位置的实体会被合并为单一节点
        """
        lines = []
        lines.append("graph TD")

        # 定义样式
        lines.append("    classDef entity fill:#e1f5ff,stroke:#01579b,stroke-width:2px")
        lines.append("    classDef artifact fill:#fff9c4,stroke:#f57f17,stroke-width:2px")
        lines.append("    classDef agent fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,stroke-dasharray: 5 5")

        # 获取数据流
        flows = self._extract_data_flows()

        # 按文件位置合并实体节点
        location_to_node = {}  # {location: {id, type, attributes}}
        id_to_location = {}    # {entity_id: location}

        # 先收集所有唯一的文件位置
        for flow in flows:
            input_entity = flow['input_entity']
            output_entity = flow['output_entity']

            for entity in [input_entity, output_entity]:
                location = entity.get('location', '')
                if location:
                    # 始终记录实体ID到位置的映射
                    id_to_location[entity['id']] = location

                    # 如果是新位置，创建节点
                    if location not in location_to_node:
                        # 生成基于位置的节点ID（替换特殊字符包括空格）
                        safe_id = location.replace('.', '_').replace('/', '_').replace('-', '_').replace(' ', '_').replace(':', '_')
                        # 确保 ID 以字母开头（Mermaid 要求）
                        if safe_id and safe_id[0].isdigit():
                            safe_id = 'node_' + safe_id
                        location_to_node[location] = {
                            'id': safe_id,
                            'type': entity.get('entity_type', 'dataset'),
                            'location': location
                        }

        # 添加合并后的实体节点
        for location, node_info in location_to_node.items():
            node_id = node_info['id']
            entity_type = node_info['type']
            short_name = location.split('/')[-1] if location else node_id

            class_name = 'artifact' if entity_type == 'artifact' else 'entity'
            lines.append(f"    {node_id}[\"{short_name}\"]:::{class_name}")

        # 收集代理和连接
        agent_nodes = {}
        flow_connections = []

        for flow in flows:
            input_entity = flow['input_entity']
            output_entity = flow['output_entity']
            activity = flow['activity']
            agent = flow['agent']

            # 获取合并后的节点ID
            input_location = id_to_location.get(input_entity['id'])
            output_location = id_to_location.get(output_entity['id'])

            if not input_location or not output_location:
                continue

            input_node_id = location_to_node[input_location]['id']
            output_node_id = location_to_node[output_location]['id']

            # 收集代理
            if agent:
                if agent['id'] not in agent_nodes:
                    agent_nodes[agent['id']] = agent

                # 记录连接关系
                flow_connections.append({
                    'input_id': input_node_id,
                    'agent_id': agent['id'],
                    'output_id': output_node_id,
                    'activity': activity
                })

        # 添加代理节点（在实体节点之后添加）
        for agent_id, agent_data in agent_nodes.items():
            agent_name = agent_data.get('name', agent_id)
            # 简化名称
            if 'claude_analysis_' in agent_name:
                short_name = agent_name.replace('claude_analysis_', 'Step ')
            else:
                short_name = agent_name
            lines.append(f"    {agent_id}[\"{short_name}\"]:::agent")

        # 添加连接：input --[activity]--> agent --[produces]--> output
        for conn in flow_connections:
            input_id = conn['input_id']
            agent_id = conn['agent_id']
            output_id = conn['output_id']
            activity = conn['activity']

            activity_type = activity.get('activity_type', '')

            # 输入实体到代理（显示活动类型）
            lines.append(f"    {input_id} ==>|\"{activity_type}\"| {agent_id}")

            # 代理到输出实体
            lines.append(f"    {agent_id} -.->|output| {output_id}")

        return "\n".join(lines)

    def _get_mermaid_label(self, node_data: Dict) -> str:
        """获取 Mermaid 节点标签"""
        node_type = node_data.get('type', '')

        if node_type == 'entity':
            location = node_data.get('location', '')
            return location.split('/')[-1] if location else node_data['id']
        elif node_type == 'activity':
            activity_type = node_data.get('activity_type', '')
            description = node_data.get('description', '')
            return f"{activity_type}\\n{description}"
        elif node_type == 'agent':
            name = node_data.get('name', '')
            return name

        return node_data.get('id', '')

    def print_summary(self):
        """打印 DAG 摘要"""
        print("\n" + "=" * 70)
        print("PROV DAG 摘要")
        print("=" * 70)

        print(f"\nDAG ID: {self.dag_data.get('dag_id', 'N/A')}")
        print(f"创建时间: {self.dag_data.get('created_at', 'N/A')}")

        stats = self.dag_data.get('statistics', {})
        print(f"\n节点统计:")
        print(f"  实体: {stats.get('total_entities', 0)}")
        print(f"  活动: {stats.get('total_activities', 0)}")
        print(f"  代理: {stats.get('total_agents', 0)}")
        print(f"  边: {stats.get('total_edges', 0)}")


def visualize_prov_dag(session_dir: str, output_file: str = None) -> str:
    """可视化 PROV DAG

    Args:
        session_dir: 会话目录
        output_file: 输出文件路径（可选）

    Returns:
        生成的可视化文本
    """
    visualizer = ProvDAGVisualizer(session_dir)

    # 打印摘要
    visualizer.print_summary()

    # 生成文本可视化
    visualization = visualizer.visualize_text()

    # 保存到文件
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(visualization)
        print(f"\n[OK] 可视化已保存到: {output_file}")
    else:
        print(visualization)

    return visualization


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python prov_visualizer.py <session_dir>")
        print("示例: python prov_visualizer.py .opentrace/session_YYYYMMDD_HHMMSS")
        sys.exit(1)

    session_dir = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    visualize_prov_dag(session_dir, output_file)
