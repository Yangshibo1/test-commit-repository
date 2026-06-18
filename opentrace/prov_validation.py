"""
PROV DAG 验证和保护模块

提供数据完整性验证和防护机制
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class ProvValidator:
    """PROV 数据验证器"""

    # PROV 标准关系及其有效的方向组合
    RELATION_RULES = {
        "used": {
            "from_types": ["activity"],
            "to_types": ["entity"]
        },
        "wasGeneratedBy": {
            "from_types": ["entity"],
            "to_types": ["activity"]
        },
        "wasAssociatedWith": {
            "from_types": ["activity"],
            "to_types": ["agent"]
        },
        "wasDerivedFrom": {
            "from_types": ["entity"],
            "to_types": ["entity"]
        },
        "wasStartedBy": {
            "from_types": ["activity"],
            "to_types": ["activity"]
        },
        "wasInformedBy": {
            "from_types": ["activity"],
            "to_types": ["activity"]
        },
        "actedOnBehalfOf": {
            "from_types": ["agent"],
            "to_types": ["agent"]
        }
    }

    def __init__(self, session_dir: str):
        self.session_dir = Path(session_dir)
        self.integrity_file = self.session_dir / ".integrity.json"

    def validate_relation(self, from_node: Dict, to_node: Dict, relation: str) -> tuple[bool, str]:
        """验证单个关系的有效性

        Args:
            from_node: 源节点数据
            to_node: 目标节点数据
            relation: 关系类型

        Returns:
            (is_valid, error_message)
        """
        if relation not in self.RELATION_RULES:
            return False, f"未知的关系类型: {relation}"

        rule = self.RELATION_RULES[relation]
        from_type = from_node.get("type")
        to_type = to_node.get("type")

        if from_type not in rule["from_types"]:
            return False, f"关系 {relation} 的源节点类型必须是 {rule['from_types']}，实际是 {from_type}"

        if to_type not in rule["to_types"]:
            return False, f"关系 {relation} 的目标节点类型必须是 {rule['to_types']}，实际是 {to_type}"

        return True, ""

    def validate_dag(self, nodes: Dict, edges: List[Dict]) -> tuple[bool, List[str]]:
        """验证整个 DAG 的有效性

        Returns:
            (is_valid, error_list)
        """
        errors = []

        # 检查节点引用完整性
        node_ids = set(nodes.keys())

        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")

            if from_id not in node_ids:
                errors.append(f"边引用了不存在的源节点: {from_id}")

            if to_id not in node_ids:
                errors.append(f"边引用了不存在的目标节点: {to_id}")

            # 验证关系类型和节点类型匹配
            from_node = nodes.get(from_id, {})
            to_node = nodes.get(to_id, {})
            relation = edge.get("relation")

            if from_node and to_node and relation:
                is_valid, error = self.validate_relation(from_node, to_node, relation)
                if not is_valid:
                    errors.append(error)

        return len(errors) == 0, errors

    def compute_integrity_hash(self) -> Optional[str]:
        """计算当前会话的完整性哈希

        Returns:
            SHA256 哈希值，如果文件不存在返回 None
        """
        dag_file = self.session_dir / "prov_dag.json"
        nodes_file = self.session_dir / "prov_nodes.json"
        edges_file = self.session_dir / "prov_edges.json"

        if not all(f.exists() for f in [dag_file, nodes_file, edges_file]):
            return None

        # 读取所有文件内容
        content = ""
        for file_path in [dag_file, nodes_file, edges_file]:
            content += file_path.read_text(encoding='utf-8')

        return hashlib.sha256(content.encode()).hexdigest()

    def save_integrity(self, metadata: Dict[str, Any] = None) -> str:
        """保存完整性记录

        Args:
            metadata: 额外的元数据

        Returns:
            完整性哈希
        """
        integrity_hash = self.compute_integrity_hash()

        if integrity_hash is None:
            raise ValueError("无法计算完整性哈希：PROV 文件不完整")

        record = {
            "hash": integrity_hash,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }

        # 读取现有记录
        history = []
        if self.integrity_file.exists():
            history = json.loads(self.integrity_file.read_text(encoding='utf-8'))

        # 添加新记录
        history.append(record)

        # 保存
        self.integrity_file.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        return integrity_hash

    def verify_integrity(self, expected_hash: str = None) -> tuple[bool, Dict]:
        """验证数据完整性

        Args:
            expected_hash: 期望的哈希值，如果为 None 则使用最新记录

        Returns:
            (is_valid, details)
        """
        current_hash = self.compute_integrity_hash()

        if current_hash is None:
            return False, {"error": "PROV 文件不完整"}

        # 如果没有提供期望值，从记录中获取最新的
        if expected_hash is None:
            if not self.integrity_file.exists():
                return False, {"error": "没有完整性记录"}
            history = json.loads(self.integrity_file.read_text(encoding='utf-8'))
            if not history:
                return False, {"error": "完整性记录为空"}
            expected_hash = history[-1]["hash"]

        is_valid = current_hash == expected_hash

        return is_valid, {
            "current_hash": current_hash,
            "expected_hash": expected_hash,
            "timestamp": datetime.now().isoformat()
        }

    def get_integrity_history(self) -> List[Dict]:
        """获取完整性历史记录"""
        if not self.integrity_file.exists():
            return []

        return json.loads(self.integrity_file.read_text(encoding='utf-8'))


class ProtectedProvDAG:
    """带保护的 PROV DAG

    特性：
    1. 所有操作前进行验证
    2. 自动计算和验证完整性哈希
    3. 支持追加模式（禁止修改现有数据）
    """

    def __init__(self, session_dir: str, append_only: bool = True):
        from opentrace.prov_dag import ProvDAG

        self.session_dir = Path(session_dir)
        self.append_only = append_only
        self.validator = ProvValidator(session_dir)

        # 加载现有 DAG 或创建新的
        if (self.session_dir / "prov_dag.json").exists():
            self.dag = ProvDAG.load(session_dir)
            # 验证加载的 DAG
            is_valid, errors = self.validator.validate_dag(self.dag.nodes, self.dag.edges)
            if not is_valid:
                raise ValueError(f"加载的 DAG 验证失败: {errors}")
            # 验证完整性
            is_valid, details = self.validator.verify_integrity()
            if not is_valid:
                raise ValueError(f"DAG 完整性验证失败: {details}")
        else:
            self.dag = ProvDAG("protected_dag", session_dir)

    def add_relation(self, from_id: str, to_id: str, relation: str,
                    attributes: Dict[str, Any] = None) -> str:
        """添加关系（带验证）"""
        # 在追加模式下，检查是否允许修改
        if self.append_only:
            # 检查是否已有相同的关系
            for edge in self.dag.edges:
                if edge["from"] == from_id and edge["to"] == to_id and edge["relation"] == relation:
                    raise ValueError(f"追加模式下不允许添加重复关系: {from_id} -> {to_id}")

        # 验证关系
        from_node = self.dag.nodes.get(from_id)
        to_node = self.dag.nodes.get(to_id)

        if not from_node:
            raise ValueError(f"源节点不存在: {from_id}")
        if not to_node:
            raise ValueError(f"目标节点不存在: {to_id}")

        is_valid, error = self.validator.validate_relation(from_node, to_node, relation)
        if not is_valid:
            raise ValueError(f"无效的关系: {error}")

        # 添加关系到 DAG
        edge_id = self.dag.add_relation(from_id, to_id, relation, attributes)

        # 保存并更新完整性
        self._save_with_integrity()

        return edge_id

    def _save_with_integrity(self):
        """保存 DAG 并更新完整性记录"""
        # 保存 DAG 文件
        self.dag.save()

        # 计算并保存完整性哈希
        self.validator.save_integrity({
            "operation": "add_relation",
            "node_count": len(self.dag.nodes),
            "edge_count": len(self.dag.edges)
        })


def validate_session(session_dir: str) -> tuple[bool, List[str]]:
    """验证整个会话的有效性

    Args:
        session_dir: 会话目录

    Returns:
        (is_valid, error_list)
    """
    validator = ProvValidator(session_dir)

    # 加载数据
    nodes_file = Path(session_dir) / "prov_nodes.json"
    edges_file = Path(session_dir) / "prov_edges.json"

    if not nodes_file.exists() or not edges_file.exists():
        return False, ["PROV 文件不存在"]

    nodes = json.loads(nodes_file.read_text(encoding='utf-8'))["nodes"]
    edges = json.loads(edges_file.read_text(encoding='utf-8'))["edges"]

    # 验证 DAG
    is_valid, errors = validator.validate_dag(nodes, edges)

    # 验证完整性
    if is_valid:
        integrity_valid, details = validator.verify_integrity()
        if not integrity_valid:
            errors.append(f"完整性验证失败: {details}")

    return is_valid, errors


if __name__ == "__main__":
    # 测试验证器
    import sys

    if len(sys.argv) > 1:
        session_dir = sys.argv[1]
        is_valid, errors = validate_session(session_dir)

        if is_valid:
            print("✓ 会话验证通过")
        else:
            print("✗ 会话验证失败:")
            for error in errors:
                print(f"  - {error}")
        sys.exit(0 if is_valid else 1)
    else:
        print("用法: python prov_validation.py <session_dir>")
