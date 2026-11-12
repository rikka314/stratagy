# Fresh 测试结果

- 日期：2026-08-23
- 命令：`.venv\\Scripts\\python.exe -m pytest -q`
- 结果：`562 passed, 5 failed, 2 warnings in 44.69s`
- 通过率：约 99.1%（562 / 567），测试矩阵未全绿。

## 失败项

1. `tests/test_composite_integration.py::TestFallbackMechanisms::test_insufficient_training_samples`
   - 预期：训练样本不足提示。
   - 实际：先触发 `rsi_z` 缺失率校验，错误消息契约不一致。
2. `tests/test_composite_integration.py::TestBacktestConsistency::test_equity_curve_monotonic_with_positive_returns`
   - 预期：结果包含 `equity` 列。
   - 实际：当前实现输出 `strategy_equity`。
3. `tests/test_composite_integration.py::TestBacktestConsistency::test_evaluation_metrics_present`
   - 预期：评估结果包含 `volatility`。
   - 实际：当前评估字典未提供该键。
4. `tests/test_refetch_us_snapshot_akshare.py::test_refetch_success_writes_relative_manifest_paths`
   - 实际：Windows 下临时目录替换触发 `PermissionError: [WinError 5]`。
5. `tests/test_web_performance_contracts.py::test_home_renders_shell_before_three_parallel_data_fragments`
   - 预期：源码包含 3 个 `@st.fragment(parallel=True)`。
   - 实际：当前首页实现为 0，属于历史性能契约与当前代码不一致。

## 警告

两项警告来自 `torch.nn.TransformerEncoder` 的 nested tensor / `norm_first` 组合，不影响测试执行完成，但应在后续模型实现中复核。
