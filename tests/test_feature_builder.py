"""CPU-only grid-feature contract, business boundaries and atomic failures."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data import feature_builder as fb
from src.data.constants import (
    CLEAN_COLUMNS, FEATURE_COLUMNS, MEASUREMENTS, SEASON_CONVENTION,
    SHARE_COLUMNS, TEMPORAL_COLUMNS,
)


@pytest.fixture
def clean_frame() -> pd.DataFrame:
    """A small fixed clean contract; no fixture is written into raw."""
    rows = 6
    frame = pd.DataFrame({
        "dataset": pd.Series(["ETTh1"] * rows, dtype="string"),
        "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h").astype(
            "datetime64[ns]"
        ),
    })
    for column in MEASUREMENTS:
        frame[column] = np.ones(rows, dtype=np.float32)
    for column in ("total_useful_load", "total_unuseful_load"):
        frame[column] = np.full(rows, 3, dtype=np.float32)
    frame["reactive_ratio"] = np.ones(rows, dtype=np.float32)
    frame["thermal_regime"] = pd.Series("Normal", index=frame.index, dtype="string")
    frame["is_imputed"] = False
    return frame.loc[:, CLEAN_COLUMNS]


def test_temporal_extraction(clean_frame: pd.DataFrame) -> None:
    frame = clean_frame.iloc[:4].copy()
    frame["timestamp"] = pd.to_datetime([
        "2026-04-30 23:00", "2026-05-01 00:00",
        "2026-10-31 12:00", "2026-11-01 08:00",
    ]).astype("datetime64[ns]")
    result = fb.extract_temporal_features(frame)
    assert result["hour"].tolist() == [23, 0, 12, 8]
    assert result["month"].tolist() == [4, 5, 10, 11]
    assert result["day_of_week"].tolist() == [3, 4, 5, 6]
    assert result["day_name"].tolist() == ["Thu", "Fri", "Sat", "Sun"]
    assert result["is_weekend"].tolist() == [False, False, True, True]
    assert result["season"].tolist() == ["Dry", "Wet", "Wet", "Dry"]
    for column in ("hour", "day_of_week", "month"):
        assert result[column].dtype == np.dtype("int32")


def test_all_months_and_weekdays(clean_frame: pd.DataFrame) -> None:
    frame = pd.concat([clean_frame] * 2, ignore_index=True)
    frame["timestamp"] = pd.date_range(
        "2026-01-01", periods=12, freq="MS",
    ).astype("datetime64[ns]")
    result = fb.extract_temporal_features(frame)
    assert result["season"].tolist() == [
        "Dry", "Dry", "Dry", "Dry", "Wet", "Wet", "Wet", "Wet", "Wet",
        "Wet", "Dry", "Dry",
    ]
    frame = pd.concat([clean_frame, clean_frame.iloc[:1]], ignore_index=True)
    frame["timestamp"] = pd.date_range(
        "2026-01-05", periods=7, freq="D",
    ).astype("datetime64[ns]")
    result = fb.extract_temporal_features(frame)
    assert result["day_name"].tolist() == [
        "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun",
    ]


def test_thermal_regime_boundaries() -> None:
    ot = pd.Series([84.99, 85, 94.99, 95, np.nan, "invalid", np.inf, -np.inf])
    result = fb.classify_thermal_regime(ot)
    assert result.tolist() == [
        "Normal", "Warning", "Warning", "Critical",
        "Unknown", "Unknown", "Unknown", "Unknown",
    ]
    assert result.index.equals(ot.index)


def test_useful_and_unuseful_load_math(clean_frame: pd.DataFrame) -> None:
    frame = clean_frame.copy()
    for column, value in zip(("HUFL", "MUFL", "LUFL"), (2, 3, 5)):
        frame[column] = np.float32(value)
    for column, value in zip(("HULL", "MULL", "LULL"), (1, 2, 4)):
        frame[column] = np.float32(value)
    result = fb.add_load_features(frame)
    np.testing.assert_array_equal(result["total_useful_load"], np.full(6, 10))
    np.testing.assert_array_equal(result["total_unuseful_load"], np.full(6, 7))
    np.testing.assert_allclose(result["reactive_ratio"], 0.7)
    for column in (*fb.FLOAT_COLUMNS, *SHARE_COLUMNS):
        assert result[column].dtype == np.dtype("float32")


def test_reactive_ratio_zero_and_negative_division(
    clean_frame: pd.DataFrame,
) -> None:
    frame = clean_frame.copy()
    frame["HUFL"] = np.array([0, -3, np.nan, 1, 1, 1], dtype=np.float32)
    frame["MUFL"] = np.float32(0)
    frame["LUFL"] = np.float32(0)
    result = fb.add_load_features(frame)
    assert result.loc[:2, "reactive_ratio"].isna().all()
    assert not np.isinf(result["reactive_ratio"]).any()
    assert result.loc[:2, list(SHARE_COLUMNS)].isna().all().all()


def test_voltage_shares_sum_to_one(clean_frame: pd.DataFrame) -> None:
    frame = clean_frame.copy()
    frame["HUFL"] = np.float32(2)
    frame["MUFL"] = np.float32(3)
    frame["LUFL"] = np.float32(5)
    result = fb.build_grid_features(frame)
    np.testing.assert_allclose(result[list(SHARE_COLUMNS)].sum(axis=1), 1, atol=1e-5)
    np.testing.assert_allclose(result["HUFL_ratio"], 0.2)
    np.testing.assert_allclose(result["MUFL_ratio"], 0.3)
    np.testing.assert_allclose(result["LUFL_ratio"], 0.5)


def test_negative_branch_invalidates_all_shares(clean_frame: pd.DataFrame) -> None:
    frame = clean_frame.copy()
    frame["HUFL"] = np.float32(-1)
    frame["MUFL"] = np.float32(3)
    result = fb.build_grid_features(frame)
    assert result["total_useful_load"].eq(3).all()
    assert result[list(SHARE_COLUMNS)].isna().all().all()
    assert result["reactive_ratio"].eq(1).all()


def test_missing_measurements_propagate(clean_frame: pd.DataFrame) -> None:
    frame = clean_frame.copy()
    frame.loc[0, "HULL"] = np.nan
    frame.loc[1, "HUFL"] = np.nan
    frame.loc[2, "OT"] = np.inf
    result = fb.build_grid_features(frame)
    assert pd.isna(result.loc[0, "total_unuseful_load"])
    assert pd.isna(result.loc[0, "reactive_ratio"])
    assert result.loc[1, list(SHARE_COLUMNS)].isna().all()
    assert pd.isna(result.loc[2, "OT"])
    assert result.loc[2, "thermal_regime"] == "Unknown"
    assert not result["is_imputed"].any()


def test_pure_idempotent_and_index_preserved(clean_frame: pd.DataFrame) -> None:
    frame = clean_frame.set_axis([9, 9, 4, 5, 3, 2])
    before = frame.copy(deep=True)
    enriched = fb.build_grid_features(frame)
    pd.testing.assert_frame_equal(frame, before)
    assert enriched.index.equals(frame.index)
    pd.testing.assert_frame_equal(enriched, fb.build_grid_features(enriched))


def test_compatibility_with_clean_ett_parquet() -> None:
    source = ROOT / "data/processed/clean_ett.parquet"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    frame = pd.read_parquet(source)
    enriched = fb.build_grid_features(frame)
    assert len(enriched) == len(frame) == 17420
    assert tuple(enriched.columns) == FEATURE_COLUMNS
    assert len(enriched.columns) == 23
    pd.testing.assert_frame_equal(
        enriched[list(MEASUREMENTS)], frame[list(MEASUREMENTS)],
    )
    pd.testing.assert_series_equal(enriched["timestamp"], frame["timestamp"])
    valid = enriched[list(SHARE_COLUMNS)].notna().all(axis=1)
    assert valid.any() and (~valid).any()
    np.testing.assert_allclose(
        enriched.loc[valid, list(SHARE_COLUMNS)].sum(axis=1), 1, atol=1e-5,
    )
    assert before == hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.parametrize("problem", [
    "missing", "extra", "duplicate_column", "null_time", "time_string",
    "timezone", "bad_dataset", "null_dataset", "duplicate_key", "unsorted",
    "bad_cadence", "imputed_dtype", "overflow",
])
def test_invalid_frame_rejected(clean_frame: pd.DataFrame, problem: str) -> None:
    frame = clean_frame.copy()
    if problem == "missing":
        frame = frame.drop(columns="OT")
    elif problem == "extra":
        frame["unexpected"] = 1
    elif problem == "duplicate_column":
        frame = pd.concat([frame, frame[["OT"]]], axis=1)
    elif problem == "null_time":
        frame.loc[0, "timestamp"] = pd.NaT
    elif problem == "time_string":
        frame["timestamp"] = frame["timestamp"].astype(str)
    elif problem == "timezone":
        frame["timestamp"] = frame["timestamp"].dt.tz_localize("UTC")
    elif problem == "bad_dataset":
        frame.loc[0, "dataset"] = "ETTm2"
    elif problem == "null_dataset":
        frame.loc[0, "dataset"] = pd.NA
    elif problem == "duplicate_key":
        frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    elif problem == "unsorted":
        frame = frame.iloc[::-1]
    elif problem == "bad_cadence":
        frame.loc[1, "timestamp"] += pd.Timedelta(minutes=1)
    elif problem == "imputed_dtype":
        frame["is_imputed"] = 0
    else:
        frame["HUFL"] = np.float64(1e100)
    with pytest.raises(ValueError):
        fb.build_grid_features(frame)


def test_multiple_datasets_not_aggregated(clean_frame: pd.DataFrame) -> None:
    other = clean_frame.copy()
    other["dataset"] = "ETTm1"
    other["timestamp"] = pd.date_range(
        "2026-01-01", periods=6, freq="15min",
    ).astype("datetime64[ns]")
    result = fb.build_grid_features(pd.concat([clean_frame, other]))
    assert result.groupby("dataset").size().to_dict() == {"ETTh1": 6, "ETTm1": 6}
    assert len(result) == 12


def test_empty_contract_roundtrip(clean_frame: pd.DataFrame, tmp_path: Path) -> None:
    empty = clean_frame.iloc[:0]
    result = fb.build_grid_features(empty)
    assert result.empty and tuple(result.columns) == FEATURE_COLUMNS
    out = tmp_path / "features.parquet"
    fb.save_grid_features(empty, out, source_hash="a" * 64)
    assert fb.load_grid_features(out).empty


def test_atomic_save_and_load(clean_frame: pd.DataFrame, tmp_path: Path) -> None:
    out = tmp_path / "features.parquet"
    fb.save_grid_features(clean_frame, out, source_hash="a" * 64)
    loaded = fb.load_grid_features(out)
    pd.testing.assert_frame_equal(loaded, fb.build_grid_features(clean_frame))
    metadata = pq.read_schema(out).metadata
    assert metadata[b"schema_version"] == b"2.0"
    assert metadata[b"source_hash"] == b"a" * 64
    assert metadata[b"timezone"] == b"unknown"
    assert json.loads(metadata[b"parameters"])["season_convention"] == SEASON_CONVENTION
    assert not Path(str(out) + ".tmp").exists()


@pytest.mark.parametrize("target", ["raw", "docs", "clean", "input_alias"])
def test_export_guardrails(
    clean_frame: pd.DataFrame, tmp_path: Path, target: str,
) -> None:
    source = tmp_path / "source.parquet"
    clean_frame.to_parquet(source)
    outputs = {
        "raw": ROOT / "data/raw/forbidden.parquet",
        "docs": ROOT / "docs/forbidden.parquet",
        "clean": ROOT / "data/processed/clean_ett.parquet",
        "input_alias": source,
    }
    with pytest.raises(ValueError):
        fb.save_grid_features(
            clean_frame, outputs[target], source_hash="a" * 64, source_path=source,
        )


def test_output_hardlink_to_source_rejected(
    clean_frame: pd.DataFrame, tmp_path: Path,
) -> None:
    alias = tmp_path / "alias.parquet"
    source = tmp_path / "source.parquet"
    clean_frame.to_parquet(source)
    alias.hardlink_to(source)
    with pytest.raises(ValueError, match="aliases"):
        fb.save_grid_features(
            clean_frame, alias, source_hash="a" * 64, source_path=source,
        )


@pytest.mark.parametrize("failure", ["write", "read", "replace"])
def test_atomic_failure_preserves_output(
    clean_frame: pd.DataFrame, tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    out = tmp_path / "features.parquet"
    out.write_bytes(b"previous artifact")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("simulated")

    if failure == "write":
        monkeypatch.setattr(fb.pq, "write_table", fail)
    elif failure == "read":
        monkeypatch.setattr(fb.pq, "read_table", fail)
    else:
        monkeypatch.setattr(fb.os, "replace", fail)
    with pytest.raises(OSError, match="simulated"):
        fb.save_grid_features(clean_frame, out, source_hash="a" * 64)
    assert out.read_bytes() == b"previous artifact"
    assert not Path(str(out) + ".tmp").exists()


def test_stale_tmp_preserved(clean_frame: pd.DataFrame, tmp_path: Path) -> None:
    out = tmp_path / "features.parquet"
    temporary = Path(str(out) + ".tmp")
    temporary.write_bytes(b"other writer")
    with pytest.raises(FileExistsError):
        fb.save_grid_features(clean_frame, out, source_hash="a" * 64)
    assert temporary.read_bytes() == b"other writer"
    assert not out.exists()


@pytest.mark.parametrize("corruption", [
    "value", "metadata", "version", "schema", "seed", "timezone",
    "source_hash", "generated_at", "dataset", "season",
])
def test_corrupt_artifact_rejected(
    clean_frame: pd.DataFrame, tmp_path: Path, corruption: str,
) -> None:
    out = tmp_path / "features.parquet"
    fb.save_grid_features(clean_frame, out, source_hash="a" * 64)
    table = pq.read_table(out)
    if corruption == "value":
        position = table.column_names.index("hour")
        table = table.set_column(position, table.schema.field("hour"), pa.array(
            [23] * len(clean_frame), type=pa.int32(),
        ))
    elif corruption == "metadata":
        table = table.replace_schema_metadata({})
    elif corruption == "version":
        metadata = dict(table.schema.metadata)
        metadata[b"schema_version"] = b"1.0"
        table = table.replace_schema_metadata(metadata)
    elif corruption == "schema":
        table = table.drop(["season"])
    else:
        metadata = dict(table.schema.metadata)
        replacement = {
            "seed": b"1", "timezone": b"UTC", "source_hash": b"bad",
            "generated_at": b"2026-01-01T00:00:00", "dataset": b'[]',
            "season": b'{"season_convention":"unverified"}',
        }
        key = b"parameters" if corruption == "season" else corruption.encode()
        metadata[key] = replacement[corruption]
        table = table.replace_schema_metadata(metadata)
    pq.write_table(table, out)
    with pytest.raises((ValueError, AssertionError)):
        fb.load_grid_features(out)


def test_invalid_source_hash(clean_frame: pd.DataFrame, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        fb.save_grid_features(clean_frame, tmp_path / "out.parquet", source_hash="bad")


def test_cpu_only_import_and_cli(tmp_path: Path) -> None:
    result = subprocess.run([
        sys.executable, "-c",
        "import sys; from src.data.feature_builder import build_grid_features; "
        "assert 'torch' not in sys.modules",
    ], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    out = tmp_path / "features.parquet"
    result = subprocess.run([
        sys.executable, "-m", "src.data.feature_builder", "--out", str(out),
    ], cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert len(fb.load_grid_features(out)) == 17420