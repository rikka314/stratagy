import pandas as pd
import pytest

from api.presentation import dataset_analysis
from api.service import prepare_dataframe, default_params
from core.indicators import add_indicators


def test_daily_analysis_uses_original_python_indicators():
    frame = prepare_dataframe(pd.read_csv('data/aapl_clean_daily.csv').tail(100))
    result = dataset_analysis(frame, period='D', train_ratio=.7)
    params = default_params()
    keys = ('rsi_period', 'macd_fast', 'macd_slow', 'macd_signal', 'ema_fast', 'ema_slow', 'adx_period', 'atr_period', 'bb_period', 'bb_std', 'indicator_period')
    expected = add_indicators(frame, **{key: params[key] for key in keys})
    assert result['candles'][-1]['rsi'] == pytest.approx(expected.iloc[-1]['rsi'])
    assert result['summary']['train_rows'] == 70
    assert result['summary']['test_rows'] == 30


def test_weekly_candles_aggregate_ohlcv_before_indicators():
    frame = prepare_dataframe(pd.read_csv('data/aapl_clean_daily.csv').tail(100))
    result = dataset_analysis(frame, period='W', train_ratio=.7)
    expected = frame.set_index('date').resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    assert len(result['candles']) == len(expected)
    assert result['candles'][-1]['volume'] == pytest.approx(expected.iloc[-1]['volume'])


def test_date_filter_applies_to_summary_and_chart():
    frame = prepare_dataframe(pd.read_csv('data/aapl_clean_daily.csv').tail(100))
    start = str(frame.iloc[40]['date'].date())
    result = dataset_analysis(frame, start_date=start)
    assert result['summary']['rows'] == 60
    assert result['candles'][0]['date'].startswith(start)


def test_current_indicator_parameters_are_used():
    frame = prepare_dataframe(pd.read_csv('data/aapl_clean_daily.csv').tail(100))
    result = dataset_analysis(frame, params={'rsi_period': 5, 'ema_fast': 4})
    defaults = dataset_analysis(frame)
    assert result['candles'][-1]['rsi'] != defaults['candles'][-1]['rsi']
    assert result['candles'][-1]['ema_fast'] != defaults['candles'][-1]['ema_fast']


def test_slice_can_expand_again_without_changing_original(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from api.models import DatasetSliceRequest
    import api.main as main
    from api.storage import ApiStorage
    store = ApiStorage(tmp_path)
    monkeypatch.setattr(main, 'storage', store)
    frame = prepare_dataframe(pd.read_csv('data/aapl_clean_daily.csv').tail(100))
    token = store.new_id()
    store.save_dataset(token, {'symbol':'AAPL','market':'US','adjust':'qfq','dataframe':frame})
    start = str(frame.iloc[40]['date'].date())
    sliced = main.slice_dataset(token, DatasetSliceRequest(start_date=start))
    assert sliced['rows'] == 60
    expanded = main.slice_dataset(sliced['dataset_id'], DatasetSliceRequest())
    assert expanded['rows'] == 100
    assert len(store.load_dataset(token)['dataframe']) == 100
    for invalid in ['invalid', '2100-01-01']:
        with pytest.raises(HTTPException) as error:
            main.slice_dataset(token, DatasetSliceRequest(start_date=invalid))
        assert error.value.status_code == 422
