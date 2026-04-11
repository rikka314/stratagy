import re

def fix():
    with open('ui/theme.py', 'r', encoding='utf-8') as f:
        text = f.read()

    # Make sure we don't duplicate
    if "translate_text._cached_pairs" not in text:
        # Erase old pairs declaration
        text = re.sub(r'_TRANSLATION_PAIRS\s*=\s*\[.*?\n\]\n?', '', text, flags=re.DOTALL)
        text = re.sub(r'_TRANSLATION_PAIRS\s*=\s*sorted.*?\n', '', text, flags=re.DOTALL)

        new_translate_text = '''def translate_text(value: object) -> object:
    if not isinstance(value, str) or get_ui_language() != "en":
        return value

    from ui.i18n import LOCALES
    if not hasattr(translate_text, "_cached_pairs"):
        pairs = []
        for k, v in LOCALES.items():
            zh = v.get('zh', '').strip()
            en = v.get('en', '').strip()
            if zh and zh != en:
                pairs.append((zh, en))
        translate_text._cached_pairs = sorted(pairs, key=lambda x: len(x[0]), reverse=True)

    translated = value
    for source, target in translate_text._cached_pairs:
        if source in translated:
            translated = translated.replace(source, target)
    return translated'''

        text = re.sub(r'def translate_text\(value: object\) -> object:\n.*?return translated', new_translate_text, text, flags=re.DOTALL)

    if "&lang=" not in text:
        new_route_href = '''def route_href(url_path: str = "") -> str:
    """system.routing.buildPath"""
    normalized = str(url_path or "").strip().strip("/")
    base = f"{BASE_ROUTE_PATH}/{normalized}" if normalized else BASE_ROUTE_PATH
    
    try:
        import streamlit as st
        from ui.i18n import get_ui_language
        lang = get_ui_language()
        if lang:
            if "?" in base:
                base = f"{base}&lang={lang}"
            else:
                base = f"{base}?lang={lang}"
    except Exception:
        pass
    return base'''

        text = re.sub(r'def route_href\(url_path: str \= ""\) -> str:\n.*?(?=\n\n(?:def [a-zA-Z_]|#|class))', new_route_href, text, flags=re.DOTALL)
        
    with open('ui/theme.py', 'w', encoding='utf-8') as f:
        f.write(text)
    print("Fixed ui/theme.py")

if __name__ == '__main__':
    fix()