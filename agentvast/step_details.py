"""
Step Details - 步骤详情记录模块

记录每个分析步骤的详细信息，包括：
- 工作内容描述
- 生成的代码文件
- 运行的命令
- 参数配置
"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any


class StepDetailsRecorder:
    """步骤详情记录器"""

    def __init__(self, session_dir: str):
        """
        初始化记录器

        Args:
            session_dir: 会话目录
        """
        self.session_dir = Path(session_dir)
        self.details_file = self.session_dir / "step_details.json"
        self.steps = []

        # 加载现有记录
        if self.details_file.exists():
            with open(self.details_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.steps = data.get('steps', [])

    def record_step(
        self,
        step_id: str,
        step_name: str,
        description: str,
        code_generated: Optional[List[str]] = None,
        code_files: Optional[List[str]] = None,
        commands_run: Optional[List[str]] = None,
        input_files: Optional[List[str]] = None,
        output_files: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None
    ):
        """
        记录一个步骤的详情

        Args:
            step_id: 步骤ID (如 "step_1")
            step_name: 步骤名称 (如 "filter_events")
            description: 步骤工作内容描述
            code_generated: 生成的代码片段列表
            code_files: 生成的代码文件路径列表
            commands_run: 运行的命令列表
            input_files: 输入文件列表
            output_files: 输出文件列表
            parameters: 参数配置
        """
        step_detail = {
            "step_id": step_id,
            "step_name": step_name,
            "timestamp": datetime.now().isoformat(),
            "description": description,
            "code_generated": code_generated or [],
            "code_files": code_files or [],
            "commands_run": commands_run or [],
            "input_files": input_files or [],
            "output_files": output_files or [],
            "parameters": parameters or {}
        }

        self.steps.append(step_detail)
        self._save()

        return step_detail

    def _save(self):
        """保存到文件"""
        data = {
            "session_id": self.session_dir.name,
            "created_at": datetime.now().isoformat(),
            "total_steps": len(self.steps),
            "steps": self.steps
        }

        with open(self.details_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_step(self, step_id: str) -> Optional[Dict]:
        """获取指定步骤的详情"""
        for step in self.steps:
            if step['step_id'] == step_id:
                return step
        return None

    def list_steps(self) -> List[Dict]:
        """列出所有步骤"""
        return self.steps

    def generate_summary(self) -> str:
        """生成步骤摘要文本"""
        lines = []
        lines.append("=" * 70)
        lines.append("分析步骤详情")
        lines.append("=" * 70)

        for i, step in enumerate(self.steps, 1):
            lines.append(f"\n步骤 {i}: {step['step_name']}")
            lines.append(f"ID: {step['step_id']}")
            lines.append(f"时间: {step['timestamp']}")
            lines.append(f"\n描述: {step['description']}")

            if step['code_files']:
                lines.append(f"\n生成的代码文件:")
                for f in step['code_files']:
                    lines.append(f"  - {f}")

            if step['code_generated']:
                lines.append(f"\n生成的代码片段:")
                for code in step['code_generated']:
                    lines.append(f"  {code}")

            if step['commands_run']:
                lines.append(f"\n运行的命令:")
                for cmd in step['commands_run']:
                    lines.append(f"  $ {cmd}")

            if step['input_files']:
                lines.append(f"\n输入文件: {', '.join(step['input_files'])}")

            if step['output_files']:
                lines.append(f"\n输出文件: {', '.join(step['output_files'])}")

            if step['parameters']:
                lines.append(f"\n参数:")
                for k, v in step['parameters'].items():
                    lines.append(f"  {k}: {v}")

            lines.append("-" * 70)

        return "\n".join(lines)


def record_step_details(
    session_dir: str,
    step_id: str,
    step_name: str,
    description: str,
    code_generated: Optional[List[str]] = None,
    code_files: Optional[List[str]] = None,
    commands_run: Optional[List[str]] = None,
    input_files: Optional[List[str]] = None,
    output_files: Optional[List[str]] = None,
    parameters: Optional[Dict[str, Any]] = None
):
    """
    记录步骤详情的便捷函数

    Args:
        session_dir: 会话目录
        step_id: 步骤ID
        step_name: 步骤名称
        description: 工作内容描述
        code_generated: 生成的代码片段
        code_files: 生成的代码文件路径
        commands_run: 运行的命令
        input_files: 输入文件
        output_files: 输出文件
        parameters: 参数配置

    Returns:
        记录的步骤详情字典
    """
    recorder = StepDetailsRecorder(session_dir)
    return recorder.record_step(
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


if __name__ == "__main__":
    # 测试
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 记录几个步骤
        record_step_details(
            session_dir=tmpdir,
            step_id="step_1",
            step_name="load_data",
            description="加载原始 MC2 数据集",
            code_files=["step1_load_data.py"],
            commands_run=["python step1_load_data.py"],
            input_files=["MC2 data.json"],
            output_files=["loaded_data.json"],
            parameters={"file_type": "json", "encoding": "utf-8"}
        )

        record_step_details(
            session_dir=tmpdir,
            step_id="step_2",
            step_name="filter_events",
            description="过滤出 SwiftWren 相关事件",
            code_generated=["filtered = [e for e in events if 'swiftwren' in str(e).lower()]"],
            code_files=["step2_filter.py"],
            commands_run=["python step2_filter.py"],
            input_files=["loaded_data.json"],
            output_files=["filtered_events.json"],
            parameters={"filter": "swiftwren", "fields": ["id", "when", "parties"]}
        )

        # 生成摘要
        recorder = StepDetailsRecorder(tmpdir)
        print(recorder.generate_summary())
