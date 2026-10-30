"""T0204 finite-pair contracts, scope isolation and render decoupling."""

import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from src.analysis import thermal_risk as risk
from src.data.constants import CLEAN_COLUMNS, LOAD_BRANCHES, DEFAULT_LOESS_PATH
from src.visuals.app_safety import build_scatter_loess


def clean_frame(n: int = 48, dataset: str = "ETTh1") -> pd.DataFrame:
    """Synthetic observations outside raw, spanning all thermal regimes."""
    x = np.linspace(-2, 8, n).astype("float32")
    frame = pd.DataFrame({
        "dataset": dataset,
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="h").astype(
            "datetime64[ns]"),
        "OT": np.linspace(70, 110, n).astype("float32"),
        **{variable: x + index for index, variable in enumerate(LOAD_BRANCHES)},
        "total_useful_load": np.float32(1),
        "total_unuseful_load": np.float32(1), "reactive_ratio": np.float32(1),
        "thermal_regime": "Unknown", "is_imputed": False,
    })
    return frame.loc[:, CLEAN_COLUMNS]


def test_schema_scopes_determinism_and_isolation() -> None:
    frame = pd.concat([clean_frame(), clean_frame(dataset="ETTh2")], ignore_index=True)
    before = frame.copy(deep=True)
    curves = risk.compute_loess_curves(frame)
    pd.testing.assert_frame_equal(frame, before)
    pd.testing.assert_frame_equal(curves, risk.compute_loess_curves(frame))
    assert list(curves) == risk.LOESS_SCHEMA.names
    assert set(curves.load_feature) == set(LOAD_BRANCHES)
    assert set(curves.scope_type) == {"all", "season", "thermal_regime"}
    assert set(curves.scope_value) >= {"ALL", "Dry", "Normal", "Warning", "Critical"}
    assert curves.x_load.dtype == curves.y_ot_smooth.dtype == np.dtype("float32")
    assert curves.sample_count.dtype == np.dtype("int32")
    assert not curves.isna().any().any()
    assert np.isfinite(curves[["x_load", "y_ot_smooth"]]).all().all()
    groups = curves.groupby(["dataset", "load_feature", "scope_type", "scope_value"])
    assert groups.size().eq(150).all()
    assert groups.sample_count.nunique().eq(1).all()
    assert all(g.x_load.is_monotonic_increasing for _, g in groups)


@pytest.mark.parametrize("problem", ["short", "constant_load", "constant_ot", "empty"])
def test_unsupported_groups_return_typed_empty(problem: str) -> None:
    frame = clean_frame(9 if problem == "short" else 36)
    if problem == "constant_load":
        frame.loc[:, list(LOAD_BRANCHES)] = 1
    elif problem == "constant_ot":
        frame["OT"] = np.float32(20)
    elif problem == "empty":
        frame = frame.iloc[:0]
    curves = risk.compute_loess_curves(frame)
    assert curves.empty
    assert list(curves) == risk.LOESS_SCHEMA.names
    assert curves.x_load.dtype == np.dtype("float32")


def test_finite_pairs_and_exact_lowess_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = clean_frame()
    frame.loc[0, "OT"] = np.nan
    calls = []
    actual = risk.lowess

    def capture(**kwargs: object) -> np.ndarray:
        calls.append(kwargs)
        return actual(**kwargs)

    monkeypatch.setattr(risk, "lowess", capture)
    curves = risk.compute_loess_curves(frame)
    assert calls and all(c["frac"] == 0.2 and c["it"] == 3 for c in calls)
    assert all(c["return_sorted"] is True for c in calls)
    assert curves.loc[curves.scope_type.eq("all"), "sample_count"].eq(47).all()


@pytest.mark.parametrize("frac,n_grid", [(0, 150), (float("nan"), 150), (0.2, 99)])
def test_parameters_rejected(frac: float, n_grid: int) -> None:
    with pytest.raises(ValueError):
        risk.compute_loess_curves(clean_frame(), frac, n_grid)


def test_atomic_metadata_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "loess_curves.parquet"
    risk.save_loess_curves(clean_frame(), path, source_hash="a" * 64)
    schema = pq.read_schema(path)
    assert schema.remove_metadata() == risk.LOESS_SCHEMA
    metadata = schema.metadata
    assert metadata[b"seed"] == b"2026"
    assert metadata[b"timezone"] == b"unknown"
    assert json.loads(metadata[b"parameters"])["fit_sampling"] == "all_finite_pairs"
    before = path.read_bytes()
    import src.analysis.common as common

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(common.os, "replace", fail)
    with pytest.raises(OSError):
        risk.save_loess_curves(clean_frame(), path, source_hash="a" * 64)
    assert path.read_bytes() == before
    assert not path.with_name(path.name + ".tmp").exists()


def test_render_uses_saved_scopes_without_lowess(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = clean_frame()
    curves = risk.compute_loess_curves(frame)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("runtime LOWESS forbidden")

    monkeypatch.setattr(risk, "lowess", forbidden)
    for season, regime, expected in [
        (None, None, "all: ALL"), ("Dry", None, "season: Dry"),
        ("Dry", "Critical", "thermal_regime: Critical"),
    ]:
        fig = build_scatter_loess(
            frame, loess_df=curves, season=season, thermal_regime=regime,
        )
        trace = next(t for t in fig.data if "LOESS" in t.name)
        assert expected in trace.name
        assert len(trace.x) == 150
    module = Path(__file__).resolve().parents[1] / "src/visuals/app_safety.py"
    tree = ast.parse(module.read_text(encoding="utf-8"))
    assert not any(isinstance(node, ast.ImportFrom) and
                   (node.module or "").startswith("statsmodels") for node in ast.walk(tree))


def test_parquet_cache_invalidates_by_source_and_version(tmp_path: Path) -> None:
    import app
    first, second = tmp_path / "a.parquet", tmp_path / "b.parquet"
    pd.DataFrame({"v": [1]}).to_parquet(first)
    pd.DataFrame({"v": [2]}).to_parquet(second)
    app.load_parquet.clear()
    assert app.load_parquet(str(first), (1, 1)).v.iloc[0] == 1
    assert app.load_parquet(str(second), (1, 1)).v.iloc[0] == 2
    pd.DataFrame({"v": [3]}).to_parquet(first)
    assert app.load_parquet(str(first), (2, 1)).v.iloc[0] == 3


def test_production_loess_contract() -> None:
    table = pq.read_table(DEFAULT_LOESS_PATH)
    assert table.schema.remove_metadata() == risk.LOESS_SCHEMA
    frame = table.to_pandas()
    assert set(frame.dataset) == {"ETTh1", "ETTh2", "ETTm1"}
    assert not frame.isna().any().any()
    assert np.isfinite(frame[["x_load", "y_ot_smooth"]]).all().all()
    assert frame.sample_count.ge(10).all()
    assert frame.groupby([
        "dataset", "load_feature", "scope_type", "scope_value",
    ]).size().eq(150).all()