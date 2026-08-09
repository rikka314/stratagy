from __future__ import annotations

import os
from typing import Any


LIGHTGBM_DEVICE_ENV = "STRATAGY_LIGHTGBM_DEVICE_TYPE"
LIGHTGBM_PLATFORM_ENV = "STRATAGY_LIGHTGBM_GPU_PLATFORM_ID"
LIGHTGBM_GPU_ENV = "STRATAGY_LIGHTGBM_GPU_DEVICE_ID"
LIGHTGBM_USE_DP_ENV = "STRATAGY_LIGHTGBM_GPU_USE_DP"
SUPPORTED_LIGHTGBM_DEVICES = ("cpu", "gpu", "cuda")


def normalize_lightgbm_device(value: Any) -> str:
    device = str(value or "cpu").strip().lower()
    if device not in SUPPORTED_LIGHTGBM_DEVICES:
        raise ValueError(
            f"Unsupported LightGBM device {value!r}; expected one of "
            f"{', '.join(SUPPORTED_LIGHTGBM_DEVICES)}."
        )
    return device


def configure_lightgbm_environment(
    *,
    device_type: str,
    gpu_platform_id: int = 0,
    gpu_device_id: int = 0,
    gpu_use_dp: bool = False,
) -> None:
    os.environ[LIGHTGBM_DEVICE_ENV] = normalize_lightgbm_device(device_type)
    os.environ[LIGHTGBM_PLATFORM_ENV] = str(int(gpu_platform_id))
    os.environ[LIGHTGBM_GPU_ENV] = str(int(gpu_device_id))
    os.environ[LIGHTGBM_USE_DP_ENV] = "1" if gpu_use_dp else "0"


def lightgbm_runtime_params() -> dict[str, Any]:
    device_type = normalize_lightgbm_device(os.getenv(LIGHTGBM_DEVICE_ENV, "cpu"))
    if device_type == "cpu":
        return {"device_type": "cpu"}

    params: dict[str, Any] = {"device_type": device_type}
    if device_type == "gpu":
        params.update(
            {
                "gpu_platform_id": int(os.getenv(LIGHTGBM_PLATFORM_ENV, "0")),
                "gpu_device_id": int(os.getenv(LIGHTGBM_GPU_ENV, "0")),
                "gpu_use_dp": os.getenv(LIGHTGBM_USE_DP_ENV, "0") == "1",
            }
        )
    return params


def validate_lightgbm_device(device_type: str) -> dict[str, Any]:
    """Run a tiny fit so GPU/CUDA builds fail before a long research run."""
    device = normalize_lightgbm_device(device_type)
    try:
        import lightgbm
        import numpy as np
        from lightgbm import LGBMClassifier
    except Exception as exc:
        return {
            "available": False,
            "device_type": device,
            "error": f"LightGBM import failed: {exc}",
        }

    previous = os.getenv(LIGHTGBM_DEVICE_ENV)
    os.environ[LIGHTGBM_DEVICE_ENV] = device
    rng = np.random.RandomState(42)
    features = rng.normal(size=(128, 8))
    labels = (features[:, 0] + features[:, 1] > 0).astype(int)
    try:
        model = LGBMClassifier(
            n_estimators=2,
            num_leaves=7,
            min_child_samples=5,
            n_jobs=1,
            verbosity=-1,
            **lightgbm_runtime_params(),
        )
        model.fit(features, labels)
        return {
            "available": True,
            "device_type": device,
            "lightgbm_version": str(lightgbm.__version__),
        }
    except Exception as exc:
        return {
            "available": False,
            "device_type": device,
            "lightgbm_version": str(lightgbm.__version__),
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        if previous is None:
            os.environ.pop(LIGHTGBM_DEVICE_ENV, None)
        else:
            os.environ[LIGHTGBM_DEVICE_ENV] = previous
