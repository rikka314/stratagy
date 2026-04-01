from __future__ import annotations

import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_TEST_ROOT = REPO_ROOT / "model-test"

for candidate in (str(REPO_ROOT), str(MODEL_TEST_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

if "akshare" not in sys.modules:
    sys.modules["akshare"] = types.ModuleType("akshare")
