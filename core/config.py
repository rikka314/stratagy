"""
全局常量配置
============
存放所有全局常量和预设策略参数。
"""

import os
import tempfile

# ============ 全局常量配置 ============
# 使用系统临时目录缓存股票数据，不占用持久磁盘空间
# 服务重启后缓存自动清理，数据按需重新下载
DATA_DIR = os.path.join(tempfile.gettempdir(), "stratagy_cache")
DEFAULT_SYMBOL = "AAPL"  # 默认股票代码（苹果公司）
DEFAULT_ADJUST = "qfq"  # 默认复权方式：前复权（qfq=前复权，hfq=后复权，none=不复权）

# 默认股票列表（硬编码，无需预下载 CSV 文件）
# 用户可以通过界面添加更多股票
DEFAULT_STOCKS = ["AAPL", "TSLA", "NVDA", "GOOGL", "META", "ORCL", "ADM", "NTR", "CTVA"]

# ===== 预设策略参数（供高级策略预评估使用）=====
# 注意：这些参数与 UI 中的 STRATEGY_PRESETS 保持一致
_PRESET_PARAMS_FOR_OPTIMIZATION = {
    "趋势跟随（保守）": {
        "entry_threshold": 0.2, "exit_threshold": -0.3,
        "adx_threshold": 15, "stop_loss_mult": 1.5, "take_profit_mult": 3.0,
        "ema_fast": 20, "ema_slow": 60,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "rsi_period": 14, "rsi_lower": 35, "rsi_upper": 65,
        "adx_period": 14, "atr_period": 14,
        "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
        "weight_bb": 0.8, "weight_obv": 1.0,
        "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
    },
    "均衡策略（默认）": {
        "entry_threshold": 0.5, "exit_threshold": -0.5,
        "adx_threshold": 20, "stop_loss_mult": 2.0, "take_profit_mult": 4.0,
        "ema_fast": 20, "ema_slow": 60,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "rsi_period": 14, "rsi_lower": 30, "rsi_upper": 70,
        "adx_period": 14, "atr_period": 14,
        "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
        "weight_bb": 0.8, "weight_obv": 1.0,
        "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
    },
    "动量突破（激进）": {
        "entry_threshold": 0.8, "exit_threshold": -0.2,
        "adx_threshold": 25, "stop_loss_mult": 3.0, "take_profit_mult": 6.0,
        "ema_fast": 15, "ema_slow": 50,
        "macd_fast": 10, "macd_slow": 22, "macd_signal": 8,
        "rsi_period": 12, "rsi_lower": 25, "rsi_upper": 75,
        "adx_period": 12, "atr_period": 12,
        "bb_period": 18, "bb_std": 2.2, "indicator_period": 18,
        "weight_bb": 0.6, "weight_obv": 1.2,
        "weight_volume": 0.8, "weight_price": 0.5, "weight_drawdown": 0.3,
    },
}

# UI 中完整的预设策略定义（含描述和额外字段）
STRATEGY_PRESETS = {
    "趋势跟随（保守）": {
        "description": "宽松入场、快速止损，适合震荡市或新手",
        "entry_min_signals": 2, "exit_min_signals": 1,
        "entry_threshold": 0.2, "exit_threshold": -0.3,
        "adx_threshold": 15, "stop_loss_mult": 1.5, "take_profit_mult": 3.0,
        "ema_fast": 20, "ema_slow": 60,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "rsi_period": 14, "rsi_lower": 35, "rsi_upper": 65,
        "adx_period": 14, "atr_period": 14,
        "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
        "momentum_short": 5, "momentum_long": 20,
        "score_lookback": 30, "score_mid_pct": 0.55, "score_high_pct": 0.75,
        "weight_mom_short": 1.0, "weight_mom_long": 1.0,
        "weight_macd": 1.0, "weight_rsi": 0.5, "weight_vol": 0.5,
        "weight_bb": 0.8, "weight_obv": 1.0,
        "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
    },
    "均衡策略（默认）": {
        "description": "攻守兼备的平衡配置，适合大多数场景",
        "entry_min_signals": 3, "exit_min_signals": 2,
        "entry_threshold": 0.5, "exit_threshold": -0.5,
        "adx_threshold": 20, "stop_loss_mult": 2.0, "take_profit_mult": 4.0,
        "ema_fast": 20, "ema_slow": 60,
        "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
        "rsi_period": 14, "rsi_lower": 30, "rsi_upper": 70,
        "adx_period": 14, "atr_period": 14,
        "bb_period": 20, "bb_std": 2.0, "indicator_period": 20,
        "momentum_short": 5, "momentum_long": 20,
        "score_lookback": 30, "score_mid_pct": 0.6, "score_high_pct": 0.8,
        "weight_mom_short": 1.0, "weight_mom_long": 1.0,
        "weight_macd": 1.0, "weight_rsi": 0.5, "weight_vol": 0.5,
        "weight_bb": 0.8, "weight_obv": 1.0,
        "weight_volume": 0.6, "weight_price": 0.7, "weight_drawdown": 0.5,
    },
    "动量突破（激进）": {
        "description": "严格筛选强趋势、放大利润，适合趋势明确的市场",
        "entry_min_signals": 4, "exit_min_signals": 3,
        "entry_threshold": 0.8, "exit_threshold": -0.2,
        "adx_threshold": 25, "stop_loss_mult": 3.0, "take_profit_mult": 6.0,
        "ema_fast": 15, "ema_slow": 50,
        "macd_fast": 10, "macd_slow": 22, "macd_signal": 8,
        "rsi_period": 12, "rsi_lower": 25, "rsi_upper": 75,
        "adx_period": 12, "atr_period": 12,
        "bb_period": 18, "bb_std": 2.2, "indicator_period": 18,
        "momentum_short": 3, "momentum_long": 15,
        "score_lookback": 25, "score_mid_pct": 0.65, "score_high_pct": 0.85,
        "weight_mom_short": 1.5, "weight_mom_long": 1.2,
        "weight_macd": 1.2, "weight_rsi": 0.3, "weight_vol": 0.3,
        "weight_bb": 0.6, "weight_obv": 1.2,
        "weight_volume": 0.8, "weight_price": 0.5, "weight_drawdown": 0.3,
    },
    "自定义参数": {
        "description": "手动调节所有参数，在下方高级设置中修改",
    },
}
