"""Regression counterexamples from the pre-T0501 integration audit."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analysis.thermal_risk import build_thermal_breach_events
from src.analysis.lag_correlation import save_lag_envelope
from src.data.constants import CLEAN_COLUMNS, MEASUREMENTS
from src.data.feature_builder import build_grid_features
from src.visuals.app_manager import _hourly_mean_fraction, compute_manager_kpis
from src.visuals.app_safety import compute_safety_kpis, build_scatter_loess
from src.visuals.charts_safety import build_ot_threshold_chart
from src.visuals.filters import (
    FilterState, filter_features, filter_events, filter_profiles,
)


def fixture(ot: list[float], dataset: str = "ETTh1") -> pd.DataFrame:
    n = len(ot)
    f = pd.DataFrame({"dataset": [dataset] * n, "timestamp": pd.date_range(
        "2026-01-01", periods=n, freq="15min" if dataset == "ETTm1" else "h"
    ).astype("datetime64[ns]")})
    for col in MEASUREMENTS:
        f[col] = np.ones(n, dtype=np.float32)
    f["OT"] = np.array(ot, dtype=np.float32)
    f["total_useful_load"] = np.float32(3)
    f["total_unuseful_load"] = np.float32(3)
    f["reactive_ratio"] = np.float32(1)
    f["thermal_regime"] = "Normal"
    f["is_imputed"] = False
    return f.loc[:, CLEAN_COLUMNS]


@pytest.mark.parametrize("dataset", ["ETTh1", "ETTm1"])
def test_no_fake_support(dataset: str) -> None:
    assert build_thermal_breach_events(fixture([96], dataset)).empty
    f = fixture([96, 80], dataset)
    f.loc[1, "timestamp"] += pd.Timedelta(hours=5)
    assert build_thermal_breach_events(f).empty
    f = fixture([96, np.nan], dataset)
    assert build_thermal_breach_events(f).empty


def test_tail_support_and_no_double_count() -> None:
    f = fixture([96, 100])
    events = build_thermal_breach_events(f)
    assert events.duration_hours.eq(1).all()
    assert events.is_right_censored.all()
    metrics = compute_safety_kpis(f, events)
    assert metrics["warning_degree_hours"] == 11
    assert metrics["critical_degree_hours"] == 1
    assert "tot_degree_hours" not in metrics


def test_negative_and_empty_kpis() -> None:
    f = build_grid_features(fixture([20, 20]))
    f["HUFL"] = -5
    f["HULL"] = 10
    fractions = _hourly_mean_fraction(f, None)
    assert fractions.loc[fractions.tier.eq("High"), "useful_frac"].isna().all()
    for key in ("ot_mean", "ot_max", "warn_pct"):
        assert pd.isna(compute_manager_kpis(f.iloc[:0])[key])


def test_gap_and_missing_line_breaks() -> None:
    f = fixture([20, np.nan, 30, 40])
    f.loc[3, "timestamp"] += pd.Timedelta(hours=4)
    fig = build_ot_threshold_chart(f)
    assert pd.isna(np.asarray(fig.data[0].y, dtype=float)).sum() >= 2


def test_no_loess_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    import statsmodels.nonparametric.smoothers_lowess as smooth
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("LOWESS in UI")
    monkeypatch.setattr(smooth, "lowess", forbidden)
    fig = build_scatter_loess(fixture([20, 21, 22]))
    assert not any(t.mode == "lines" and "LOESS" in t.name for t in fig.data)


def test_cache_keys_and_stl_path(tmp_path: Path) -> None:
    import app
    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    pd.DataFrame({"v": [1]}).to_parquet(a)
    pd.DataFrame({"v": [2]}).to_parquet(b)
    app.load_parquet.clear()
    assert app.load_parquet(str(a), app.artifact_version(a)).v.iloc[0] == 1
    assert app.load_parquet(str(b), app.artifact_version(b)).v.iloc[0] == 2
    pd.DataFrame({"v": [333]}).to_parquet(a)
    assert app.load_parquet(str(a), app.artifact_version(a)).v.iloc[0] == 333
    assert app.load_stl(str(b), app.artifact_version(b)).v.iloc[0] == 2


def test_json_envelope(tmp_path: Path) -> None:
    out = tmp_path / "lag.json"
    save_lag_envelope(fixture([20, 21, 22, 23]), out, source_hash="a" * 64)
    payload = json.loads(out.read_text())
    assert set(payload) == {"schema_version", "timezone", "generated_at", "seed", "source_hash", "records"}
    for record in payload["records"]:
        assert np.shape(record["correlation_matrix"]) == (6, 13)
        assert np.shape(record["sample_counts"]) == (6, 13)


def test_shared_filter_excludes_partial_events() -> None:
    f = build_grid_features(fixture([96, 100, 80]))
    events = build_thermal_breach_events(f)
    state = FilterState("ETTh1", "Dry", pd.Timestamp("2026-01-01 01:00"),
                        pd.Timestamp("2026-01-01 03:00"))
    assert len(filter_features(f, state)) == 2
    assert filter_events(events, state, f).empty


def test_stl_and_diagnostic_export(tmp_path: Path) -> None:
    import pyarrow.parquet as pq
    from src.analysis.load_profiling import save_load_profiles_stl
    from src.analysis.diagnostics import save_diagnostics
    f = fixture(list(30 + np.sin(np.arange(72) / 4)))
    f["HUFL"] = np.linspace(1, 5, len(f)).astype("float32")
    f = build_grid_features(f)
    out = save_load_profiles_stl(f, tmp_path / "stl.parquet", source_hash="a" * 64)
    stl = pd.read_parquet(out)
    assert set(stl.record_type) == {"stl", "profile"}
    valid = stl.loc[stl.record_type.eq("stl")].dropna(subset=["trend"])
    np.testing.assert_allclose(valid.observed, valid.trend + valid.seasonal +
                               valid.residual, atol=1e-5)
    files = save_diagnostics(f, build_thermal_breach_events(f), tmp_path,
                             source_hash="a" * 64, source_path=Path(__file__))
    assert pq.read_metadata(files["loess_curves"]).num_rows > 0
    assert pq.read_metadata(files["event_load_zscores"]).num_rows == 0


def test_calendar_absolute_color_scale() -> None:
    from src.visuals.charts_manager import build_calendar_heatmap
    fig = build_calendar_heatmap(build_grid_features(fixture([20, 30, 40])))
    trace = fig.data[0]
    assert trace.zmax >= 95
    red_start = next(position for position, color in trace.colorscale
                     if color == "#DC2626")
    assert trace.zmin + red_start * (trace.zmax - trace.zmin) >= 95 - 1e-6


def test_all_dataset_artifacts() -> None:
    import pyarrow.parquet as pq
    from src.data.constants import DEFAULT_CLEAN_PATH, ARTIFACTS_DIR
    clean = pd.read_parquet(DEFAULT_CLEAN_PATH)
    assert clean.groupby("dataset").size().to_dict() == {
        "ETTh1": 17420, "ETTh2": 17420, "ETTm1": 69680}
    for filename, columns in (
        ("load_profiles_stl.parquet", 14), ("quantile_bands.parquet", 13),
        ("thermal_breach_events.parquet", 11),
    ):
        assert len(pq.read_schema(ARTIFACTS_DIR / filename)) == columns
    payload = json.loads((ARTIFACTS_DIR / "lag_correlation_matrix.json").read_text())
    assert {record["dataset"] for record in payload["records"]} == set(clean.dataset)


def test_profiles_follow_observation_scope() -> None:
    rows = pd.DataFrame({
        "dataset": ["ETTh1", "ETTh1", "ETTh2", "ETTh1"],
        "timestamp": pd.to_datetime(["2026-01-01", "2026-05-01",
                                     "2026-01-01", None]),
        "record_type": ["stl", "stl", "stl", "profile"],
        "season": [None, None, None, "Dry"],
    })
    state = FilterState("ETTh1", "Dry", pd.Timestamp("2026-01-01"),
                        pd.Timestamp("2026-02-01"))
    result = filter_profiles(rows, state)
    assert result.index.tolist() == [0, 3]