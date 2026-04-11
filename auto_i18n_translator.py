import os
import ast
import json
import requests

# ==========================================
# 通过环境变量提供您的 DEEPSEEK API 配置
# ==========================================
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "").strip()
API_URL = "https://api.deepseek.com/chat/completions"

TARGET_FILES = [
    "app.py",
    "ui/theme.py",
    "ui/home.py",
    "ui/sidebar.py",
    "ui/single_stock_entry.py",
    "ui/multi_stock_entry.py",
    "ui/single_stock.py",
    "ui/multi_stock.py",
    "ui/model_evaluation.py",
    "ui/export_reports.py",
    "ui/single_stock_workflow.py"
]

def call_deepseek_translate(texts: list) -> dict:
    print(f"正在向 DeepSeek 请求翻译 {len(texts)} 条文本...")
    prompt = (
        "你是一个国际化(i18n)专家。我将给你一组中文UI文本，请你返回一个JSON对象。\n"
        "规则：\n"
        "1. 生成一个符合逻辑层级的英文 key（例如 'home.title', 'button.submit'）\n"
        "2. 提供对应的原本中文(zh)和流利地道、简短的英文翻译(en)\n"
        "3. 返回纯JSON格式（以外层中文字符串为key，内层为 {'key': '...', 'en': '...'}）\n"
        f"文本列表：\n{json.dumps(texts, ensure_ascii=False)}"
    )
    
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
        return json.loads(content)
    except Exception as e:
        print(f"DeepSeek 翻译异常: {e}")
        return {}

def extract_chinese_strings_from_file(file_path: str) -> set:
    found_strings = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip()
                if any('\u4e00' <= c <= '\u9fff' for c in val) and len(val) < 150 and "{" not in val and "}" not in val:
                    found_strings.add(val)
    except Exception as e:
        print(f"解析 {file_path} 失败: {e}")
    return found_strings

def main():
    if not API_KEY:
        print("错误：请先设置环境变量 DEEPSEEK_API_KEY！")
        return

    all_texts = set()
    for f in TARGET_FILES:
        full_path = os.path.join(os.getcwd(), f)
        if os.path.exists(full_path):
            texts = extract_chinese_strings_from_file(full_path)
            all_texts.update(texts)
            print(f"🔍 从 {f} 中扫出了 {len(texts)} 条需翻译中文字符串。")

    all_texts = list(all_texts)
    print(f"✅ 全站汇总到 {len(all_texts)} 条中文文本待处理！")
    
    chunk_size = 50
    final_dict = {}
    for i in range(0, len(all_texts), chunk_size):
        chunk = all_texts[i:i+chunk_size]
        result = call_deepseek_translate(chunk)
        final_dict.update(result)

    with open("i18n_dict.json", "w", encoding="utf-8") as out:
        json.dump(final_dict, out, ensure_ascii=False, indent=2)
    print("🎉 翻译收集完成！字典已保存至 i18n_dict.json")

if __name__ == "__main__":
    main()
