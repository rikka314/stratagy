"""Shared builders for the expert-system reconstruction Phase 1 experiment."""

from __future__ import annotations

import json
from typing import Sequence

import numpy as np
import pandas as pd

from core.macro_factors import MACRO_FEATURE_COLUMNS
from model_test.expert_panel import compute_future_utility


class ExpertSystemPhase1Error(ValueError):
    """Raised when Phase 1 inputs violate the frozen research contract."""


def build_horizon_sequence_panel(
    sequence_panel: pd.DataFrame,
    expert_day_panel: pd.DataFrame,
    *,
    horizon_days: int,
    expert_ids: Sequence[str],
    lambda_downside: float,
    lambda_turnover: float,
) -> pd.DataFrame:
    """Attach a complete expert utility vector for one future horizon."""

    required_sequence = {"sequence_end_date", "sequence_values", "symbol", "market"}
    required_daily = {
        "date",
        "symbol",
        "expert_id",
        "expert_status",
        "strategy_return",
        "turnover",
        "split_memberships_json",
    }
    missing_sequence = required_sequence - set(sequence_panel.columns)
    missing_daily = required_daily - set(expert_day_panel.columns)
    if missing_sequence:
        raise ExpertSystemPhase1Error(
            f"sequence panel is missing columns: {sorted(missing_sequence)}"
        )
    if missing_daily:
        raise ExpertSystemPhase1Error(
            f"expert panel is missing columns: {sorted(missing_daily)}"
        )
    experts = tuple(str(value) for value in expert_ids)
    if not experts or len(set(experts)) != len(experts):
        raise ExpertSystemPhase1Error("expert_ids must be non-empty and unique")

    daily = expert_day_panel.copy()
    daily["date"] = pd.to_datetime(daily["date"], errors="coerce").dt.normalize()
    daily["symbol"] = daily["symbol"].astype(str)
    daily["expert_id"] = daily["expert_id"].astype(str)
    daily = daily.loc[daily["expert_id"].isin(experts)].copy()
    if set(daily["expert_id"].unique()) != set(experts):
        raise ExpertSystemPhase1Error("expert panel does not contain every configured expert")

    labeled_parts: list[pd.DataFrame] = []
    for (_, _), group in daily.groupby(["symbol", "expert_id"], sort=False):
        group = group.sort_values("date").copy()
        computed = compute_future_utility(
            group[["date", "strategy_return", "turnover"]],
            horizon_days=int(horizon_days),
            lambda_downside=float(lambda_downside),
            lambda_turnover=float(lambda_turnover),
        )
        group["phase1_future_utility"] = computed["future_utility"].to_numpy()
        group.loc[
            ~group["expert_status"].eq("available"), "phase1_future_utility"
        ] = np.nan
        labeled_parts.append(group)
    labeled = pd.concat(labeled_parts, ignore_index=True)

    membership_counts = labeled.groupby(["date", "symbol"])[
        "split_memberships_json"
    ].nunique(dropna=False)
    if membership_counts.gt(1).any():
        raise ExpertSystemPhase1Error("split memberships differ across experts")
    memberships = labeled.drop_duplicates(["date", "symbol"])[
        ["date", "symbol", "split_memberships_json"]
    ]
    utilities = labeled.pivot(
        index=["date", "symbol"],
        columns="expert_id",
        values="phase1_future_utility",
    )
    missing_experts = set(experts) - set(utilities.columns)
    if missing_experts:
        raise ExpertSystemPhase1Error(
            f"utility panel is missing experts: {sorted(missing_experts)}"
        )
    utilities = utilities[list(experts)].dropna(how="any").reset_index()
    utilities["expert_utilities_json"] = utilities.apply(
        lambda row: json.dumps(
            {expert: float(row[expert]) for expert in experts},
            ensure_ascii=False,
            sort_keys=True,
        ),
        axis=1,
    )
    utility_rows = utilities[["date", "symbol", "expert_utilities_json"]].merge(
        memberships,
        on=["date", "symbol"],
        how="left",
        validate="one_to_one",
    ).rename(columns={"date": "utility_date"})

    result = sequence_panel.copy()
    result["sequence_end_date"] = pd.to_datetime(
        result["sequence_end_date"], errors="coerce"
    ).dt.normalize()
    result["symbol"] = result["symbol"].astype(str)
    result = result.drop(
        columns=[
            column
            for column in ("expert_utilities_json", "split_memberships_json")
            if column in result.columns
        ]
    )
    result = result.merge(
        utility_rows,
        left_on=["sequence_end_date", "symbol"],
        right_on=["utility_date", "symbol"],
        how="inner",
        validate="one_to_one",
    ).drop(columns=["utility_date"])
    result["label_horizon_days"] = int(horizon_days)
    return result.sort_values(["sequence_end_date", "symbol"]).reset_index(drop=True)


def append_macro_sequences(
    sequence_panel: pd.DataFrame,
    macro_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Append the five macro factors to every day of every state sequence."""

    required_panel = {"sequence_dates", "sequence_values", "symbol"}
    required_macro = {"date", "symbol", *MACRO_FEATURE_COLUMNS}
    missing_panel = required_panel - set(sequence_panel.columns)
    missing_macro = required_macro - set(macro_panel.columns)
    if missing_panel:
        raise ExpertSystemPhase1Error(
            f"sequence panel is missing macro join fields: {sorted(missing_panel)}"
        )
    if missing_macro:
        raise ExpertSystemPhase1Error(
            f"macro panel is missing columns: {sorted(missing_macro)}"
        )
    macro = macro_panel.copy()
    macro["date"] = pd.to_datetime(macro["date"], errors="coerce").dt.normalize()
    macro["symbol"] = macro["symbol"].astype(str)
    if macro.duplicated(["date", "symbol"]).any():
        raise ExpertSystemPhase1Error("macro panel contains duplicate date-symbol rows")
    lookup = {
        (row.date, str(row.symbol)): np.asarray(
            [getattr(row, column) for column in MACRO_FEATURE_COLUMNS], dtype=float
        )
        for row in macro[["date", "symbol", *MACRO_FEATURE_COLUMNS]].itertuples(index=False)
    }

    augmented: list[list[list[float]]] = []
    for row in sequence_panel[["sequence_dates", "sequence_values", "symbol"]].itertuples(
        index=False
    ):
        dates = pd.DatetimeIndex(pd.to_datetime(list(row.sequence_dates))).normalize()
        raw_values = row.sequence_values
        if isinstance(raw_values, np.ndarray) and raw_values.dtype == object:
            raw_values = raw_values.tolist()
        values = np.asarray(raw_values, dtype=float)
        if values.ndim != 2 or len(values) != len(dates):
            raise ExpertSystemPhase1Error("sequence dates and values are not aligned")
        macro_values = np.vstack(
            [
                lookup.get(
                    (date, str(row.symbol)),
                    np.full(len(MACRO_FEATURE_COLUMNS), np.nan, dtype=float),
                )
                for date in dates
            ]
        )
        augmented.append(np.concatenate([values, macro_values], axis=1))
    result = sequence_panel.copy()
    result["sequence_values"] = augmented
    return result


__all__ = [
    "ExpertSystemPhase1Error",
    "append_macro_sequences",
    "build_horizon_sequence_panel",
]
