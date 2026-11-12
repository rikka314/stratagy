"""使用多数据源下载 VIX 和 SPY 宏观数据

优先级: pandas_datareader (FRED/CBOE) -> 本地样例数据
"""

import pandas as pd
from pathlib import Path
import json
import sys
from datetime import datetime


def download_vix_spy_data():
    """下载并保存 VIX 和 SPY 数据"""

    # 创建目录
    macro_dir = Path("data/macro")
    macro_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 方法 1: 尝试使用 pandas_datareader
        try:
            import pandas_datareader as pdr
            print("Using pandas_datareader...")

            # 下载 VIX 从 FRED
            print("Downloading VIX from FRED...")
            vix_df = pdr.get_data_fred("VIXCLS", start="2015-01-01")
            vix_df = vix_df.reset_index()
            vix_df.columns = ['date', 'close']
            vix_df['date'] = pd.to_datetime(vix_df['date']).dt.date

            # 为 VIX 添加 open/high/low (使用 close 作为近似)
            vix_df['open'] = vix_df['close']
            vix_df['high'] = vix_df['close']
            vix_df['low'] = vix_df['close']
            vix_df = vix_df[['date', 'open', 'high', 'low', 'close']]

            print(f"[OK] Downloaded VIX: {len(vix_df)} rows")

        except ImportError:
            print("pandas_datareader not available, using alternative...")
            # 方法 2: 使用 AkShare 下载美股 SPY，然后估算 VIX
            import akshare as ak

            # 创建简化的 VIX 数据 (使用 SPY 波动率估算)
            print("Creating VIX estimate from SPY volatility...")
            spy_temp = ak.stock_us_hist(symbol="SPY", period="daily", adjust="qfq")
            spy_temp = spy_temp.rename(columns={'日期': 'date', '收盘': 'close'})
            spy_temp['date'] = pd.to_datetime(spy_temp['date'])
            spy_temp = spy_temp.sort_values('date')

            # 计算 20 日滚动波动率 * 100 作为 VIX 代理
            spy_temp['returns'] = spy_temp['close'].pct_change()
            spy_temp['vix_estimate'] = spy_temp['returns'].rolling(20).std() * 100 * (252 ** 0.5)
            spy_temp['vix_estimate'] = spy_temp['vix_estimate'].fillna(15.0)  # 默认值

            vix_df = spy_temp[['date', 'vix_estimate']].copy()
            vix_df = vix_df.rename(columns={'vix_estimate': 'close'})
            vix_df['date'] = vix_df['date'].dt.date
            vix_df['open'] = vix_df['close']
            vix_df['high'] = vix_df['close']
            vix_df['low'] = vix_df['close']
            vix_df = vix_df[['date', 'open', 'high', 'low', 'close']]

            print(f"[OK] Created VIX estimate: {len(vix_df)} rows")

        # 保存 VIX
        vix_path = macro_dir / "vix_daily.parquet"
        vix_df.to_parquet(vix_path, index=False)
        print(f"  Date range: {vix_df['date'].min()} to {vix_df['date'].max()}")

        # 下载 SPY (使用 AkShare)
        print("\nDownloading SPY from AkShare...")
        import akshare as ak
        spy_df = ak.stock_us_hist(symbol="SPY", period="daily", adjust="qfq")

        if spy_df.empty:
            print("[ERROR] SPY download failed: empty data")
            return False

        # 重命名列
        spy_df = spy_df.rename(columns={
            '日期': 'date',
            '开盘': 'open',
            '最高': 'high',
            '最低': 'low',
            '收盘': 'close',
            '成交量': 'volume',
        })

        spy_df = spy_df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
        spy_df['date'] = pd.to_datetime(spy_df['date']).dt.date
        spy_df = spy_df.sort_values('date').reset_index(drop=True)

        spy_path = macro_dir / "spy_daily.parquet"
        spy_df.to_parquet(spy_path, index=False)
        print(f"[OK] Saved SPY: {len(spy_df)} rows")
        print(f"  Date range: {spy_df['date'].min()} to {spy_df['date'].max()}")

        # 生成 manifest
        manifest = {
            "vix_daily.parquet": {
                "source": "pandas_datareader.FRED or SPY volatility estimate",
                "rows": len(vix_df),
                "date_range": [str(vix_df['date'].min()), str(vix_df['date'].max())],
                "columns": list(vix_df.columns),
            },
            "spy_daily.parquet": {
                "source": "akshare.stock_us_hist(SPY, qfq)",
                "rows": len(spy_df),
                "date_range": [str(spy_df['date'].min()), str(spy_df['date'].max())],
                "columns": list(spy_df.columns),
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
    success = download_vix_spy_data()
    sys.exit(0 if success else 1)
