#!/usr/bin/env python3
"""
OpenTrace 命令行工具

用法：
    python opentrace_cli.py start              # 启动交互式追踪
    python opentrace_cli.py status            # 查看当前会话
    python opentrace_cli.py export <session>  # 导出会话
    python opentrace_cli.py list              # 列出所有会话
"""

import sys
import json
from pathlib import Path
from opentrace.mcp_server import OpenTraceServer


def cmd_start():
    """启动交互式追踪会话"""
    server = OpenTraceServer('.opentrace')

    print("=" * 60)
    print("OpenTrace 交互式追踪会话")
    print("=" * 60)

    # 询问任务描述
    task = input("任务描述: ")
    data_path = input("数据文件路径: ")
    data_type = input("数据类型 (json/csv) [默认: json]: ") or "json"

    # 初始化会话
    result = server.init_session(task, data_path, data_type)

    if "error" in result:
        print(f"错误: {result['error']}")
        return None

    session_id = result['session_id']

    print(f"\n[OK] 会话已创建: {session_id}")
    print(f"数据行数: {result.get('total_rows', 'N/A')}")
    print(f"\n会话存储在: .opentrace/{session_id}/")

    print("\n现在你可以在代码中使用这个 session_id 进行追踪")

    return session_id


def cmd_status():
    """查看当前会话状态"""
    base_dir = Path('.opentrace')

    if not base_dir.exists():
        print("没有找到任何会话")
        return

    sessions = sorted([d for d in base_dir.iterdir() if d.is_dir()])

    if not sessions:
        print("没有找到任何会话")
        return

    print(f"找到 {len(sessions)} 个会话：\n")

    for session_dir in sessions[-5:]:  # 显示最近5个
        meta_file = session_dir / "meta.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding='utf-8'))
            print(f"  会话: {meta['session_id']}")
            print(f"    创建时间: {meta['created_at']}")
            print(f"    步骤数: {meta['total_steps']}")
            print()


def cmd_export(session_id):
    """导出指定会话"""
    server = OpenTraceServer('.opentrace')

    # 检查会话是否存在
    session_dir = Path('.opentrace') / session_id
    if not session_dir.exists():
        print(f"会话不存在: {session_id}")
        return

    # 加载会话
    try:
        from opentrace.tracker import LineageTracker
        tracker = LineageTracker.load_session(session_id, '.opentrace')
        export_path = tracker.export_session()
        print(f"[OK] 会话已导出: {export_path}")
    except Exception as e:
        print(f"导出失败: {e}")


def cmd_list():
    """列出所有会话"""
    cmd_status()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "start":
        cmd_start()
    elif command == "status":
        cmd_status()
    elif command == "export":
        if len(sys.argv) < 3:
            print("用法: opentrace_cli.py export <session_id>")
            return
        cmd_export(sys.argv[2])
    elif command == "list":
        cmd_list()
    else:
        print(f"未知命令: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
