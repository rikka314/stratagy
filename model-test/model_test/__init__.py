from __future__ import annotations

import logging
import sys
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = PACKAGE_ROOT.parent
REPO_ROOT = WORKSPACE_ROOT.parent

for candidate in (str(WORKSPACE_ROOT), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

for logger_name in (
    "streamlit",
    "streamlit.runtime",
    "streamlit.runtime.caching",
    "streamlit.runtime.state",
    "streamlit.runtime.scriptrunner_utils",
):
    logging.getLogger(logger_name).setLevel(logging.ERROR)


__all__ = [
    "PACKAGE_ROOT",
    "WORKSPACE_ROOT",
    "REPO_ROOT",
]
