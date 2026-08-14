from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_perf_module():
    import importlib.util

    module_path = PROJECT_ROOT / "core" / "perf.py"
    spec = importlib.util.spec_from_file_location("stratagy_perf_for_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_performance_span_is_silent_when_tracing_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("STRATAGY_PERF_TRACE", raising=False)
    perf = _load_perf_module()

    with perf.performance_span("home", "headlines", source="newsapi"):
        pass

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_performance_span_emits_safe_json_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STRATAGY_PERF_TRACE", "1")
    perf = _load_perf_module()

    with perf.performance_span(
        "home",
        "headlines",
        cache="miss",
        source="newsapi",
        api_key="must-not-leak",
    ):
        time.sleep(0.001)

    payload = json.loads(capsys.readouterr().err)
    assert payload["event"] == "stratagy.performance"
    assert payload["route"] == "home"
    assert payload["phase"] == "headlines"
    assert payload["status"] == "ok"
    assert payload["cache"] == "miss"
    assert payload["source"] == "newsapi"
    assert payload["elapsed_ms"] >= 0
    assert "api_key" not in payload
    assert "must-not-leak" not in json.dumps(payload)


def test_performance_span_preserves_exception_and_marks_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STRATAGY_PERF_TRACE", "true")
    perf = _load_perf_module()

    with pytest.raises(RuntimeError, match="expected failure"):
        with perf.performance_span("report", "parse"):
            raise RuntimeError("expected failure")

    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "error"
    assert "expected failure" not in json.dumps(payload)


def test_measurement_summary_reports_three_samples_without_hard_failure() -> None:
    from scripts.measure_app_performance import summarize_samples

    summary = summarize_samples([1.0, 3.0, 2.0], budget_ms=2.5)

    assert summary == {
        "samples_ms": [1.0, 3.0, 2.0],
        "sample_count": 3,
        "p50_ms": 2.0,
        "p75_ms": 2.5,
        "budget_ms": 2.5,
        "within_budget": True,
    }


def test_measurement_script_import_probe_outputs_json() -> None:
    env = {**os.environ, "STRATAGY_PERF_TRACE": "0"}
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "measure_app_performance.py"),
            "--samples",
            "1",
            "--skip-apptest",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["layers"]["python"]["import_app"]["sample_count"] == 1
    assert payload["layers"]["streamlit"] == {}
    assert payload["layers"]["browser"]["status"] == "not_measured"


def _run_import_probe(code: str) -> dict[str, object]:
    env = {
        **os.environ,
        "STRATAGY_PERF_TRACE": "0",
        "STRATAGY_PERF_IMPORT_PROBE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_core_config_import_does_not_load_heavy_optional_modules() -> None:
    payload = _run_import_probe(
        "import json, sys; "
        "import core.config; "
        "print(json.dumps({name: name in sys.modules for name in "
        "['akshare', 'lightgbm', 'optuna', 'sklearn', 'st_keyup']}))"
    )

    assert payload == {
        "akshare": False,
        "lightgbm": False,
        "optuna": False,
        "sklearn": False,
        "st_keyup": False,
    }


def test_app_import_probe_does_not_load_unvisited_route_dependencies() -> None:
    payload = _run_import_probe(
        "import json, sys; "
        "import app; "
        "print(json.dumps({name: name in sys.modules for name in "
        "['akshare', 'lightgbm', 'optuna', 'sklearn', 'st_keyup', "
        "'ui.single_stock', 'ui.multi_stock', 'ui.sidebar', "
        "'ui.model_evaluation', 'ui.final_report']}))"
    )

    assert payload == {
        "akshare": False,
        "lightgbm": False,
        "optuna": False,
        "sklearn": False,
        "st_keyup": False,
        "ui.single_stock": False,
        "ui.multi_stock": False,
        "ui.sidebar": False,
        "ui.model_evaluation": False,
        "ui.final_report": False,
    }


def test_core_public_api_lazy_exports_remain_compatible() -> None:
    payload = _run_import_probe(
        "import json, sys; "
        "import core; "
        "from core import DATA_DIR, DEFAULT_SYMBOL, add_indicators; "
        "print(json.dumps({"
        "'has_data_dir': bool(str(DATA_DIR)), "
        "'default_symbol': DEFAULT_SYMBOL, "
        "'add_indicators_callable': callable(add_indicators), "
        "'sklearn_loaded': 'sklearn' in sys.modules"
        "}))"
    )

    assert payload["has_data_dir"] is True
    assert payload["default_symbol"]
    assert payload["add_indicators_callable"] is True
    assert payload["sklearn_loaded"] is False


def test_market_context_import_does_not_load_akshare() -> None:
    payload = _run_import_probe(
        "import json, sys; "
        "import core.market_context; "
        "print(json.dumps({name: name in sys.modules for name in "
        "['akshare', 'lightgbm', 'optuna', 'sklearn', 'st_keyup']}))"
    )

    assert payload == {
        "akshare": False,
        "lightgbm": False,
        "optuna": False,
        "sklearn": False,
        "st_keyup": False,
    }


def test_sidebar_import_does_not_load_st_keyup() -> None:
    payload = _run_import_probe(
        "import json, sys; "
        "import ui.sidebar; "
        "print(json.dumps({'st_keyup': 'st_keyup' in sys.modules}))"
    )

    assert payload == {"st_keyup": False}


def test_home_renders_shell_before_three_parallel_data_fragments() -> None:
    home_source = (PROJECT_ROOT / "ui" / "home.py").read_text(encoding="utf-8")
    render_source = home_source.split("def render_home_page() -> None:", maxsplit=1)[1]

    assert home_source.count("@st.fragment(parallel=True)") == 3
    shell_position = render_source.index("_render_home_loading_stage_markup")
    fragment_positions = [
        render_source.index("_render_home_headlines_fragment(language)"),
        render_source.index("_render_home_stock_cloud_fragment(language, selected_market)"),
        render_source.index("_render_home_market_lens_fragment(language, selected_market)"),
    ]
    assert all(shell_position < position for position in fragment_positions)


def test_phase_five_css_bundles_stay_route_scoped_and_within_budget() -> None:
    from ui.theme import get_style_bundle_css

    bundles = {
        name: get_style_bundle_css(name)
        for name in ("base", "home", "entry", "analysis", "report")
    }

    assert len(bundles["base"]) + len(bundles["home"]) < 40_000
    assert ".native-report-shell" in bundles["report"]
    assert all(
        ".native-report-shell" not in bundles[name]
        for name in ("base", "home", "entry", "analysis")
    )
    assert "market-news-hop" in bundles["home"]
    assert "market-news-hop" not in bundles["report"]
    assert ".analysis-page-shell" in bundles["analysis"]
    assert ".analysis-page-shell" not in bundles["home"]
    assert ".entry-title" in bundles["entry"]
    assert ".entry-title" not in bundles["report"]


def test_stale_streamlit_elements_are_hidden_during_reconciliation() -> None:
    """Old rerun trees must not remain visible or interactive while replaced."""
    from ui.theme import get_style_bundle_css

    # The global stale rule belongs to the base bundle, which every route
    # injects before its page-specific bundle.
    base_css = get_style_bundle_css("base")
    assert '[data-testid="stElementContainer"][data-stale="true"]' in base_css
    assert "display: none !important" in base_css
    assert "pointer-events: none !important" in base_css

    for bundle in ("home", "entry", "analysis", "report"):
        css = get_style_bundle_css(bundle)
        assert 'div.element-container[data-stale="true"]' not in css


def test_phase_five_routes_inject_only_their_style_bundle() -> None:
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert "inject_base_styles()" in app_source
    assert "def _render_home_route() -> None:\n    inject_home_styles()" in app_source
    assert "inject_entry_styles()\n        render_route_nav(\"single\")" in app_source
    assert "inject_entry_styles()\n        render_route_nav(\"multi\")" in app_source
    assert "def _render_model_evaluation_route() -> None:\n    inject_analysis_styles()" in app_source
    assert "def _render_final_report_route() -> None:\n    inject_report_styles()" in app_source


def test_phase_four_sidebar_batches_advanced_parameters_in_a_form() -> None:
    sidebar_source = (PROJECT_ROOT / "ui" / "sidebar.py").read_text(encoding="utf-8")

    assert 'strategy_form = st.form("sidebar_strategy_parameters")' in sidebar_source
    assert 'strategy_form.form_submit_button("应用参数", width="stretch")' in sidebar_source


def test_phase_four_single_display_cache_key_changes_for_display_inputs() -> None:
    from ui.single_stock import _build_single_display_cache_key

    base_key = _build_single_display_cache_key(
        context_key="context-a",
        artifact_id="artifact-a",
        split_date="2026-01-31",
        period_key="D",
        chart_scope="dataset",
        indicator_view="MACD",
        indicator_kwargs={"ema_fast": 20, "ema_slow": 60},
        rsi_upper=70.0,
        rsi_lower=30.0,
        language="zh",
        theme="light",
    )
    changed_view_key = _build_single_display_cache_key(
        context_key="context-a",
        artifact_id="artifact-a",
        split_date="2026-01-31",
        period_key="D",
        chart_scope="dataset",
        indicator_view="RSI",
        indicator_kwargs={"ema_fast": 20, "ema_slow": 60},
        rsi_upper=70.0,
        rsi_lower=30.0,
        language="zh",
        theme="light",
    )
    changed_context_key = _build_single_display_cache_key(
        context_key="context-b",
        artifact_id="artifact-a",
        split_date="2026-01-31",
        period_key="D",
        chart_scope="dataset",
        indicator_view="MACD",
        indicator_kwargs={"ema_fast": 20, "ema_slow": 60},
        rsi_upper=70.0,
        rsi_lower=30.0,
        language="zh",
        theme="light",
    )

    assert base_key != changed_view_key
    assert base_key != changed_context_key


def test_phase_four_multi_adjustment_helper_preserves_input_params() -> None:
    from ui.multi_stock import _apply_multi_adjustments

    params = {"entry_threshold": 0.5, "weight_bb": 0.8, "market": "US"}
    adjusted = _apply_multi_adjustments(params, {"entry_threshold": 0.9, "weight_bb": 1.1})

    assert params == {"entry_threshold": 0.5, "weight_bb": 0.8, "market": "US"}
    assert adjusted == {"entry_threshold": 0.9, "weight_bb": 1.1, "market": "US"}


def test_core_lazy_module_import_remains_compatible() -> None:
    payload = _run_import_probe(
        "import json; "
        "from core import ml_filter; "
        "print(json.dumps({'module_name': ml_filter.__name__, 'has_model': hasattr(ml_filter, 'MLModel')}))"
    )

    assert payload == {"module_name": "core.ml_filter", "has_model": True}


def test_core_star_import_does_not_load_module_only_exports() -> None:
    payload = _run_import_probe(
        "import json\n"
        "from core import *\n"
        "import sys\n"
        "print(json.dumps({name: name in sys.modules for name in "
        "['core.market_context', 'core.adaptive_regime', 'core.news_factor', 'core.perf']}))"
    )

    assert payload == {
        "core.market_context": False,
        "core.adaptive_regime": False,
        "core.news_factor": False,
        "core.perf": False,
    }


def test_unknown_core_export_raises_attribute_error() -> None:
    payload = _run_import_probe(
        "import json\n"
        "import core\n"
        "try:\n"
        "    getattr(core, 'definitely_not_a_public_core_symbol')\n"
        "except AttributeError:\n"
        "    print(json.dumps({'raised': True}))\n"
        "else:\n"
        "    print(json.dumps({'raised': False}))"
    )

    assert payload == {"raised": True}


def test_phase_six_runtime_dependency_contract_is_versioned_and_hash_gated() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    run_script = (PROJECT_ROOT / "run.bat").read_text(encoding="utf-8")

    assert "streamlit>=1.60.0,<1.62.0" in requirements
    assert "Get-FileHash -Algorithm SHA256" in run_script
    assert ".venv\\.requirements.sha256" in run_script
    assert "requirements.txt unchanged; skipping pip install" in run_script
    assert ".venv\\Scripts\\python.exe -m streamlit run app.py" in run_script
    assert 'if /I "%~1"=="--setup-only"' in run_script


def test_phase_six_incremental_deploy_installs_changed_requirements_before_restart() -> None:
    sync_script = (PROJECT_ROOT / "deploy" / "sync.bat").read_text(encoding="utf-8")
    install_position = sync_script.index("install_requirements_if_needed.sh %REMOTE_DIR%")
    restart_position = sync_script.index("systemctl restart stratagy")

    assert "install_requirements_if_needed.sh" in sync_script
    assert "check_runtime.sh" in sync_script
    assert install_position < restart_position
    assert "check_runtime.sh %REMOTE_DIR%" in sync_script


def test_phase_six_full_deploy_records_versions_fingerprint_and_health() -> None:
    deploy_script = (PROJECT_ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
    install_helper = (
        PROJECT_ROOT / "deploy" / "install_requirements_if_needed.sh"
    ).read_text(encoding="utf-8")
    runtime_helper = (PROJECT_ROOT / "deploy" / "check_runtime.sh").read_text(
        encoding="utf-8"
    )

    assert "venv/.requirements.sha256" in deploy_script
    assert 'Streamlit {streamlit.__version__}' in deploy_script
    assert 'check_runtime.sh" "${APP_DIR}"' in deploy_script
    assert "sha256sum" in install_helper
    assert "unchanged; skipping pip install" in install_helper
    assert "/strategy/_stcore/health" in runtime_helper
    assert "curl --fail" in runtime_helper


def test_phase_six_nginx_separates_static_cache_from_runtime_endpoints() -> None:
    nginx = (PROJECT_ROOT / "deploy" / "nginx_strategy.conf").read_text(
        encoding="utf-8"
    )

    assert "location ^~ /strategy/static/" in nginx
    assert 'Cache-Control "public, max-age=31536000, immutable"' in nginx
    assert "location ^~ /strategy/_stcore/" in nginx
    assert 'Cache-Control "no-store"' in nginx
    assert nginx.count("proxy_hide_header Cache-Control;") == 2
    assert "proxy_buffering on;" in nginx
    assert "proxy_buffering off;" in nginx
    assert "location ^~ /strategy/" in nginx
