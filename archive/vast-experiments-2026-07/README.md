# VAST 2026-07 实验测试归档

本目录中的测试来自早期 VAST 专题分析，当前不参与 `pytest tests/`：

- `test_draw_john_intervention_network.py`
- `test_extract_three_txt_posting_chains_dataset.py`
- `test_q6_john_posting_intervention_network.mjs`
- `test_vast_core_visualizations.py`
- `test_vast_full_chain_189.py`

其中部分断言依赖旧输出结构或特定渲染实现，重新启用前必须先与当前
`VAST_Challenge_2026_MC2/src` 对齐。仍有效的回归测试应迁入 `tests/vast/`，而不是直接从本
目录执行。
