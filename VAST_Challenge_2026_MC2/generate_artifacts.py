#!/usr/bin/env python3
"""
LLM 数据产物生成脚本

将 VAST_Challenge_2026_MC2/src/ 中的脚本、数据集、报告文件
转换为结构化数据产物（.analysis.json），供前端使用。
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    print("错误: 需要安装 httpx")
    print("运行: pip install httpx")
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    print("警告: 未安装 python-dotenv，将使用系统环境变量")
    load_dotenv = lambda: None


# ==================== 配置 ====================

class Config:
    """配置管理"""

    def __init__(self):
        script_dir = Path(__file__).resolve().parent
        env_file = script_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        else:
            load_dotenv()

        self.api_base_url = os.getenv("LLM_API_BASE_URL", "https://hk.coin.hhm.moe")
        self.model = os.getenv("LLM_MODEL", "gpt-5.5")
        self.api_key = os.getenv("LLM_API_KEY", "")

        if not self.api_key:
            print("警告: LLM_API_KEY 未设置")

        # 默认值
        self.default_input_dir = Path("VAST_Challenge_2026_MC2/src")
        self.default_output_dir = Path("VAST_Challenge_2026_MC2/artifacts_llm")
        self.default_context_dir = Path("VAST_Challenge_2026_MC2/context")

        # 内容限制
        self.large_json_sample_items = 1000      # 大型 JSON 数组最大样例数量
        self.max_file_content_chars = 12000      # 传给 LLM 的最大文件内容字符数
        self.fallback_json_sample_items = 20     # 内容仍过大时保留的兜底样例数量

    @classmethod
    def from_env(cls) -> "Config":
        return cls()


# ==================== 文件类型识别 ====================

def summarize_json_data(data: Any, config: Config, fallback: bool = False) -> Any:
    """为大型 JSON 构建摘要和样例，避免把完整数据塞进 prompt。"""
    sample_size = config.fallback_json_sample_items if fallback else config.large_json_sample_items

    if isinstance(data, list):
        return {
            "_summary": {
                "json_type": "array",
                "total_items": len(data),
                "sample_items": min(len(data), sample_size),
                "fields": sorted(data[0].keys()) if data and isinstance(data[0], dict) else []
            },
            "sample_data": data[:sample_size]
        }

    if isinstance(data, dict):
        result = {"_summary": {"json_type": "object", "keys": list(data.keys())}}
        for key, value in data.items():
            if isinstance(value, list):
                result[key] = {
                    "_summary": {
                        "json_type": "array_field",
                        "total_items": len(value),
                        "sample_items": min(len(value), sample_size),
                        "fields": sorted(value[0].keys()) if value and isinstance(value[0], dict) else []
                    },
                    "sample_data": value[:sample_size]
                }
            else:
                result[key] = value
        return result

    return data


def truncate_file_content(content: str, file_path: Path, config: Config) -> str:
    """截断文件内容；大型 JSON 使用摘要 + 样例，避免 API 请求过大。"""
    if file_path.suffix.lower() == ".json":
        try:
            data = json.loads(content)
            summarized = summarize_json_data(data, config)
            summarized_text = json.dumps(summarized, ensure_ascii=False, indent=2)

            if summarized_text != content:
                print(f"  JSON 已整理为摘要 + 样例 ({len(summarized_text)} 字符)")

            if len(summarized_text) <= config.max_file_content_chars:
                return summarized_text

            fallback = summarize_json_data(data, config, fallback=True)
            fallback_text = json.dumps(fallback, ensure_ascii=False, indent=2)
            if len(fallback_text) <= config.max_file_content_chars:
                print(f"  JSON 摘要仍较大，兜底保留前 {config.fallback_json_sample_items} 条样例")
                return fallback_text

            print(f"  JSON 内容仍然较大 ({len(fallback_text)} 字符)，截断到 {config.max_file_content_chars} 字符")
            return fallback_text[:config.max_file_content_chars] + "\n\n...[内容已截断]..."
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  JSON 解析失败，使用原始内容: {e}")

    if len(content) > config.max_file_content_chars:
        print(f"  内容较大 ({len(content)} 字符)，截断到 {config.max_file_content_chars} 字符")
        return content[:config.max_file_content_chars] + "\n\n...[内容已截断]..."

    return content

def get_file_type(file_path: Path) -> Optional[str]:
    """根据文件扩展名确定类型"""
    suffix = file_path.suffix.lower()

    if file_path.name.endswith(".analysis.json"):
        return None

    if suffix == ".py":
        return "script"
    elif suffix == ".json":
        # 需要判断是数据集还是报告
        # 简单规则：包含 "report" 或 "analysis" 的认为是报告
        if "report" in file_path.name.lower() or "analysis" in file_path.name.lower():
            return "report"
        return "dataset"
    elif suffix == ".txt":
        # 可能是报告或可视化文本
        return "report"
    else:
        return None


# ==================== Prompt 模板加载 ====================

class PromptTemplate:
    """Prompt 模板管理"""

    REQUIRED_TEMPLATES = ("script", "dataset", "report")

    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self._templates = {}
        self._validate_templates()

    def _validate_templates(self):
        """检查外部模板是否齐全；缺失时直接报错，不自动创建。"""
        missing = [
            str(self.templates_dir / f"{file_type}_prompt.txt")
            for file_type in self.REQUIRED_TEMPLATES
            if not (self.templates_dir / f"{file_type}_prompt.txt").exists()
        ]
        if missing:
            raise ValueError("Prompt 模板文件缺失，请手动创建:\n" + "\n".join(missing))

    def get_template(self, file_type: str) -> str:
        """获取指定类型的 prompt 模板"""
        if file_type not in self._templates:
            template_file = self.templates_dir / f"{file_type}_prompt.txt"
            if not template_file.exists():
                raise ValueError(f"模板文件不存在: {template_file}")

            self._templates[file_type] = template_file.read_text(encoding="utf-8")

        return self._templates[file_type]


# ==================== 上下文加载 ====================

class ContextLoader:
    """全局上下文加载器"""

    def __init__(self, context_dir: Path):
        self.context_dir = context_dir
        self._context = None

    def load(self) -> Dict[str, Any]:
        """加载全局上下文"""
        if self._context is not None:
            return self._context

        self._context = {
            "background": "",
            "problems": []
        }

        # 加载背景（简化版本，只保留问题描述）
        background_file = self.context_dir / "background.md"
        if background_file.exists():
            content = background_file.read_text(encoding="utf-8")
            # 只保留问题描述部分，去除技术细节
            self._context["background"] = content

        # 加载问题列表
        problems_file = self.context_dir / "problems.json"
        if problems_file.exists():
            try:
                self._context["problems"] = json.loads(problems_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._context["problems"] = []

        return self._context


# ==================== LLM API 调用 ====================

class LLMClient:
    """LLM API 客户端"""

    def __init__(self, config: Config):
        self.config = config
        self.client = httpx.Client(timeout=120.0)  # 增加超时时间到120秒

    def _build_payload(self, prompt: str) -> Dict[str, Any]:
        """构建 API 请求负载"""
        return {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的数据分析师和可视化专家。输出严格的 JSON 格式，不要包含任何其他文字。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }

    def call(self, prompt: str, retry_count: int = 0) -> Optional[Dict[str, Any]]:
        """调用 LLM API，支持指数退避重试"""
        max_retries = 4
        base_delay = 1

        for attempt in range(max_retries):
            try:
                payload = self._build_payload(prompt)

                headers = {}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"

                response = self.client.post(
                    f"{self.config.api_base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers
                )

                response.raise_for_status()
                result = response.json()

                # 提取响应内容
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    print(f"调试: LLM 返回内容（前200字符）: {content[:200]}")

                    # 尝试解析 JSON
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError as e:
                        print(f"JSON 解析错误: {e}")
                        # 尝试提取 JSON 片段
                        content = content.strip()
                        if content.startswith("```json"):
                            content = content[7:]
                        if content.startswith("```"):
                            content = content[3:]
                        if content.endswith("```"):
                            content = content[:-3]

                        try:
                            return json.loads(content.strip())
                        except json.JSONDecodeError as e2:
                            print(f"清理后仍然无法解析 JSON: {e2}")
                            print(f"内容: {content[:500]}")
                            return None
                else:
                    print(f"警告: API 响应格式异常: {result}")
                    return None

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    print("错误: API 认证失败，请检查 LLM_API_KEY")
                    return None
                elif e.response.status_code == 429:
                    # 限流，延长等待时间
                    delay = base_delay * (2 ** attempt) * 2
                    print(f"限流，等待 {delay} 秒后重试...")
                    time.sleep(delay)
                else:
                    print(f"HTTP 错误: {e.response.status_code}")
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        print(f"等待 {delay} 秒后重试...")
                        time.sleep(delay)
                    else:
                        return None

            except (httpx.RequestError, httpx.TimeoutException) as e:
                print(f"网络错误: {e}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"等待 {delay} 秒后重试...")
                    time.sleep(delay)
                else:
                    return None

            except json.JSONDecodeError as e:
                print(f"JSON 解析错误: {e}")
                return None

        return None

    def close(self):
        """关闭客户端"""
        self.client.close()


# ==================== 文件处理 ====================

class FileProcessor:
    """文件处理器"""

    def __init__(
        self,
        config: Config,
        prompt_template: PromptTemplate,
        context_loader: ContextLoader,
        llm_client: LLMClient
    ):
        self.config = config
        self.prompt_template = prompt_template
        self.context_loader = context_loader
        self.llm_client = llm_client

        self.failed_files = []

    def get_output_path(self, input_file: Path, output_dir: Path) -> Path:
        """获取输出文件路径"""
        # 简化处理：只使用文件名，保持扁平结构
        # 如果需要保留子目录结构，可以根据 input_file 的相对路径来计算
        return output_dir / f"{input_file.stem}.analysis.json"

    def should_process(self, input_file: Path, output_file: Path, force: bool) -> bool:
        """判断是否需要处理该文件"""
        if force:
            return True
        return not output_file.exists()

    def build_prompt(
        self,
        file_type: str,
        file_path: Path,
        file_content: str,
        context: Dict[str, Any]
    ) -> str:
        """构建完整的 prompt"""
        template = self.prompt_template.get_template(file_type)

        # 加载上下文
        background = context.get("background", "")
        problems = context.get("problems", [])

        # 格式化问题列表
        problems_text = "\n".join([f"- {p}" for p in problems]) if problems else "无"

        return template.format(
            background=background,
            problems=problems_text,
            file_path=str(file_path),
            file_content=file_content,
            input_datasets="[]",
            output_datasets="[]"
        )

    def process_file(
        self,
        input_file: Path,
        output_file: Path,
        file_type: str,
        force: bool = False,
        index: int = 0,
        total: int = 0
    ) -> bool:
        """处理单个文件"""
        if not self.should_process(input_file, output_file, force):
            if total > 0:
                print(f"[{index}/{total}] 跳过（已存在）: {input_file.name}")
            else:
                print(f"跳过（已存在）: {input_file}")
            return True

        if total > 0:
            print(f"[{index}/{total}] 处理: {input_file.name} ({file_type})")
        else:
            print(f"处理: {input_file} ({file_type})")

        try:
            # 读取文件内容
            try:
                content = input_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = input_file.read_text(encoding="utf-8", errors="ignore")

            # 截断过大的文件内容
            content = truncate_file_content(content, input_file, self.config)

            # 加载上下文
            context = self.context_loader.load()

            # 构建 prompt
            prompt = self.build_prompt(file_type, input_file, content, context)

            # 检查 prompt 长度
            if len(prompt) > 15000:
                print(f"  警告: Prompt 太长 ({len(prompt)} 字符)，可能导致 API 错误")

            print(f"  Prompt 长度: {len(prompt)} 字符")

            # 调用 LLM
            result = self.llm_client.call(prompt)

            if result is None:
                print(f"失败: {input_file}")
                self.failed_files.append(str(input_file))
                return False

            # 只保存 content 部分
            output_data = result

            # 写入输出文件
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            print(f"成功: {input_file} -> {output_file}")
            return True

        except Exception as e:
            print(f"错误: {input_file} - {e}")
            self.failed_files.append(str(input_file))
            return False


# ==================== 主逻辑 ====================

def scan_files(
    input_dir: Path,
    file_type_filter: Optional[str] = None
) -> List[Tuple[Path, str]]:
    """扫描输入目录，返回待处理文件列表"""
    files = []

    for file_path in input_dir.rglob("*"):
        if file_path.is_file():
            ft = get_file_type(file_path)
            if ft and (file_type_filter is None or ft == file_type_filter):
                files.append((file_path, ft))

    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="LLM 数据产物生成脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本使用
  python generate_artifacts.py

  # 强制覆盖
  python generate_artifacts.py --force

  # 只处理脚本
  python generate_artifacts.py --type script

  # 自定义路径
  python generate_artifacts.py --input my_src/ --output my_artifacts/
        """
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("src"),
        help="输入源目录（默认: src）"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts_llm"),
        help="输出产物目录（默认: artifacts_llm）"
    )
    parser.add_argument(
        "--context-dir",
        type=Path,
        default=Path("context"),
        help="全局上下文目录（默认: context）"
    )
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=Path("templates"),
        help="Prompt 模板目录（默认: templates）"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖已存在的 .analysis.json"
    )
    parser.add_argument(
        "--type",
        choices=["script", "dataset", "report"],
        help="只处理特定类型文件"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="并发处理数量（默认: 1，暂不支持并发）"
    )

    args = parser.parse_args()

    # 加载配置
    config = Config.from_env()

    # 初始化组件
    templates_dir = args.templates_dir if args.templates_dir.is_absolute() else Path.cwd() / args.templates_dir
    context_dir = args.context_dir if args.context_dir.is_absolute() else Path.cwd() / args.context_dir
    prompt_template = PromptTemplate(templates_dir)
    context_loader = ContextLoader(context_dir)
    llm_client = LLMClient(config)
    file_processor = FileProcessor(config, prompt_template, context_loader, llm_client)

    # 扫描文件
    input_dir = args.input if args.input.is_absolute() else Path.cwd() / args.input
    output_dir = args.output if args.output.is_absolute() else Path.cwd() / args.output
    print(f"扫描输入目录: {input_dir}")
    files = scan_files(input_dir, args.type)
    print(f"找到 {len(files)} 个待处理文件")

    if not files:
        print("没有找到需要处理的文件")
        return

    # 处理文件
    success_count = 0
    total_files = len(files)
    for idx, (input_file, file_type) in enumerate(files, 1):
        output_file = file_processor.get_output_path(input_file, output_dir)
        if file_processor.process_file(input_file, output_file, file_type, args.force, idx, total_files):
            success_count += 1

    # 关闭客户端
    llm_client.close()

    # 输出结果
    print(f"\n处理完成:")
    print(f"  成功: {success_count}/{len(files)}")
    print(f"  失败: {len(file_processor.failed_files)}")

    if file_processor.failed_files:
        output_dir.mkdir(parents=True, exist_ok=True)
        failed_file = output_dir / "failed_files.txt"
        failed_file.write_text("\n".join(file_processor.failed_files), encoding="utf-8")
        print(f"  失败列表已保存到: {failed_file}")


if __name__ == "__main__":
    main()
