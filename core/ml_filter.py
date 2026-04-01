"""
ML 信号过滤层
==============
基于 SM/FSM 产生的买入信号构建训练样本，并用 Logistic / LightGBM
过滤低置信度开仓信号。
"""

from __future__ import annotations

import os
from collections import namedtuple
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - 仅在缺少依赖时触发
    LGBMClassifier = None


MLModel = namedtuple("MLModel", ["model", "scaler", "model_type", "threshold"])


@dataclass(frozen=True)
class FeatureBundle:
    feature_table: pd.DataFrame
    future_return_frame: pd.DataFrame
    horizon: int
    min_excess_samples: int
    row_count: int

ML_FEATURE_COLUMNS = (
    "factor_score",
    "factor_percentile",
    "target_position",
    "mom_short_z",
    "mom_long_z",
    "macd_z",
    "rsi_z",
    "vol_z",
    "bb_position_rank",
    "obv_trend_rank",
    "volume_ratio_rank",
    "price_position_rank",
    "drawdown_rank",
    "rsi",
    "macd",
    "signal",
    "adx",
    "atr_pct",
    "volume_ratio",
    "bb_position",
    "bb_width",
    "price_position",
    "drawdown",
    "trend_ok",
    "strength_ok",
    "rsi_ok",
    "macd_above",
    "entry_count",
    "ema_spread_pct",
)

ML_METADATA_COLUMNS = (
    "signal_pos",
    "date",
)

ML_LABEL_COLUMNS = (
    "ml_label",
    "label_mode",
    "future_strategy_return",
    "future_naive_return",
    "future_excess_return",
)

_REQUIRED_SIGNAL_COLUMNS = (
    "close",
    "target_position",
    "factor_score",
    "factor_percentile",
    "mom_short_z",
    "mom_long_z",
    "macd_z",
    "rsi_z",
    "vol_z",
    "bb_position_rank",
    "obv_trend_rank",
    "volume_ratio_rank",
    "price_position_rank",
    "drawdown_rank",
    "rsi",
    "macd",
    "signal",
    "adx",
    "atr",
    "volume_ratio",
    "bb_position",
    "bb_width",
    "price_position",
    "drawdown",
    "trend_ok",
    "strength_ok",
    "rsi_ok",
    "ema_fast",
    "ema_slow",
)


def _resolve_ml_n_jobs(default_jobs: int) -> int:
    env_value = os.getenv("STRATAGY_ML_MAX_WORKERS")
    if env_value is None or env_value == "":
        return int(default_jobs)
    try:
        parsed = int(env_value)
    except Exception:
        return int(default_jobs)
    return max(1, parsed)


class _ConstantProbabilityModel:
    """训练样本退化到单一类别时的稳定兜底模型。"""

    def __init__(self, positive_probability: float) -> None:
        prob = float(np.clip(positive_probability, 0.0, 1.0))
        self.positive_probability_ = prob
        self.classes_ = np.array([0, 1], dtype=int)

    def predict_proba(self, x: pd.DataFrame | np.ndarray) -> np.ndarray:
        n_samples = len(x)
        proba_pos = np.full(n_samples, self.positive_probability_, dtype=float)
        return np.column_stack([1.0 - proba_pos, proba_pos])


def _coerce_numeric(series: pd.Series, default: float = 0.0) -> pd.Series:
    return (
        pd.to_numeric(series, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .fillna(default)
    )


def _bool_to_float(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool).astype(float)


def _ensure_signal_columns(df_signals: pd.DataFrame) -> None:
    missing = [col for col in _REQUIRED_SIGNAL_COLUMNS if col not in df_signals.columns]
    if missing:
        raise ValueError(f"ML 过滤输入缺少必要列: {', '.join(missing)}")


def _derive_buy_mask(df_signals: pd.DataFrame) -> pd.Series:
    if "buy_signal" in df_signals.columns:
        return df_signals["buy_signal"].fillna(False).astype(bool)

    target_position = _coerce_numeric(df_signals["target_position"])
    prev_position = target_position.shift(1).fillna(0.0)
    return (target_position > 0) & (prev_position <= 0)


def _derive_entry_count(df_signals: pd.DataFrame) -> pd.Series:
    if "entry_count" in df_signals.columns:
        return _coerce_numeric(df_signals["entry_count"])

    if "macd_above" in df_signals.columns:
        macd_above = df_signals["macd_above"].fillna(False).astype(bool)
    else:
        macd_above = (df_signals["macd"] > df_signals["signal"]).fillna(False)

    proxy_count = (
        (df_signals["factor_score"] >= 0).astype(int)
        + df_signals["trend_ok"].fillna(False).astype(int)
        + df_signals["strength_ok"].fillna(False).astype(int)
        + df_signals["rsi_ok"].fillna(False).astype(int)
        + macd_above.astype(int)
    )
    return proxy_count.astype(float)


def _compute_future_return_frame(
    df_signals: pd.DataFrame,
    signal_positions: np.ndarray,
    horizon: int,
) -> pd.DataFrame:
    """
    为每个买入信号预计算未来收益标签源数组。
    """
    close_returns = _coerce_numeric(df_signals["close"].pct_change().fillna(0.0)).to_numpy(dtype=float)
    target_position = _coerce_numeric(df_signals["target_position"]).clip(lower=0.0, upper=1.0).to_numpy(dtype=float)
    n_rows = len(df_signals)

    future_strategy_return = np.full(len(signal_positions), np.nan, dtype=float)
    future_naive_return = np.full(len(signal_positions), np.nan, dtype=float)

    for row_idx, signal_pos in enumerate(signal_positions):
        end_pos = int(signal_pos) + int(horizon)
        if end_pos >= n_rows:
            continue

        horizon_returns = close_returns[signal_pos + 1 : end_pos + 1]
        horizon_weights = target_position[signal_pos:end_pos]

        if len(horizon_returns) != horizon or len(horizon_weights) != horizon:
            continue

        future_naive_return[row_idx] = float(np.prod(1.0 + horizon_returns) - 1.0)
        future_strategy_return[row_idx] = float(np.prod(1.0 + horizon_weights * horizon_returns) - 1.0)

    future_excess_return = future_strategy_return - future_naive_return
    return pd.DataFrame(
        {
            "future_strategy_return": future_strategy_return,
            "future_naive_return": future_naive_return,
            "future_excess_return": future_excess_return,
        }
    )


def _materialize_label_frame(
    future_return_frame: pd.DataFrame,
    *,
    min_excess_samples: int,
) -> pd.DataFrame:
    future_excess_return = pd.to_numeric(
        future_return_frame.get("future_excess_return"),
        errors="coerce",
    ).to_numpy(dtype=float)
    future_strategy_return = pd.to_numeric(
        future_return_frame.get("future_strategy_return"),
        errors="coerce",
    ).to_numpy(dtype=float)
    future_naive_return = pd.to_numeric(
        future_return_frame.get("future_naive_return"),
        errors="coerce",
    ).to_numpy(dtype=float)

    valid_primary = np.isfinite(future_excess_return)
    primary_labels = (future_excess_return[valid_primary] > 0).astype(int)

    use_absolute_label = (
        primary_labels.size < int(min_excess_samples)
        or np.unique(primary_labels).size < 2
    )
    if use_absolute_label:
        raw_label_source = future_strategy_return
        label_mode = "absolute_return"
    else:
        raw_label_source = future_excess_return
        label_mode = "excess_return"

    labels = np.where(np.isfinite(raw_label_source), (raw_label_source > 0).astype(float), np.nan)
    return pd.DataFrame(
        {
            "ml_label": labels,
            "label_mode": label_mode,
            "future_strategy_return": future_strategy_return,
            "future_naive_return": future_naive_return,
            "future_excess_return": future_excess_return,
        },
        index=future_return_frame.index,
    )


def _compute_forward_label_frame(
    df_signals: pd.DataFrame,
    signal_positions: np.ndarray,
    horizon: int,
    min_excess_samples: int,
) -> pd.DataFrame:
    future_return_frame = _compute_future_return_frame(
        df_signals=df_signals,
        signal_positions=signal_positions,
        horizon=horizon,
    )
    return _materialize_label_frame(
        future_return_frame,
        min_excess_samples=min_excess_samples,
    )


def _extract_feature_frame(feature_df: pd.DataFrame, feature_columns: list[str] | tuple[str, ...] | None = None) -> pd.DataFrame:
    columns = list(feature_columns or ML_FEATURE_COLUMNS)
    missing = [col for col in columns if col not in feature_df.columns]
    if missing:
        raise ValueError(f"特征表缺少必要列: {', '.join(missing)}")

    x = feature_df.loc[:, columns].copy()
    for column in columns:
        x[column] = _coerce_numeric(x[column])
    return x


def _positive_class_proba(model, x: pd.DataFrame | np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        raw = np.asarray(model.predict_proba(x), dtype=float)
        if raw.ndim == 1:
            return np.clip(raw, 0.0, 1.0)

        classes = list(getattr(model, "classes_", [0, 1]))
        if 1 in classes:
            return np.clip(raw[:, classes.index(1)], 0.0, 1.0)
        if len(classes) == 1:
            return np.full(len(raw), 1.0 if classes[0] == 1 else 0.0, dtype=float)
        return np.clip(raw[:, -1], 0.0, 1.0)

    if hasattr(model, "decision_function"):
        decision = np.asarray(model.decision_function(x), dtype=float)
        return 1.0 / (1.0 + np.exp(-decision))

    prediction = np.asarray(model.predict(x), dtype=float)
    return np.clip(prediction, 0.0, 1.0)


def _build_trade_block_map(df_signals: pd.DataFrame, eps: float = 1e-8) -> dict[int, np.ndarray]:
    target_position = _coerce_numeric(df_signals["target_position"]).to_numpy(dtype=float)
    active = target_position > eps
    block_map: dict[int, np.ndarray] = {}
    start_pos: int | None = None

    for pos, is_active in enumerate(active):
        if is_active and start_pos is None:
            start_pos = pos
        elif start_pos is not None and not is_active:
            block_map[start_pos] = np.arange(start_pos, pos, dtype=int)
            start_pos = None

    if start_pos is not None:
        block_map[start_pos] = np.arange(start_pos, len(active), dtype=int)

    return block_map


def build_feature_bundle(
    df_signals: pd.DataFrame,
    horizon: int = 10,
    min_excess_samples: int = 20,
) -> FeatureBundle:
    """
    从 `compute_signals()` 输出中抽取一次可复用的 ML 特征 bundle。
    """
    _ensure_signal_columns(df_signals)

    buy_mask = _derive_buy_mask(df_signals)
    signal_positions = np.flatnonzero(buy_mask.to_numpy(dtype=bool))

    if len(signal_positions) == 0:
        empty_feature_table = pd.DataFrame(
            columns=[*ML_METADATA_COLUMNS, *ML_FEATURE_COLUMNS],
            index=pd.Index([], name=df_signals.index.name),
        )
        empty_future_return_frame = pd.DataFrame(
            columns=["future_strategy_return", "future_naive_return", "future_excess_return"],
            index=empty_feature_table.index,
        )
        return FeatureBundle(
            feature_table=empty_feature_table,
            future_return_frame=empty_future_return_frame,
            horizon=int(horizon),
            min_excess_samples=int(min_excess_samples),
            row_count=int(len(df_signals)),
        )

    sampled = df_signals.iloc[signal_positions].copy()
    macd_above = (
        sampled["macd_above"].fillna(False).astype(bool)
        if "macd_above" in sampled.columns
        else (sampled["macd"] > sampled["signal"]).fillna(False)
    )

    feature_table = pd.DataFrame(index=sampled.index)
    feature_table["signal_pos"] = signal_positions
    feature_table["date"] = sampled["date"] if "date" in sampled.columns else pd.NaT

    feature_table["factor_score"] = _coerce_numeric(sampled["factor_score"])
    feature_table["factor_percentile"] = _coerce_numeric(sampled["factor_percentile"])
    feature_table["target_position"] = _coerce_numeric(sampled["target_position"])
    feature_table["mom_short_z"] = _coerce_numeric(sampled["mom_short_z"])
    feature_table["mom_long_z"] = _coerce_numeric(sampled["mom_long_z"])
    feature_table["macd_z"] = _coerce_numeric(sampled["macd_z"])
    feature_table["rsi_z"] = _coerce_numeric(sampled["rsi_z"])
    feature_table["vol_z"] = _coerce_numeric(sampled["vol_z"])
    feature_table["bb_position_rank"] = _coerce_numeric(sampled["bb_position_rank"])
    feature_table["obv_trend_rank"] = _coerce_numeric(sampled["obv_trend_rank"])
    feature_table["volume_ratio_rank"] = _coerce_numeric(sampled["volume_ratio_rank"])
    feature_table["price_position_rank"] = _coerce_numeric(sampled["price_position_rank"])
    feature_table["drawdown_rank"] = _coerce_numeric(sampled["drawdown_rank"])
    feature_table["rsi"] = _coerce_numeric(sampled["rsi"])
    feature_table["macd"] = _coerce_numeric(sampled["macd"])
    feature_table["signal"] = _coerce_numeric(sampled["signal"])
    feature_table["adx"] = _coerce_numeric(sampled["adx"])
    feature_table["atr_pct"] = _coerce_numeric(sampled["atr"] / sampled["close"])
    feature_table["volume_ratio"] = _coerce_numeric(sampled["volume_ratio"])
    feature_table["bb_position"] = _coerce_numeric(sampled["bb_position"])
    feature_table["bb_width"] = _coerce_numeric(sampled["bb_width"])
    feature_table["price_position"] = _coerce_numeric(sampled["price_position"])
    feature_table["drawdown"] = _coerce_numeric(sampled["drawdown"])
    feature_table["trend_ok"] = _bool_to_float(sampled["trend_ok"])
    feature_table["strength_ok"] = _bool_to_float(sampled["strength_ok"])
    feature_table["rsi_ok"] = _bool_to_float(sampled["rsi_ok"])
    feature_table["macd_above"] = macd_above.astype(float)
    feature_table["entry_count"] = _coerce_numeric(_derive_entry_count(df_signals).iloc[signal_positions])
    feature_table["ema_spread_pct"] = _coerce_numeric((sampled["ema_fast"] - sampled["ema_slow"]) / sampled["close"])
    future_return_frame = _compute_future_return_frame(
        df_signals=df_signals,
        signal_positions=signal_positions,
        horizon=horizon,
    )
    feature_table.attrs["feature_columns"] = list(ML_FEATURE_COLUMNS)
    future_return_frame.index = feature_table.index
    return FeatureBundle(
        feature_table=feature_table[[*ML_METADATA_COLUMNS, *ML_FEATURE_COLUMNS]],
        future_return_frame=future_return_frame,
        horizon=int(horizon),
        min_excess_samples=int(min_excess_samples),
        row_count=int(len(df_signals)),
    )


def build_feature_view(
    bundle: FeatureBundle,
    *,
    min_signal_pos: int | None = None,
    max_signal_pos: int | None = None,
    label_boundary_limit: int | None = None,
) -> pd.DataFrame:
    result_columns = [*ML_METADATA_COLUMNS, *ML_FEATURE_COLUMNS, *ML_LABEL_COLUMNS]
    feature_table = bundle.feature_table
    if feature_table.empty:
        return pd.DataFrame(columns=result_columns, index=feature_table.index.copy())

    signal_pos = pd.to_numeric(feature_table["signal_pos"], errors="coerce").fillna(-1).astype(int)
    selection_mask = pd.Series(True, index=feature_table.index, dtype=bool)
    if min_signal_pos is not None:
        selection_mask &= signal_pos >= int(min_signal_pos)
    if max_signal_pos is not None:
        selection_mask &= signal_pos < int(max_signal_pos)

    selected_feature_table = feature_table.loc[selection_mask].copy()
    if selected_feature_table.empty:
        return pd.DataFrame(columns=result_columns, index=selected_feature_table.index)

    selected_future_returns = bundle.future_return_frame.loc[selected_feature_table.index].copy()
    boundary_limit = int(bundle.row_count if label_boundary_limit is None else label_boundary_limit)
    overflow_mask = (
        pd.to_numeric(selected_feature_table["signal_pos"], errors="coerce").fillna(-1).astype(int)
        + int(bundle.horizon)
        >= boundary_limit
    )
    if overflow_mask.any():
        selected_future_returns.loc[
            overflow_mask,
            ["future_strategy_return", "future_naive_return", "future_excess_return"],
        ] = np.nan

    label_frame = _materialize_label_frame(
        selected_future_returns,
        min_excess_samples=bundle.min_excess_samples,
    )
    result = pd.concat([selected_feature_table, label_frame], axis=1)
    result.attrs["feature_columns"] = list(ML_FEATURE_COLUMNS)
    result.attrs["label_mode"] = (
        str(label_frame["label_mode"].iloc[0]) if not label_frame.empty else "excess_return"
    )
    return result[result_columns]


def build_feature_table(
    df_signals: pd.DataFrame,
    horizon: int = 10,
    min_excess_samples: int = 20,
) -> pd.DataFrame:
    """
    从 `compute_signals()` 输出中抽取 ML 样本表。

    - 只对买入信号（buy_signal）生成样本
    - 特征严格使用信号当日可见信息
    - 标签默认是未来 10 日是否跑赢 Naive，信号过少时退化为未来 10 日是否正收益
    """
    bundle = build_feature_bundle(
        df_signals,
        horizon=horizon,
        min_excess_samples=min_excess_samples,
    )
    return build_feature_view(bundle)


def fit_ml_filter(
    feature_df: pd.DataFrame,
    labels: pd.Series | np.ndarray | list | None = None,
    model_type: str = "logistic",
    threshold: float = 0.5,
) -> MLModel:
    """
    训练 ML 信号过滤模型。

    约束：
    - `feature_df` 必须只包含训练期样本
    - Logistic 仅在训练集上 fit `StandardScaler`
    - 当训练样本退化到单一类别时，返回稳定的常数概率模型，避免流程中断
    """
    if feature_df is None or feature_df.empty:
        raise ValueError("feature_df 为空，无法训练 ML 过滤器")

    x = _extract_feature_frame(feature_df)

    if labels is None:
        if "ml_label" not in feature_df.columns:
            raise ValueError("labels 未提供，且 feature_df 中缺少 ml_label 列")
        y = pd.Series(feature_df["ml_label"], index=feature_df.index)
    else:
        y = pd.Series(labels, index=feature_df.index if len(labels) == len(feature_df) else None)
        if not y.index.equals(feature_df.index):
            y = y.reindex(feature_df.index)

    y = pd.to_numeric(y, errors="coerce")
    valid_mask = y.notna()
    x = x.loc[valid_mask]
    y = y.loc[valid_mask].astype(int).clip(lower=0, upper=1)

    if x.empty:
        raise ValueError("训练标签全部为空，无法训练 ML 过滤器")

    model_key = str(model_type or "logistic").strip().lower()
    threshold_value = float(np.clip(threshold, 0.0, 1.0))

    scaler = None
    x_fit: pd.DataFrame | np.ndarray = x

    if model_key == "logistic":
        scaler = StandardScaler()
        x_fit = scaler.fit_transform(x)
    elif model_key == "lgbm":
        if LGBMClassifier is None:
            raise ImportError("当前环境缺少 lightgbm，无法训练 lgbm 过滤器")
    else:
        raise ValueError("model_type 只支持 'logistic' 或 'lgbm'")

    unique_labels = np.unique(y)
    if len(unique_labels) < 2 or len(x) < 8:
        model = _ConstantProbabilityModel(float(y.mean()))
    elif model_key == "logistic":
        model = LogisticRegression(
            max_iter=1000,
            solver="liblinear",
            class_weight="balanced",
            random_state=42,
        )
        model.fit(x_fit, y)
    else:
        model = LGBMClassifier(
            objective="binary",
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=15,
            min_child_samples=10,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_alpha=0.1,
            reg_lambda=0.1,
            class_weight="balanced",
            random_state=42,
            n_jobs=_resolve_ml_n_jobs(-1),
            verbosity=-1,
        )
        model.fit(x, y)

    model.feature_columns_ = list(x.columns)
    model.training_samples_ = int(len(x))
    model.label_positive_rate_ = float(y.mean())
    return MLModel(model=model, scaler=scaler, model_type=model_key, threshold=threshold_value)


def predict_filter(ml_model: MLModel, feature_df: pd.DataFrame) -> pd.Series:
    """对买入信号样本输出“值得保留”的概率。"""
    if feature_df is None or feature_df.empty:
        return pd.Series(dtype=float, name="ml_proba")
    if ml_model is None:
        raise ValueError("ml_model 不能为空")

    feature_columns = getattr(ml_model.model, "feature_columns_", list(ML_FEATURE_COLUMNS))
    x = _extract_feature_frame(feature_df, feature_columns)

    x_input: pd.DataFrame | np.ndarray = x
    if ml_model.scaler is not None:
        x_input = ml_model.scaler.transform(x)

    probability = _positive_class_proba(ml_model.model, x_input)
    return pd.Series(probability, index=feature_df.index, name="ml_proba")


def apply_filter(
    df_signals: pd.DataFrame,
    ml_model: MLModel,
    feature_df: pd.DataFrame | None = None,
    threshold: float | None = None,
) -> pd.DataFrame:
    """
    把 ML 概率映射回原始信号表，并过滤掉低置信度开仓段。

    过滤规则：
    - 只对 `buy_signal` 对应的整段 `target_position > 0` 持仓块做开/关决策
    - 若某个买点被拒绝，则该买点对应的整段目标仓位全部置 0
    - 过滤后重新计算 `buy_signal` / `sell_signal`
    """
    if "target_position" not in df_signals.columns:
        raise ValueError("apply_filter 需要含 target_position 的信号表")

    out = df_signals.copy()
    sample_df = build_feature_table(out) if feature_df is None else feature_df.copy()

    out["ml_proba"] = np.nan
    out["ml_pass"] = pd.Series(pd.NA, index=out.index, dtype="boolean")

    if sample_df.empty:
        return out

    proba = predict_filter(ml_model, sample_df)
    threshold_value = float(
        np.clip(ml_model.threshold if threshold is None else threshold, 0.0, 1.0)
    )
    pass_mask = (proba >= threshold_value)

    out.loc[proba.index, "ml_proba"] = proba.to_numpy(dtype=float)
    out.loc[pass_mask.index, "ml_pass"] = pass_mask.astype("boolean")

    if "signal_pos" in sample_df.columns:
        signal_positions = pd.to_numeric(sample_df["signal_pos"], errors="coerce")
    else:
        signal_positions = pd.Series(np.arange(len(sample_df)), index=sample_df.index, dtype=float)

    block_map = _build_trade_block_map(out)
    target_position_col = out.columns.get_loc("target_position")

    for row_index, signal_pos in signal_positions.items():
        if pd.isna(signal_pos) or bool(pass_mask.get(row_index, False)):
            continue

        block_positions = block_map.get(int(signal_pos))
        if block_positions is None:
            continue
        out.iloc[block_positions, target_position_col] = 0.0

    out["target_position"] = _coerce_numeric(out["target_position"]).clip(lower=0.0, upper=1.0)
    prev_position = out["target_position"].shift(1).fillna(0.0)
    out["buy_signal"] = (out["target_position"] > 0) & (prev_position <= 0)
    out["sell_signal"] = (out["target_position"] <= 0) & (prev_position > 0)
    return out


def evaluate_ml_quality(
    y_true: pd.Series | np.ndarray | list,
    y_pred_proba: pd.Series | np.ndarray | list,
    threshold: float = 0.5,
) -> dict[str, float | None]:
    """统一输出 ML 过滤器的质量指标。"""
    threshold_value = float(np.clip(threshold, 0.0, 1.0))
    y_true_series = pd.Series(y_true)
    y_pred_series = pd.Series(y_pred_proba)

    if len(y_true_series) == len(y_pred_series):
        aligned = pd.DataFrame({"y_true": y_true_series.to_numpy(), "y_pred_proba": y_pred_series.to_numpy()})
    else:
        aligned = pd.concat(
            [
                y_true_series.rename("y_true"),
                y_pred_series.rename("y_pred_proba"),
            ],
            axis=1,
            join="inner",
        )

    aligned["y_true"] = pd.to_numeric(aligned["y_true"], errors="coerce")
    aligned["y_pred_proba"] = pd.to_numeric(aligned["y_pred_proba"], errors="coerce")
    aligned = aligned.dropna(subset=["y_true", "y_pred_proba"])

    if aligned.empty:
        return {
            "precision": None,
            "recall": None,
            "f1": None,
            "pr_auc": None,
            "signal_pass_rate": None,
        }

    y_true_values = aligned["y_true"].astype(int).clip(lower=0, upper=1)
    y_pred_proba_values = aligned["y_pred_proba"].clip(lower=0.0, upper=1.0)
    y_pred_labels = (y_pred_proba_values >= threshold_value).astype(int)

    pr_auc: float | None = None
    if y_true_values.nunique() >= 2:
        pr_auc = float(average_precision_score(y_true_values, y_pred_proba_values))

    return {
        "precision": float(precision_score(y_true_values, y_pred_labels, zero_division=0)),
        "recall": float(recall_score(y_true_values, y_pred_labels, zero_division=0)),
        "f1": float(f1_score(y_true_values, y_pred_labels, zero_division=0)),
        "pr_auc": pr_auc,
        "signal_pass_rate": float(y_pred_labels.mean()),
    }


__all__ = [
    "MLModel",
    "FeatureBundle",
    "ML_FEATURE_COLUMNS",
    "ML_METADATA_COLUMNS",
    "ML_LABEL_COLUMNS",
    "build_feature_bundle",
    "build_feature_view",
    "build_feature_table",
    "fit_ml_filter",
    "predict_filter",
    "apply_filter",
    "evaluate_ml_quality",
]
