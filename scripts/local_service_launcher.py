"""Desktop launcher for the local Streamlit service.

The generated executable lives on the desktop, while the application remains in
the repository.  The project root can be overridden with STRATAGY_PROJECT_ROOT
for portability; the current workspace path is the default for this machine.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


DEFAULT_PROJECT_ROOT = Path(
    r"D:\Learn\20_Projects\2026_SPRING\AIE1902\课堂内容\stratagy"
)
SERVICE_URL = "http://127.0.0.1:8501/strategy"
WAIT_SECONDS = 120


def _project_root() -> Path:
    configured = os.environ.get("STRATAGY_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    # This also makes a locally-built executable work when copied into the repo.
    for candidate in (Path(__file__).resolve().parent.parent, DEFAULT_PROJECT_ROOT):
        if (candidate / "run.bat").is_file() and (candidate / "app.py").is_file():
            return candidate
    return DEFAULT_PROJECT_ROOT


def _service_is_ready() -> bool:
    try:
        with urllib.request.urlopen(SERVICE_URL, timeout=1.5) as response:
            return response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Strategy local service", message)
        root.destroy()
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    root = _project_root()
    run_bat = root / "run.bat"
    if not run_bat.is_file():
        _show_error(f"找不到启动脚本：{run_bat}")
        return 1

    if not _service_is_ready():
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        try:
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", str(run_bat)],
                cwd=str(root),
                creationflags=creation_flags,
            )
        except OSError as exc:
            _show_error(f"无法启动本地服务：{exc}")
            return 1

        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            if _service_is_ready():
                break
            time.sleep(1)
        else:
            _show_error(
                "服务尚未就绪。请查看新打开的命令窗口中的日志，\n"
                f"并手动访问 {SERVICE_URL}。"
            )
            return 1

    webbrowser.open(SERVICE_URL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
