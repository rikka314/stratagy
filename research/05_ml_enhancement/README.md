# 05 · ML Enhancement and Parameter Optimization

## Why this line started

After establishing baseline SM/FSM strategies, the goal was to enhance performance through machine learning: Bayesian optimization, genetic algorithms, and LightGBM filtering for parameter search and signal refinement.

## Frozen scope

- Markets: US and CN_A
- ML methods: Bayesian optimization, Genetic algorithm, Random search, LightGBM filter
- Integration: Optional ML filter branch in strategy pipeline
- Optimization target: Multi-objective (Sharpe, return, drawdown, coverage)

## Research flow

1. Implement Bayesian and Genetic parameter search alongside random baseline
2. Add LightGBM filter as optional preprocessing stage
3. Integrate ML filter into SM/FSM pipeline as conditional branch
4. Evaluate ML-enhanced variants against non-ML baselines
5. Freeze ML as research option, not automatic production upgrade

## Key decisions and ideas

- ML enhancement remains optional; it is not universally better
- Each variant is evaluated independently with its own artifact trail
- Search fairness requires equal budget across optimization methods
- Filter adds computational cost; may not improve all symbols

## Result

ML-enhanced variants (SM+Bayesian, FSM+Genetic, etc.) were included in the full-market baseline comparison. They ranked competitively but did not universally dominate non-ML variants. ML filter became a conditional branch rather than a required production component.

## Gate and current status

Status: `completed`. ML enhancement integrated as research-optional feature.

## Source files

- Planning: [`PARAM_OPTIMIZATION_FIX.md`](plans/PARAM_OPTIMIZATION_FIX.md), [`PARAM_OPTIMIZATION_UPGRADE.md`](plans/PARAM_OPTIMIZATION_UPGRADE.md), [`FILTER_FEATURE.md`](plans/FILTER_FEATURE.md), [`STRATEGY_IMPROVEMENT.md`](plans/STRATEGY_IMPROVEMENT.md)
- Code: `core/optimizer.py`, `core/ml_filter.py`, `core/fa_filter.py`
- Tests: `tests/test_optimizer_v2.py`, `tests/test_ml_filter_v2.py`

## Reproduction boundary

ML-enhanced strategy variants are materialized through the full-market baseline runner. Their performance is recorded in the baseline comparison, not claimed as standalone alpha.
