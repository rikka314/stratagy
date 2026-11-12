from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path

from docx import Document


def main() -> None:
    path = Path("reports/stratagy课程设计报告.docx")
    document = Document(path)
    body_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    table_text = "\n".join(
        cell.text
        for table in document.tables
        for row in table.rows
        for cell in row.cells
    )
    text = f"{body_text}\n{table_text}"

    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        media = [
            name
            for name in archive.namelist()
            if name.startswith("word/media/") and not name.endswith("/")
        ]

    print(f"bytes={path.stat().st_size}")
    print(f"sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
    print(
        f"paragraphs={len(document.paragraphs)} tables={len(document.tables)} "
        f"inline_shapes={len(document.inline_shapes)}"
    )
    print(f"zip_bad={bad_member} media={len(media)} unique_media_names={len(set(media))}")
    print(f"chapter_titles={len(re.findall(r'^[一二三四五六七]、', body_text, re.MULTILINE))}")
    print(f"placeholders={text.count('【请填写】')}")
    print(
        "test_summary="
        f"{'562 passed' in text and '5 failed' in text and '2 warnings' in text}"
    )
    print(
        "chapter5_captions="
        f"{len(re.findall(r'图5-(?:[1-9]|10)(?!\\d)', text))} "
        "chapter6_captions="
        f"{len(re.findall(r'图6-(?:[1-9]|10)(?!\\d)', text))}"
    )
    print(f"core_modules={sum(text.count(f'5.{index} ') for index in range(1, 19))}")


if __name__ == "__main__":
    main()
