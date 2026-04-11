import json
import glob
import os

def main():
    with open('i18n_dict.json', 'r', encoding='utf-8') as f:
        i18n_data = json.load(f)

    keys_mapping = {k: v['key'] for k, v in i18n_data.items()}

    def replace_in_file(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        made_changes = False
        original_content = content

        for literal, key in keys_mapping.items():
            # only simple string literals, avoids destroying f-strings
            if f'"{literal}"' in content:
                content = content.replace(f'"{literal}"', f'tr("{key}")')
                made_changes = True
            
            if f"'{literal}'" in content:
                content = content.replace(f"'{literal}'", f'tr("{key}")')
                made_changes = True

        if made_changes:
            if 'from ui.i18n import tr' not in content:
                lines = content.split('\n')
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.startswith('import ') or line.startswith('from '):
                        insert_idx = i + 1
                lines.insert(insert_idx, 'from ui.i18n import tr')
                content = '\n'.join(lines)
                
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f'Updated {filepath}')

    target_files = ['app.py'] + glob.glob('ui/*.py')
    for f in set(target_files):
        if os.path.exists(f):
            replace_in_file(f)

if __name__ == '__main__':
    main()
