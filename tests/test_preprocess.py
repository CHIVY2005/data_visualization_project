"""Acceptance, quality and failure-path tests for the clean ETT v2.0 ETL."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import preprocess_ett as etl

PARQUET_PATH = ROOT / "data" / "processed" / "clean_ett.parquet"
EXPECTED_COLUMNS = (
    "dataset", "timestamp", "OT", "HUFL", "HULL", "MUFL", "MULL", "LUFL",
    "LULL", "total_useful_load", "total_unuseful_load", "reactive_ratio",
    "thermal_regime", "is_imputed",
)
EXPECTED_HASHES = {
    "ETTh1": "f18de3ad269cef59bb07b5438d79bb3042d3be49bdeecf01c1cd6d29695ee066",
    "ETTh2": "a3dc2c597b9218c7ce1cd55eb77b283fd459a1d09d753063f944967dd6b9218b",
    "ETTm1": "6ce1759b1a18e3328421d5d75fadcb316c449fcd7cec32820c8dafda71986c9e",
    "ETTm2": "db973ca252c6410a30d0469b13d696cf919648d0f3fd588c60f03fdbdbadd1fd",
}


@pytest.fixture(scope="module")
def production_frame() -> pd.DataFrame:
    """Read the actual generated artifact, never regenerate it in a test."""
    return pd.read_parquet(PARQUET_PATH)


def sample_raw(rows: int = 6, frequency: str = "h") -> pd.DataFrame:
    """Return synthetic measurements with temperatures at project boundaries."""
    frame = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=rows, freq=frequency),
    })
    for column in ("OT", "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL"):
        frame[column] = np.ones(rows, dtype=np.float32)
    frame["OT"] = np.resize(
        np.array([84.999, 85, 94.999, 95, np.nan, 120], dtype=np.float32), rows,
    )
    return frame


def write_source(tmp_path: Path, frame: pd.DataFrame) -> Path:
    """Write fixtures under pytest temp only, never under repository raw."""
    directory = tmp_path / "input"
    directory.mkdir(exist_ok=True)
    path = directory / "ETTh1.csv"
    frame.to_csv(path, index=False)
    return path


def test_parquet_file_exists() -> None:
    assert PARQUET_PATH.is_file()
    assert PARQUET_PATH.stat().st_size > 0
    assert not PARQUET_PATH.with_name(PARQUET_PATH.name + ".tmp").exists()


def test_clean_parquet_schema_v2(production_frame: pd.DataFrame) -> None:
    frame = production_frame
    assert tuple(frame.columns) == EXPECTED_COLUMNS
    assert len(frame.columns) == 14
    assert frame["timestamp"].dtype == np.dtype("datetime64[ns]")
    assert frame["is_imputed"].dtype == np.dtype(bool)
    for column in EXPECTED_COLUMNS[2:12]:
        assert frame[column].dtype == np.dtype("float32")
    for column in ("dataset", "thermal_regime"):
        assert pd.api.types.is_string_dtype(frame[column])
        assert not frame[column].isna().any()
    assert not any(c.endswith("_scaled") for c in frame)
    assert not {"date", "split", "hour", "day_of_week", "month", "day"} & set(frame)
    schema = pq.read_schema(PARQUET_PATH)
    assert schema.field("dataset").type == pa.string()
    assert schema.field("thermal_regime").type == pa.string()
    assert schema.field("timestamp").type == pa.timestamp("ns")


def test_data_hygiene_and_integrity(production_frame: pd.DataFrame) -> None:
    frame = production_frame
    raw = pd.read_csv(ROOT / "data" / "raw" / "ETTh1.csv")
    assert len(frame) == len(raw) == 17420
    assert frame["dataset"].eq("ETTh1").all()
    assert not frame.duplicated(["dataset", "timestamp"]).any()
    assert frame["timestamp"].is_monotonic_increasing
    assert (frame["timestamp"].diff().dropna() == pd.Timedelta(hours=1)).all()
    np.testing.assert_array_equal(
        frame["timestamp"].to_numpy(), pd.to_datetime(raw["date"]).to_numpy(),
    )
    for column in etl.MEASUREMENTS:
        np.testing.assert_array_equal(frame[column], raw[column].astype("float32"))
    assert frame["OT"].min() < 0
    assert frame["OT"].max() > 40
    assert not frame[list(etl.MEASUREMENTS)].isna().any().any()
    assert not np.isinf(frame[list(etl.FLOAT_COLUMNS)].to_numpy()).any()
    assert not frame["is_imputed"].any()


def test_thermal_regime_and_reactive_ratio_logic(tmp_path: Path) -> None:
    source_frame = sample_raw()
    source_frame["HUFL"] = [1, 0, -1, np.nan, 1, 1]
    source_frame["MUFL"] = [1, 0, -1, 1, 1, 1]
    source_frame["LUFL"] = [1, 0, -1, 1, 1, 1]
    source = write_source(tmp_path, source_frame)
    frame, metadata = etl.load_clean_dataset(source, "ETTh1")
    assert frame["thermal_regime"].tolist() == [
        "Normal", "Warning", "Warning", "Critical", "Unknown", "Critical",
    ]
    np.testing.assert_allclose(
        frame["reactive_ratio"], [1, np.nan, np.nan, np.nan, 1, 1],
        equal_nan=True,
    )
    assert pd.isna(frame.loc[3, "total_useful_load"])
    assert frame.loc[5, "OT"] == 120
    assert not frame["is_imputed"].any()
    quality = json.loads(metadata["quality_audit"])
    assert quality["missing_measurements"]["OT"] == 1
    assert quality["missing_measurements"]["HUFL"] == 1
    etl.validate_clean_frame(frame, "ETTh1")
    out = tmp_path / "clean.parquet"
    etl.export_atomic(frame, metadata, out, source.parent)
    loaded = pd.read_parquet(out)
    assert pd.isna(loaded.loc[4, "OT"])
    assert loaded.loc[4, "thermal_regime"] == "Unknown"


def test_production_derived_values(production_frame: pd.DataFrame) -> None:
    frame = production_frame
    useful = frame["HUFL"] + frame["MUFL"] + frame["LUFL"]
    unuseful = frame["HULL"] + frame["MULL"] + frame["LULL"]
    np.testing.assert_allclose(frame["total_useful_load"], useful, rtol=1e-6)
    np.testing.assert_allclose(frame["total_unuseful_load"], unuseful, rtol=1e-6)
    expected_ratio = unuseful / useful.where(useful > 0)
    np.testing.assert_allclose(
        frame["reactive_ratio"], expected_ratio, rtol=1e-6, equal_nan=True,
    )
    assert frame.loc[useful <= 0, "reactive_ratio"].isna().all()
    assert frame["thermal_regime"].eq("Normal").all()


def test_parquet_metadata_v2() -> None:
    metadata = {
        k.decode(): v.decode() for k, v in pq.read_schema(PARQUET_PATH).metadata.items()
    }
    assert metadata["schema_version"] == "2.0"
    assert metadata["dataset"] == "ETTh1"
    assert metadata["seed"] == "2026"
    assert metadata["timezone"] == "unknown"
    assert metadata["source_hash"] == EXPECTED_HASHES["ETTh1"]
    assert metadata["source_hash_algorithm"] == "sha256_lf_normalized"
    created = datetime.fromisoformat(metadata["generated_at"])
    assert created.utcoffset() == timedelta(0)
    parameters = json.loads(metadata["parameters"])
    assert parameters["warning_threshold_c"] == 85
    assert parameters["critical_threshold_c"] == 95
    assert parameters["missing_policy"] == "preserve_null_no_imputation"
    assert json.loads(metadata["quality_audit"])["gap_count"] == 0


def test_parquet_roundtrip_validation(production_frame: pd.DataFrame) -> None:
    """String/object representation after Parquet must remain acceptable."""
    etl.validate_clean_frame(production_frame, "ETTh1")


@pytest.mark.parametrize("dataset", tuple(EXPECTED_HASHES))
def test_raw_data_untouched(dataset: str) -> None:
    """Check content equivalence independently of Git checkout line endings."""
    data = (ROOT / "data" / "raw" / f"{dataset}.csv").read_bytes()
    normalized = data.replace(b"\r\n", b"\n")
    actual = hashlib.sha256(normalized).hexdigest()
    assert actual == EXPECTED_HASHES[dataset], (
        f"Raw content changed (LF-normalized SHA-256): {dataset}"
    )


def test_hash_line_endings_and_mutation() -> None:
    assert etl.content_hash(b"a,b\r\n1,2\r\n") == etl.content_hash(b"a,b\n1,2\n")
    assert etl.content_hash(b"a,b\n1,3\n") != etl.content_hash(b"a,b\n1,2\n")


@pytest.mark.parametrize("dataset,frequency", [("ETTh2", "h"), ("ETTm1", "15min")])
def test_other_dataset_resolution(
    tmp_path: Path, dataset: str, frequency: str,
) -> None:
    raw_dir = tmp_path / "input"
    raw_dir.mkdir()
    source = raw_dir / f"{dataset}.csv"
    sample_raw(frequency=frequency).to_csv(source, index=False)
    summary = etl.run_pipeline(dataset, raw_dir, tmp_path / "clean.parquet")
    assert summary["dataset"] == dataset
    assert summary["rows"] == 6
    assert pd.read_parquet(tmp_path / "clean.parquet")["dataset"].eq(dataset).all()


@pytest.mark.parametrize("problem", [
    "duplicate", "timestamp_null", "timestamp_invalid", "timezone", "cadence",
    "infinity", "missing_column", "extra_column", "empty", "nonnumeric",
])
def test_invalid_input_rejected(tmp_path: Path, problem: str) -> None:
    frame = sample_raw()
    if problem == "duplicate":
        frame.loc[1, "date"] = frame.loc[0, "date"]
    elif problem == "timestamp_null":
        frame.loc[1, "date"] = pd.NaT
    elif problem == "timestamp_invalid":
        frame["date"] = frame["date"].astype(str)
        frame.loc[1, "date"] = "not-a-date"
    elif problem == "timezone":
        frame["date"] = frame["date"].dt.tz_localize("UTC")
    elif problem == "cadence":
        frame.loc[1, "date"] = frame.loc[0, "date"] + pd.Timedelta(minutes=30)
    elif problem == "infinity":
        frame.loc[0, "OT"] = np.inf
    elif problem == "missing_column":
        frame = frame.drop(columns="OT")
    elif problem == "extra_column":
        frame["unexpected"] = 1
    elif problem == "empty":
        frame = frame.iloc[:0]
    else:
        frame["HUFL"] = frame["HUFL"].astype(object)
        frame.loc[0, "HUFL"] = "invalid"
    source = write_source(tmp_path, frame)
    out = tmp_path / "clean.parquet"
    out.write_bytes(b"existing artifact")
    with pytest.raises((ValueError, TypeError)):
        etl.run_pipeline("ETTh1", source.parent, out)
    assert out.read_bytes() == b"existing artifact"


def test_sort_and_gap_policy(tmp_path: Path) -> None:
    frame = sample_raw().drop(index=2).iloc[::-1]
    clean, metadata = etl.load_clean_dataset(write_source(tmp_path, frame), "ETTh1")
    assert len(clean) == 5
    assert clean["timestamp"].is_monotonic_increasing
    assert json.loads(metadata["quality_audit"])["gap_count"] == 1
    assert not clean["is_imputed"].any()


@pytest.mark.parametrize("target", ["raw", "raw_tmp", "docs", "custom_raw"])
def test_output_guardrail(tmp_path: Path, target: str) -> None:
    custom_raw = tmp_path / "input"
    destinations = {
        "raw": ROOT / "data/raw/forbidden.parquet",
        "raw_tmp": ROOT / "data/raw/forbidden.parquet.tmp",
        "docs": ROOT / "docs/forbidden.parquet",
        "custom_raw": custom_raw / "forbidden.parquet",
    }
    with pytest.raises(ValueError, match="protected"):
        etl.validate_output_path(destinations[target], custom_raw)
    assert not destinations[target].exists()


def test_output_hardlink_guardrail(tmp_path: Path) -> None:
    source = write_source(tmp_path, sample_raw())
    alias = tmp_path / "alias.parquet"
    alias.hardlink_to(source)
    with pytest.raises(ValueError, match="aliases"):
        etl.validate_output_path(alias, source.parent)


@pytest.mark.parametrize("failure", ["write", "verify", "replace"])
def test_atomic_failure_preserves_existing_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    source = write_source(tmp_path, sample_raw())
    frame, metadata = etl.load_clean_dataset(source, "ETTh1")
    out = tmp_path / "clean.parquet"
    out.write_bytes(b"previous valid bytes")

    def fail(*args: Any, **kwargs: Any) -> None:
        raise OSError("simulated failure")

    if failure == "write":
        monkeypatch.setattr(etl.pq, "write_table", fail)
    elif failure == "verify":
        monkeypatch.setattr(etl.pq, "read_table", fail)
    else:
        monkeypatch.setattr(etl.os, "replace", fail)
    with pytest.raises(OSError, match="simulated"):
        etl.export_atomic(frame, metadata, out, source.parent)
    assert out.read_bytes() == b"previous valid bytes"
    assert not out.with_name(out.name + ".tmp").exists()


def test_existing_tmp_not_overwritten(tmp_path: Path) -> None:
    source = write_source(tmp_path, sample_raw())
    frame, metadata = etl.load_clean_dataset(source, "ETTh1")
    out = tmp_path / "clean.parquet"
    temporary = out.with_name(out.name + ".tmp")
    temporary.write_bytes(b"other process")
    with pytest.raises(FileExistsError):
        etl.export_atomic(frame, metadata, out, source.parent)
    assert temporary.read_bytes() == b"other process"
    assert not out.exists()


def test_atomic_replace_uses_verified_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_source(tmp_path, sample_raw())
    frame, metadata = etl.load_clean_dataset(source, "ETTh1")
    out = tmp_path / "clean.parquet"
    replace = etl.os.replace
    calls: list[tuple[Path, Path]] = []

    def check_replace(src: Path, dst: Path) -> None:
        assert src == out.with_name(out.name + ".tmp")
        assert pq.read_table(src).num_rows == len(frame)
        calls.append((src, dst))
        replace(src, dst)

    monkeypatch.setattr(etl.os, "replace", check_replace)
    etl.export_atomic(frame, metadata, out, source.parent)
    assert calls == [(out.with_name(out.name + ".tmp"), out)]
    assert tuple(pd.read_parquet(out).columns) == EXPECTED_COLUMNS
    assert not calls[0][0].exists()


def test_invalid_clean_frame_not_exported(tmp_path: Path) -> None:
    source = write_source(tmp_path, sample_raw())
    frame, metadata = etl.load_clean_dataset(source, "ETTh1")
    frame["total_useful_load"] = np.float32(999)
    out = tmp_path / "clean.parquet"
    with pytest.raises(ValueError, match="derived"):
        etl.export_atomic(frame, metadata, out, source.parent)
    assert not out.exists()


def test_cli_contract_and_error_exit(tmp_path: Path) -> None:
    assert etl.parse_args([]).data == "ETTh1"
    with pytest.raises(SystemExit):
        etl.parse_args(["--data", "ETTm2"])
    assert etl.main([
        "--raw_dir", str(tmp_path / "absent"), "--out", str(tmp_path / "out.parquet"),
    ]) == 1
    assert not (tmp_path / "out.parquet").exists()