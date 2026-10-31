"""Reproducible loader/filter/chart/AppTest benchmark; no artifact writes."""

from __future__ import annotations

import hashlib
import json
import os
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit
from streamlit.testing.v1 import AppTest

from src.data.constants import ARTIFACTS_DIR, DEFAULT_FEATURE_PATH
from src.visuals.cache_manager import (
    artifact_version, clear_artifact_caches, load_artifact,
)
from src.visuals.filters import FilterState, filter_features
from src.visuals import (
    build_calendar_heatmap, build_lag_heatmap, build_quantile_fan,
    build_regime_boxplots, build_scatter_loess, build_small_multiples,
    build_stacked_bar, build_stl_panels, build_ot_threshold_chart,
    build_barcode_rug,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = {
    "grid_features": DEFAULT_FEATURE_PATH,
    "stl": ARTIFACTS_DIR / "load_profiles_stl.parquet",
    "quantiles": ARTIFACTS_DIR / "quantile_bands.parquet",
    "lag": ARTIFACTS_DIR / "lag_correlation_matrix.json",
    "events": ARTIFACTS_DIR / "thermal_breach_events.parquet",
    "loess": ARTIFACTS_DIR / "loess_curves.parquet",
}


def measure(callable_, repeats: int = 5) -> dict[str, float]:
    """Run callable repeatedly and summarize wall-clock seconds."""
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        callable_()
        samples.append(perf_counter() - started)
    return {"runs": repeats, "mean_seconds": statistics.mean(samples),
            "median_seconds": statistics.median(samples),
            "min_seconds": min(samples), "max_seconds": max(samples)}


def atomic_write_text(path: Path, text: str) -> None:
    """Persist benchmark evidence using verified temporary replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    owned = False
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            owned = True
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_text(encoding="utf-8") != text:
            raise ValueError("Benchmark evidence round-trip mismatch")
        os.replace(temporary, path)
    finally:
        if owned and temporary.exists():
            temporary.unlink()


def main() -> None:
    """Benchmark each layer separately and record environment/evidence."""
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise RuntimeError("Activate the repository .venv first")
    files = {name: {"path": str(path.resolve()), "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for name, path in ARTIFACTS.items()}
    results: dict[str, object] = {
        "environment": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform(),
                        "processor": platform.processor(),
                        "streamlit": streamlit.__version__, "pandas": pd.__version__},
        "artifacts": files,
    }

    clear_artifact_caches()
    cold_started = perf_counter()
    loaded = {name: load_artifact(path) for name, path in ARTIFACTS.items()}
    cold_seconds = perf_counter() - cold_started
    warm_started = perf_counter()
    warm = {name: load_artifact(path) for name, path in ARTIFACTS.items()}
    warm_seconds = perf_counter() - warm_started
    assert all(warm[name].equals(loaded[name]) for name in ARTIFACTS)
    results["loader_six_artifacts"] = {
        "cold_seconds": cold_seconds, "warm_seconds": warm_seconds,
        "cache_hit_returns_equal_frames": True,
    }

    features = loaded["grid_features"]
    events = loaded["events"]
    profiles = loaded["stl"]
    quantiles = loaded["quantiles"]
    loess = loaded["loess"]
    lag = loaded["lag"]
    dates_by_dataset = {
        dataset: group.timestamp for dataset, group in features.groupby("dataset")
    }
    datasets = sorted(dates_by_dataset)
    first_date, last_date = features.timestamp.min(), features.timestamp.max()

    def switch_dataset() -> None:
        for dataset in datasets:
            state = FilterState(dataset, None, first_date, last_date + pd.Timedelta(nanoseconds=1))
            filtered = filter_features(features, state)
            assert filtered.dataset.nunique() == 1 and filtered.dataset.iloc[0] == dataset

    def filter_date_range() -> None:
        for dataset in datasets:
            dates = dates_by_dataset[dataset]
            start, end = dates.iloc[len(dates)//3], dates.iloc[2*len(dates)//3]
            state = FilterState(dataset, "Dry", start, end)
            subset = filter_features(features, state)
            assert subset.dataset.eq(dataset).all()

    results["dataset_switch_three_datasets"] = measure(switch_dataset, 10)
    results["date_season_filter_three_datasets"] = measure(filter_date_range, 10)

    dataset = "ETTh1"
    full = features.loc[features.dataset.eq(dataset)]
    all_state = FilterState(dataset, None, full.timestamp.min(),
                            full.timestamp.max() + pd.Timedelta(nanoseconds=1))
    sliced = filter_features(features, all_state)
    charts = {
        "calendar": lambda: build_calendar_heatmap(sliced),
        "stacked_bar": lambda: build_stacked_bar(sliced, dataset_label=dataset),
        "lag_heatmap": lambda: build_lag_heatmap(lag, dataset=dataset, season="Dry"),
        "quantile_fan": lambda: build_quantile_fan(quantiles, dataset=dataset, season="Dry"),
        "stl_panels": lambda: build_stl_panels(
            profiles.loc[profiles.dataset.eq(dataset) & profiles.record_type.eq("stl")],
            variable="OT", dataset_label=dataset),
        "ot_threshold": lambda: build_ot_threshold_chart(sliced),
        "barcode_rug": lambda: build_barcode_rug(events.loc[events.dataset.eq(dataset)]),
        "small_multiples": lambda: build_small_multiples(sliced),
        "loess_scatter": lambda: build_scatter_loess(
            sliced, load_variable="HUFL",
            loess_df=loess.loc[loess.dataset.eq(dataset)
                               & loess.load_feature.eq("HUFL")],
            dataset_label=dataset),
        "regime_boxplots": lambda: build_regime_boxplots(sliced, variable="OT"),
    }
    results["chart_build_per_view"] = {
        name: measure(builder, 5) for name, builder in charts.items()
    }

    # AppTest includes Streamlit server-side rendering and view switch, not browser paint.
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    started = perf_counter()
    app.run()
    initial = perf_counter() - started
    if app.exception:
        raise RuntimeError(str(app.exception))
    selectboxes = app.sidebar.selectbox
    if len(selectboxes) < 4:
        raise RuntimeError(f"Unexpected sidebar selectbox layout: {len(selectboxes)}")
    switch_samples = []
    for dataset_name in list(selectboxes[0].options):
        started = perf_counter()
        app.sidebar.selectbox[0].select(dataset_name).run()
        switch_samples.append(perf_counter() - started)
        if app.exception:
            raise RuntimeError(str(app.exception))
    role_samples = []
    story_options = list(app.sidebar.radio[0].options)
    for story in [story_options[1], story_options[0], story_options[1]]:
        started = perf_counter()
        app.sidebar.radio[0].set_value(story).run()
        role_samples.append(perf_counter() - started)
        if app.exception:
            raise RuntimeError(str(app.exception))
    variable_samples = []
    variables = list(app.sidebar.selectbox[3].options)
    for variable in [variables[1], variables[0]]:
        started = perf_counter()
        app.sidebar.selectbox[3].select(variable).run()
        variable_samples.append(perf_counter() - started)
        if app.exception:
            raise RuntimeError(str(app.exception))
    date_control = app.sidebar.date_input[0]
    date_range = date_control.value
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        midpoint = start_date + (end_date - start_date) // 2
        started = perf_counter()
        date_control.set_value((start_date, midpoint)).run()
        date_filter_seconds = perf_counter() - started
        if app.exception:
            raise RuntimeError(str(app.exception))
    else:
        date_filter_seconds = None
    app.sidebar.radio[0].set_value(app.sidebar.radio[0].options[1]).run()
    switch_view = app.sidebar.selectbox[2]
    view_samples = []
    for view in list(switch_view.options):
        started = perf_counter()
        app.sidebar.selectbox[2].select(view).run()
        view_samples.append(perf_counter() - started)
        if app.exception:
            raise RuntimeError(str(app.exception))
    app.sidebar.radio[0].set_value(app.sidebar.radio[0].options[0]).run()
    story1_view = app.sidebar.selectbox[2]
    for view in list(story1_view.options):
        started = perf_counter()
        app.sidebar.selectbox[2].select(view).run()
        view_samples.append(perf_counter() - started)
        if app.exception:
            raise RuntimeError(str(app.exception))
    warm_app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    warm_started = perf_counter()
    warm_app.run()
    warm_initial = perf_counter() - warm_started
    if warm_app.exception:
        raise RuntimeError(str(warm_app.exception))
    all_interactions = (switch_samples + role_samples + variable_samples + view_samples
                        + ([date_filter_seconds] if date_filter_seconds is not None else []))
    results["streamlit_apptest_server_side"] = {
        "initial_render_seconds": initial,
        "warm_initial_render_seconds": warm_initial,
        "dataset_switch_seconds": switch_samples,
        "role_switch_seconds": role_samples,
        "variable_switch_seconds": variable_samples,
        "date_range_filter_seconds": date_filter_seconds,
        "view_switch_seconds": view_samples,
        "max_switch_seconds": max(all_interactions),
        "exceptions": 0,
        "browser_paint_included": False,
        "network_included": False,
    }
    results["sla_thresholds_seconds"] = {
        "stretch_target": 1.5, "project_sla": 2.0,
        "warm_loader_mean_pass": warm_seconds < 1.5,
        "dataset_switch_mean_pass": results["dataset_switch_three_datasets"]["mean_seconds"] < 1.5,
        "filter_mean_pass": results["date_season_filter_three_datasets"]["mean_seconds"] < 1.5,
    }
    results["scope_note"] = (
        "Local single-run AppTest excludes browser paint/network. Repeated in-process "
        "loader/filter/chart timings are not production concurrency or end-to-end SLA."
    )
    evidence_path = ROOT / "audit" / "performance_sla_benchmark.json"
    atomic_write_text(evidence_path, json.dumps(results, indent=2, allow_nan=False) + "\n")
    rows = [
        "# T0504 Streamlit cache & SLA benchmark",
        "",
        f"- **Generated:** {pd.Timestamp.now(tz='UTC').isoformat()}",
        f"- **Branch:** `{subprocess.check_output(['git','branch','--show-current'], cwd=ROOT, text=True).strip()}`",
        f"- **Python / Streamlit:** {sys.version.split()[0]} / {streamlit.__version__}",
        f"- **Platform / CPU:** {platform.platform()} / {platform.processor() or 'not reported'}",
        "- **Measurement boundary:** AppTest server-side; excludes browser paint, network, concurrency, and user-device variance.",
        "",
        "## Loader and interaction measurements",
        "",
        "| Scenario | Runs | Mean (s) | Median (s) | Max (s) |",
        "|---|---:|---:|---:|---:|",
        f"| Cold load, six artifacts | 1 | {cold_seconds:.4f} | — | {cold_seconds:.4f} |",
        f"| Warm cached load, six artifacts | 1 | {warm_seconds:.4f} | — | {warm_seconds:.4f} |",
        f"| Dataset switch + slice (three datasets) | 10 | {results['dataset_switch_three_datasets']['mean_seconds']:.4f} | {results['dataset_switch_three_datasets']['median_seconds']:.4f} | {results['dataset_switch_three_datasets']['max_seconds']:.4f} |",
        f"| Season/date slice helper (three datasets) | 10 | {results['date_season_filter_three_datasets']['mean_seconds']:.4f} | {results['date_season_filter_three_datasets']['median_seconds']:.4f} | {results['date_season_filter_three_datasets']['max_seconds']:.4f} |",
        f"| AppTest initial app render | 1 | {initial:.4f} | — | {initial:.4f} |",
        f"| AppTest warm initial app render | 1 | {warm_initial:.4f} | — | {warm_initial:.4f} |",
        f"| AppTest max dataset/role/variable/view/date interaction | 1 set | — | — | {results['streamlit_apptest_server_side']['max_switch_seconds']:.4f} |",
        "",
        "## Per-view chart construction (ETTh1, five runs each)",
        "",
        "| View | Mean (s) | Median (s) | Max (s) |",
        "|---|---:|---:|---:|",
    ]
    for name, timing in results["chart_build_per_view"].items():
        rows.append(f"| {name} | {timing['mean_seconds']:.4f} | {timing['median_seconds']:.4f} | {timing['max_seconds']:.4f} |")
    rows.extend([
        "",
        "## Assessment",
        "",
        f"- Warm loader mean <1.5s: **{results['sla_thresholds_seconds']['warm_loader_mean_pass']}**.",
        f"- Dataset-slice mean <1.5s: **{results['sla_thresholds_seconds']['dataset_switch_mean_pass']}**.",
        f"- Date/season filter helper mean <1.5s: **{results['sla_thresholds_seconds']['filter_mean_pass']}**.",
        f"- Cold AppTest initial render <2s: **{'PASS' if initial < 2 else 'FAIL'}** ({initial:.4f}s).",
        f"- Warm AppTest initial render <2s: **{'PASS' if warm_initial < 2 else 'FAIL'}** ({warm_initial:.4f}s).",
        f"- Warm AppTest switch maximum <2s: **{'PASS' if results['streamlit_apptest_server_side']['max_switch_seconds'] < 2 else 'FAIL'}**.",
        "- **Overall browser/end-to-end SLA: NOT MEASURED.** AppTest is not browser paint/network timing.",
        "- No universal SLA claim is made from these local single-process timings.",
        "",
        "## Artifact identity and reproducibility",
        "",
        "Inputs are identified by path, byte size, and SHA-256 in `performance_sla_benchmark.json`.",
        "The six cached inputs are grid features, STL/profile, quantile bands, lag JSON, events, and LOESS.",
        "Streamlit cache keys include resolved path + `(mtime_ns, size)`; no cache-key argument is underscore-prefixed.",
        "Per-view chart timings exclude sidebar, browser rendering, and network transfer.",
        "",
        "## Machine-readable evidence",
        "",
        "See `audit/performance_sla_benchmark.json` for raw timing samples, environment, and artifact hashes.",
    ])
    atomic_write_text(ROOT / "audit" / "performance_sla_benchmark.md", "\n".join(rows) + "\n")
    print(json.dumps({
        "evidence": str(evidence_path),
        "loader_cold_seconds": cold_seconds,
        "loader_warm_seconds": warm_seconds,
        "dataset_switch_mean_seconds": results["dataset_switch_three_datasets"]["mean_seconds"],
        "filter_mean_seconds": results["date_season_filter_three_datasets"]["mean_seconds"],
        "apptest_initial_seconds": initial,
        "apptest_max_switch_seconds": results["streamlit_apptest_server_side"]["max_switch_seconds"],
        "apptest_exceptions": 0,
    }, indent=2))


if __name__ == "__main__":
    main()