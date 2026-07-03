"""
MCP 服务器 - OpenTrace 血缘追踪工具

提供 Claude Code/OpenDevin 等 agent 调用的接口
当前版本专注于直接调用接口，MCP 集成将在后续完善
"""

import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from opentrace.tracker import LineageTracker
from opentrace.prov_dag import ProvDAG


def _get_default_base_dir() -> Path:
    """获取默认基础目录（使用绝对路径）

    优先级：
    1. 环境变量 OPENTRACE_BASE_DIR
    2. 项目根目录下的 .opentrace
    """
    env_dir = os.environ.get("OPENTRACE_BASE_DIR")
    if env_dir:
        return Path(env_dir).absolute()

    return Path(__file__).resolve().parent.parent / ".opentrace"


class OpenTraceServer:
    """OpenTrace 服务器

    提供直接调用接口，MCP 协议支持待完善
    """

    def __init__(self, base_dir: str = None):
        # 使用绝对路径，避免路径问题
        if base_dir is None:
            self.base_dir = _get_default_base_dir()
        else:
            self.base_dir = Path(base_dir).absolute()

        self.base_dir.mkdir(parents=True, exist_ok=True)

        # 会话管理
        self.sessions: Dict[str, LineageTracker] = {}

        # 启动时加载现有会话
        self._load_existing_sessions()

    # ==================== 核心接口 ====================

    def init_session(self,
                    task_description: str,
                    data_path: str,
                    data_type: str = "json") -> Dict[str, Any]:
        """初始化血缘追踪会话

        Args:
            task_description: 任务描述
            data_path: 数据文件路径
            data_type: 数据类型 (json/csv)

        Returns:
            会话ID和初始化信息
        """
        session_id = self._generate_session_id()
        tracker = LineageTracker(session_id, str(self.base_dir))

        try:
            if data_type == "json":
                result = tracker.init_from_json(data_path)
            elif data_type == "csv":
                result = tracker.init_from_csv(data_path)
            else:
                raise ValueError(f"不支持的数据类型: {data_type}")

            self.sessions[session_id] = tracker

            return {
                "session_id": session_id,
                "task_description": task_description,
                "status": "initialized",
                **result
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def record_step(self,
                   session_id: str,
                   step_name: str,
                   operation: str,
                   description: str = "",
                   metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """记录一个处理步骤

        Args:
            session_id: 会话ID
            step_name: 步骤名称
            operation: 操作类型
            description: 详细描述
            metadata: 额外的元数据

        Returns:
            步骤ID
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            step_id = tracker.record_step(step_name, operation, description, metadata)
            return {
                "step_id": step_id,
                "step_name": step_name,
                "status": "recorded"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def record_mapping(self,
                      session_id: str,
                      step_id: str,
                      from_ids: List[str],
                      to_id: str,
                      operation: str,
                      value_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """记录数据映射关系

        Args:
            session_id: 会话ID
            step_id: 步骤ID
            from_ids: 源数据ID列表
            to_id: 目标数据ID
            operation: 操作描述
            value_info: 值信息 (可选)

        Returns:
            确认信息
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            tracker.record_mapping(step_id, from_ids, to_id, operation, value_info)
            return {
                "status": "recorded",
                "mapping_count": len(from_ids),
                "to_id": to_id
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def record_step_with_mappings(self,
                                  session_id: str,
                                  step_name: str,
                                  operation: str,
                                  description: str,
                                  mappings: List[Dict[str, Any]],
                                  metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """一步记录步骤和映射

        Args:
            session_id: 会话ID
            step_name: 步骤名称
            operation: 操作类型
            description: 详细描述
            mappings: 映射列表
            metadata: 额外元数据

        Returns:
            步骤ID
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            step_id = tracker.record_step_with_mappings(
                step_name, operation, description, mappings, metadata
            )
            return {
                "step_id": step_id,
                "step_name": step_name,
                "mappings_count": len(mappings),
                "status": "recorded"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def trace_element(self,
                     session_id: str,
                     element_id: str,
                     max_depth: int = 50) -> Dict[str, Any]:
        """追踪数据元素的血缘链

        Args:
            session_id: 会话ID
            element_id: 数据元素ID
            max_depth: 最大追踪深度

        Returns:
            血缘链信息
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            chain = tracker.trace_element(element_id, max_depth)

            return {
                "element_id": element_id,
                "chain_length": len(chain),
                "chain": chain,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def analyze_error(self,
                     error_message: str,
                     session_id: str,
                     affected_element: str = None,
                     context: Dict[str, Any] = None) -> Dict[str, Any]:
        """分析错误来源

        Args:
            session_id: 会话ID
            error_message: 错误信息
            affected_element: 受影响的数据元素 (可选)
            context: 额外上下文 (可选)

        Returns:
            错误分析结果
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            analysis = tracker.analyze_error(error_message, affected_element, context)

            return {
                "analysis": analysis,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """获取会话概览

        Args:
            session_id: 会话ID

        Returns:
            会话概览信息
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            summary = tracker.get_session_summary()

            return {
                "summary": summary,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_step_detail(self, session_id: str, step_id: str) -> Dict[str, Any]:
        """获取步骤详情

        Args:
            session_id: 会话ID
            step_id: 步骤ID

        Returns:
            步骤详情
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            detail = tracker.get_step_detail(step_id)

            if not detail:
                return {"error": "步骤不存在"}

            return {
                "detail": detail,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def export_session(self, session_id: str, format: str = "json") -> Dict[str, Any]:
        """导出会话数据

        Args:
            session_id: 会话ID
            format: 导出格式 (json)

        Returns:
            导出文件路径
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            export_path = tracker.export_session(format)

            return {
                "export_path": export_path,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    # ==================== 数据处理记录 ====================

    def record_processing(self,
                         session_id: str,
                         step_id: str,
                         input_spec: Dict[str, Any],
                         algorithm_spec: Dict[str, Any],
                         result_data: Dict[str, Any],
                         large_result_threshold: int = 1000) -> Dict[str, Any]:
        """记录数据处理步骤（包含 input/algorithm/result 三要素）

        Args:
            session_id: 会话ID
            step_id: 关联的步骤ID
            input_spec: 输入规格 (source, source_type, filter_condition, etc.)
            algorithm_spec: 算法规格 (type, language, code, logic_description)
            result_data: 结果数据字典
            large_result_threshold: 外存阈值

        Returns:
            processing_id 和状态
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            processing_id = tracker.record_processing(
                step_id, input_spec, algorithm_spec, result_data, large_result_threshold
            )

            return {
                "processing_id": processing_id,
                "step_id": step_id,
                "status": "recorded"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_processing_detail(self,
                             session_id: str,
                             processing_id: str) -> Dict[str, Any]:
        """获取处理记录详情

        Args:
            session_id: 会话ID
            processing_id: 处理记录ID

        Returns:
            处理记录详情
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            detail = tracker.get_processing_detail(processing_id)

            if not detail:
                return {"error": "处理记录不存在"}

            return {
                "detail": detail,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def list_processings(self,
                        session_id: str,
                        step_id: str = None) -> Dict[str, Any]:
        """列出处理记录

        Args:
            session_id: 会话ID
            step_id: 可选，筛选特定步骤

        Returns:
            处理记录列表
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            processings = tracker.list_processings(step_id)

            return {
                "processings": processings,
                "count": len(processings),
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    # ==================== PROV DAG 接口 ====================

    def record_step_details(self,
                          session_id: str,
                          step_id: str,
                          step_name: str,
                          description: str,
                          code_generated: List[str] = None,
                          code_files: List[str] = None,
                          commands_run: List[str] = None,
                          input_files: List[str] = None,
                          output_files: List[str] = None,
                          parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """记录步骤详情（细粒度的步骤信息）

        Args:
            session_id: 会话ID
            step_id: 步骤ID (如 "step_1")
            step_name: 步骤名称 (如 "filter_events")
            description: 步骤工作内容描述
            code_generated: 生成的代码片段列表
            code_files: 生成的代码文件路径列表 (.py, .sql, etc.)
            commands_run: 运行的命令列表
            input_files: 输入文件列表
            output_files: 输出文件列表
            parameters: 参数配置

        Returns:
            记录结果
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            from opentrace.step_details import record_step_details

            tracker = self.sessions[session_id]
            session_dir = tracker.session_dir

            record_step_details(
                session_dir=str(session_dir),
                step_id=step_id,
                step_name=step_name,
                description=description,
                code_generated=code_generated,
                code_files=code_files,
                commands_run=commands_run,
                input_files=input_files,
                output_files=output_files,
                parameters=parameters
            )

            return {
                "status": "success",
                "step_id": step_id,
                "step_name": step_name
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_step_details(self, session_id: str) -> Dict[str, Any]:
        """获取会话的所有步骤详情

        Args:
            session_id: 会话ID

        Returns:
            所有步骤详情
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            from opentrace.step_details import StepDetailsRecorder

            tracker = self.sessions[session_id]
            session_dir = tracker.session_dir

            recorder = StepDetailsRecorder(str(session_dir))
            steps = recorder.list_steps()

            return {
                "steps": steps,
                "count": len(steps),
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def record_prov_relation(self,
                            session_id: str,
                            entities: List[Dict[str, Any]],
                            activities: List[Dict[str, Any]],
                            agents: List[Dict[str, Any]],
                            relations: List[Tuple[str, str, str]]) -> Dict[str, Any]:
        """记录 PROV 关系（文件级别追踪）

        Args:
            session_id: 会话ID
            entities: 实体列表 [{"entity_type": "dataset", "location": "...", "attributes": {...}}, ...]
            activities: 活动列表 [{"activity_type": "filter", "description": "...", "attributes": {...}}, ...]
            agents: 代理列表 [{"agent_type": "python_code", "name": "...", "attributes": {...}}, ...]
            relations: 关系列表 [(from_id, to_id, relation), ...] - 使用临时ID引用

        Returns:
            记录结果，包含生成的实际ID映射
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            # 获取会话目录
            tracker = self.sessions[session_id]
            session_dir = tracker.session_dir

            # 创建或加载 DAG
            dag_id = f"dag_{session_id}"
            dag_file = session_dir / "prov_dag.json"

            if dag_file.exists():
                dag = ProvDAG.load(session_dir)
            else:
                dag = ProvDAG(dag_id, session_dir)

            # 批量添加实体（系统自动生成ID）
            entity_id_mapping = dag.add_entities_from_list(entities)

            # 批量添加活动
            activity_id_mapping = dag.add_activities_from_list(activities)

            # 批量添加代理
            agent_id_mapping = dag.add_agents_from_list(agents)

            # 合并ID映射
            all_mappings = {**entity_id_mapping, **activity_id_mapping, **agent_id_mapping}

            # 批量添加关系（使用ID映射转换）
            dag.add_relations_from_list(relations, all_mappings)

            # 保存 DAG
            saved_files = dag.save()

            return {
                "status": "success",
                "dag_id": dag.dag_id,
                "id_mappings": all_mappings,
                "saved_files": saved_files,
                "statistics": dag.stats
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_prov_entity_lineage(self,
                                session_id: str,
                                entity_id: str) -> Dict[str, Any]:
        """获取实体的 PROV 溯源链

        Args:
            session_id: 会话ID
            entity_id: 实体ID

        Returns:
            溯源链信息
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            dag = ProvDAG.load(tracker.session_dir)

            lineage = dag.get_entity_lineage(entity_id)

            return {
                "lineage": lineage,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_prov_dag_overview(self, session_id: str) -> Dict[str, Any]:
        """获取 PROV DAG 概览

        Args:
            session_id: 会话ID

        Returns:
            DAG 概览信息
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            dag = ProvDAG.load(tracker.session_dir)

            # 按类型分组节点
            entities = dag.get_nodes_by_type("entity")
            activities = dag.get_nodes_by_type("activity")
            agents = dag.get_nodes_by_type("agent")

            return {
                "dag_id": dag.dag_id,
                "metadata": dag.metadata,
                "statistics": dag.stats,
                "nodes": {
                    "entities": [e["id"] for e in entities],
                    "activities": [a["id"] for a in activities],
                    "agents": [a["id"] for a in agents]
                },
                "edges": dag.edges,
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    def get_prov_node_detail(self,
                            session_id: str,
                            node_id: str) -> Dict[str, Any]:
        """获取 PROV 节点详情

        Args:
            session_id: 会话ID
            node_id: 节点ID

        Returns:
            节点详情
        """
        if session_id not in self.sessions:
            return {"error": "会话不存在"}

        try:
            tracker = self.sessions[session_id]
            dag = ProvDAG.load(tracker.session_dir)

            if node_id not in dag.nodes:
                return {"error": "节点不存在"}

            node = dag.nodes[node_id]

            # 获取相关的关系
            incoming = [e for e in dag.edges if e["to"] == node_id]
            outgoing = [e for e in dag.edges if e["from"] == node_id]

            return {
                "node": node,
                "relations": {
                    "incoming": incoming,
                    "outgoing": outgoing
                },
                "status": "success"
            }

        except Exception as e:
            return {"error": str(e), "status": "failed"}

    # ==================== 辅助方法 ====================

    def _generate_session_id(self) -> str:
        """生成唯一会话ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"session_{timestamp}"

    def _load_existing_sessions(self):
        """加载现有的会话（从磁盘恢复）"""
        if not self.base_dir.exists():
            return

        # 扫描所有 session_ 开头的目录
        for session_dir in self.base_dir.glob("session_*"):
            if not session_dir.is_dir():
                continue

            session_id = session_dir.name
            meta_file = session_dir / "meta.json"

            if meta_file.exists():
                try:
                    # 创建追踪器实例（不重新初始化）
                    tracker = LineageTracker.__new__(LineageTracker)
                    tracker.session_id = session_id
                    tracker.base_dir = self.base_dir
                    tracker.session_dir = session_dir

                    # 加载元数据
                    tracker.metadata = json.loads(meta_file.read_text(encoding='utf-8'))

                    self.sessions[session_id] = tracker
                except Exception as e:
                    print(f"警告: 无法加载会话 {session_id}: {e}")

    def get_session(self, session_id: str) -> Optional[LineageTracker]:
        """获取会话追踪器"""
        return self.sessions.get(session_id)

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话

        Returns:
            会话信息列表
        """
        session_list = []

        for session_dir in self.base_dir.glob("session_*"):
            if not session_dir.is_dir():
                continue

            meta_file = session_dir / "meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding='utf-8'))
                    session_list.append({
                        "session_id": session_dir.name,
                        "task_description": meta.get("task_description", ""),
                        "created_at": meta.get("created_at", ""),
                        "is_loaded": session_dir.name in self.sessions
                    })
                except:
                    pass

        return sorted(session_list, key=lambda x: x["created_at"], reverse=True)


# ==================== 服务器实例管理 ====================

# 使用字典管理多个服务器实例，支持不同 base_dir
_server_instances: Dict[str, OpenTraceServer] = {}


def get_server(base_dir: str = None) -> OpenTraceServer:
    """获取服务器实例（支持多实例）

    Args:
        base_dir: 基础目录，如果为 None 则使用默认路径
                 每个不同的 base_dir 会创建独立的服务器实例

    Returns:
        OpenTraceServer 实例

    注意：
        - 相同 base_dir 返回同一实例（单例模式）
        - 不同 base_dir 返回不同实例（支持多数据存储）
    """
    global _server_instances

    # 解析绝对路径作为键
    if base_dir is None:
        abs_dir = str(_get_default_base_dir())
    else:
        abs_dir = str(Path(base_dir).absolute())

    # 根据绝对路径返回实例
    if abs_dir not in _server_instances:
        _server_instances[abs_dir] = OpenTraceServer(base_dir=abs_dir)

    return _server_instances[abs_dir]


def list_all_servers() -> List[Dict[str, Any]]:
    """列出所有服务器实例

    Returns:
        服务器实例信息列表
    """
    result = []
    for base_dir, server in _server_instances.items():
        sessions = server.list_sessions()
        result.append({
            "base_dir": base_dir,
            "session_count": len(sessions),
            "sessions": [s["session_id"] for s in sessions]
        })
    return result


if __name__ == "__main__":
    # 测试服务器
    print("OpenTrace 服务器 (直接调用模式)")
    print("使用 get_server() 获取实例")
