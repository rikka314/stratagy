"""
Build CN_A Factor Panel CLI

Usage:
    python model-test/build_cn_a_factor_panel.py --config model-test/configs/composite_cn_a.json

This script:
1. Loads CN_A universe symbols from the frozen source
2. Builds market-native CN_A factor panel
3. Validates PIT compliance and quality gates
4. Saves panel parquet, manifest, quality report, and lineage
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from model_test.cn_a_factor_panel import (
    build_cn_a_factor_panel,
    validate_panel_quality,
    save_panel_artifacts,
    get_factor_metadata_registry,
)


def load_universe_symbols(data_dir: Path, universe_name: str, expand_to: int = None) -> list[str]:
    """
    Load CN_A universe symbols from data directory.

    Expected structure:
        model-test/outputs/<universe_name>/data_snapshot/<symbol>_daily.csv

    Args:
        data_dir: Data directory path
        universe_name: Universe name
        expand_to: If provided, expand to N symbols from catalog
    """
    # Use the frozen universe snapshot
    snapshot_dir = Path("model-test/outputs") / universe_name / "data_snapshot"

    if not snapshot_dir.exists():
        raise FileNotFoundError(f"CN_A snapshot directory not found: {snapshot_dir}")

    # Get all CSV files
    csv_files = sorted(snapshot_dir.glob("*_daily.csv"))
    symbols = [f.stem.replace("_daily", "") for f in csv_files]

    if not symbols:
        raise ValueError(f"No symbols found in {snapshot_dir}")

    print(f"Loaded {len(symbols)} symbols from {snapshot_dir}")

    # If expand_to is specified and we need more symbols
    if expand_to and len(symbols) < expand_to:
        print(f"Expanding from {len(symbols)} to {expand_to} symbols using catalog...")

        # Load catalog
        catalog_path = Path("core/catalogs/a_stock_catalog.csv")
        if catalog_path.exists():
            import pandas as pd
            catalog = pd.read_csv(catalog_path)
            all_symbols = catalog['code'].astype(str).str.zfill(6).tolist()

            # Add symbols from catalog that have data available
            additional_needed = expand_to - len(symbols)
            for sym in all_symbols:
                if sym not in symbols:
                    # Check if data exists
                    sym_path = snapshot_dir / f"{sym}_daily.csv"
                    if sym_path.exists():
                        symbols.append(sym)
                        if len(symbols) >= expand_to:
                            break

            print(f"Expanded to {len(symbols)} symbols")

    return symbols[:expand_to] if expand_to else symbols


def verify_source_lock(symbols: list[str], config: dict) -> bool:
    """
    Verify that loaded symbols match the source lock.

    Returns:
        True if verification passes
    """
    expected_count = config["source_lock"]["expected_symbol_count"]
    actual_count = len(symbols)

    if actual_count != expected_count:
        print(f"[ERROR] Universe count mismatch: expected {expected_count}, got {actual_count}")
        return False

    print(f"[OK] Universe count verified: {actual_count} symbols")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Build CN_A factor panel for Composite research"
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to composite_cn_a.json config file"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Override data directory (default: project_root/data)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory (default: from config)"
    )

    args = parser.parse_args()

    # Load config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    print(f"[OK] Loaded config: {config_path}")
    print(f"   Market: {config['market']}")
    print(f"   Universe: {config['universe']}")
    print(f"   Schema version: {config['schema_version']}")

    # Determine data directory
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        data_dir = project_root / "data"

    if not data_dir.exists():
        print(f"[ERROR] Data directory not found: {data_dir}")
        sys.exit(1)

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_subdir = config.get("output_subdir", "composite_cn_a")
        output_dir = project_root / "model-test" / "outputs" / output_subdir

    print(f"[OK] Data directory: {data_dir}")
    print(f"[OK] Output directory: {output_dir}")
    print()

    # Load universe symbols
    print("=" * 60)
    print("STEP 1: Load Universe Symbols")
    print("=" * 60)

    try:
        symbols = load_universe_symbols(data_dir, config["universe"])
    except Exception as e:
        print(f"[ERROR] Failed to load universe symbols: {e}")
        sys.exit(1)

    # Verify source lock
    if not verify_source_lock(symbols, config):
        print("[ERROR] Source lock verification failed")
        sys.exit(1)

    print()

    # Build factor panel
    print("=" * 60)
    print("STEP 2: Build Factor Panel")
    print("=" * 60)

    warm_up_days = config["factor_panel"].get("warm_up_days", 60)
    print(f"Warm-up period: {warm_up_days} days")
    print(f"Technical factors: {len(config['factor_panel']['technical_factors'])}")
    print(f"Market factors: {len(config['factor_panel']['market_factors'])}")
    print()
    print("Building panel... (this may take a few minutes)")

    # Use snapshot directory as data source
    snapshot_dir = project_root / "model-test" / "outputs" / config["universe"] / "data_snapshot"

    try:
        panel = build_cn_a_factor_panel(
            symbols=symbols,
            data_dir=snapshot_dir,
            config=config,
            warm_up_days=warm_up_days,
        )
        print(f"[OK] Panel built: {len(panel):,} rows")
        print(f"   Date range: {panel['date'].min()} to {panel['date'].max()}")
        print(f"   Symbols: {panel['symbol'].nunique()}")
    except Exception as e:
        print(f"[ERROR] Failed to build panel: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()

    # Validate quality
    print("=" * 60)
    print("STEP 3: Validate Quality")
    print("=" * 60)

    factor_metadata = get_factor_metadata_registry()

    try:
        quality = validate_panel_quality(
            panel=panel,
            config=config,
            factor_metadata=factor_metadata,
        )

        print(f"Status: {quality.status}")
        print(f"Total rows: {quality.total_rows:,}")
        print(f"Universe coverage: {quality.coverage_rate:.2%}")
        print(f"Duplicate primary keys: {quality.duplicate_primary_keys}")
        print(f"Technical factor mean missing: {quality.technical_factor_mean_missing:.2%}")
        print(f"Market factor mean missing: {quality.market_factor_mean_missing:.2%}")
        print(f"Forward-looking violations: {quality.forward_looking_violations}")

        if quality.quality_flags:
            print("\n[WARN] Quality Flags:")
            for flag in quality.quality_flags:
                print(f"  - {flag}")
        else:
            print("\n[OK] No quality issues detected")

    except Exception as e:
        print(f"[ERROR] Failed to validate quality: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()

    # Save artifacts
    print("=" * 60)
    print("STEP 4: Save Artifacts")
    print("=" * 60)

    try:
        manifest = save_panel_artifacts(
            panel=panel,
            quality=quality,
            config=config,
            factor_metadata=factor_metadata,
            output_dir=output_dir,
        )

        print(f"[OK] Artifacts saved to: {output_dir}")
        print("\nArtifacts:")
        for filename, sha256 in manifest["artifacts"].items():
            print(f"  - {filename}")
            print(f"    SHA-256: {sha256}")

    except Exception as e:
        print(f"[ERROR] Failed to save artifacts: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Status: {quality.status}")

    if quality.status == 'ready':
        print("[OK] Factor panel is ready for Composite training (Phase 4)")
        sys.exit(0)
    elif quality.status == 'pending':
        print("[WARN] Factor panel has warnings. Review quality report before proceeding.")
        sys.exit(0)
    else:
        print("[ERROR] Factor panel failed quality gates. Do not proceed to Phase 4.")
        sys.exit(1)


if __name__ == "__main__":
    main()
