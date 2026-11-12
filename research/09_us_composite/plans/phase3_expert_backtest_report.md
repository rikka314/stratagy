# Phase 3 专家回测报告

> Returns use `strategy_return` semantics with execution costs charged once in this research runner.

## Metrics

| expert_id           |   coverage |    sharpe |   total_return |   max_drawdown |   win_rate |
|:--------------------|-----------:|----------:|---------------:|---------------:|-----------:|
| momentum_optimized  |       2349 |  0.718527 |       0.196242 |     -0.0521505 |   0.536824 |
| mean_reversion      |       2349 |  0.13199  |       0.045252 |     -0.0899342 |   0.496381 |
| macro_defensive     |       2349 |  1.20889  |       0.756431 |     -0.0865693 |   0.558536 |
| volume_confirmed    |       2349 | -0.380892 |      -0.129308 |     -0.156158  |   0.494679 |
| composite_optimized |       2349 |  1.08314  |       5.18315  |     -0.349555  |   0.555981 |
| cash                |       2349 |  0        |       0        |      0         |   0        |

## Decision

- Status: `failed`
- Average correlation: `0.200042`
- Distinct fold winners: `1`
- Composite Sharpe improvement over Phase 2: `0.093420`
- Residual average Spearman correlation: `0.067484`
- Maximum absolute SPY beta: `0.925134`

A full frozen-universe run is formal Phase 3 evidence.
