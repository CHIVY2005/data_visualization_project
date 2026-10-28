"""Pure grid features and a separate 23-column Parquet contract for WP02.

Dry/Wet are user-approved month bins, not verified ETT station climate. Load
units remain those of the source. Shares are fractions, not percent values.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.constants import (
    CADENCE_MINUTES,
    CLEAN_COLUMNS,
    CRITICAL_TEMP_THRESHOLD,
    DAY_NAMES,
    DEFAULT_CLEAN_PATH,
    DEFAULT_FEATURE_PATH,
    DRY_MONTHS,
    FEATURE_COLUMNS,
    FLOAT_COLUMNS,
    MEASUREMENTS,
    ROOT,
    SCHEMA_VERSION,
    SEASON_CONVENTION,
    SEED,
    SHARE_COLUMNS,
    UNUSEFUL_LOADS,
    USEFUL_LOADS,
    WARNING_TEMP_THRESHOLD,
)

FEATURE_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("timestamp", pa.timestamp("ns"), nullable=False),
    *(pa.field(column, pa.float32()) for column in FLOAT_COLUMNS),
    pa.field("thermal_regime", pa.string(), nullable=False),
    pa.field("is_imputed", pa.bool_(), nullable=False),
    pa.field("hour", pa.int32(), nullable=False),
    pa.field("day_of_week", pa.int32(), nullable=False),
    pa.field("day_name", pa.string(), nullable=False),
    pa.field("is_weekend", pa.bool_(), nullable=False),
    pa.field("month", pa.int32(), nullable=False),
    pa.field("season", pa.string(), nullable=False),
    *(pa.field(column, pa.float32()) for column in SHARE_COLUMNS),
])


def _numeric(series: pd.Series) -> pd.Series:
    """Invalid/non-finite measurements become null, never fake zeros."""
    values = pd.to_numeric(series, errors="coerce").astype("float64")
    return values.where(np.isfinite(values))


def classify_thermal_regime(ot: pd.Series) -> pd.Series:
    """Classify finite OT; invalid, missing and infinity map to Unknown."""
    values = _numeric(ot)
    result = pd.Series("Unknown", index=ot.index, dtype="string")
    result.loc[values < WARNING_TEMP_THRESHOLD] = "Normal"
    result.loc[
        (values >= WARNING_TEMP_THRESHOLD) & (values < CRITICAL_TEMP_THRESHOLD)
    ] = "Warning"
    result.loc[values >= CRITICAL_TEMP_THRESHOLD] = "Critical"
    return result


def extract_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add explicit locale-independent calendar bins without sorting/mutation."""
    if "timestamp" not in frame:
        raise ValueError("Missing timestamp")
    timestamp = frame["timestamp"]
    if timestamp.dtype != np.dtype("datetime64[ns]") or timestamp.isna().any():
        raise ValueError("timestamp must be non-null timezone-naive datetime64[ns]")
    result = frame.copy(deep=True)
    result["hour"] = timestamp.dt.hour.astype("int32")
    result["day_of_week"] = timestamp.dt.dayofweek.astype("int32")
    result["day_name"] = result["day_of_week"].map(
        dict(enumerate(DAY_NAMES))
    ).astype("string")
    result["is_weekend"] = result["day_of_week"].ge(5)
    result["month"] = timestamp.dt.month.astype("int32")
    result["season"] = pd.Series("Wet", index=result.index, dtype="string")
    result.loc[result["month"].isin(DRY_MONTHS), "season"] = "Dry"
    return result


def add_load_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add null-safe totals/ratios; negative useful branches invalidate shares."""
    missing = set((*USEFUL_LOADS, *UNUSEFUL_LOADS)).difference(frame.columns)
    if missing:
        raise ValueError(f"Missing load columns: {sorted(missing)}")
    result = frame.copy(deep=True)
    for column in (*USEFUL_LOADS, *UNUSEFUL_LOADS):
        values = _numeric(result[column])
        if (values.abs() > np.finfo(np.float32).max).any():
            raise ValueError(f"float32 overflow: {column}")
        result[column] = values.astype("float32")
    useful = result[list(USEFUL_LOADS)].astype("float64")
    unuseful = result[list(UNUSEFUL_LOADS)].astype("float64")
    total = useful.sum(axis=1, min_count=3)
    other = unuseful.sum(axis=1, min_count=3)
    values = {
        "total_useful_load": total,
        "total_unuseful_load": other,
        "reactive_ratio": other / total.where(total > 0),
    }
    valid = (total > 0) & useful.notna().all(axis=1) & useful.ge(0).all(axis=1)
    for column, share in zip(USEFUL_LOADS, SHARE_COLUMNS):
        values[share] = useful[column] / total.where(valid)
    for column, series in values.items():
        if ((series.abs() > np.finfo(np.float32).max) | np.isinf(series)).any():
            raise ValueError(f"float32 overflow: {column}")
        result[column] = series.astype("float32")
    return result


def _validate_keys(frame: pd.DataFrame) -> None:
    """Keep datasets separate and enforce unique time keys/cadence per dataset."""
    if frame["dataset"].isna().any():
        raise ValueError("Missing dataset key")
    if not frame["dataset"].isin(CADENCE_MINUTES).all():
        raise ValueError("Unsupported dataset key")
    if frame.duplicated(["dataset", "timestamp"]).any():
        raise ValueError("Duplicate dataset/timestamp key")
    for dataset, group in frame.groupby("dataset", sort=False):
        time = group["timestamp"]
        if not time.is_monotonic_increasing:
            raise ValueError("Timestamp must increase within each dataset")
        deltas = time.diff().dropna()
        cadence = pd.Timedelta(minutes=CADENCE_MINUTES[dataset])
        if ((deltas < cadence) | (deltas % cadence != pd.Timedelta(0))).any():
            raise ValueError("Invalid dataset cadence")


def build_grid_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Enrich clean v2.0 without changing its file or mutating the input frame.

    Exactly clean or enriched schemas are accepted. Invalid OT is retained as
    null/Unknown; invalid loads propagate null to dependent metrics. No temporal
    filling, cross-dataset aggregation or physical-unit normalization occurs.
    """
    columns = set(frame.columns)
    if not frame.columns.is_unique or columns not in (
        set(CLEAN_COLUMNS), set(FEATURE_COLUMNS),
    ):
        raise ValueError("Expected exact clean v2.0 or grid-features schema")
    result = extract_temporal_features(frame.loc[:, CLEAN_COLUMNS])
    _validate_keys(result)
    if result["is_imputed"].dtype != np.dtype(bool):
        raise ValueError("is_imputed must be non-null bool")
    result["dataset"] = result["dataset"].astype("string")
    ot = _numeric(result["OT"])
    if (ot.abs() > np.finfo(np.float32).max).any():
        raise ValueError("float32 overflow: OT")
    result["OT"] = ot.astype("float32")
    result["thermal_regime"] = classify_thermal_regime(result["OT"])
    result = add_load_features(result)
    return result.loc[:, FEATURE_COLUMNS]


def _output_path(out: Path, source: Path | None = None) -> Path:
    """Do not overwrite protected sources or the canonical 14-column clean."""
    destination = out.resolve()
    if destination.name == DEFAULT_CLEAN_PATH.name:
        raise ValueError("Use a separate feature artifact, never clean_ett.parquet")
    protected = [ROOT / "data/raw", ROOT / "docs"]
    for directory in protected:
        directory = directory.resolve()
        if destination == directory or destination.is_relative_to(directory):
            raise ValueError("Output targets a protected directory")
    sources = [DEFAULT_CLEAN_PATH]
    if source is not None:
        sources.append(source)
    if destination.exists():
        if not destination.is_file():
            raise ValueError("Output must be a file")
        for directory in protected:
            sources.extend(p for p in directory.rglob("*") if p.is_file())
    for path in sources:
        if destination == path.resolve():
            raise ValueError("Output aliases source")
        if destination.exists() and path.exists() and destination.samefile(path):
            raise ValueError("Output aliases source")
    return destination


def save_grid_features(
    frame: pd.DataFrame, out: Path | str = DEFAULT_FEATURE_PATH, *,
    source_hash: str, source_path: Path | None = None,
) -> Path:
    """Build and save validated features with exclusive tmp and atomic replace."""
    if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
        raise ValueError("source_hash must be lowercase SHA-256")
    destination = _output_path(Path(out), source_path)
    features = build_grid_features(frame)
    parameters = {
        "season_convention": SEASON_CONVENTION,
        "share_policy": "all_null_if_nonpositive_total_missing_or_negative_branch",
        "share_unit": "fraction_0_1",
        "invalid_measurement_policy": "null_no_imputation",
        "warning_threshold_c": WARNING_TEMP_THRESHOLD,
        "critical_threshold_c": CRITICAL_TEMP_THRESHOLD,
    }
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "grid_features",
        "dataset": json.dumps(sorted(features["dataset"].unique().tolist())),
        "seed": str(SEED),
        "source_hash": source_hash,
        "source_hash_algorithm": "sha256_source_file_bytes",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "unknown",
        "parameters": json.dumps(parameters, sort_keys=True, allow_nan=False),
        "quality_audit": json.dumps({
            "rows": len(features),
            "unknown_ot": int(features["thermal_regime"].eq("Unknown").sum()),
            "invalid_share_rows": int(features[SHARE_COLUMNS[0]].isna().sum()),
        }, sort_keys=True),
    }
    table = pa.Table.from_pandas(
        features, schema=FEATURE_SCHEMA, preserve_index=False, safe=True,
    ).replace_schema_metadata({k.encode(): v.encode() for k, v in metadata.items()})
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    owns_tmp = False
    try:
        with temporary.open("xb") as handle:
            owns_tmp = True
            pq.write_table(table, handle, compression="snappy")
            handle.flush()
            os.fsync(handle.fileno())
        if not pq.read_table(temporary).equals(table, check_metadata=True):
            raise ValueError("Feature Parquet round-trip verification failed")
        _output_path(destination, source_path)
        os.replace(temporary, destination)
    finally:
        if owns_tmp and temporary.exists():
            temporary.unlink()
    return destination


def load_grid_features(path: Path | str = DEFAULT_FEATURE_PATH) -> pd.DataFrame:
    """Load only the fixed feature contract and validate computed fields."""
    table = pq.read_table(path)
    if not table.schema.equals(FEATURE_SCHEMA, check_metadata=False):
        raise ValueError("Invalid grid feature Parquet schema")
    metadata = table.schema.metadata or {}
    required = (
        "schema_version", "artifact_type", "dataset", "seed", "source_hash",
        "generated_at", "timezone", "parameters", "quality_audit",
    )
    if any(key.encode() not in metadata for key in required):
        raise ValueError("Missing grid feature metadata")
    if metadata[b"schema_version"] != b"2.0":
        raise ValueError("Unsupported feature schema version")
    if metadata[b"artifact_type"] != b"grid_features":
        raise ValueError("Incorrect artifact type")
    if metadata[b"timezone"] != b"unknown" or metadata[b"seed"] != str(SEED).encode():
        raise ValueError("Invalid feature timezone/seed")
    digest = metadata[b"source_hash"].decode()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid source hash")
    generated = datetime.fromisoformat(metadata[b"generated_at"].decode())
    if generated.tzinfo is None or generated.utcoffset() != timezone.utc.utcoffset(
        generated
    ):
        raise ValueError("generated_at must have a verified UTC offset")
    parameters = json.loads(metadata[b"parameters"])
    if parameters["season_convention"] != SEASON_CONVENTION:
        raise ValueError("Season convention mismatch")
    frame = table.to_pandas()
    if json.loads(metadata[b"dataset"]) != sorted(frame["dataset"].unique().tolist()):
        raise ValueError("Metadata dataset mismatch")
    expected = build_grid_features(frame)
    pd.testing.assert_frame_equal(
        frame, expected, check_dtype=False, check_exact=False, rtol=1e-6,
    )
    return expected


def main(argv: Sequence[str] | None = None) -> int:
    """Precompute offline: python -m src.data.feature_builder --input ..."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_CLEAN_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_FEATURE_PATH)
    args = parser.parse_args(argv)
    try:
        _output_path(args.out, args.input)
        data = args.input.read_bytes()
        frame = pd.read_parquet(io.BytesIO(data))
        output = save_grid_features(
            frame, args.out, source_hash=hashlib.sha256(data).hexdigest(),
            source_path=args.input,
        )
        print(json.dumps({"output": str(output), "rows": len(frame)}))
    except (OSError, ValueError, TypeError, AssertionError) as exc:
        parser.exit(1, f"Feature export failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())