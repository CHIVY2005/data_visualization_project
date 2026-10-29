"""Regression coverage for the canonical lag boundary and integration sync."""

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app
from scripts.run_statistical_engine import run_engine
from src.analysis.lag_correlation import export_lag_correlation_artifact
from src.data.constants import (
    ARTIFACTS_DIR, DEFAULT_CLEAN_PATH, DEFAULT_LAG_JSON_PATH, LOAD_BRANCHES,
)
from src.visuals import build_lag_heatmap
from src.visuals.lag_artifact import lag_envelope_frame


def envelope() -> dict:
    """Return an independent synthetic canonical record including nulls."""
    return {
        "schema_version": "2.0", "timezone": "unknown",
        "generated_at": "2026-10-29T00:00:00+00:00", "seed": 2026,
        "source_hash": "a" * 64,
        "records": [{
            "dataset": "ETTh1", "season": "Dry", "method": "pearson",
            "load_variables": list(LOAD_BRANCHES), "lags_hours": list(range(13)),
            "correlation_matrix": [[None, *([0.5] * 12)] for _ in LOAD_BRANCHES],
            "sample_counts": [[0, *([4] * 12)] for _ in LOAD_BRANCHES],
        }],
    }


def test_canonical_json_heatmap_preserves_nulls() -> None:
    payload = envelope()
    before = deepcopy(payload)
    frame = lag_envelope_frame(payload)
    assert payload == before
    assert len(frame) == 78
    assert frame.loc[frame.lag_hour.eq(0), "correlation"].isna().all()
    figure = build_lag_heatmap(frame, dataset="ETTh1", season="Dry")
    assert np.shape(figure.data[0].z) == (6, 13)
    assert frame.lag_hour.dtype == np.dtype("int32")


@pytest.mark.parametrize("problem", ["shape", "nan", "count", "order", "duplicate"])
def test_invalid_lag_json_rejected(problem: str) -> None:
    payload = envelope()
    record = payload["records"][0]
    if problem == "shape":
        record["correlation_matrix"][0].pop()
    elif problem == "nan":
        record["correlation_matrix"][0][0] = float("nan")
    elif problem == "count":
        record["sample_counts"][0][0] = -1
    elif problem == "order":
        record["load_variables"].reverse()
    else:
        payload["records"].append(deepcopy(record))
    with pytest.raises(ValueError):
        lag_envelope_frame(payload)


def test_json_cache_identity_and_version(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    payload = envelope()
    first.write_text(json.dumps(payload), encoding="utf-8")
    payload["records"][0]["dataset"] = "ETTh2"
    second.write_text(json.dumps(payload), encoding="utf-8")
    app.load_lag_json.clear()
    assert app.load_lag_json(str(first), (1, 1)).dataset.eq("ETTh1").all()
    assert app.load_lag_json(str(second), (1, 1)).dataset.eq("ETTh2").all()
    first.write_text(json.dumps(payload), encoding="utf-8")
    assert app.load_lag_json(str(first), (2, 1)).dataset.eq("ETTh2").all()


def test_engine_exports_only_canonical_lag(tmp_path: Path) -> None:
    # Small observed slice, never a write into raw or production artifacts.
    source = tmp_path / "clean.parquet"
    clean = pd.read_parquet(DEFAULT_CLEAN_PATH)
    clean.loc[clean.dataset.eq("ETTh1")].head(72).to_parquet(source)
    outputs = run_engine(source, tmp_path / "artifacts")
    assert "lag_matrix" not in outputs
    assert Path(outputs["lag_correlation_matrix"]).name == DEFAULT_LAG_JSON_PATH.name
    assert not (tmp_path / "artifacts" / "lag_matrix.parquet").exists()
    frame = lag_envelope_frame(json.loads(
        Path(outputs["lag_correlation_matrix"]).read_text(encoding="utf-8")
    ))
    assert len(frame) == 156
    direct = export_lag_correlation_artifact(source, tmp_path / "lag.json")
    assert set(direct) == {"lag_correlation_matrix"}


def test_production_canonical_names() -> None:
    assert app._PATH_LAG_MATRIX == DEFAULT_LAG_JSON_PATH
    assert DEFAULT_CLEAN_PATH.is_file()
    for filename in (
        "load_profiles_stl.parquet", "quantile_bands.parquet",
        "lag_correlation_matrix.json", "thermal_breach_events.parquet",
    ):
        assert (ARTIFACTS_DIR / filename).is_file()