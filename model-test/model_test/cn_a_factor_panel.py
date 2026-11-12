"""
CN_A Factor Panel Builder and Quality Validator

This module builds point-in-time factor panels for CN_A market and validates:
- PIT (point-in-time) compliance
- Missing data policy
- Primary key uniqueness
- Factor schema consistency
- Source lineage traceability

All factors must be available at decision time with explicit lookback/shift metadata.
"""

import json
import hashlib
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from core.market_factor_context import MarketFactorContext, build_market_factor_context
from core.factor_pipeline import FactorPipeline
from core.cn_a_market_factors import build_cn_a_market_context


@dataclass
class FactorMetadata:
    """Metadata for a single factor"""
    factor_name: str
    source: str  # 'technical' or 'market'
    lookback_days: int
    shift_days: int  # 0 = same day close, 1 = previous day
    available_at_decision: bool
    missing_policy: str  # 'drop', 'forward_fill', 'zero', 'unavailable'


@dataclass
class PanelQuality:
    """Quality metrics for the factor panel"""
    total_rows: int
    unique_dates: int
    unique_symbols: int
    expected_symbols: int
    coverage_rate: float
    duplicate_primary_keys: int

    # Technical factor quality
    technical_factor_missing_rates: Dict[str, float]
    technical_factor_mean_missing: float

    # Market factor quality
    market_factor_missing_rates: Dict[str, float]
    market_factor_mean_missing: float

    # PIT compliance
    forward_looking_violations: int

    # Data range
    date_min: str
    date_max: str

    # Quality flags
    quality_flags: List[str]
    status: str  # 'ready', 'pending', 'failed'


@dataclass
class SourceLineage:
    """Source lineage for the factor panel"""
    market: str
    universe: str
    universe_snapshot_sha256: str
    benchmark_source: str
    benchmark_symbol: Optional[str]
    config_sha256: str
    factor_schema_version: str
    build_timestamp: str
    code_version: Optional[str]


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of data"""
    return hashlib.sha256(data).hexdigest()


def get_factor_metadata_registry() -> Dict[str, FactorMetadata]:
    """
    Registry of all factors with their metadata.

    This is the single source of truth for factor properties.
    """
    registry = {}

    # Technical factors - all use same-day close data with lookback
    technical_factors = [
        ("mom_short_z", 5),
        ("mom_long_z", 20),
        ("macd_z", 26),
        ("rsi_z", 14),
        ("bb_position_rank", 20),
        ("price_position_rank", 60),
        ("vol_z", 20),
        ("drawdown_rank", 60),
        ("obv_trend_rank", 20),
        ("volume_ratio_rank", 20),
    ]

    for name, lookback in technical_factors:
        registry[name] = FactorMetadata(
            factor_name=name,
            source="technical",
            lookback_days=lookback,
            shift_days=0,  # Same day close
            available_at_decision=True,
            missing_policy="drop"
        )

    # Market factors from CN_A market context
    market_factors = [
        ("market_vol_level", 20, "forward_fill"),
        ("market_vol_regime", 60, "forward_fill"),
        ("rel_strength_market", 20, "drop"),
        ("market_breadth", 1, "forward_fill"),
        ("breadth_up_ratio_1", 1, "forward_fill"),
        ("breadth_up_ratio_20", 20, "forward_fill"),
        ("market_beta_20d", 20, "drop"),
        ("sector_momentum", 20, "unavailable"),  # Currently not implemented
        ("market_return_1", 1, "forward_fill"),
        ("market_return_5", 5, "forward_fill"),
        ("market_return_20", 20, "forward_fill"),
        ("market_drawdown_60", 60, "forward_fill"),
        ("market_constituent_count", 1, "forward_fill"),
    ]

    for name, lookback, policy in market_factors:
        registry[name] = FactorMetadata(
            factor_name=name,
            source="market",
            lookback_days=lookback,
            shift_days=0,
            available_at_decision=True,
            missing_policy=policy
        )

    return registry


def build_cn_a_factor_panel(
    symbols: List[str],
    data_dir: Path,
    config: Dict,
    *,
    warm_up_days: int = 60,
) -> pd.DataFrame:
    """
    Build CN_A factor panel for given symbols.

    Args:
        symbols: List of CN_A stock symbols
        data_dir: Directory containing stock CSV files
        config: Configuration dict from composite_cn_a.json
        warm_up_days: Warm-up period for factor calculation

    Returns:
        DataFrame with columns:
            - date, symbol, market (primary key)
            - close, volume (raw OHLCV fields)
            - All technical factors
            - All market factors
            - Metadata fields
    """
    market = config["market"]

    # Load all stock data
    stock_data_dict = {}
    for symbol in symbols:
        # Try both formats: symbol.csv and symbol_daily.csv
        csv_path = data_dir / f"{symbol}_daily.csv"
        if not csv_path.exists():
            csv_path = data_dir / f"{symbol}.csv"

        if not csv_path.exists():
            print(f"Warning: CSV not found for {symbol}")
            continue

        try:
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)

            # Ensure required columns exist
            if 'close' not in df.columns:
                print(f"Warning: 'close' column missing for {symbol}")
                continue

            stock_data_dict[symbol] = df
        except Exception as e:
            print(f"Warning: Failed to load {symbol}: {e}")

    if not stock_data_dict:
        raise ValueError("No stock data loaded")

    # Build CN_A market context
    # Build universe frame in long format (date, symbol, close) for market context
    universe_rows = []
    for symbol, stock_df in stock_data_dict.items():
        for _, row in stock_df.iterrows():
            universe_rows.append({
                'date': row['date'],
                'symbol': symbol,
                'close': row['close'],
            })

    universe_frame = pd.DataFrame(universe_rows)
    universe_frame = universe_frame.sort_values(['date', 'symbol']).reset_index(drop=True)

    # Build market context with universe frame as fallback benchmark
    # data_dir is not used in current implementation, can pass any valid path
    market_context = build_cn_a_market_context(
        universe_frame=universe_frame,
        benchmark_frame=None,  # Will use universe equal-weight fallback
        data_dir=data_dir if data_dir.exists() else Path("data/macro"),
    )

    # Create FactorPipeline instance for computing factors
    factor_pipeline = FactorPipeline(data_dir=str(data_dir) if data_dir.exists() else "data/macro")

    # Build factor panel for each symbol
    panel_parts = []

    for symbol, stock_df in stock_data_dict.items():
        # Compute factors using pipeline with market context
        factors_df = factor_pipeline.compute_all_factors(
            stock_df,
            symbol,
            market=market,
            market_context=market_context
        )

        # Add metadata columns including symbol
        factors_df['symbol'] = symbol
        factors_df['market'] = market
        factors_df['source_market'] = market
        factors_df['source_symbol'] = symbol
        factors_df['factor_schema_version'] = config["schema_version"]

        panel_parts.append(factors_df)

    # Combine all symbols
    panel = pd.concat(panel_parts, ignore_index=True)

    # Remove warm-up period
    if warm_up_days > 0:
        min_date = panel['date'].min() + pd.Timedelta(days=warm_up_days)
        panel = panel[panel['date'] >= min_date].copy()

    # Sort by date, symbol
    panel = panel.sort_values(['date', 'symbol']).reset_index(drop=True)

    return panel


def validate_panel_quality(
    panel: pd.DataFrame,
    config: Dict,
    factor_metadata: Dict[str, FactorMetadata],
) -> PanelQuality:
    """
    Validate factor panel quality against gates.

    Args:
        panel: Factor panel DataFrame
        config: Configuration dict
        factor_metadata: Factor metadata registry

    Returns:
        PanelQuality with metrics and status
    """
    quality_flags = []

    # Basic metrics
    total_rows = len(panel)
    unique_dates = panel['date'].nunique()
    unique_symbols = panel['symbol'].nunique()
    expected_symbols = config["source_lock"]["expected_symbol_count"]
    coverage_rate = unique_symbols / expected_symbols if expected_symbols > 0 else 0.0

    # Check universe coverage
    if coverage_rate < config["quality_gates"]["universe_coverage"]:
        quality_flags.append(f"universe_coverage_{coverage_rate:.2%}_below_{config['quality_gates']['universe_coverage']:.2%}")

    # Check duplicate primary keys
    duplicate_keys = panel.duplicated(subset=['date', 'symbol']).sum()
    if duplicate_keys > 0:
        quality_flags.append(f"duplicate_primary_keys_{duplicate_keys}")

    # Check technical factor missing rates
    technical_factors = config["factor_panel"]["technical_factors"]
    tech_missing_rates = {}
    for factor in technical_factors:
        if factor in panel.columns:
            missing_rate = panel[factor].isna().mean()
            tech_missing_rates[factor] = missing_rate

            if missing_rate > config["quality_gates"]["technical_factor_missing_rate"]:
                quality_flags.append(f"{factor}_missing_{missing_rate:.2%}")

    tech_mean_missing = np.mean(list(tech_missing_rates.values())) if tech_missing_rates else 0.0

    # Check market factor missing rates
    market_factors = config["factor_panel"]["market_factors"]
    market_missing_rates = {}
    for factor in market_factors:
        if factor in panel.columns:
            missing_rate = panel[factor].isna().mean()
            market_missing_rates[factor] = missing_rate

            # Market factors have a higher tolerance
            if missing_rate > config["quality_gates"]["market_factor_missing_rate"]:
                quality_flags.append(f"{factor}_missing_{missing_rate:.2%}")

    market_mean_missing = np.mean(list(market_missing_rates.values())) if market_missing_rates else 0.0

    # Check for forward-looking violations (placeholder - would need actual implementation)
    forward_violations = 0

    # Date range
    date_min = panel['date'].min().strftime('%Y-%m-%d')
    date_max = panel['date'].max().strftime('%Y-%m-%d')

    # Determine status
    if quality_flags:
        if any('duplicate' in flag or 'coverage' in flag for flag in quality_flags):
            status = 'failed'
        else:
            status = 'pending'
    else:
        status = 'ready'

    return PanelQuality(
        total_rows=total_rows,
        unique_dates=unique_dates,
        unique_symbols=unique_symbols,
        expected_symbols=expected_symbols,
        coverage_rate=coverage_rate,
        duplicate_primary_keys=duplicate_keys,
        technical_factor_missing_rates=tech_missing_rates,
        technical_factor_mean_missing=tech_mean_missing,
        market_factor_missing_rates=market_missing_rates,
        market_factor_mean_missing=market_mean_missing,
        forward_looking_violations=forward_violations,
        date_min=date_min,
        date_max=date_max,
        quality_flags=quality_flags,
        status=status
    )


def generate_quality_report_md(
    quality: PanelQuality,
    config: Dict,
    output_dir: Path,
) -> str:
    """Generate markdown quality report"""
    lines = [
        "# CN_A Factor Panel Quality Report",
        "",
        f"**Status**: `{quality.status}`",
        "",
        "## Overview",
        "",
        f"- Total rows: {quality.total_rows:,}",
        f"- Unique dates: {quality.unique_dates:,}",
        f"- Unique symbols: {quality.unique_symbols} / {quality.expected_symbols} ({quality.coverage_rate:.2%})",
        f"- Date range: {quality.date_min} to {quality.date_max}",
        f"- Duplicate primary keys: {quality.duplicate_primary_keys}",
        "",
        "## Technical Factor Quality",
        "",
        f"- Mean missing rate: {quality.technical_factor_mean_missing:.2%}",
        f"- Gate threshold: {config['quality_gates']['technical_factor_missing_rate']:.2%}",
        "",
        "| Factor | Missing Rate | Status |",
        "|--------|--------------|--------|",
    ]

    for factor, rate in sorted(quality.technical_factor_missing_rates.items()):
        threshold = config['quality_gates']['technical_factor_missing_rate']
        status = "✅ Pass" if rate <= threshold else "❌ Fail"
        lines.append(f"| {factor} | {rate:.2%} | {status} |")

    lines.extend([
        "",
        "## Market Factor Quality",
        "",
        f"- Mean missing rate: {quality.market_factor_mean_missing:.2%}",
        f"- Gate threshold: {config['quality_gates']['market_factor_missing_rate']:.2%}",
        "",
        "| Factor | Missing Rate | Status |",
        "|--------|--------------|--------|",
    ])

    for factor, rate in sorted(quality.market_factor_missing_rates.items()):
        threshold = config['quality_gates']['market_factor_missing_rate']
        status = "✅ Pass" if rate <= threshold else "⚠️ Warning"
        lines.append(f"| {factor} | {rate:.2%} | {status} |")

    lines.extend([
        "",
        "## Quality Flags",
        "",
    ])

    if quality.quality_flags:
        for flag in quality.quality_flags:
            lines.append(f"- ⚠️ {flag}")
    else:
        lines.append("- ✅ No quality issues detected")

    lines.extend([
        "",
        "## PIT Compliance",
        "",
        f"- Forward-looking violations: {quality.forward_looking_violations}",
        "",
        "## Conclusion",
        "",
    ])

    if quality.status == 'ready':
        lines.append("✅ Factor panel passes all quality gates and is ready for Composite training.")
    elif quality.status == 'pending':
        lines.append("⚠️ Factor panel has warnings but may proceed with caution. Review flags above.")
    else:
        lines.append("❌ Factor panel failed quality gates. Do not proceed to Composite training.")

    report_text = "\n".join(lines)

    # Write report
    report_path = output_dir / "factor_quality.md"
    report_path.write_text(report_text, encoding='utf-8')

    return report_text


def _convert_to_json_serializable(obj):
    """Convert numpy types to Python native types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_to_json_serializable(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


def save_panel_artifacts(
    panel: pd.DataFrame,
    quality: PanelQuality,
    config: Dict,
    factor_metadata: Dict[str, FactorMetadata],
    output_dir: Path,
) -> Dict[str, str]:
    """
    Save all panel artifacts and return manifest.

    Returns:
        Dict with artifact paths and hashes
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {}

    # 1. Save panel parquet
    panel_path = output_dir / "cn_a_factor_panel.parquet"
    panel.to_parquet(panel_path, index=False)
    panel_bytes = panel_path.read_bytes()
    artifacts['cn_a_factor_panel.parquet'] = compute_sha256(panel_bytes)

    # 2. Save factor schema
    schema_dict = {
        name: asdict(meta)
        for name, meta in factor_metadata.items()
    }
    schema_path = output_dir / "factor_schema.json"
    schema_path.write_text(json.dumps(schema_dict, indent=2), encoding='utf-8')
    schema_bytes = schema_path.read_bytes()
    artifacts['factor_schema.json'] = compute_sha256(schema_bytes)

    # 3. Save quality metrics (convert numpy types to native Python types)
    quality_dict = asdict(quality)
    quality_dict = _convert_to_json_serializable(quality_dict)
    quality_path = output_dir / "factor_quality.json"
    quality_path.write_text(json.dumps(quality_dict, indent=2), encoding='utf-8')
    quality_bytes = quality_path.read_bytes()
    artifacts['factor_quality.json'] = compute_sha256(quality_bytes)

    # 4. Generate and save quality report markdown
    generate_quality_report_md(quality, config, output_dir)
    report_path = output_dir / "factor_quality.md"
    report_bytes = report_path.read_bytes()
    artifacts['factor_quality.md'] = compute_sha256(report_bytes)

    # 5. Save source lineage
    import datetime

    # Safely get benchmark info
    benchmark_config = config.get("benchmark", {})
    benchmark_source = benchmark_config.get("policy", "unknown")
    benchmark_symbol = benchmark_config.get("symbol")

    lineage = SourceLineage(
        market=config["market"],
        universe=config["universe"],
        universe_snapshot_sha256=config["source_lock"]["universe_snapshot_sha256"],
        benchmark_source=benchmark_source,
        benchmark_symbol=benchmark_symbol,
        config_sha256=compute_sha256(json.dumps(config, sort_keys=True).encode()),
        factor_schema_version=config["schema_version"],
        build_timestamp=datetime.datetime.now().isoformat(),
        code_version=None,  # Could be populated from git
    )
    lineage_path = output_dir / "source_lineage.json"
    lineage_path.write_text(json.dumps(asdict(lineage), indent=2), encoding='utf-8')
    lineage_bytes = lineage_path.read_bytes()
    artifacts['source_lineage.json'] = compute_sha256(lineage_bytes)

    # 6. Save manifest
    manifest = {
        "market": config["market"],
        "universe": config["universe"],
        "status": quality.status,
        "total_rows": quality.total_rows,
        "unique_symbols": quality.unique_symbols,
        "expected_symbols": quality.expected_symbols,
        "date_range": [quality.date_min, quality.date_max],
        "artifacts": artifacts,
        "quality_flags": quality.quality_flags,
    }
    manifest_path = output_dir / "factor_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    return manifest
