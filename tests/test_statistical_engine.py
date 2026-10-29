"""Synthetic WP02 tests for STL, quantiles, lag and thermal events."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import lag_correlation as lag
from src.analysis import load_profiling as profiling
from src.analysis import thermal_risk as risk
from src.data import feature_builder as fb
from src.data.constants import CLEAN_COLUMNS, LOAD_BRANCHES, MEASUREMENTS


def _clean_frame(rows: int = 72) -> pd.DataFrame:
    """Build a clean contract fixture without touching repository raw data."""
    t = np.arange(rows, dtype="float64")
    daily = np.sin(2 * np.pi * t / 24)
    frame = pd.DataFrame({
        "dataset": pd.Series(["ETTh1"] * rows, dtype="string"),
        "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h").astype(
            "datetime64[ns]"
        ),
        "OT": (30 + 2 * np.sin(2 * np.pi * (t - 3) / 24)).astype("float32"),
        "HUFL": (10 + daily).astype("float32"),
        "HULL": (5 + daily * 0.5).astype("float32"),
        "MUFL": (8 + daily * 0.8).astype("float32"),
        "MULL": (4 + daily * 0.4).astype("float32"),
        "LUFL": (6 + daily * 0.6).astype("float32"),
        "LULL": (3 + daily * 0.3).astype("float32"),
    })
    frame["total_useful_load"] = frame[["HUFL", "MUFL", "LUFL"]].sum(
        axis=1
    ).astype("float32")
    frame["total_unuseful_load"] = frame[["HULL", "MULL", "LULL"]].sum(
        axis=1
    ).astype("float32")
    frame["reactive_ratio"] = (
        frame["total_unuseful_load"] / frame["total_useful_load"]
    ).astype("float32")
    frame["thermal_regime"] = fb.classify_thermal_regime(frame["OT"])
    frame["is_imputed"] = False
    return frame.loc[:, CLEAN_COLUMNS]


def test_t0201_stl_and_quantile_contracts() -> None:
    pytest.importorskip("statsmodels")
    features = fb.build_grid_features(_clean_frame(72))
    profiles = profiling.build_load_profiles_stl(features, variables=("OT",))
    assert tuple(profiles.columns) == tuple(profiling.LOAD_PROFILE_SCHEMA.names)
    assert {"stl", "profile"} == set(profiles["record_type"])

    stl = profiles.loc[profiles["record_type"].eq("stl")].dropna(
        subset=["trend", "seasonal", "residual"]
    )
    assert not stl.empty
    np.testing.assert_allclose(
        stl["observed"],
        stl["trend"] + stl["seasonal"] + stl["residual"],
        rtol=1e-5,
        atol=1e-5,
    )

    bands = profiling.build_quantile_bands(features, variables=("OT",))
    assert tuple(bands.columns) == tuple(profiling.QUANTILE_SCHEMA.names)
    assert len(bands) == 24
    assert bands["hour"].tolist() == list(range(24))
    ordered = bands[["q025", "q10", "q25", "q50", "q75", "q90", "q975"]]
    assert (ordered.diff(axis=1).iloc[:, 1:] >= 0).all().all()


def test_t0201_atomic_save_metadata(tmp_path: Path) -> None:
    pytest.importorskip("statsmodels")
    out = tmp_path / "hourly_quantiles.parquet"
    profiling.save_hourly_quantiles(
        _clean_frame(72), out, source_hash="a" * 64,
    )
    metadata = pq.read_schema(out).metadata
    assert metadata[b"schema_version"] == b"2.0"
    assert metadata[b"artifact_type"] == b"quantile_bands"
    assert json.loads(metadata[b"parameters"])["bands"]["95"] == ["q025", "q975"]
    assert not out.with_name(out.name + ".tmp").exists()


def test_t0202_lag_peak_uses_positive_load_leads() -> None:
    records = lag.build_lag_correlation_records(
        _clean_frame(96),
        load_variables=("HUFL",),
        lags_hours=(0, 1, 2, 3, 4, 5),
        methods=("pearson",),
        min_pairs=20,
    )
    assert len(records) == 1
    record = records[0]
    assert record["load_variables"] == ["HUFL"]
    assert record["lags_hours"] == [0, 1, 2, 3, 4, 5]
    row = record["correlation_matrix"][0]
    peak_lag = record["lags_hours"][int(np.nanargmax(np.abs(row)))]
    assert peak_lag == 3
    assert record["sample_counts"][0][3] > record["sample_counts"][0][5]


def test_t0202_lag_matrix_contract_and_save(tmp_path: Path) -> None:
    matrix = lag.build_lag_matrix(_clean_frame(48), min_pairs=3)
    assert tuple(matrix.columns) == tuple(lag.LAG_MATRIX_SCHEMA.names)
    assert set(matrix["method"]) == {"pearson", "spearman"}
    assert set(matrix["load_variable"]) == set(LOAD_BRANCHES)
    assert matrix.groupby(
        ["dataset", "season", "method", "load_variable"]
    )["is_peak_abs"].sum().eq(1).all()

    out = tmp_path / "lag_matrix.parquet"
    lag.save_lag_matrix(_clean_frame(48), out, source_hash="b" * 64)
    metadata = pq.read_schema(out).metadata
    assert metadata[b"artifact_type"] == b"lag_matrix"
    assert not out.with_name(out.name + ".tmp").exists()


def _risk_clean_frame() -> pd.DataFrame:
    frame = _clean_frame(10)
    frame["OT"] = np.array(
        [80, 86, 87, 80, 96, 100, 97, 80, 96, 97], dtype=np.float32
    )
    for idx, variable in enumerate(LOAD_BRANCHES):
        frame[variable] = np.linspace(10 + idx, 20 + idx, len(frame)).astype("float32")
    frame["total_useful_load"] = frame[["HUFL", "MUFL", "LUFL"]].sum(
        axis=1
    ).astype("float32")
    frame["total_unuseful_load"] = frame[["HULL", "MULL", "LULL"]].sum(
        axis=1
    ).astype("float32")
    frame["reactive_ratio"] = (
        frame["total_unuseful_load"] / frame["total_useful_load"]
    ).astype("float32")
    frame["thermal_regime"] = fb.classify_thermal_regime(frame["OT"])
    return frame.loc[:, CLEAN_COLUMNS]


def test_t0203_thermal_events_degree_hours_and_zscores() -> None:
    events = risk.build_thermal_breach_events(_risk_clean_frame())
    assert tuple(events.columns) == tuple(risk.THERMAL_BREACH_SCHEMA.names)
    assert len(events.columns) == 11

    critical = events.loc[
        events["thermal_regime"].eq("Critical")
        & events["start_timestamp"].eq(pd.Timestamp("2026-01-01 04:00:00"))
    ].iloc[0]
    assert critical["duration_hours"] == pytest.approx(3)
    assert critical["peak_ot"] == pytest.approx(100)
    assert critical["degree_hours"] == pytest.approx(8)
    assert critical["sample_count"] == 3
    assert not bool(critical["is_right_censored"])
    assert critical["end_timestamp"] == pd.Timestamp("2026-01-01 07:00:00")

    tail = events.loc[
        events["thermal_regime"].eq("Critical")
        & events["start_timestamp"].eq(pd.Timestamp("2026-01-01 08:00:00"))
    ].iloc[0]
    assert bool(tail["is_right_censored"])


def test_t0203_empty_events_keep_schema() -> None:
    events = risk.build_thermal_breach_events(_clean_frame(24))
    assert events.empty
    assert tuple(events.columns) == tuple(risk.THERMAL_BREACH_SCHEMA.names)


def test_t0203_atomic_save_metadata(tmp_path: Path) -> None:
    out = tmp_path / "breach_events.parquet"
    risk.save_thermal_breach_events(_risk_clean_frame(), out, source_hash="c" * 64)
    metadata = pq.read_schema(out).metadata
    assert metadata[b"artifact_type"] == b"thermal_breach_events"
    params = json.loads(metadata[b"parameters"])
    assert params["support_policy"].startswith("next_finite")
    assert not out.with_name(out.name + ".tmp").exists()
