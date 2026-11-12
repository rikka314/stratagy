"""Data behind the original basic-information panels; calculations stay in Python."""
from __future__ import annotations

import pandas as pd

from core.indicators import add_indicators
from .service import validated_params, json_value, prepare_dataframe, records


def dataset_analysis(frame: pd.DataFrame, *, period: str = 'D', train_ratio: float = .7,
                     start_date: str | None = None, end_date: str | None = None, params: dict | None = None) -> dict:
    data = prepare_dataframe(frame, start_date=start_date, end_date=end_date)
    if len(data) < 2:
        raise ValueError('At least two rows are required for analysis')
    if period not in {'D', 'W', 'M'}:
        raise ValueError('Unsupported chart period')
    params = validated_params(params or {})
    keys = ('rsi_period', 'macd_fast', 'macd_slow', 'macd_signal', 'ema_fast', 'ema_slow',
            'adx_period', 'atr_period', 'bb_period', 'bb_std', 'indicator_period')
    kwargs = {key: params[key] for key in keys}
    daily = add_indicators(data.copy(), **kwargs)
    chart = data.copy()
    if period != 'D':
        aggregates = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}
        if 'volume' in chart:
            aggregates['volume'] = 'sum'
        chart = chart.set_index('date').resample('W-FRI' if period == 'W' else 'ME').agg(aggregates)
        chart = chart.dropna(subset=['open', 'high', 'low', 'close']).reset_index()
    chart = add_indicators(chart, **kwargs)
    split = min(max(1, int(len(data) * train_ratio)), len(data) - 1)
    latest = daily.iloc[-1]
    close = pd.to_numeric(data['close'], errors='coerce')
    summary = {
        'rows': len(data), 'train_rows': split, 'test_rows': len(data) - split,
        'split_date': data.iloc[split - 1]['date'], 'test_start': data.iloc[split]['date'],
        'start_date': data.iloc[0]['date'], 'end_date': data.iloc[-1]['date'],
        'latest_price': close.iloc[-1], 'change': close.iloc[-1] - close.iloc[-2],
        'change_pct': close.iloc[-1] / close.iloc[-2] - 1,
        'total_return': close.iloc[-1] / close.iloc[0] - 1,
        'annualized_volatility': close.pct_change().std() * 252 ** .5,
        'volume_20d': data['volume'].tail(20).mean() if 'volume' in data else None,
        'latest': latest.to_dict(),
        'snapshot': {
            'rsi': latest.get('rsi'), 'rsi_lower': params['rsi_lower'], 'rsi_upper': params['rsi_upper'],
            'histogram': latest.get('histogram'),
            'relative_volume': latest.get('volume') / data['volume'].tail(20).mean()
                if 'volume' in data and data['volume'].tail(20).mean() > 0 else None,
            'range_position': max(0, min(1, (close.iloc[-1] - data['low'].min()) / (data['high'].max() - data['low'].min())))
                if data['high'].max() > data['low'].min() else None,
            'volatility_60d': close.pct_change().dropna().tail(60).std() * 252 ** .5,
            'ema_spread': (latest.get('ema_fast') - latest.get('ema_slow')) / close.iloc[-1],
        },
    }
    return {'summary': json_value(summary), 'candles': records(chart), 'prices': records(data, ['date', 'close'])}
