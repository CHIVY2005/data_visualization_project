"""Read-only ETT ingestion and atomic export of the clean v2.0 contract.

Each invocation replaces one dataset artifact; it never appends other datasets.
Missing measurements remain null (no implicit interpolation or future filling).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
SEED = 2026
SCHEMA_VERSION = "2.0"
WARNING_TEMP_THRESHOLD = 85.0
CRITICAL_TEMP_THRESHOLD = 95.0
CADENCE_MINUTES = {"ETTh1": 60, "ETTh2": 60, "ETTm1": 15}
MEASUREMENTS = ("OT", "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL")
TOTAL_COLUMNS = ("total_useful_load", "total_unuseful_load")
FLOAT_COLUMNS = (*MEASUREMENTS, *TOTAL_COLUMNS, "reactive_ratio")
CLEAN_COLUMNS = (
    "dataset", "timestamp", *MEASUREMENTS, *TOTAL_COLUMNS,
    "reactive_ratio", "thermal_regime", "is_imputed",
)
CLEAN_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("timestamp", pa.timestamp("ns"), nullable=False),
    *(pa.field(name, pa.float32()) for name in FLOAT_COLUMNS),
    pa.field("thermal_regime", pa.string(), nullable=False),
    pa.field("is_imputed", pa.bool_(), nullable=False),
])
LOGGER = logging.getLogger("preprocess_ett")


def content_hash(data: bytes) -> str:
    """Hash LF-normalized CSV bytes without touching the source file."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def validate_output_path(out: Path, raw_dir: Path) -> Path:
    """Reject protected destinations, including resolved symlinks/hard links."""
    destination = out.resolve()
    protected = (ROOT / "data" / "raw", ROOT / "docs", raw_dir)
    for directory in protected:
        resolved = directory.resolve()
        if destination == resolved or destination.is_relative_to(resolved):
            raise ValueError(f"Output cannot target protected directory: {resolved}")
    if destination.exists():
        if not destination.is_file():
            raise ValueError("Output must be a file")
        for directory in protected:
            if directory.is_dir():
                for source in directory.rglob("*"):
                    if source.is_file() and destination.samefile(source):
                        raise ValueError("Output aliases a protected source file")
    return destination


def thermal_regimes(ot: pd.Series) -> pd.Series:
    """Assign project regimes; missing temperature is never Normal."""
    result = pd.Series("Unknown", index=ot.index, dtype="string")
    result.loc[ot < WARNING_TEMP_THRESHOLD] = "Normal"
    result.loc[
        (ot >= WARNING_TEMP_THRESHOLD) & (ot < CRITICAL_TEMP_THRESHOLD)
    ] = "Warning"
    result.loc[ot >= CRITICAL_TEMP_THRESHOLD] = "Critical"
    return result


def derive_measurements(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute derived columns without normalization or null-skipping sums."""
    result = frame.copy()
    for column in MEASUREMENTS:
        result[column] = pd.to_numeric(result[column], errors="raise").astype(
            "float32"
        )
        if np.isinf(result[column].to_numpy()).any():
            raise ValueError(f"Infinite/overflow measurement: {column}")
    result["total_useful_load"] = result[
        ["HUFL", "MUFL", "LUFL"]
    ].sum(axis=1, min_count=3).astype("float32")
    result["total_unuseful_load"] = result[
        ["HULL", "MULL", "LULL"]
    ].sum(axis=1, min_count=3).astype("float32")
    denominator = result["total_useful_load"]
    result["reactive_ratio"] = (
        result["total_unuseful_load"] / denominator.where(denominator > 0)
    ).astype("float32")
    for column in (*TOTAL_COLUMNS, "reactive_ratio"):
        if np.isinf(result[column].to_numpy()).any():
            raise ValueError(f"Overflow in derived measurement: {column}")
    result["thermal_regime"] = thermal_regimes(result["OT"])
    result["is_imputed"] = pd.Series(False, index=result.index, dtype=bool)
    return result


def load_clean_dataset(
    source: Path, dataset: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Audit one CSV snapshot, retain nulls/gaps, reject ambiguous timestamps."""
    if dataset not in CADENCE_MINUTES:
        raise ValueError(f"Unsupported dataset: {dataset}")
    data = source.read_bytes()
    frame = pd.read_csv(io.BytesIO(data))
    if set(frame.columns) != {"date", *MEASUREMENTS}:
        raise ValueError("Raw CSV must contain date and exactly seven measurements")
    if frame.empty:
        raise ValueError("Raw CSV must contain at least one sample")
    timestamps = pd.to_datetime(frame.pop("date"), errors="raise")
    if timestamps.isna().any():
        raise ValueError("Missing timestamp")
    if not pd.api.types.is_datetime64_any_dtype(timestamps.dtype):
        raise ValueError("Mixed or unsupported timestamp offsets")
    if timestamps.dt.tz is not None:
        raise ValueError("Timezone-aware source requires an explicit timezone policy")
    frame["timestamp"] = timestamps.astype("datetime64[ns]")
    if frame["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamp; refusing to discard observations")
    frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
    cadence = pd.Timedelta(minutes=CADENCE_MINUTES[dataset])
    deltas = frame["timestamp"].diff().dropna()
    if ((deltas < cadence) | (deltas % cadence != pd.Timedelta(0))).any():
        raise ValueError("Timestamp cadence does not match dataset resolution")
    gap_count = int((deltas > cadence).sum())
    frame = derive_measurements(frame)
    frame["dataset"] = pd.Series(dataset, index=frame.index, dtype="string")
    audit = {
        "row_count": len(frame),
        "gap_count": gap_count,
        "missing_measurements": {
            column: int(frame[column].isna().sum()) for column in MEASUREMENTS
        },
        "duplicate_count": 0,
        "imputed_count": 0,
    }
    metadata: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset": dataset,
        "seed": str(SEED),
        "source_hash": content_hash(data),
        "source_hash_algorithm": "sha256_lf_normalized",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": "unknown",
        "parameters": json.dumps({
            "cadence_minutes": CADENCE_MINUTES[dataset],
            "warning_threshold_c": WARNING_TEMP_THRESHOLD,
            "critical_threshold_c": CRITICAL_TEMP_THRESHOLD,
            "missing_policy": "preserve_null_no_imputation",
            "gap_policy": "preserve_observed_samples_no_gap_filling",
            "duplicate_policy": "reject",
            "write_policy": "replace_single_dataset",
        }, sort_keys=True, allow_nan=False),
        "quality_audit": json.dumps(audit, sort_keys=True, allow_nan=False),
    }
    LOGGER.info("Dataset %s audit: %s", dataset, audit)
    return frame.loc[:, CLEAN_COLUMNS], metadata


def validate_clean_frame(frame: pd.DataFrame, dataset: str) -> None:
    """Validate the fixed clean contract before touching an output file."""
    if tuple(frame.columns) != CLEAN_COLUMNS or frame.empty:
        raise ValueError("Invalid clean schema or empty dataset")
    if frame["dataset"].isna().any() or not frame["dataset"].eq(dataset).all():
        raise ValueError("Dataset key mismatch")
    timestamp = frame["timestamp"]
    if timestamp.dtype != np.dtype("datetime64[ns]"):
        raise ValueError("Timestamp must be timezone-naive datetime64[ns]")
    if timestamp.isna().any() or not timestamp.is_unique:
        raise ValueError("Timestamp must be non-null and unique")
    if not timestamp.is_monotonic_increasing:
        raise ValueError("Timestamp must be increasing")
    for column in FLOAT_COLUMNS:
        if frame[column].dtype != np.dtype("float32"):
            raise ValueError(f"Invalid dtype: {column}")
        if np.isinf(frame[column].to_numpy()).any():
            raise ValueError(f"Infinite value: {column}")
    if frame["is_imputed"].dtype != np.dtype(bool):
        raise ValueError("is_imputed must be bool")
    if frame["is_imputed"].any():
        raise ValueError("This producer does not impute measurements")
    expected = derive_measurements(frame)
    for column in (*TOTAL_COLUMNS, "reactive_ratio"):
        if not np.allclose(frame[column], expected[column], equal_nan=True):
            raise ValueError(f"Incorrect derived measurement: {column}")
    actual_regime = frame["thermal_regime"].astype("string")
    if not actual_regime.equals(expected["thermal_regime"]):
        raise ValueError("Incorrect thermal regime")


def export_atomic(
    frame: pd.DataFrame, metadata: dict[str, Any], out: Path, raw_dir: Path,
) -> Path:
    """Validate, exclusively create .tmp, fsync, verify, then os.replace.

    A stale/existing temporary file is not overwritten or removed. On handled
    failures only the temporary file owned by this invocation is cleaned up.
    """
    destination = validate_output_path(out, raw_dir)
    dataset = str(metadata["dataset"])
    validate_clean_frame(frame, dataset)
    table = pa.Table.from_pandas(
        frame, schema=CLEAN_SCHEMA, preserve_index=False, safe=True,
    ).replace_schema_metadata({
        key.encode("utf-8"): str(value).encode("utf-8")
        for key, value in metadata.items()
    })
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    owns_temporary = False
    try:
        with temporary.open("xb") as handle:
            owns_temporary = True
            pq.write_table(table, handle, compression="snappy")
            handle.flush()
            os.fsync(handle.fileno())
        verification = pq.read_table(temporary)
        if not verification.equals(table, check_metadata=True):
            raise ValueError("Temporary Parquet round-trip verification failed")
        validate_output_path(destination, raw_dir)
        os.replace(temporary, destination)
    finally:
        if owns_temporary and temporary.exists():
            temporary.unlink()
    return destination


def run_pipeline(
    dataset_name: str = "ETTh1",
    raw_dir: Path | str = ROOT / "data" / "raw",
    out_path: Path | str = ROOT / "data" / "processed" / "clean_ett.parquet",
) -> dict[str, Any]:
    """Export exactly one dataset, preserving physical measurements and raw."""
    random.seed(SEED)
    np.random.seed(SEED)
    raw_directory = Path(raw_dir).resolve()
    output = validate_output_path(Path(out_path), raw_directory)
    if dataset_name not in CADENCE_MINUTES:
        raise ValueError(f"Unsupported dataset: {dataset_name}")
    frame, metadata = load_clean_dataset(
        raw_directory / f"{dataset_name}.csv", dataset_name,
    )
    destination = export_atomic(frame, metadata, output, raw_directory)
    return {
        "status": "SUCCESS", "dataset": dataset_name, "rows": len(frame),
        "columns": list(frame.columns), "output": str(destination),
        "size_bytes": destination.stat().st_size,
        "source_hash": metadata["source_hash"],
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the single-dataset v2.0 CLI contract."""
    parser = argparse.ArgumentParser(
        description="Export physical ETT measurements using clean schema v2.0.",
        epilog="Each invocation replaces one dataset; no implicit append/merge.",
    )
    parser.add_argument("--data", choices=tuple(CADENCE_MINUTES), default="ETTh1")
    parser.add_argument("--raw_dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "data" / "processed" / "clean_ett.parquet",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run CLI; failures leave an existing output artifact untouched."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args(argv)
    try:
        summary = run_pipeline(args.data, args.raw_dir, args.out)
    except (OSError, ValueError, TypeError) as exc:
        LOGGER.error("ETL failed: %s", exc)
        return 1
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())