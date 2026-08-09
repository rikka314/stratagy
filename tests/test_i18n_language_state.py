from __future__ import annotations

from ui import i18n


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, str] = {}
        self.query_params: dict[str, str] = {}


def test_query_language_overrides_session_and_drives_translation(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    fake_st.session_state[i18n.UI_LANGUAGE_STATE_KEY] = "en"
    fake_st.query_params["lang"] = "zh-CN"
    monkeypatch.setattr(i18n, "st", fake_st)

    assert i18n.get_ui_language() == "zh"
    assert fake_st.session_state[i18n.UI_LANGUAGE_STATE_KEY] == "zh"
    assert i18n.tr("nav.home") == "首页"


def test_set_language_persists_supported_value(monkeypatch) -> None:
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(i18n, "st", fake_st)

    i18n.set_ui_language("en-US")
    assert fake_st.session_state[i18n.UI_LANGUAGE_STATE_KEY] == "en"
    assert fake_st.query_params["lang"] == "en"

    i18n.set_ui_language("zh")
    assert fake_st.session_state[i18n.UI_LANGUAGE_STATE_KEY] == "zh"
    assert fake_st.query_params["lang"] == "zh"
