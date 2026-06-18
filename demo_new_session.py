"""演示：新 session 自动记录"""

from opentrace.mcp_server import OpenTraceServer

# 创建第一个 session
server = OpenTraceServer('.opentrace_demo')

session1 = server.init_session(
    task_description="分析数据集A",
    data_path="test_data.json",
    data_type="json"
)

print(f"Session 1: {session1['session_id']}")
# 创建 .opentrace_demo/session_20260615_HHMMSS/

# 记录一些操作
server.record_step(
    session1['session_id'],
    "筛选数据",
    "filter",
    "筛选有效记录"
)

print(f"  → 记录了1个步骤")

# 创建第二个 session（完全独立）
session2 = server.init_session(
    task_description="分析数据集B",
    data_path="test_data.json",
    data_type="json"
)

print(f"\nSession 2: {session2['session_id']}")
# 创建 .opentrace_demo/session_20260615_HHMMSS_NEW/

# 记录不同的操作
server.record_step(
    session2['session_id'],
    "聚合统计",
    "aggregate",
    "计算平均值"
)

print(f"  → 记录了1个步骤")

# 两个 session 互不干扰
print(f"\n两个 session 的数据是独立的：")
print(f"  - Session 1 有自己的步骤文件")
print(f"  - Session 2 有自己的步骤文件")
print(f"  - 互不影响，完全隔离")

print(f"\n查看目录：")
print(f"  ls .opentrace_demo/")
print(f"  → 会看到两个独立的 session 目录")
