"""
FA 因子提炼层
==============
在训练集上拟合 FactorAnalysis，并将 10 个标准化因子压缩为单一 FSM 分数。
"""

from __future__ import annotations

from collections import namedtuple

import numpy as np
import pandas as pd
from sklearn.decomposition import FactorAnalysis
from sklearn.preprocessing import StandardScaler


FAModel = namedtuple("FAModel", ["fa", "scaler", "n_components"])

# 输入来自 compute_signals() 预先计算好的 10 个标准化因子列。
FA_SOURCE_COLUMNS = (
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
)


def _build_fa_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing_columns = [col for col in FA_SOURCE_COLUMNS if col not in df.columns]
    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise ValueError(f"FA 输入缺少必要因子列: {missing_text}")

    feature_df = pd.DataFrame(
        {
            "mom_short": df["mom_short_z"],
            "mom_long": df["mom_long_z"],
            "macd": df["macd_z"],
            "rsi": df["rsi_z"],
            "volatility": -df["vol_z"],
            "bb_position": (df["bb_position_rank"] - 0.5) * 2,
            "obv_trend": (df["obv_trend_rank"] - 0.5) * 2,
            "volume_ratio": (df["volume_ratio_rank"] - 0.5) * 2,
            "price_position": (df["price_position_rank"] - 0.5) * 2,
            "drawdown": -(df["drawdown_rank"] - 0.5) * 2,
        },
        index=df.index,
    )

    return feature_df.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _resolve_component_count(feature_df: pd.DataFrame, n_components: int) -> int:
    if feature_df.empty:
        raise ValueError("FA 训练集为空，无法拟合模型")

    requested = int(n_components)
    if requested <= 0:
        raise ValueError("n_components 必须为正整数")

    max_components = min(len(feature_df), feature_df.shape[1])
    return max(1, min(requested, max_components))


def fit_fa(df_train: pd.DataFrame, n_components: int = 3) -> FAModel:
    """
    在训练集上拟合 FA 模型。

    输入要求:
    - df_train 已包含 compute_signals() 生成的 10 个标准化因子列
    - 只能传训练集，避免数据泄露
    """
    feature_df = _build_fa_feature_frame(df_train)
    effective_components = _resolve_component_count(feature_df, n_components)

    scaler = StandardScaler()
    scaled_features = scaler.fit_transform(feature_df)

    fa = FactorAnalysis(n_components=effective_components, random_state=42)
    latent_scores = fa.fit_transform(scaled_features)

    # 用训练集上的等权“正向因子均值”统一潜在因子的方向，避免 FSM 分数语义翻转。
    anchor_score = feature_df.mean(axis=1).to_numpy(dtype=float)
    component_signs = np.ones(effective_components, dtype=float)
    if len(anchor_score) > 1 and np.nanstd(anchor_score) > 0:
        for idx in range(effective_components):
            component = latent_scores[:, idx]
            if np.nanstd(component) == 0:
                continue
            corr = np.corrcoef(component, anchor_score)[0, 1]
            if np.isfinite(corr) and corr < 0:
                component_signs[idx] = -1.0

    corrected_scores = latent_scores * component_signs
    raw_fsm_score = corrected_scores.mean(axis=1)
    score_mean = float(np.nanmean(raw_fsm_score))
    score_std = float(np.nanstd(raw_fsm_score))
    if not np.isfinite(score_std) or score_std < 1e-8:
        score_std = 1.0

    fa.component_signs_ = component_signs
    fa.score_mean_ = score_mean
    fa.score_std_ = score_std
    fa.feature_names_ = list(feature_df.columns)

    return FAModel(fa=fa, scaler=scaler, n_components=effective_components)


def transform_fa(fa_model: FAModel, df: pd.DataFrame) -> pd.Series:
    """
    使用训练好的 FA 模型将 10 因子映射为单一 FSM 分数。
    """
    if fa_model is None:
        raise ValueError("fa_model 不能为空")

    feature_df = _build_fa_feature_frame(df)
    if feature_df.empty:
        return pd.Series(dtype=float, index=df.index, name="fsm_score")

    scaled_features = fa_model.scaler.transform(feature_df)
    latent_scores = fa_model.fa.transform(scaled_features)

    component_signs = getattr(fa_model.fa, "component_signs_", np.ones(fa_model.n_components))
    corrected_scores = latent_scores * component_signs
    fsm_score = corrected_scores.mean(axis=1)

    score_mean = float(getattr(fa_model.fa, "score_mean_", 0.0))
    score_std = float(getattr(fa_model.fa, "score_std_", 1.0))
    if not np.isfinite(score_std) or score_std < 1e-8:
        score_std = 1.0

    standardized_score = (fsm_score - score_mean) / score_std
    series = pd.Series(standardized_score, index=df.index, name="fsm_score")
    return series.replace([np.inf, -np.inf], np.nan).fillna(0.0)


__all__ = ["FAModel", "FA_SOURCE_COLUMNS", "fit_fa", "transform_fa"]
