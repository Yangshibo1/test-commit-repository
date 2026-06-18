"""
核心血缘追踪器

针对160万行JSON数据优化的轻量级实现
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class Mapping:
    """映射关系"""
    from_ids: List[str]
    to_id: str
    operation: str
    timestamp: str
    value_info: Optional[Dict[str, Any]] = None


@dataclass
class ProcessingRecord:
    """数据处理记录"""
    processing_id: str
    step_id: str
    timestamp: str
    input: Dict[str, Any]
    algorithm: Dict[str, Any]
    result: Dict[str, Any]


@dataclass
class StepRecord:
    """步骤记录"""
    step_id: str
    step_name: str
    operation: str
    description: str
    timestamp: str
    metadata: Optional[Dict[str, Any]] = None
    mappings: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.mappings is None:
            self.mappings = []
        if self.metadata is None:
            self.metadata = {}


class LineageTracker:
    """轻量级血缘追踪器"""

    def __init__(self, session_id: str, base_dir: str = ".opentrace"):
        self.session_id = session_id
        self.base_dir = Path(base_dir)
        self.session_dir = self.base_dir / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.current_step = 0
        self.steps: List[StepRecord] = []

        # 元信息
        self.metadata = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "total_steps": 0
        }

    # ==================== 初始化 ====================

    def init_from_json(self, json_path: str, sample_size: int = 1000) -> Dict[str, Any]:
        """从JSON初始化（懒生成ID，只采样结构）"""

        # 加载数据
        data = self._load_json(json_path)

        # 分析数据规模
        total_rows = len(data) if isinstance(data, list) else 1
        total_size = Path(json_path).stat().st_size if Path(json_path).exists() else 0

        # 采样分析结构
        sample = data[:sample_size] if isinstance(data, list) else data
        structure = self._analyze_json_structure(sample)

        # 记录初始步骤
        step_record = StepRecord(
            step_id="step_000",
            step_name="数据加载",
            operation="load_json",
            description=f"从 {json_path} 加载JSON数据",
            timestamp=datetime.now().isoformat(),
            metadata={
                "source": json_path,
                "total_rows": total_rows,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "structure": structure,
                "sample_size": sample_size,
                "lazy_id_generation": True
            }
        )

        self._add_step(step_record)

        # 保存工作副本
        working_copy = self.session_dir / "working_data.json"
        self._save_json(data, working_copy)

        # 保存元信息
        self._save_metadata()

        return {
            "status": "initialized",
            "session_id": self.session_id,
            "total_rows": total_rows,
            "structure": structure,
            "working_copy": str(working_copy)
        }

    def init_from_csv(self, csv_path: str, sample_size: int = 1000) -> Dict[str, Any]:
        """从CSV初始化"""
        try:
            import pandas as pd
        except ImportError:
            return {"error": "需要安装 pandas: pip install pandas"}

        # 读取数据
        df = pd.read_csv(csv_path)

        # 分析结构
        structure = {
            "type": "dataframe",
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "shape": df.shape,
            "sample": df.head(min(sample_size, len(df))).to_dict("records")
        }

        # 记录初始步骤
        step_record = StepRecord(
            step_id="step_000",
            step_name="数据加载",
            operation="load_csv",
            description=f"从 {csv_path} 加载CSV数据",
            timestamp=datetime.now().isoformat(),
            metadata={
                "source": csv_path,
                "total_rows": len(df),
                "total_cols": len(df.columns),
                "structure": structure,
                "sample_size": sample_size
            }
        )

        self._add_step(step_record)

        # 保存工作副本
        working_copy = self.session_dir / "working_data.csv"
        df.to_csv(working_copy, index=False)

        self._save_metadata()

        return {
            "status": "initialized",
            "session_id": self.session_id,
            "total_rows": len(df),
            "total_cols": len(df.columns),
            "structure": structure,
            "working_copy": str(working_copy)
        }

    # ==================== 步骤记录 ====================

    def record_step(self,
                   step_name: str,
                   operation: str,
                   description: str = "",
                   metadata: Dict[str, Any] = None) -> str:
        """记录一个处理步骤"""

        self.current_step += 1
        step_id = f"step_{self.current_step:03d}"

        step_record = StepRecord(
            step_id=step_id,
            step_name=step_name,
            operation=operation,
            description=description,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )

        self._add_step(step_record)
        return step_id

    def record_mapping(self,
                      step_id: str,
                      from_ids: List[str],
                      to_id: str,
                      operation: str,
                      value_info: Dict[str, Any] = None) -> None:
        """记录映射关系到指定步骤"""

        # 查找步骤
        step_record = next((s for s in self.steps if s.step_id == step_id), None)
        if not step_record:
            raise ValueError(f"步骤不存在: {step_id}")

        # 添加映射
        mapping = Mapping(
            from_ids=from_ids,
            to_id=to_id,
            operation=operation,
            timestamp=datetime.now().isoformat(),
            value_info=value_info
        )

        step_record.mappings.append(asdict(mapping))
        self._save_step(step_record)

    def record_step_with_mappings(self,
                                  step_name: str,
                                  operation: str,
                                  description: str,
                                  mappings: List[Dict[str, Any]],
                                  metadata: Dict[str, Any] = None) -> str:
        """记录步骤和映射（一步完成）"""

        step_id = self.record_step(step_name, operation, description, metadata)

        for mapping in mappings:
            self.record_mapping(
                step_id,
                mapping["from"],
                mapping["to"],
                mapping["operation"],
                mapping.get("value_info")
            )

        return step_id

    # ==================== 数据处理记录 ====================

    def record_processing(self,
                         step_id: str,
                         input_spec: Dict[str, Any],
                         algorithm_spec: Dict[str, Any],
                         result_data: Dict[str, Any],
                         large_result_threshold: int = 1000) -> str:
        """记录数据处理步骤（包含 input/algorithm/result 三要素）

        Args:
            step_id: 关联的步骤ID
            input_spec: 输入规格
                - source: 数据来源标识
                - source_type: 数据类型 (json_array, dataframe, etc.)
                - filter_condition: 筛选条件 (可选)
                - total_count_before: 处理前的数据量 (可选)
                - reference: 引用的数据文件 (可选)
            algorithm_spec: 算法规格
                - type: 算法类型 (filter, aggregate, transform, etc.)
                - language: 实现语言 (python, sql, etc.)
                - code: 代码片段
                - logic_description: 算法逻辑描述
            result_data: 结果数据
                - 包含处理结果的字典，会根据大小自动决定内嵌或外存
            large_result_threshold: 超过这个数量就外存为文件

        Returns:
            processing_id: 处理记录ID
        """

        processing_id = f"processing_{step_id}"

        # 判断结果大小并决定存储方式
        result_ref = self._prepare_result_storage(
            processing_id,
            result_data,
            large_result_threshold
        )

        # 创建处理记录
        processing_record = ProcessingRecord(
            processing_id=processing_id,
            step_id=step_id,
            timestamp=datetime.now().isoformat(),
            input=input_spec,
            algorithm=algorithm_spec,
            result=result_ref
        )

        # 保存处理记录
        self._save_processing(processing_record)

        return processing_id

    def _prepare_result_storage(self, processing_id: str, result_data: Dict[str, Any],
                               threshold: int) -> Dict[str, Any]:
        """根据结果大小决定存储方式

        Args:
            processing_id: 处理记录ID
            result_data: 结果数据
            threshold: 内嵌/外存的阈值

        Returns:
            result引用结构
        """

        # 估算结果大小
        total_items = 0
        for key, value in result_data.items():
            if isinstance(value, list):
                total_items += len(value)
            elif isinstance(value, dict):
                total_items += len(value)

        if total_items > threshold:
            # 外存为单独文件
            result_file = self.session_dir / f"{processing_id}_result.json"
            self._save_json(result_data, result_file)

            return {
                "format": "external_file",
                "file": str(result_file.name),
                "item_count": total_items,
                "statistics": self._extract_statistics(result_data)
            }
        else:
            # 内嵌
            return {
                "format": "inline",
                "data": result_data,
                "item_count": total_items
            }

    def _extract_statistics(self, result_data: Dict[str, Any]) -> Dict[str, Any]:
        """从结果数据中提取统计信息"""
        stats = {}

        for key, value in result_data.items():
            if isinstance(value, list):
                stats[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                stats[f"{key}_keys"] = list(value.keys())
            elif isinstance(value, (int, float)):
                stats[key] = value

        return stats

    def _save_processing(self, processing_record: ProcessingRecord) -> None:
        """保存处理记录到文件"""
        processing_file = self.session_dir / f"{processing_record.processing_id}.json"
        self._save_json(asdict(processing_record), processing_file)

    def get_processing_detail(self, processing_id: str) -> Optional[Dict[str, Any]]:
        """获取处理记录详情

        Args:
            processing_id: 处理记录ID

        Returns:
            处理记录详情，如果存在外存文件则自动加载
        """

        processing_file = self.session_dir / f"{processing_id}.json"
        if not processing_file.exists():
            return None

        # 加载处理记录（指定UTF-8编码）
        record = json.loads(processing_file.read_text(encoding='utf-8'))

        # 如果结果是外存文件，加载它
        if record.get("result", {}).get("format") == "external_file":
            result_file_name = record["result"]["file"]
            result_file = self.session_dir / result_file_name
            if result_file.exists():
                record["result"]["data"] = json.loads(result_file.read_text(encoding='utf-8'))

        return record

    def list_processings(self, step_id: str = None) -> List[Dict[str, Any]]:
        """列出处理记录

        Args:
            step_id: 可选，筛选特定步骤的处理记录

        Returns:
            处理记录列表
        """

        processings = []
        try:
            processing_files = sorted(self.session_dir.glob("processing_*.json"))

            for pf in processing_files:
                try:
                    record = json.loads(pf.read_text(encoding='utf-8'))
                    if step_id is None or record.get("step_id") == step_id:
                        processings.append({
                            "processing_id": record.get("processing_id", "unknown"),
                            "step_id": record.get("step_id", "unknown"),
                            "timestamp": record.get("timestamp", ""),
                            "algorithm_type": record.get("algorithm", {}).get("type"),
                            "result_format": record.get("result", {}).get("format"),
                            "item_count": record.get("result", {}).get("item_count")
                        })
                except Exception as e:
                    # 跳过有问题的文件
                    continue
        except Exception as e:
            # 如果整体失败，返回空列表
            pass

        return processings

    # ==================== 追踪查询 ====================

    def trace_element(self, element_id: str, max_depth: int = 50) -> List[Dict[str, Any]]:
        """追踪数据元素的完整血缘链"""

        chain = []
        visited = set()

        def recursive_trace(current_id: str, steps_from_now: int, depth: int):
            if depth > max_depth or current_id in visited:
                return
            visited.add(current_id)

            # 从后往前查找步骤
            for i in range(len(self.steps) - 1 - steps_from_now, -1, -1):
                step = self.steps[i]

                # 查找映射
                for mapping in step.mappings:
                    if mapping["to_id"] == current_id:
                        chain.append({
                            "step": step.step_name,
                            "step_id": step.step_id,
                            "operation": mapping["operation"],
                            "from": mapping["from_ids"],
                            "to": mapping["to_id"],
                            "timestamp": mapping["timestamp"],
                            "value_info": mapping.get("value_info")
                        })

                        # 递归追踪所有来源
                        for source_id in mapping["from_ids"]:
                            recursive_trace(source_id, len(self.steps) - i - 1, depth + 1)
                        return

        recursive_trace(element_id, 0, 0)
        return list(reversed(chain))

    def trace_row(self, row_id: str) -> List[Dict[str, Any]]:
        """追踪行的命运"""

        journey = []

        for step in self.steps:
            # 查找行相关的映射
            for mapping in step.mappings:
                # 检查映射中是否包含此行
                if any(row_id in str(from_id) for from_id in mapping["from_ids"]):
                    journey.append({
                        "step": step.step_name,
                        "step_id": step.step_id,
                        "from": mapping["from_ids"],
                        "to": mapping["to_id"],
                        "operation": mapping["operation"],
                        "timestamp": mapping["timestamp"]
                    })
                    break

        return journey

    # ==================== 错误分析 ====================

    def analyze_error(self,
                     error_message: str,
                     affected_element: str = None,
                     context: Dict[str, Any] = None) -> Dict[str, Any]:
        """分析错误来源"""

        analysis = {
            "error_message": error_message,
            "affected_element": affected_element,
            "timestamp": datetime.now().isoformat(),
            "lineage_chain": [],
            "possible_sources": [],
            "suggestions": []
        }

        if affected_element:
            # 追踪元素血缘
            chain = self.trace_element(affected_element)
            analysis["lineage_chain"] = chain

            # 分析最近的操作
            if chain:
                recent_operations = chain[-5:] if len(chain) >= 5 else chain

                for op in reversed(recent_operations):
                    operation_desc = op["operation"].lower()

                    # 除法相关
                    if "div" in operation_desc or "/" in operation_desc:
                        analysis["possible_sources"].append({
                            "step": op["step"],
                            "reason": "可能存在除零错误",
                            "operation": op["operation"]
                        })

                    # 填充相关
                    if "fillna" in operation_desc or "fill" in operation_desc:
                        analysis["possible_sources"].append({
                            "step": op["step"],
                            "reason": "填充策略可能不当",
                            "operation": op["operation"]
                        })

                    # 类型转换
                    if "astype" in operation_desc or "cast" in operation_desc:
                        analysis["possible_sources"].append({
                            "step": op["step"],
                            "reason": "类型转换可能失败",
                            "operation": op["operation"]
                        })

        # 检查最近的步骤（即使没有血缘信息）
        recent_steps = self.steps[-3:] if len(self.steps) >= 3 else self.steps

        for step in recent_steps:
            if "filter" in step.operation.lower():
                analysis["possible_sources"].append({
                    "step": step.step_name,
                    "reason": "过滤操作可能移除了必要数据",
                    "operation": step.operation
                })

        # 生成建议
        if analysis["possible_sources"]:
            for source in analysis["possible_sources"][:3]:  # 最多3个建议
                if "除零" in source["reason"]:
                    analysis["suggestions"].append("检查除数是否为0，添加除零保护")
                elif "填充" in source["reason"]:
                    analysis["suggestions"].append("检查填充策略，确保填充值合理")
                elif "过滤" in source["reason"]:
                    analysis["suggestions"].append("检查过滤条件，确认没有过度过滤")

        return analysis

    # ==================== 会话管理 ====================

    def get_session_summary(self) -> Dict[str, Any]:
        """获取会话概览"""

        return {
            "session_id": self.session_id,
            "created_at": self.metadata["created_at"],
            "total_steps": len(self.steps),
            "steps": [
                {
                    "step_id": s.step_id,
                    "name": s.step_name,
                    "operation": s.operation,
                    "mappings_count": len(s.mappings),
                    "timestamp": s.timestamp
                }
                for s in self.steps
            ]
        }

    def get_step_detail(self, step_id: str) -> Optional[Dict[str, Any]]:
        """获取步骤详情"""

        step_record = next((s for s in self.steps if s.step_id == step_id), None)
        if not step_record:
            return None

        return {
            "step_id": step_record.step_id,
            "step_name": step_record.step_name,
            "operation": step_record.operation,
            "description": step_record.description,
            "timestamp": step_record.timestamp,
            "metadata": step_record.metadata,
            "mappings": step_record.mappings,
            "mappings_count": len(step_record.mappings)
        }

    def export_session(self, format: str = "json") -> str:
        """导出会话数据"""

        export_data = {
            "metadata": self.metadata,
            "steps": [asdict(s) for s in self.steps]
        }

        export_file = self.session_dir / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"

        if format == "json":
            export_file.write_text(json.dumps(export_data, indent=2, ensure_ascii=False))
        else:
            raise ValueError(f"不支持的格式: {format}")

        return str(export_file)

    # ==================== 辅助方法 ====================

    def _load_json(self, path: str) -> Any:
        """加载JSON文件（支持大数据流式读取）"""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_json(self, data: Any, path: Path) -> None:
        """保存JSON文件"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _analyze_json_structure(self, data: Any, prefix: str = "") -> Dict[str, Any]:
        """分析JSON结构（不生成ID，只分析结构）"""

        if isinstance(data, list):
            return self._analyze_list_structure(data, prefix)
        elif isinstance(data, dict):
            return self._analyze_dict_structure(data, prefix)
        else:
            return {"type": type(data).__name__, "value": data}

    def _analyze_list_structure(self, data: list, prefix: str = "") -> Dict[str, Any]:
        """分析列表结构"""

        if not data:
            return {"type": "empty_list"}

        # 分析第一个元素
        first_item = data[0]

        structure = {
            "type": "list",
            "length": len(data),
            "item_type": type(first_item).__name__
        }

        # 如果元素是对象，分析其字段
        if isinstance(first_item, dict):
            fields = {}
            for key, value in first_item.items():
                field_path = f"{prefix}[0].{key}" if prefix else f"[0].{key}"
                fields[key] = self._analyze_json_structure(value, field_path)
            structure["fields"] = fields

        return structure

    def _analyze_dict_structure(self, data: dict, prefix: str = "") -> Dict[str, Any]:
        """分析字典结构"""

        structure = {
            "type": "dict",
            "keys": list(data.keys())
        }

        # 分析每个值的类型
        field_types = {}
        for key, value in data.items():
            field_path = f"{prefix}.{key}" if prefix else key
            field_types[key] = {
                "type": type(value).__name__,
                "path": field_path
            }

            # 如果是嵌套结构，递归分析
            if isinstance(value, (dict, list)):
                field_types[key]["structure"] = self._analyze_json_structure(value, field_path)

        structure["fields"] = field_types
        return structure

    def _add_step(self, step_record: StepRecord) -> None:
        """添加步骤并保存"""
        self.steps.append(step_record)
        self.metadata["total_steps"] = len(self.steps)
        self._save_step(step_record)
        self._save_metadata()

    def _save_step(self, step_record: StepRecord) -> None:
        """保存步骤到文件"""
        step_file = self.session_dir / f"{step_record.step_id}.json"
        self._save_json(asdict(step_record), step_file)

    def _save_metadata(self) -> None:
        """保存元信息"""
        metadata_file = self.session_dir / "meta.json"
        self._save_json(self.metadata, metadata_file)

    @classmethod
    def load_session(cls, session_id: str, base_dir: str = ".opentrace") -> 'LineageTracker':
        """加载已有会话"""
        session_dir = Path(base_dir) / session_id
        metadata_file = session_dir / "meta.json"

        if not metadata_file.exists():
            raise ValueError(f"会话不存在: {session_id}")

        metadata = json.loads(metadata_file.read_text())
        tracker = cls(session_id, base_dir)
        tracker.metadata = metadata

        # 加载所有步骤
        step_files = sorted(session_dir.glob("step_*.json"))
        for step_file in step_files:
            step_data = json.loads(step_file.read_text())
            # 重建 StepRecord
            step_record = StepRecord(**step_data)
            tracker.steps.append(step_record)

        tracker.current_step = len(tracker.steps)

        return tracker
