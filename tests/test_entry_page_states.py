from __future__ import annotations

import ui.multi_stock_entry as multi_entry
import ui.single_stock_entry as single_entry


class _FakeBlock:
    def __init__(self, host) -> None:
        self._host = host

    def __enter__(self):
        return self._host

    def __exit__(self, exc_type, exc, tb):
        return False

    def __getattr__(self, name):
        return getattr(self._host, name)


class _FakeStreamlit:
    def __init__(self) -> None:
        self.markdowns: list[str] = []
        self.codes: list[str] = []
        self.captions: list[str] = []

    def container(self, *, key=None):
        _ = key
        return _FakeBlock(self)

    def popover(self, label, **kwargs):
        _ = label, kwargs
        return _FakeBlock(self)

    def columns(self, spec, gap=None):
        _ = spec, gap
        return [_FakeBlock(self), _FakeBlock(self)]

    def markdown(self, text, unsafe_allow_html=False):
        _ = unsafe_allow_html
        self.markdowns.append(text)

    def code(self, text, language=None):
        _ = language
        self.codes.append(text)

    def caption(self, text):
        self.captions.append(text)

    def button(self, label, key=None, **kwargs):
        _ = label, key, kwargs
        return False


def test_single_entry_handles_missing_recommendation_fields(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(single_entry, "st", fake_st)
    monkeypatch.setattr(single_entry, "tr", lambda key, **kwargs: key.format(**kwargs))

    action = single_entry._render_recommendation_rows([{}], market="US")

    assert action is None
    assert "award.common.noData" in fake_st.markdowns[0]


def test_multi_entry_handles_missing_recommendation_fields(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(multi_entry, "st", fake_st)
    monkeypatch.setattr(multi_entry, "tr", lambda key, **kwargs: key.format(**kwargs))

    multi_entry._render_recommendation_rows([{}])

    assert "award.common.noData" in fake_st.markdowns[0]


def test_empty_market_snapshot_uses_explicit_fallback(monkeypatch) -> None:
    status_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(single_entry, "tr", lambda key, **kwargs: key)
    monkeypatch.setattr(
        single_entry,
        "render_status_note",
        lambda message, tone="info": status_calls.append((message, tone)),
    )

    single_entry._render_snapshot([])

    assert status_calls == [("award.entry.marketEmpty", "warning")]


def test_recommendation_rows_show_heat_when_available(monkeypatch) -> None:
    fake_st = _FakeStreamlit()

    def fake_tr(key, **kwargs):
        if key == "award.entry.heatQuote":
            return f"heat={kwargs['heat']} change={kwargs['change']}"
        return key

    monkeypatch.setattr(single_entry, "st", fake_st)
    monkeypatch.setattr(single_entry, "tr", fake_tr)

    single_entry._render_recommendation_rows(
        [{"symbol": "NVDA", "name": "NVIDIA", "heat_text": "123,456", "pct_text": "+1.25%"}],
        market="US",
    )

    assert "heat=123,456 change=+1.25%" in fake_st.markdowns[0]
    assert "Price" not in fake_st.markdowns[0]


def test_multi_recommendation_rows_share_heat_metadata(monkeypatch) -> None:
    fake_st = _FakeStreamlit()

    def fake_tr(key, **kwargs):
        if key == "award.entry.heatQuote":
            return f"heat={kwargs['heat']} change={kwargs['change']}"
        return key

    monkeypatch.setattr(multi_entry, "st", fake_st)
    monkeypatch.setattr(multi_entry, "tr", fake_tr)

    multi_entry._render_recommendation_rows(
        [{"symbol": "NVDA", "name": "NVIDIA", "heat_text": "123,456", "pct_text": "+1.25%"}]
    )

    assert "heat=123,456 change=+1.25%" in fake_st.markdowns[0]


def test_csv_requirements_popover_includes_required_columns_and_example(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    translations = {
        "entry.csvRequirements.trigger": "查看标准化 CSV 数据要求",
        "entry.csvRequirements.title": "上传文件需要满足什么格式？",
        "entry.csvRequirements.body": "必需列 date open high low close volume，成交量单位为股。",
        "entry.csvRequirements.source": "可从行情终端导出。",
    }
    monkeypatch.setattr(single_entry, "st", fake_st)
    monkeypatch.setattr(single_entry, "tr", lambda key, **kwargs: translations.get(key, key))

    single_entry._render_csv_requirements_popover()

    assert any("date open high low close volume" in text for text in fake_st.markdowns)
    assert fake_st.codes and fake_st.codes[0].startswith("date,open,high,low,close,volume")
    assert fake_st.captions == ["可从行情终端导出。"]
