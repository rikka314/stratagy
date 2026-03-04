"""
参数优化模块
============
预设评估、随机搜索、贝叶斯优化（Optuna）、遗传算法优化。
"""

import numpy as np
import pandas as pd
import streamlit as st

from core.config import _PRESET_PARAMS_FOR_OPTIMIZATION
from core.indicators import add_indicators
from core.signals import compute_signals
from core.backtest import simulate_strategy, sharpe_ratio, max_drawdown


def evaluate_presets_for_optimization(
    df_raw: pd.DataFrame,
    split_idx: int,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
) -> tuple[dict, str, list[tuple[str, float]]]:
    """
    快速评估 3 个预设策略在训练集上的表现，返回最佳预设参数。
    用于贝叶斯优化/遗传算法热启动。
    """
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx

    best_score = -np.inf
    best_name = ""
    best_params = None
    scores = []

    for name, params in _PRESET_PARAMS_FOR_OPTIMIZATION.items():
        try:
            df_ind = add_indicators(
                df_raw,
                rsi_period=params["rsi_period"],
                macd_fast=params["macd_fast"],
                macd_slow=params["macd_slow"],
                macd_signal=params["macd_signal"],
                ema_fast=params["ema_fast"],
                ema_slow=params["ema_slow"],
                adx_period=params["adx_period"],
                atr_period=params["atr_period"],
                bb_period=params["bb_period"],
                bb_std=params["bb_std"],
                indicator_period=params["indicator_period"],
            )
            df_sig = compute_signals(
                df_ind,
                rsi_lower=params["rsi_lower"],
                rsi_upper=params["rsi_upper"],
                adx_threshold=params["adx_threshold"],
                momentum_short=momentum_short,
                momentum_long=momentum_long,
                score_lookback=score_lookback,
                score_mid_pct=score_mid_pct,
                score_high_pct=score_high_pct,
                weight_mom_short=weight_mom_short,
                weight_mom_long=weight_mom_long,
                weight_macd=weight_macd,
                weight_rsi=weight_rsi,
                weight_vol=weight_vol,
                entry_threshold=params["entry_threshold"],
                exit_threshold=params["exit_threshold"],
                use_trend_filter=use_trend_filter,
                use_strength_filter=use_strength_filter,
                use_rsi_filter=use_rsi_filter,
                use_macd_filter=use_macd_filter,
                weight_bb=params["weight_bb"],
                weight_obv=params["weight_obv"],
                weight_volume=params["weight_volume"],
                weight_price=params["weight_price"],
                weight_drawdown=params["weight_drawdown"],
                exit_min_signals=2,
                entry_min_signals=3,
            )

            train_sim = simulate_strategy(
                df_sig.iloc[:sub_train_end],
                initial_position=0,
                stop_loss_mult=params["stop_loss_mult"],
                take_profit_mult=params["take_profit_mult"],
            )
            train_return = train_sim["strategy_equity"].iloc[-1] - 1
            train_sharpe = sharpe_ratio(train_sim["strategy_return"])
            train_dd = max_drawdown(train_sim["strategy_equity"])
            train_score = train_sharpe + train_return - abs(train_dd) * 0.5

            if sub_train_end < split_idx:
                val_sim = simulate_strategy(
                    df_sig.iloc[sub_train_end:split_idx],
                    initial_position=0,
                    stop_loss_mult=params["stop_loss_mult"],
                    take_profit_mult=params["take_profit_mult"],
                )
                val_return = val_sim["strategy_equity"].iloc[-1] - 1
                val_sharpe = sharpe_ratio(val_sim["strategy_return"])
                val_dd = max_drawdown(val_sim["strategy_equity"])
                val_score = val_sharpe + val_return - abs(val_dd) * 0.5
                score = 0.4 * train_score + 0.6 * val_score - 0.3 * abs(train_score - val_score)
            else:
                score = train_score

            scores.append((name, score))
            if score > best_score:
                best_score = score
                best_name = name
                best_params = params.copy()
        except Exception:
            scores.append((name, -np.inf))

    return best_params or {}, best_name, scores


def random_search_params(
    df_indicators: pd.DataFrame,
    split_idx: int,
    rsi_lower: float,
    rsi_upper: float,
    adx_threshold: float,
    momentum_short: int,
    momentum_long: int,
    score_lookback: int,
    score_mid_pct: float,
    score_high_pct: float,
    weight_mom_short: float,
    weight_mom_long: float,
    weight_macd: float,
    weight_rsi: float,
    weight_vol: float,
    trials: int,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    progress_callback=None,
) -> dict | None:
    """
    随机搜索最优参数（含防过拟合：子验证集 + 正则化）
    """
    rng = np.random.default_rng(7)
    best = None
    
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx
    
    _rs_param_defaults = {
        "entry_threshold": (0.5, -1.0, 1.5), "exit_threshold": (-0.5, -1.5, 0.5),
        "adx_threshold": (20, 10, 35), "stop_loss_mult": (2.0, 0.0, 4.0),
        "take_profit_mult": (4.0, 0.0, 6.0),
    }
    
    for trial_i in range(trials):
        if progress_callback:
            progress_callback(trial_i, trials)
        
        entry_threshold = round(rng.uniform(-1.0, 1.5), 2)
        exit_threshold = round(rng.uniform(-1.5, 0.5), 2)
        
        if entry_threshold <= exit_threshold:
            continue
        
        adx_candidate = round(rng.uniform(10, 35), 0)
        stop_loss_mult = round(rng.uniform(0.0, 4.0), 1)
        take_profit_mult = round(rng.uniform(0.0, 6.0), 1)
        
        df_signals = compute_signals(
            df_indicators,
            rsi_lower=rsi_lower,
            rsi_upper=rsi_upper,
            adx_threshold=adx_candidate,
            momentum_short=momentum_short,
            momentum_long=momentum_long,
            score_lookback=score_lookback,
            score_mid_pct=score_mid_pct,
            score_high_pct=score_high_pct,
            weight_mom_short=weight_mom_short,
            weight_mom_long=weight_mom_long,
            weight_macd=weight_macd,
            weight_rsi=weight_rsi,
            weight_vol=weight_vol,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            use_trend_filter=use_trend_filter,
            use_strength_filter=use_strength_filter,
            use_rsi_filter=use_rsi_filter,
            use_macd_filter=use_macd_filter,
            exit_min_signals=2,
            entry_min_signals=3,
        )
        
        train_sim = simulate_strategy(
            df_signals.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=stop_loss_mult,
            take_profit_mult=take_profit_mult,
        )
        
        train_return = train_sim["strategy_equity"].iloc[-1] - 1
        train_sharpe = sharpe_ratio(train_sim["strategy_return"])
        train_score = train_sharpe + train_return
        
        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                df_signals.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=stop_loss_mult,
                take_profit_mult=take_profit_mult,
            )
            val_return = val_sim["strategy_equity"].iloc[-1] - 1
            val_sharpe = sharpe_ratio(val_sim["strategy_return"])
            val_score = val_sharpe + val_return
            score = 0.4 * train_score + 0.6 * val_score - 0.3 * abs(train_score - val_score)
        else:
            score = train_score
            val_sharpe = train_sharpe
            val_return = train_return
        
        reg_penalty = 0.0
        for pname, pval in [("entry_threshold", entry_threshold), ("exit_threshold", exit_threshold),
                            ("adx_threshold", adx_candidate), ("stop_loss_mult", stop_loss_mult),
                            ("take_profit_mult", take_profit_mult)]:
            if pname in _rs_param_defaults:
                default, lo, hi = _rs_param_defaults[pname]
                span = hi - lo
                if span > 0:
                    reg_penalty += ((pval - default) / span) ** 2
        score -= 0.02 * reg_penalty
        
        if best is None or score > best["score"]:
            best = {
                "score": score,
                "sharpe": train_sharpe,
                "return": train_return,
                "val_sharpe": val_sharpe,
                "val_return": val_return,
                "adx_threshold": adx_candidate,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "stop_loss_mult": stop_loss_mult,
                "take_profit_mult": take_profit_mult,
            }
    
    return best


def bayesian_optimize_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    n_trials: int,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    progress_callback=None,
    seed_params: dict | None = None,
) -> dict | None:
    """
    使用贝叶斯优化（Optuna）搜索最优参数（含热启动 + 防过拟合）
    """
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        st.error("需要安装 optuna 库。请运行：pip install optuna")
        return None
    
    best_result = {"score": -np.inf}
    
    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx
    
    _param_defaults = {
        "ema_fast": (12, 5, 50), "ema_slow": (60, 20, 200),
        "macd_fast": (12, 5, 20), "macd_slow": (26, 10, 40), "macd_signal": (9, 5, 20),
        "rsi_period": (14, 5, 30), "rsi_lower": (30, 10, 50), "rsi_upper": (70, 50, 90),
        "adx_period": (14, 5, 30), "atr_period": (14, 5, 30),
        "bb_period": (20, 5, 50), "bb_std": (2.0, 1.0, 3.0), "indicator_period": (20, 5, 60),
        "entry_threshold": (0.5, -1.0, 2.0), "exit_threshold": (-0.5, -2.0, 0.5),
        "adx_threshold": (20, 10, 35), "stop_loss_mult": (2.0, 0.5, 4.0), "take_profit_mult": (4.0, 1.0, 6.0),
        "weight_bb": (0.8, 0.0, 2.0), "weight_obv": (1.0, 0.0, 2.0),
        "weight_volume": (0.6, 0.0, 1.5), "weight_price": (0.7, 0.0, 1.5), "weight_drawdown": (0.5, 0.0, 1.5),
    }
    
    def _regularization_penalty(params_dict: dict, lam: float = 0.02) -> float:
        penalty = 0.0
        for name, value in params_dict.items():
            if name in _param_defaults:
                default, lo, hi = _param_defaults[name]
                span = hi - lo
                if span > 0:
                    penalty += ((value - default) / span) ** 2
        return lam * penalty
    
    def objective(trial):
        ema_fast = trial.suggest_int("ema_fast", 5, 50)
        ema_slow = trial.suggest_int("ema_slow", 20, 200)
        if ema_fast >= ema_slow:
            return -np.inf
        
        macd_fast = trial.suggest_int("macd_fast", 5, 20)
        macd_slow = trial.suggest_int("macd_slow", 10, 40)
        macd_signal = trial.suggest_int("macd_signal", 5, 20)
        if macd_fast >= macd_slow:
            return -np.inf
        
        rsi_period = trial.suggest_int("rsi_period", 5, 30)
        rsi_lower = trial.suggest_float("rsi_lower", 10, 50)
        rsi_upper = trial.suggest_float("rsi_upper", 50, 90)
        
        adx_period = trial.suggest_int("adx_period", 5, 30)
        atr_period = trial.suggest_int("atr_period", 5, 30)
        
        bb_period = trial.suggest_int("bb_period", 5, 50)
        bb_std = trial.suggest_float("bb_std", 1.0, 3.0)
        indicator_period = trial.suggest_int("indicator_period", 5, 60)
        
        entry_threshold = trial.suggest_float("entry_threshold", -1.0, 2.0)
        exit_threshold = trial.suggest_float("exit_threshold", -2.0, 0.5)
        if entry_threshold <= exit_threshold:
            return -np.inf
        
        adx_candidate = trial.suggest_float("adx_threshold", 10, 35)
        stop_loss_mult = trial.suggest_float("stop_loss_mult", 0.5, 4.0)
        take_profit_mult = trial.suggest_float("take_profit_mult", 1.0, 6.0)
        
        weight_bb = trial.suggest_float("weight_bb", 0.0, 2.0)
        weight_obv = trial.suggest_float("weight_obv", 0.0, 2.0)
        weight_volume = trial.suggest_float("weight_volume", 0.0, 1.5)
        weight_price = trial.suggest_float("weight_price", 0.0, 1.5)
        weight_drawdown = trial.suggest_float("weight_drawdown", 0.0, 1.5)
        
        try:
            df_indicators = add_indicators(
                df_raw,
                rsi_period=rsi_period,
                macd_fast=macd_fast, macd_slow=macd_slow, macd_signal=macd_signal,
                ema_fast=ema_fast, ema_slow=ema_slow,
                adx_period=adx_period, atr_period=atr_period,
                bb_period=bb_period, bb_std=bb_std,
                indicator_period=indicator_period,
            )
        except Exception:
            return -np.inf
        
        df_signals = compute_signals(
            df_indicators,
            rsi_lower=rsi_lower, rsi_upper=rsi_upper,
            adx_threshold=adx_candidate,
            momentum_short=momentum_short, momentum_long=momentum_long,
            score_lookback=score_lookback,
            score_mid_pct=score_mid_pct, score_high_pct=score_high_pct,
            weight_mom_short=weight_mom_short, weight_mom_long=weight_mom_long,
            weight_macd=weight_macd, weight_rsi=weight_rsi, weight_vol=weight_vol,
            entry_threshold=entry_threshold, exit_threshold=exit_threshold,
            use_trend_filter=use_trend_filter, use_strength_filter=use_strength_filter,
            use_rsi_filter=use_rsi_filter, use_macd_filter=use_macd_filter,
            weight_bb=weight_bb, weight_obv=weight_obv,
            weight_volume=weight_volume, weight_price=weight_price,
            weight_drawdown=weight_drawdown,
            exit_min_signals=2, entry_min_signals=3,
        )
        
        train_sim = simulate_strategy(
            df_signals.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=stop_loss_mult, take_profit_mult=take_profit_mult,
        )
        
        train_return = train_sim["strategy_equity"].iloc[-1] - 1
        train_sharpe = sharpe_ratio(train_sim["strategy_return"])
        train_dd = max_drawdown(train_sim["strategy_equity"])
        train_score = train_sharpe + train_return - abs(train_dd) * 0.5
        
        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                df_signals.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=stop_loss_mult, take_profit_mult=take_profit_mult,
            )
            val_return = val_sim["strategy_equity"].iloc[-1] - 1
            val_sharpe = sharpe_ratio(val_sim["strategy_return"])
            val_dd = max_drawdown(val_sim["strategy_equity"])
            val_score = val_sharpe + val_return - abs(val_dd) * 0.5
            
            blended_score = 0.4 * train_score + 0.6 * val_score
            gap_penalty = 0.3 * abs(train_score - val_score)
            score = blended_score - gap_penalty
        else:
            score = train_score
            val_sharpe = train_sharpe
            val_return = train_return
            val_dd = train_dd
        
        trial_params = {
            "ema_fast": ema_fast, "ema_slow": ema_slow,
            "macd_fast": macd_fast, "macd_slow": macd_slow, "macd_signal": macd_signal,
            "rsi_period": rsi_period, "rsi_lower": rsi_lower, "rsi_upper": rsi_upper,
            "adx_period": adx_period, "atr_period": atr_period,
            "bb_period": bb_period, "bb_std": bb_std, "indicator_period": indicator_period,
            "entry_threshold": entry_threshold, "exit_threshold": exit_threshold,
            "adx_threshold": adx_candidate, "stop_loss_mult": stop_loss_mult,
            "take_profit_mult": take_profit_mult,
            "weight_bb": weight_bb, "weight_obv": weight_obv,
            "weight_volume": weight_volume, "weight_price": weight_price,
            "weight_drawdown": weight_drawdown,
        }
        score -= _regularization_penalty(trial_params)
        
        nonlocal best_result
        if score > best_result["score"]:
            best_result = {
                "score": score,
                "sharpe": train_sharpe, "return": train_return, "max_drawdown": train_dd,
                "val_sharpe": val_sharpe, "val_return": val_return, "val_max_drawdown": val_dd,
                **trial_params,
            }
        
        return score
    
    study = optuna.create_study(direction="maximize")
    
    if seed_params:
        _seed_trial = {}
        _optuna_param_keys = [
            "ema_fast", "ema_slow", "macd_fast", "macd_slow", "macd_signal",
            "rsi_period", "rsi_lower", "rsi_upper", "adx_period", "atr_period",
            "bb_period", "bb_std", "indicator_period",
            "entry_threshold", "exit_threshold", "adx_threshold",
            "stop_loss_mult", "take_profit_mult",
            "weight_bb", "weight_obv", "weight_volume", "weight_price", "weight_drawdown",
        ]
        for k in _optuna_param_keys:
            if k in seed_params:
                _seed_trial[k] = seed_params[k]
        if _seed_trial:
            study.enqueue_trial(_seed_trial)
    
    _trial_counter = [0]
    def _optuna_callback(study, trial):
        _trial_counter[0] += 1
        if progress_callback:
            progress_callback(_trial_counter[0], n_trials)
    
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False, callbacks=[_optuna_callback])
    
    return best_result if best_result["score"] > -np.inf else None


def genetic_algorithm_optimize_params(
    df_raw: pd.DataFrame,
    split_idx: int,
    population_size: int = 30,
    generations: int = 20,
    crossover_rate: float = 0.8,
    mutation_rate: float = 0.2,
    momentum_short: int = 5,
    momentum_long: int = 20,
    score_lookback: int = 30,
    score_mid_pct: float = 0.6,
    score_high_pct: float = 0.8,
    weight_mom_short: float = 1.0,
    weight_mom_long: float = 1.0,
    weight_macd: float = 1.0,
    weight_rsi: float = 0.5,
    weight_vol: float = 0.5,
    use_trend_filter: bool = True,
    use_strength_filter: bool = True,
    use_rsi_filter: bool = True,
    use_macd_filter: bool = True,
    progress_callback=None,
    seed_params: dict | None = None,
) -> dict | None:
    """
    使用遗传算法搜索最优参数（含热启动 + 多核并行 + 精英保留 + 防过拟合）
    """
    rng = np.random.default_rng(42)

    sub_train_end = int(split_idx * 0.7)
    if sub_train_end < 50:
        sub_train_end = split_idx

    _param_space = {
        "ema_fast":         (12,   5,   50,  "int"),
        "ema_slow":         (60,   20,  200, "int"),
        "macd_fast":        (12,   5,   20,  "int"),
        "macd_slow":        (26,   10,  40,  "int"),
        "macd_signal":      (9,    5,   20,  "int"),
        "rsi_period":       (14,   5,   30,  "int"),
        "rsi_lower":        (30.0, 10,  50,  "float"),
        "rsi_upper":        (70.0, 50,  90,  "float"),
        "adx_period":       (14,   5,   30,  "int"),
        "atr_period":       (14,   5,   30,  "int"),
        "bb_period":        (20,   5,   50,  "int"),
        "bb_std":           (2.0,  1.0, 3.0, "float"),
        "indicator_period": (20,   5,   60,  "int"),
        "entry_threshold":  (0.5,  -1.0, 2.0,  "float"),
        "exit_threshold":   (-0.5, -2.0, 0.5,  "float"),
        "adx_threshold":    (20.0, 10,   35,   "float"),
        "stop_loss_mult":   (2.0,  0.5,  4.0,  "float"),
        "take_profit_mult": (4.0,  1.0,  6.0,  "float"),
        "weight_bb":        (0.8, 0.0, 2.0, "float"),
        "weight_obv":       (1.0, 0.0, 2.0, "float"),
        "weight_volume":    (0.6, 0.0, 1.5, "float"),
        "weight_price":     (0.7, 0.0, 1.5, "float"),
        "weight_drawdown":  (0.5, 0.0, 1.5, "float"),
    }
    param_names = list(_param_space.keys())

    def _random_individual():
        ind = {}
        for name, (default, lo, hi, ptype) in _param_space.items():
            val = rng.uniform(lo, hi)
            if ptype == "int":
                val = int(round(val))
            ind[name] = val
        return ind

    def _clip_individual(ind):
        for name, (default, lo, hi, ptype) in _param_space.items():
            val = np.clip(ind[name], lo, hi)
            if ptype == "int":
                val = int(round(val))
            ind[name] = val if ptype != "int" else int(val)
        return ind

    def _is_valid(ind):
        if ind["ema_fast"] >= ind["ema_slow"]:
            return False
        if ind["macd_fast"] >= ind["macd_slow"]:
            return False
        if ind["entry_threshold"] <= ind["exit_threshold"]:
            return False
        return True

    def _regularization_penalty(ind, lam=0.02):
        penalty = 0.0
        for name, (default, lo, hi, ptype) in _param_space.items():
            span = hi - lo
            if span > 0:
                penalty += ((ind[name] - default) / span) ** 2
        return lam * penalty

    def _evaluate(ind):
        if not _is_valid(ind):
            return -np.inf

        try:
            df_indicators = add_indicators(
                df_raw,
                rsi_period=int(ind["rsi_period"]),
                macd_fast=int(ind["macd_fast"]), macd_slow=int(ind["macd_slow"]),
                macd_signal=int(ind["macd_signal"]),
                ema_fast=int(ind["ema_fast"]), ema_slow=int(ind["ema_slow"]),
                adx_period=int(ind["adx_period"]), atr_period=int(ind["atr_period"]),
                bb_period=int(ind["bb_period"]), bb_std=ind["bb_std"],
                indicator_period=int(ind["indicator_period"]),
            )
        except Exception:
            return -np.inf

        df_signals = compute_signals(
            df_indicators,
            rsi_lower=ind["rsi_lower"], rsi_upper=ind["rsi_upper"],
            adx_threshold=ind["adx_threshold"],
            momentum_short=momentum_short, momentum_long=momentum_long,
            score_lookback=score_lookback,
            score_mid_pct=score_mid_pct, score_high_pct=score_high_pct,
            weight_mom_short=weight_mom_short, weight_mom_long=weight_mom_long,
            weight_macd=weight_macd, weight_rsi=weight_rsi, weight_vol=weight_vol,
            entry_threshold=ind["entry_threshold"], exit_threshold=ind["exit_threshold"],
            use_trend_filter=use_trend_filter, use_strength_filter=use_strength_filter,
            use_rsi_filter=use_rsi_filter, use_macd_filter=use_macd_filter,
            weight_bb=ind["weight_bb"], weight_obv=ind["weight_obv"],
            weight_volume=ind["weight_volume"], weight_price=ind["weight_price"],
            weight_drawdown=ind["weight_drawdown"],
            exit_min_signals=2, entry_min_signals=3,
        )

        train_sim = simulate_strategy(
            df_signals.iloc[:sub_train_end],
            initial_position=0,
            stop_loss_mult=ind["stop_loss_mult"], take_profit_mult=ind["take_profit_mult"],
        )

        train_return = train_sim["strategy_equity"].iloc[-1] - 1
        train_sharpe = sharpe_ratio(train_sim["strategy_return"])
        train_dd = max_drawdown(train_sim["strategy_equity"])
        train_score = train_sharpe + train_return - abs(train_dd) * 0.5

        if sub_train_end < split_idx:
            val_sim = simulate_strategy(
                df_signals.iloc[sub_train_end:split_idx],
                initial_position=0,
                stop_loss_mult=ind["stop_loss_mult"], take_profit_mult=ind["take_profit_mult"],
            )
            val_return = val_sim["strategy_equity"].iloc[-1] - 1
            val_sharpe = sharpe_ratio(val_sim["strategy_return"])
            val_dd = max_drawdown(val_sim["strategy_equity"])
            val_score = val_sharpe + val_return - abs(val_dd) * 0.5

            blended_score = 0.4 * train_score + 0.6 * val_score
            gap_penalty = 0.3 * abs(train_score - val_score)
            score = blended_score - gap_penalty
        else:
            score = train_score

        score -= _regularization_penalty(ind)
        return score

    def _get_result_dict(ind, score):
        if not _is_valid(ind):
            return None
        try:
            df_indicators = add_indicators(
                df_raw,
                rsi_period=int(ind["rsi_period"]),
                macd_fast=int(ind["macd_fast"]), macd_slow=int(ind["macd_slow"]),
                macd_signal=int(ind["macd_signal"]),
                ema_fast=int(ind["ema_fast"]), ema_slow=int(ind["ema_slow"]),
                adx_period=int(ind["adx_period"]), atr_period=int(ind["atr_period"]),
                bb_period=int(ind["bb_period"]), bb_std=ind["bb_std"],
                indicator_period=int(ind["indicator_period"]),
            )
            df_signals = compute_signals(
                df_indicators,
                rsi_lower=ind["rsi_lower"], rsi_upper=ind["rsi_upper"],
                adx_threshold=ind["adx_threshold"],
                momentum_short=momentum_short, momentum_long=momentum_long,
                score_lookback=score_lookback,
                score_mid_pct=score_mid_pct, score_high_pct=score_high_pct,
                weight_mom_short=weight_mom_short, weight_mom_long=weight_mom_long,
                weight_macd=weight_macd, weight_rsi=weight_rsi, weight_vol=weight_vol,
                entry_threshold=ind["entry_threshold"], exit_threshold=ind["exit_threshold"],
                use_trend_filter=use_trend_filter, use_strength_filter=use_strength_filter,
                use_rsi_filter=use_rsi_filter, use_macd_filter=use_macd_filter,
                weight_bb=ind["weight_bb"], weight_obv=ind["weight_obv"],
                weight_volume=ind["weight_volume"], weight_price=ind["weight_price"],
                weight_drawdown=ind["weight_drawdown"],
                exit_min_signals=2, entry_min_signals=3,
            )
            train_sim = simulate_strategy(
                df_signals.iloc[:sub_train_end],
                initial_position=0,
                stop_loss_mult=ind["stop_loss_mult"], take_profit_mult=ind["take_profit_mult"],
            )
            train_return = train_sim["strategy_equity"].iloc[-1] - 1
            train_sharpe = sharpe_ratio(train_sim["strategy_return"])
            train_dd = max_drawdown(train_sim["strategy_equity"])

            if sub_train_end < split_idx:
                val_sim = simulate_strategy(
                    df_signals.iloc[sub_train_end:split_idx],
                    initial_position=0,
                    stop_loss_mult=ind["stop_loss_mult"], take_profit_mult=ind["take_profit_mult"],
                )
                val_return = val_sim["strategy_equity"].iloc[-1] - 1
                val_sharpe = sharpe_ratio(val_sim["strategy_return"])
                val_dd = max_drawdown(val_sim["strategy_equity"])
            else:
                val_sharpe = train_sharpe
                val_return = train_return
                val_dd = train_dd
        except Exception:
            return None

        return {
            "score": score,
            "sharpe": train_sharpe, "return": train_return, "max_drawdown": train_dd,
            "val_sharpe": val_sharpe, "val_return": val_return, "val_max_drawdown": val_dd,
            "ema_fast": int(ind["ema_fast"]), "ema_slow": int(ind["ema_slow"]),
            "macd_fast": int(ind["macd_fast"]), "macd_slow": int(ind["macd_slow"]),
            "macd_signal": int(ind["macd_signal"]),
            "rsi_period": int(ind["rsi_period"]),
            "rsi_lower": ind["rsi_lower"], "rsi_upper": ind["rsi_upper"],
            "adx_period": int(ind["adx_period"]), "atr_period": int(ind["atr_period"]),
            "bb_period": int(ind["bb_period"]), "bb_std": ind["bb_std"],
            "indicator_period": int(ind["indicator_period"]),
            "adx_threshold": ind["adx_threshold"],
            "entry_threshold": ind["entry_threshold"], "exit_threshold": ind["exit_threshold"],
            "stop_loss_mult": ind["stop_loss_mult"], "take_profit_mult": ind["take_profit_mult"],
            "weight_bb": ind["weight_bb"], "weight_obv": ind["weight_obv"],
            "weight_volume": ind["weight_volume"], "weight_price": ind["weight_price"],
            "weight_drawdown": ind["weight_drawdown"],
            "_method": "genetic_algorithm",
        }

    def _tournament_select(population, fitnesses, k=3):
        indices = rng.choice(len(population), size=k, replace=False)
        best_idx = indices[0]
        for idx in indices[1:]:
            if fitnesses[idx] > fitnesses[best_idx]:
                best_idx = idx
        return population[best_idx].copy()

    def _blx_alpha_crossover(parent1, parent2, alpha=0.5):
        child = {}
        for name in param_names:
            p1, p2 = parent1[name], parent2[name]
            lo_val, hi_val = min(p1, p2), max(p1, p2)
            span = hi_val - lo_val
            new_lo = lo_val - alpha * span
            new_hi = hi_val + alpha * span
            child[name] = rng.uniform(new_lo, new_hi)
        return _clip_individual(child)

    def _gaussian_mutate(ind, rate):
        mutated = ind.copy()
        for name, (default, lo, hi, ptype) in _param_space.items():
            if rng.random() < rate:
                span = hi - lo
                noise = rng.normal(0, span * 0.1)
                mutated[name] = ind[name] + noise
        return _clip_individual(mutated)

    # 初始化种群
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import multiprocessing
    _max_workers = min(multiprocessing.cpu_count(), population_size, 8)

    population = []

    if seed_params:
        seed_ind = {}
        for name, (default, lo, hi, ptype) in _param_space.items():
            val = seed_params.get(name, default)
            if ptype == "int":
                val = int(round(val))
            seed_ind[name] = val
        seed_ind = _clip_individual(seed_ind)
        if _is_valid(seed_ind):
            population.append(seed_ind)

        for _ in range(3):
            mutated_seed = _gaussian_mutate(seed_ind.copy(), 0.5)
            if _is_valid(mutated_seed):
                population.append(mutated_seed)

    max_init_attempts = population_size * 10
    attempts = 0
    while len(population) < population_size and attempts < max_init_attempts:
        ind = _random_individual()
        if _is_valid(ind):
            population.append(ind)
        attempts += 1
    if len(population) < population_size:
        return None

    total_evals = population_size + generations * population_size
    current_eval = [0]

    def _eval_and_track(ind):
        return _evaluate(ind)

    # 并行评估初始种群
    fitnesses = [0.0] * len(population)
    with ThreadPoolExecutor(max_workers=_max_workers) as executor:
        future_to_idx = {executor.submit(_eval_and_track, ind): i for i, ind in enumerate(population)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            fitnesses[idx] = future.result()
            current_eval[0] += 1
            if progress_callback:
                progress_callback(current_eval[0], total_evals)

    # 进化循环
    elite_count = 2
    best_ever_score = -np.inf
    best_ever_ind = None

    for gen in range(generations):
        gen_best_idx = int(np.argmax(fitnesses))
        if fitnesses[gen_best_idx] > best_ever_score:
            best_ever_score = fitnesses[gen_best_idx]
            best_ever_ind = population[gen_best_idx].copy()

        sorted_indices = np.argsort(fitnesses)[::-1]
        new_population = [population[i].copy() for i in sorted_indices[:elite_count]]
        new_fitnesses = [fitnesses[i] for i in sorted_indices[:elite_count]]

        children_to_eval = []
        while len(new_population) + len(children_to_eval) < population_size:
            parent1 = _tournament_select(population, fitnesses)
            parent2 = _tournament_select(population, fitnesses)

            if rng.random() < crossover_rate:
                child = _blx_alpha_crossover(parent1, parent2)
            else:
                child = parent1.copy()

            child = _gaussian_mutate(child, mutation_rate)

            for _ in range(5):
                if _is_valid(child):
                    break
                child = _gaussian_mutate(_random_individual(), mutation_rate)

            if not _is_valid(child):
                child = _random_individual()
                if not _is_valid(child):
                    continue

            children_to_eval.append(child)

        child_fitnesses = [0.0] * len(children_to_eval)
        with ThreadPoolExecutor(max_workers=_max_workers) as executor:
            future_to_idx = {executor.submit(_eval_and_track, c): i for i, c in enumerate(children_to_eval)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                child_fitnesses[idx] = future.result()
                current_eval[0] += 1
                if progress_callback:
                    progress_callback(current_eval[0], total_evals)

        new_population.extend(children_to_eval)
        new_fitnesses.extend(child_fitnesses)

        population = new_population
        fitnesses = new_fitnesses

    final_best_idx = int(np.argmax(fitnesses))
    if fitnesses[final_best_idx] > best_ever_score:
        best_ever_score = fitnesses[final_best_idx]
        best_ever_ind = population[final_best_idx].copy()

    if best_ever_ind is None or best_ever_score <= -np.inf:
        return None

    return _get_result_dict(best_ever_ind, best_ever_score)
