import os, glob
import re

def fix():
    for f in glob.glob('ui/*.py') + ['app.py', 'core/*.py']:
        if not os.path.exists(f):
            continue
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # replace ""tr("key")"" with """key"""
        new_content = re.sub(r'""tr\("([^"]+)"\)""', r'"""\1"""', content)
        
        if content != new_content:
            with open(f, 'w', encoding='utf-8') as file:
                file.write(new_content)
            print("Fixed", f)

if __name__ == '__main__':
    fix()
