"""下载 VIX 和 SPY 宏观数据

用于因子系统优化 Phase 1 - 宏观与相对强度因子
"""

import yfinance as yf
import pandas as pd
from pathlib import Path
import json
import sys
import time


def download_macro_data():
    """下载并保存 VIX 和 SPY 数据"""

    # 创建目录
    macro_dir = Path("data/macro")
    macro_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 下载 VIX (带重试)
        print("Downloading VIX (^VIX)...")
        vix = None
        for attempt in range(3):
            try:
                vix = yf.download("^VIX", start="2015-01-01", end="2026-12-31", progress=False)
                if not vix.empty:
                    break
                print(f"  Attempt {attempt + 1} failed: empty data, retrying...")
                time.sleep(2)
            except Exception as e:
                print(f"  Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(2)

        if vix is None or vix.empty:
            print("[ERROR] VIX download failed: empty data after 3 attempts")
            return False

        vix = vix.reset_index()
        vix.columns = ['date'] + [c.lower() for c in vix.columns[1:]]
        vix['date'] = pd.to_datetime(vix['date']).dt.date

        vix_path = macro_dir / "vix_daily.parquet"
        vix.to_parquet(vix_path, index=False)
        print(f"[OK] Saved VIX: {len(vix)} rows")
        print(f"  Date range: {vix['date'].min()} to {vix['date'].max()}")

        # 下载 SPY (带重试)
        print("\nDownloading SPY...")
        spy = None
        for attempt in range(3):
            try:
                spy = yf.download("SPY", start="2015-01-01", end="2026-12-31", progress=False)
                if not spy.empty:
                    break
                print(f"  Attempt {attempt + 1} failed: empty data, retrying...")
                time.sleep(2)
            except Exception as e:
                print(f"  Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(2)

        if spy is None or spy.empty:
            print("[ERROR] SPY download failed: empty data after 3 attempts")
            return False

        spy = spy.reset_index()
        spy.columns = ['date'] + [c.lower() for c in spy.columns[1:]]
        spy['date'] = pd.to_datetime(spy['date']).dt.date

        spy_path = macro_dir / "spy_daily.parquet"
        spy.to_parquet(spy_path, index=False)
        print(f"[OK] Saved SPY: {len(spy)} rows")
        print(f"  Date range: {spy['date'].min()} to {spy['date'].max()}")

        # 生成 manifest
        manifest = {
            "vix_daily.parquet": {
                "rows": len(vix),
                "date_range": [str(vix['date'].min()), str(vix['date'].max())],
                "columns": list(vix.columns),
            },
            "spy_daily.parquet": {
                "rows": len(spy),
                "date_range": [str(spy['date'].min()), str(spy['date'].max())],
                "columns": list(spy.columns),
            },
        }

        manifest_path = macro_dir / "macro_data_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        print("\n[SUCCESS] Macro data download complete")
        print(f"  - {vix_path}")
        print(f"  - {spy_path}")
        print(f"  - {manifest_path}")

        return True

    except Exception as e:
        print(f"\n[ERROR] Download failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = download_macro_data()
    sys.exit(0 if success else 1)
