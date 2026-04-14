import json

def fix_i18n():
    with open('i18n_dict.json', encoding='utf-8') as f:
        d = json.load(f)

    locales = {}
    for zh, v in d.items():
        locales[v['key']] = {'zh': zh, 'en': v['en']}

    new_content = f"""import streamlit as st

UI_LANGUAGE_STATE_KEY = "ui_language"

LOCALES: dict[str, dict[str, str]] = {json.dumps(locales, ensure_ascii=False, indent=4)}

def set_ui_language(language: str) -> None:
    lang = "en" if language.lower() == "en" else "zh"
    st.session_state[UI_LANGUAGE_STATE_KEY] = lang
    st.query_params["lang"] = lang

def get_ui_language() -> str:
    lang_param = st.query_params.get("lang")
    if lang_param in ("zh", "en"):
        st.session_state[UI_LANGUAGE_STATE_KEY] = lang_param
        return lang_param
    
    lang = str(st.session_state.get(UI_LANGUAGE_STATE_KEY, "zh")).strip().lower()
    return "en" if lang == "en" else "zh"

def tr(key: str, **kwargs) -> str:
    lang = get_ui_language()
    
    locale_dict = LOCALES.get(key, {{}})
    text = locale_dict.get(lang, key)
    
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
            
    return text

def localize_entity_name(symbol: str, raw_label: str, kind: str = "") -> str:
    lang = get_ui_language()
    if lang == 'en':
        if symbol:
            return symbol
        else:
            return raw_label
            
    return raw_label if raw_label else symbol
"""

    with open('ui/i18n.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == "__main__":
    fix_i18n()