from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
SM_ROOT = ROOT / "model-test" / "outputs" / "full_us_deans_60"
COMPOSITE_PATH = ROOT / "model-test" / "outputs" / "phase3_expert_pool_v2" / "expert_return_audit.parquet"
OUTPUT = ROOT / "model-test" / "outputs" / "composite_vs_sm_comparison"
SYMBOLS = ("AAPL", "MSFT", "NVDA", "TSLA", "AMZN")
START = pd.Timestamp("2021-08-02")
END = pd.Timestamp("2026-08-07")


def max_drawdown(equity: pd.Series) -> float:
    return float((equity / equity.cummax() - 1.0).min())


def build_metrics(frame: pd.DataFrame, model: str, symbol: str) -> tuple[dict, pd.DataFrame]:
    if frame.empty:
        raise ValueError(f"{symbol}/{model} has no rows in the effective comparison window")
    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError(f"{symbol}/{model} has invalid or duplicate dates")
    frame = frame.assign(date=dates).sort_values("date").reset_index(drop=True)
    returns = pd.to_numeric(frame["strategy_return"], errors="coerce")
    if not np.isfinite(returns.to_numpy(dtype=float)).all() or (returns <= -1.0).any():
        raise ValueError(f"{symbol}/{model} has invalid strategy returns")
    returns = returns.fillna(0.0)
    equity = (1.0 + returns).cumprod()
    std = float(returns.std(ddof=1))
    position = pd.to_numeric(
        frame.get("position", pd.Series(0.0, index=frame.index)), errors="coerce"
    ).fillna(0.0)
    turnover = pd.to_numeric(
        frame.get("turnover", pd.Series(0.0, index=frame.index)), errors="coerce"
    ).fillna(0.0)
    transaction_cost = pd.to_numeric(
        frame.get("transaction_cost", pd.Series(0.0, index=frame.index)), errors="coerce"
    ).fillna(0.0)
    row = {
        "status": "diagnostic_only",
        "symbol": symbol,
        "model": model,
        "start": frame["date"].min().date().isoformat(),
        "end": frame["date"].max().date().isoformat(),
        "coverage": int(len(frame)),
        "total_return": float(equity.iloc[-1] - 1.0),
        "sharpe": float(returns.mean() / std * np.sqrt(252.0)) if std > 1e-12 else 0.0,
        "max_drawdown": max_drawdown(equity),
        "daily_win_rate": float((returns > 0).mean()),
        "trade_count": None,
        "trade_win_rate": None,
        "turnover": float(turnover.sum()),
        "transaction_cost": float(transaction_cost.sum()),
        "mean_position": float(position.mean()),
        "near_full_exposure": float((position > 0.9).mean()),
    }
    curve = pd.DataFrame(
        {
            "date": frame["date"].to_numpy(),
            "equity": equity.to_numpy(),
            "strategy_return": returns.to_numpy(),
            "position": position.to_numpy(),
            "turnover": turnover.to_numpy(),
            "transaction_cost": transaction_cost.to_numpy(),
        }
    )
    return row, curve


def write_plot(
    symbol: str,
    sm_returns: pd.DataFrame,
    sm_trades: pd.DataFrame,
    composite: pd.DataFrame,
    sm_curve: pd.DataFrame,
    composite_curve: pd.DataFrame,
) -> None:
    snapshot = pd.read_csv(SM_ROOT / "data_snapshot" / f"{symbol}_daily.csv")
    snapshot["date"] = pd.to_datetime(snapshot["date"])
    price = snapshot[(snapshot["date"] >= START) & (snapshot["date"] <= END)].sort_values("date")

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(14, 8),
        sharex=True,
        gridspec_kw={"height_ratios": [1.35, 1]},
    )
    effective_start = sm_returns["date"].min()
    effective_end = sm_returns["date"].max()
    price_axis = axes[0]
    price = price[(price["date"] >= effective_start) & (price["date"] <= effective_end)]
    price_axis.plot(price["date"], price["close"], color="#334155", linewidth=1.3, label=f"{symbol} close")
    entries = sm_trades.merge(price[["date", "close"]], left_on="entry_date", right_on="date", how="left")
    exits = sm_trades.merge(price[["date", "close"]], left_on="exit_date", right_on="date", how="left")
    price_axis.scatter(entries["entry_date"], entries["close"], marker="^", s=45, color="#15803d", label="SM buy", zorder=4)
    price_axis.scatter(exits["exit_date"], exits["close"], marker="v", s=45, color="#b91c1c", label="SM sell", zorder=4)

    composite_position = pd.to_numeric(composite["position"], errors="coerce").fillna(0.0)
    if (composite_position > 0).any():
        composite_entry = composite.loc[composite_position > 0, "date"].iloc[0]
        entry_price = price[price["date"] == composite_entry]
        if not entry_price.empty:
            price_axis.scatter(
                entry_price["date"],
                entry_price["close"],
                marker="^",
                s=65,
                facecolors="none",
                edgecolors="#2563eb",
                linewidths=1.5,
                label="Composite exposure start",
            )

    price_axis.set_title(
        f"{symbol}: frozen test price and event markers "
        f"({effective_start.date()} to {effective_end.date()})"
    )
    price_axis.set_ylabel("Adjusted close")
    price_axis.grid(alpha=0.2)
    price_axis.legend(loc="upper left", ncol=3, fontsize=8)

    equity_axis = axes[1]
    equity_axis.plot(sm_curve["date"], sm_curve["equity"], color="#0f766e", label="SM equity")
    equity_axis.plot(composite_curve["date"], composite_curve["equity"], color="#7c3aed", label="Composite equity")
    equity_axis.axhline(1.0, color="#94a3b8", linewidth=0.8)
    equity_axis.set_ylabel("Equity")
    equity_axis.set_xlabel("Date")
    equity_axis.grid(alpha=0.2)
    equity_axis.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(OUTPUT / f"{symbol}_price_signals_equity.png", dpi=150)
    plt.close(fig)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    composite_all = pd.read_parquet(COMPOSITE_PATH)
    manifest_path = COMPOSITE_PATH.parent / "expert_pool_manifest.json"
    manifest = pd.read_json(manifest_path, typ="series")
    manifest_status = str(manifest.get("status", ""))
    manifest_reason = str(manifest.get("reason", ""))
    if manifest_status != "failed" or manifest_reason != "data_quality_blocked":
        raise ValueError(
            "Unexpected Phase 3 manifest state; this diagnostic runner only permits "
            "the known data-quality-blocked artifact."
        )
    composite_all["date"] = pd.to_datetime(composite_all["date"])
    composite_all = composite_all[
        (composite_all["expert_id"] == "composite_optimized")
        & composite_all["symbol"].isin(SYMBOLS)
        & (composite_all["date"] >= START)
        & (composite_all["date"] <= END)
    ].copy()

    rows = []
    plot_data = {}
    for symbol in SYMBOLS:
        model_dir = SM_ROOT / "artifacts" / symbol / "main" / "sm"
        sm_returns = pd.read_csv(model_dir / "returns.csv")
        sm_returns["date"] = pd.to_datetime(sm_returns["date"])
        sm_daily = pd.read_csv(model_dir / "daily.csv")
        sm_daily["date"] = pd.to_datetime(sm_daily["date"])
        sm_returns = sm_returns[(sm_returns["date"] >= START) & (sm_returns["date"] <= END)].copy()
        sm_daily = sm_daily[sm_daily["date"].isin(sm_returns["date"])].copy()
        if set(sm_returns["date"]) != set(sm_daily["date"]):
            raise ValueError(f"{symbol}/SM returns and daily dates do not match")
        sm_trades = pd.read_csv(model_dir / "trades.csv")
        sm_trades["entry_date"] = pd.to_datetime(sm_trades["entry_date"])
        sm_trades["exit_date"] = pd.to_datetime(sm_trades["exit_date"])
        sm_trades = sm_trades[(sm_trades["entry_date"] <= END) & (sm_trades["exit_date"] >= START)].copy()

        sm_row, sm_curve = build_metrics(sm_returns, "SM", symbol)
        sm_row["trade_count"] = int(len(sm_trades))
        sm_row["trade_win_rate"] = float(sm_trades["is_win"].mean()) if len(sm_trades) else 0.0
        sm_row["turnover"] = float(pd.to_numeric(sm_daily["turnover"], errors="coerce").fillna(0.0).sum())
        sm_row["transaction_cost"] = float(
            pd.to_numeric(sm_daily["transaction_cost"], errors="coerce").fillna(0.0).sum()
        )
        rows.append(sm_row)

        composite = composite_all[composite_all["symbol"] == symbol].sort_values("date").copy()
        composite = composite[
            (composite["date"] >= sm_returns["date"].min())
            & (composite["date"] <= sm_returns["date"].max())
        ].copy()
        composite_row, composite_curve = build_metrics(composite, "composite_optimized", symbol)
        position = pd.to_numeric(composite["position"], errors="coerce").fillna(0.0)
        composite_row["exposure_episode_count"] = int(
            ((position > 0.1) & ~(position > 0.1).shift(1, fill_value=False)).sum()
        )
        composite_row["trade_count"] = None
        rows.append(composite_row)
        plot_data[symbol] = (sm_returns, sm_trades, composite, sm_curve, composite_curve)

    summary = pd.DataFrame(rows)
    summary.to_csv(OUTPUT / "comparison_metrics.csv", index=False)
    summary.pivot(index="symbol", columns="model", values=[
        "total_return", "sharpe", "max_drawdown", "daily_win_rate", "trade_count",
        "turnover", "transaction_cost", "mean_position", "near_full_exposure",
    ]).to_csv(OUTPUT / "comparison_metrics_wide.csv")

    for symbol, data in plot_data.items():
        write_plot(symbol, *data)

    (OUTPUT / "README.md").write_text(
        "# Composite vs original SM\n\n"
        "- Comparison model: original `model_id=sm`.\n"
        "- Effective common window: 2025-02-05 through 2026-08-07 (the frozen SM main artifact is 378 rows).\n"
        "- The requested 2021-08-02 start is retained as an upper-bound filter only; no SM rows exist before 2025-02-05 in this artifact.\n"
        "- Costs: existing US research artifacts, 1 bps commission + 2 bps slippage.\n"
        "- SM data comes from the frozen `full_us_deans_60` main-window artifacts.\n"
        "- Composite data comes from `phase3_expert_pool_v2/expert_return_audit.parquet`.\n"
        "- The Phase 3 manifest is `status=failed`, `reason=data_quality_blocked`, with 1,315 raw price anomalies; results are diagnostic only.\n"
        "- Composite uses bounded continuous long exposure; its marker is an exposure start, not discrete buy/sell events.\n"
        "- `daily_win_rate` is the apples-to-apples win metric; `trade_win_rate` is only defined for SM here.\n",
        encoding="utf-8",
    )
    print(summary[[
        "symbol", "model", "coverage", "total_return", "sharpe", "max_drawdown",
        "daily_win_rate", "trade_count", "turnover", "transaction_cost", "mean_position",
    ]].to_string(index=False))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
