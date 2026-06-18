"""
生成 MC1 数据血缘可视化
"""
import sys
from pathlib import Path

sys.path.insert(0, "C:/Users/83734/Desktop/opentrace")

from opentrace.prov_visualizer import visualize_prov_dag

# 使用最新会话
session_dir = "C:/Users/83734/Desktop/opentrace/VAST_Challenge_2026_MC1/.opentrace/session_20260617_115027"
output_file = "C:/Users/83734/Desktop/opentrace/VAST_Challenge_2026_MC1/.opentrace/mc1_prov_viz.txt"

print(f"生成可视化...")
print(f"会话目录: {session_dir}")
print(f"输出文件: {output_file}")

visualize_prov_dag(session_dir, output_file)

print(f"\n可视化已生成!")
