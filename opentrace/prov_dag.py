"""
PROV DAG 模块

基于 W3C PROV 标准的数据溯源 DAG 实现
支持实体(Entity)、活动(Activity)、代理(Agent)及其关系
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field


@dataclass
class ProvEntity:
    """PROV 实体（数据集、文件、产物）"""
    id: str
    type: str = "entity"  # 固定为 "entity"
    entity_type: str = ""  # "dataset" | "file" | "artifact"
    location: str = ""
    timestamp: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvActivity:
    """PROV 活动（数据处理操作）"""
    id: str
    type: str = "activity"  # 固定为 "activity"
    activity_type: str = ""  # "filter" | "aggregate" | "transform" | "join" | "split"...
    description: str = ""
    timestamp: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvAgent:
    """PROV 代理（执行者）"""
    id: str
    type: str = "agent"  # 固定为 "agent"
    agent_type: str = ""  # "python_code" | "agent" | "user"
    name: str = ""
    timestamp: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)


class ProvDAG:
    """PROV DAG（有向无环图）"""

    # PROV 标准关系类型
    RELATION_TYPES = {
        # Entity → Activity
        "wasGeneratedBy": "实体由活动生成",

        # Activity → Entity
        "used": "活动使用了实体",

        # Activity → Agent
        "wasAssociatedWith": "活动与代理关联",

        # Entity → Entity
        "wasDerivedFrom": "实体派生自另一个实体",

        # Activity → Activity
        "wasStartedBy": "活动由另一个活动启动",
        "wasInformedBy": "活动使用了另一个活动的输出",

        # Agent → Agent
        "actedOnBehalfOf": "代理代表另一个代理行动"
    }

    def __init__(self, dag_id: str, session_dir: Path):
        self.dag_id = dag_id
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 存储结构
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []

        # 统计信息
        self.stats = {
            "total_entities": 0,
            "total_activities": 0,
            "total_agents": 0,
            "total_edges": 0
        }

        # 元数据
        self.metadata = {
            "dag_id": dag_id,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "description": "",
            "tags": []
        }

    def _generate_id(self, prefix: str) -> str:
        """生成唯一ID"""
        unique_id = uuid.uuid4().hex[:8]
        return f"{prefix}_{unique_id}"

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        return datetime.now().isoformat()

    # ==================== 节点操作 ====================

    def add_entity(self, entity_type: str, location: str,
                   attributes: Dict[str, Any] = None) -> str:
        """添加实体节点

        Args:
            entity_type: 实体类型 (dataset | file | artifact)
            location: 文件路径或标识
            attributes: 额外属性（自由格式）

        Returns:
            生成的实体ID
        """
        entity_id = self._generate_id("entity")

        self.nodes[entity_id] = {
            "id": entity_id,
            "type": "entity",
            "entity_type": entity_type,
            "location": location,
            "attributes": attributes or {},
            "timestamp": self._get_timestamp()
        }

        self.stats["total_entities"] += 1
        self._update_timestamp()

        return entity_id

    def add_activity(self, activity_type: str, description: str,
                     attributes: Dict[str, Any] = None) -> str:
        """添加活动节点

        Args:
            activity_type: 活动类型 (filter | aggregate | transform...)
            description: 活动描述
            attributes: 额外属性（自由格式）

        Returns:
            生成的活动ID
        """
        activity_id = self._generate_id("activity")

        self.nodes[activity_id] = {
            "id": activity_id,
            "type": "activity",
            "activity_type": activity_type,
            "description": description,
            "attributes": attributes or {},
            "timestamp": self._get_timestamp()
        }

        self.stats["total_activities"] += 1
        self._update_timestamp()

        return activity_id

    def add_agent(self, agent_type: str, name: str,
                  attributes: Dict[str, Any] = None) -> str:
        """添加代理节点

        Args:
            agent_type: 代理类型 (python_code | agent | user)
            name: 代理名称
            attributes: 额外属性（自由格式）

        Returns:
            生成的代理ID
        """
        agent_id = self._generate_id("agent")

        self.nodes[agent_id] = {
            "id": agent_id,
            "type": "agent",
            "agent_type": agent_type,
            "name": name,
            "attributes": attributes or {},
            "timestamp": self._get_timestamp()
        }

        self.stats["total_agents"] += 1
        self._update_timestamp()

        return agent_id

    # ==================== 关系操作 ====================

    def add_relation(self, from_id: str, to_id: str, relation: str,
                     attributes: Dict[str, Any] = None) -> str:
        """添加关系边

        Args:
            from_id: 源节点ID
            to_id: 目标节点ID
            relation: 关系类型
            attributes: 额外属性（自由格式）

        Returns:
            生成的边ID

        Raises:
            ValueError: 如果关系类型无效
        """
        if relation not in self.RELATION_TYPES:
            raise ValueError(f"无效的关系类型: {relation}. 有效类型: {list(self.RELATION_TYPES.keys())}")

        # 检查节点是否存在
        if from_id not in self.nodes:
            raise ValueError(f"源节点不存在: {from_id}")
        if to_id not in self.nodes:
            raise ValueError(f"目标节点不存在: {to_id}")

        edge_id = self._generate_id("edge")

        edge = {
            "id": edge_id,
            "from": from_id,
            "to": to_id,
            "relation": relation,
            "timestamp": self._get_timestamp(),
            "attributes": attributes or {}
        }

        self.edges.append(edge)
        self.stats["total_edges"] += 1
        self._update_timestamp()

        return edge_id

    # ==================== 批量操作 ====================

    def add_entities_from_list(self, entities_list: List[Dict[str, Any]]) -> Dict[str, str]:
        """批量添加实体

        Args:
            entities_list: 实体列表，每个包含 entity_type, location, attributes

        Returns:
            ID映射字典 {临时ID: 实际ID}
        """
        id_mapping = {}

        for i, entity_data in enumerate(entities_list):
            actual_id = self.add_entity(
                entity_type=entity_data["entity_type"],
                location=entity_data["location"],
                attributes=entity_data.get("attributes", {})
            )
            # 创建临时ID映射（方便后续建立关系）
            temp_id = entity_data.get("id", f"temp_entity_{i}")
            id_mapping[temp_id] = actual_id

        return id_mapping

    def add_activities_from_list(self, activities_list: List[Dict[str, Any]]) -> Dict[str, str]:
        """批量添加活动

        Returns:
            ID映射字典 {临时ID: 实际ID}
        """
        id_mapping = {}

        for i, activity_data in enumerate(activities_list):
            actual_id = self.add_activity(
                activity_type=activity_data["activity_type"],
                description=activity_data["description"],
                attributes=activity_data.get("attributes", {})
            )
            temp_id = activity_data.get("id", f"temp_activity_{i}")
            id_mapping[temp_id] = actual_id

        return id_mapping

    def add_agents_from_list(self, agents_list: List[Dict[str, Any]]) -> Dict[str, str]:
        """批量添加代理

        Returns:
            ID映射字典 {临时ID: 实际ID}
        """
        id_mapping = {}

        for i, agent_data in enumerate(agents_list):
            actual_id = self.add_agent(
                agent_type=agent_data["agent_type"],
                name=agent_data["name"],
                attributes=agent_data.get("attributes", {})
            )
            temp_id = agent_data.get("id", f"temp_agent_{i}")
            id_mapping[temp_id] = actual_id

        return id_mapping

    def add_relations_from_list(self, relations_list: List[Tuple[str, str, str]],
                               id_mapping: Dict[str, str] = None):
        """批量添加关系

        Args:
            relations_list: 关系列表 [(from, to, relation), ...]
            id_mapping: ID映射字典（用于将临时ID转换为实际ID）
        """
        for from_id, to_id, relation in relations_list:
            # 转换ID
            actual_from = id_mapping.get(from_id, from_id) if id_mapping else from_id
            actual_to = id_mapping.get(to_id, to_id) if id_mapping else to_id

            self.add_relation(actual_from, actual_to, relation)

    # ==================== 查询操作 ====================

    def get_upstream(self, node_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """获取上游节点

        Args:
            node_id: 起始节点ID
            max_depth: 最大深度

        Returns:
            上游路径列表
        """
        if node_id not in self.nodes:
            return []

        paths = []
        visited = set()

        def _dfs(current_id: str, path: List[Dict], depth: int):
            if depth > max_depth or current_id in visited:
                return

            visited.add(current_id)

            # 查找指向当前节点的边
            for edge in self.edges:
                if edge["to"] == current_id:
                    from_node = self.nodes[edge["from"]]
                    new_path = path + [{
                        "from": edge["from"],
                        "to": edge["to"],
                        "relation": edge["relation"],
                        "node_type": from_node["type"],
                        "timestamp": edge["timestamp"]
                    }]
                    paths.append(new_path)
                    _dfs(edge["from"], new_path, depth + 1)

        _dfs(node_id, [], 0)
        return paths

    def get_downstream(self, node_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """获取下游节点

        Args:
            node_id: 起始节点ID
            max_depth: 最大深度

        Returns:
            下游路径列表
        """
        if node_id not in self.nodes:
            return []

        paths = []
        visited = set()

        def _dfs(current_id: str, path: List[Dict], depth: int):
            if depth > max_depth or current_id in visited:
                return

            visited.add(current_id)

            # 查找从当前节点出发的边
            for edge in self.edges:
                if edge["from"] == current_id:
                    to_node = self.nodes[edge["to"]]
                    new_path = path + [{
                        "from": edge["from"],
                        "to": edge["to"],
                        "relation": edge["relation"],
                        "node_type": to_node["type"],
                        "timestamp": edge["timestamp"]
                    }]
                    paths.append(new_path)
                    _dfs(edge["to"], new_path, depth + 1)

        _dfs(node_id, [], 0)
        return paths

    def get_entity_lineage(self, entity_id: str) -> Dict[str, Any]:
        """获取实体的完整溯源链

        Args:
            entity_id: 实体ID

        Returns:
            溯源链信息
        """
        if entity_id not in self.nodes:
            return {"error": "实体不存在"}

        upstream_paths = self.get_upstream(entity_id)

        # 构建溯源链（简化版，只返回主路径）
        lineage_chain = []
        visited = {entity_id}

        current_id = entity_id
        while current_id:
            found_next = False
            for edge in self.edges:
                if edge["to"] == current_id and edge["from"] not in visited:
                    from_node = self.nodes[edge["from"]]
                    lineage_chain.append({
                        "step": len(lineage_chain) + 1,
                        "entity_id": edge["from"],
                        "entity_type": from_node.get("entity_type", from_node.get("type")),
                        "location": from_node.get("location", ""),
                        "activity": edge["relation"],
                        "relation": edge["relation"]
                    })
                    visited.add(edge["from"])
                    current_id = edge["from"]
                    found_next = True
                    break

            if not found_next:
                break

        return {
            "entity_id": entity_id,
            "entity_info": self.nodes[entity_id],
            "lineage_chain": list(reversed(lineage_chain)),
            "total_upstream_paths": len(upstream_paths)
        }

    def get_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        """按类型获取节点

        Args:
            node_type: 节点类型 (entity | activity | agent)

        Returns:
            该类型的所有节点
        """
        return [
            node for node in self.nodes.values()
            if node["type"] == node_type
        ]

    # ==================== 存储操作 ====================

    def _update_timestamp(self):
        """更新更新时间"""
        self.metadata["updated_at"] = self._get_timestamp()

    def save(self) -> Dict[str, str]:
        """保存 DAG 到文件

        Returns:
            保存的文件路径
        """
        # 保存 DAG 元数据
        dag_file = self.session_dir / "prov_dag.json"
        dag_data = {
            **self.metadata,
            "statistics": self.stats
        }
        self._save_json(dag_data, dag_file)

        # 保存节点
        nodes_file = self.session_dir / "prov_nodes.json"
        self._save_json({"nodes": self.nodes}, nodes_file)

        # 保存边
        edges_file = self.session_dir / "prov_edges.json"
        self._save_json({"edges": self.edges}, edges_file)

        return {
            "dag_file": str(dag_file),
            "nodes_file": str(nodes_file),
            "edges_file": str(edges_file)
        }

    def _save_json(self, data: Any, path: Path):
        """保存 JSON 文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, session_dir: Path) -> 'ProvDAG':
        """从文件加载 DAG

        Args:
            session_dir: 会话目录

        Returns:
            ProvDAG 实例
        """
        session_dir = Path(session_dir)

        # 加载元数据
        dag_file = session_dir / "prov_dag.json"
        if dag_file.exists():
            dag_data = json.loads(dag_file.read_text(encoding='utf-8'))
            dag_id = dag_data.get("dag_id", "loaded_dag")
        else:
            dag_id = "loaded_dag"

        # 创建实例
        dag = cls(dag_id, session_dir)

        # 加载节点
        nodes_file = session_dir / "prov_nodes.json"
        if nodes_file.exists():
            nodes_data = json.loads(nodes_file.read_text(encoding='utf-8'))
            dag.nodes = nodes_data.get("nodes", {})

        # 加载边
        edges_file = session_dir / "prov_edges.json"
        if edges_file.exists():
            edges_data = json.loads(edges_file.read_text(encoding='utf-8'))
            dag.edges = edges_data.get("edges", [])

        # 更新统计
        dag._update_stats()

        return dag

    def _update_stats(self):
        """更新统计信息"""
        for node in self.nodes.values():
            if node["type"] == "entity":
                self.stats["total_entities"] += 1
            elif node["type"] == "activity":
                self.stats["total_activities"] += 1
            elif node["type"] == "agent":
                self.stats["total_agents"] += 1

        self.stats["total_edges"] = len(self.edges)


if __name__ == "__main__":
    # 测试代码
    dag = ProvDAG("test_dag", Path("test/opentrace_test"))

    # 添加节点
    entity1 = dag.add_entity("dataset", "raw_data.csv", {"rows": 1000})
    activity1 = dag.add_activity("filter", "筛选数据")
    entity2 = dag.add_entity("dataset", "filtered_data.csv", {"rows": 100})
    agent1 = dag.add_agent("python_code", "claude_analysis")

    # 添加关系
    dag.add_relation(activity1, entity1, "used")
    dag.add_relation(entity2, activity1, "wasGeneratedBy")
    dag.add_relation(activity1, agent1, "wasAssociatedWith")
    dag.add_relation(entity2, entity1, "wasDerivedFrom")

    # 保存
    files = dag.save()
    print(f"DAG 已保存: {files}")
