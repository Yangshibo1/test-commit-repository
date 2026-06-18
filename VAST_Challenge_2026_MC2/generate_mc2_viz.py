"""
使用标准 prov_visualizer 生成 MC2 可视化
"""
import sys
from pathlib import Path

sys.path.insert(0, "C:/Users/83734/Desktop/opentrace")

from opentrace.prov_visualizer import visualize_prov_dag

session_dir = "C:/Users/83734/Desktop/opentrace/.opentrace/VAST_Challenge_2026_MC2/.opentrace/session_20260617_144434"
output_file = "C:/Users/83734/Desktop/opentrace/.opentrace/VAST_Challenge_2026_MC2/.opentrace/session_20260617_144434/mc2_prov_viz.txt"

print(f"生成标准可视化...")
print(f"会话: {session_dir}")
print(f"输出: {output_file}")

visualize_prov_dag(session_dir, output_file)

print(f"\n完成!")
