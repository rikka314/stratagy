"""
Tests for CN_A Factor Panel Builder

Covers:
- Factor metadata registry
- Panel schema and primary keys
- PIT compliance
- Missing data handling
- Quality validation
- Artifact generation
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import tempfile
import json

from model_test.cn_a_factor_panel import (
    get_factor_metadata_registry,
    build_cn_a_factor_panel,
    validate_panel_quality,
    save_panel_artifacts,
    compute_sha256,
)


@pytest.fixture
def sample_config():
    """Sample configuration for testing"""
    return {
        "schema_version": "1.0",
        "market": "CN_A",
        "universe": "test_universe",
        "random_seed": 42,
        "horizon_days": 20,
        "benchmark": {
            "policy": "frozen_universe_equal_weight",
            "symbol": None,
        },
        "factor_panel": {
            "warm_up_days": 20,
            "technical_factors": [
                "mom_short_z",
                "mom_long_z",
                "macd_z",
                "rsi_z",
            ],
            "market_factors": [
                "market_vol_level",
                "rel_strength_market",
                "market_breadth",
            ]
        },
        "source_lock": {
            "universe_snapshot_sha256": "test_hash",
            "expected_symbol_count": 2,
        },
        "quality_gates": {
            "universe_coverage": 1.0,
            "technical_factor_missing_rate": 0.01,
            "market_factor_missing_rate": 0.05,
            "duplicate_primary_key_rate": 0.0,
            "forward_looking_violations": 0,
        }
    }


@pytest.fixture
def sample_stock_data():
    """Generate sample stock data for testing"""
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    data = {
        'date': dates,
        'open': np.random.uniform(10, 20, 100),
        'high': np.random.uniform(15, 25, 100),
        'low': np.random.uniform(5, 15, 100),
        'close': np.random.uniform(10, 20, 100),
        'volume': np.random.uniform(1000000, 5000000, 100),
    }
    return pd.DataFrame(data)


class TestFactorMetadataRegistry:
    """Test factor metadata registry"""

    def test_registry_structure(self):
        """Test that registry returns valid metadata"""
        registry = get_factor_metadata_registry()

        assert isinstance(registry, dict)
        assert len(registry) > 0

        # Check a few known factors
        assert "mom_short_z" in registry
        assert "macd_z" in registry
        assert "market_vol_level" in registry

    def test_technical_factor_metadata(self):
        """Test technical factor metadata properties"""
        registry = get_factor_metadata_registry()

        tech_factor = registry["mom_short_z"]
        assert tech_factor.source == "technical"
        assert tech_factor.lookback_days > 0
        assert tech_factor.shift_days == 0
        assert tech_factor.available_at_decision is True

    def test_market_factor_metadata(self):
        """Test market factor metadata properties"""
        registry = get_factor_metadata_registry()

        market_factor = registry["market_vol_level"]
        assert market_factor.source == "market"
        assert market_factor.lookback_days > 0
        assert market_factor.available_at_decision is True

    def test_all_factors_have_missing_policy(self):
        """Test that all factors have a defined missing policy"""
        registry = get_factor_metadata_registry()

        valid_policies = ["drop", "forward_fill", "zero", "unavailable"]

        for name, meta in registry.items():
            assert meta.missing_policy in valid_policies, \
                f"Factor {name} has invalid missing policy: {meta.missing_policy}"


class TestPanelSchema:
    """Test panel schema and structure"""

    def test_panel_primary_key_columns(self, sample_config, tmp_path):
        """Test that panel has required primary key columns"""
        # Create minimal test data
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir()

        # Create two test stocks
        for symbol in ["TEST1", "TEST2"]:
            dates = pd.date_range('2023-01-01', periods=50, freq='D')
            df = pd.DataFrame({
                'date': dates,
                'open': np.random.uniform(10, 20, 50),
                'high': np.random.uniform(15, 25, 50),
                'low': np.random.uniform(5, 15, 50),
                'close': np.random.uniform(10, 20, 50),
                'volume': np.random.uniform(1000000, 5000000, 50),
            })
            df.to_csv(test_data_dir / f"{symbol}.csv", index=False)

        # Build panel
        panel = build_cn_a_factor_panel(
            symbols=["TEST1", "TEST2"],
            data_dir=test_data_dir,
            config=sample_config,
            warm_up_days=20,
        )

        # Check primary key columns exist
        assert 'date' in panel.columns
        assert 'symbol' in panel.columns
        assert 'market' in panel.columns

        # Check all market values are CN_A
        assert (panel['market'] == 'CN_A').all()

    def test_panel_no_duplicate_primary_keys(self, sample_config, tmp_path):
        """Test that panel has no duplicate primary keys"""
        # Create test data
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir()

        for symbol in ["TEST1", "TEST2"]:
            dates = pd.date_range('2023-01-01', periods=50, freq='D')
            df = pd.DataFrame({
                'date': dates,
                'open': np.random.uniform(10, 20, 50),
                'high': np.random.uniform(15, 25, 50),
                'low': np.random.uniform(5, 15, 50),
                'close': np.random.uniform(10, 20, 50),
                'volume': np.random.uniform(1000000, 5000000, 50),
            })
            df.to_csv(test_data_dir / f"{symbol}.csv", index=False)

        panel = build_cn_a_factor_panel(
            symbols=["TEST1", "TEST2"],
            data_dir=test_data_dir,
            config=sample_config,
            warm_up_days=20,
        )

        # Check no duplicates
        duplicates = panel.duplicated(subset=['date', 'symbol']).sum()
        assert duplicates == 0

    def test_panel_sorted_by_date_symbol(self, sample_config, tmp_path):
        """Test that panel is sorted by date then symbol"""
        test_data_dir = tmp_path / "data"
        test_data_dir.mkdir()

        for symbol in ["TEST1", "TEST2"]:
            dates = pd.date_range('2023-01-01', periods=50, freq='D')
            df = pd.DataFrame({
                'date': dates,
                'open': np.random.uniform(10, 20, 50),
                'high': np.random.uniform(15, 25, 50),
                'low': np.random.uniform(5, 15, 50),
                'close': np.random.uniform(10, 20, 50),
                'volume': np.random.uniform(1000000, 5000000, 50),
            })
            df.to_csv(test_data_dir / f"{symbol}.csv", index=False)

        panel = build_cn_a_factor_panel(
            symbols=["TEST1", "TEST2"],
            data_dir=test_data_dir,
            config=sample_config,
            warm_up_days=20,
        )

        # Check sorting
        sorted_panel = panel.sort_values(['date', 'symbol']).reset_index(drop=True)
        pd.testing.assert_frame_equal(panel, sorted_panel)


class TestQualityValidation:
    """Test quality validation"""

    def test_quality_validation_structure(self, sample_config):
        """Test quality validation returns proper structure"""
        # Create minimal panel
        panel = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=10),
            'symbol': ['TEST1'] * 10,
            'market': ['CN_A'] * 10,
            'mom_short_z': np.random.randn(10),
            'market_vol_level': np.random.randn(10),
        })

        factor_metadata = get_factor_metadata_registry()

        quality = validate_panel_quality(
            panel=panel,
            config=sample_config,
            factor_metadata=factor_metadata,
        )

        # Check structure
        assert hasattr(quality, 'status')
        assert hasattr(quality, 'total_rows')
        assert hasattr(quality, 'unique_symbols')
        assert hasattr(quality, 'coverage_rate')
        assert hasattr(quality, 'quality_flags')

    def test_quality_detects_coverage_issue(self, sample_config):
        """Test that quality validation detects coverage issues"""
        # Panel with only 1 symbol but expecting 2
        panel = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=10),
            'symbol': ['TEST1'] * 10,
            'market': ['CN_A'] * 10,
            'mom_short_z': np.random.randn(10),
        })

        factor_metadata = get_factor_metadata_registry()

        quality = validate_panel_quality(
            panel=panel,
            config=sample_config,
            factor_metadata=factor_metadata,
        )

        # Should detect coverage issue
        assert quality.coverage_rate < 1.0
        assert any('coverage' in flag for flag in quality.quality_flags)

    def test_quality_detects_duplicate_keys(self, sample_config):
        """Test that quality validation detects duplicate keys"""
        # Panel with duplicate date/symbol
        panel = pd.DataFrame({
            'date': ['2023-01-01', '2023-01-01', '2023-01-02'],
            'symbol': ['TEST1', 'TEST1', 'TEST1'],
            'market': ['CN_A'] * 3,
            'mom_short_z': [1.0, 2.0, 3.0],
        })
        panel['date'] = pd.to_datetime(panel['date'])

        factor_metadata = get_factor_metadata_registry()

        quality = validate_panel_quality(
            panel=panel,
            config=sample_config,
            factor_metadata=factor_metadata,
        )

        # Should detect duplicates
        assert quality.duplicate_primary_keys > 0
        assert quality.status == 'failed'


class TestArtifactGeneration:
    """Test artifact generation"""

    def test_save_artifacts_creates_files(self, sample_config, tmp_path):
        """Test that save_artifacts creates all expected files"""
        # Create minimal panel
        panel = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=10),
            'symbol': ['TEST1'] * 10,
            'market': ['CN_A'] * 10,
            'mom_short_z': np.random.randn(10),
        })

        factor_metadata = get_factor_metadata_registry()

        quality = validate_panel_quality(
            panel=panel,
            config=sample_config,
            factor_metadata=factor_metadata,
        )

        output_dir = tmp_path / "output"

        manifest = save_panel_artifacts(
            panel=panel,
            quality=quality,
            config=sample_config,
            factor_metadata=factor_metadata,
            output_dir=output_dir,
        )

        # Check files exist
        assert (output_dir / "cn_a_factor_panel.parquet").exists()
        assert (output_dir / "factor_schema.json").exists()
        assert (output_dir / "factor_quality.json").exists()
        assert (output_dir / "factor_quality.md").exists()
        assert (output_dir / "source_lineage.json").exists()
        assert (output_dir / "factor_manifest.json").exists()

    def test_manifest_contains_hashes(self, sample_config, tmp_path):
        """Test that manifest contains artifact hashes"""
        panel = pd.DataFrame({
            'date': pd.date_range('2023-01-01', periods=10),
            'symbol': ['TEST1'] * 10,
            'market': ['CN_A'] * 10,
        })

        factor_metadata = get_factor_metadata_registry()

        quality = validate_panel_quality(
            panel=panel,
            config=sample_config,
            factor_metadata=factor_metadata,
        )

        output_dir = tmp_path / "output"

        manifest = save_panel_artifacts(
            panel=panel,
            quality=quality,
            config=sample_config,
            factor_metadata=factor_metadata,
            output_dir=output_dir,
        )

        # Check manifest structure
        assert "artifacts" in manifest
        assert "cn_a_factor_panel.parquet" in manifest["artifacts"]
        assert len(manifest["artifacts"]["cn_a_factor_panel.parquet"]) == 64  # SHA-256 hex length


class TestComputeSHA256:
    """Test SHA-256 computation"""

    def test_compute_sha256_deterministic(self):
        """Test that SHA-256 is deterministic"""
        data = b"test data"
        hash1 = compute_sha256(data)
        hash2 = compute_sha256(data)

        assert hash1 == hash2

    def test_compute_sha256_different_data(self):
        """Test that different data produces different hashes"""
        hash1 = compute_sha256(b"data1")
        hash2 = compute_sha256(b"data2")

        assert hash1 != hash2

    def test_compute_sha256_length(self):
        """Test that SHA-256 produces 64 hex characters"""
        data = b"test"
        hash_value = compute_sha256(data)

        assert len(hash_value) == 64
        assert all(c in '0123456789abcdef' for c in hash_value)
