"""T0202: gap-aware lag cross-correlation between load branches and OT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Literal, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa

from src.analysis.common import (
    atomic_write_json,
    utc_now_iso,
    atomic_write_parquet,
    dataset_names,
    file_sha256,
    load_feature_input,
    metadata_bytes,
    set_seed,
)
from src.data.constants import (
    DEFAULT_FEATURE_PATH,
    DEFAULT_LAG_JSON_PATH,
    LOAD_BRANCHES,
    SEED,
)
from src.data.feature_builder import build_grid_features

CorrelationMethod = Literal["pearson", "spearman"]

LAG_MATRIX_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("season", pa.string(), nullable=False),
    pa.field("method", pa.string(), nullable=False),
    pa.field("load_variable", pa.string(), nullable=False),
    pa.field("lag_hour", pa.int32(), nullable=False),
    pa.field("correlation", pa.float32()),
    pa.field("abs_correlation", pa.float32()),
    pa.field("sample_count", pa.int32(), nullable=False),
    pa.field("is_peak_abs", pa.bool_(), nullable=False),
])


def _finite_pairs(left: pd.Series, right: pd.Series) -> pd.DataFrame:
    """Return finite numeric pairs only; nulls never become zeros."""
    pairs = pd.DataFrame({
        "load": pd.to_numeric(left, errors="coerce"),
        "ot": pd.to_numeric(right, errors="coerce"),
    })
    return pairs.replace([np.inf, -np.inf], np.nan).dropna()


def _correlate(
    pairs: pd.DataFrame, method: CorrelationMethod, min_pairs: int,
) -> float | None:
    """Compute a correlation coefficient or null for unsupported cases."""
    if len(pairs) < min_pairs:
        return None
    if pairs["load"].nunique(dropna=True) < 2 or pairs["ot"].nunique(dropna=True) < 2:
        return None
    value = pairs["load"].corr(pairs["ot"], method=method)
    if pd.isna(value) or not np.isfinite(value):
        return None
    return float(value)


def _lag_pairs(
    dataset_frame: pd.DataFrame, season_frame: pd.DataFrame,
    load_variable: str, lag_hour: int,
) -> pd.DataFrame:
    """Align load(t) to OT(t+k hours) by timestamp rather than blind shifting."""
    left = season_frame[["timestamp", load_variable]].copy()
    left["target_timestamp"] = left["timestamp"] + pd.Timedelta(hours=lag_hour)
    right = dataset_frame[["timestamp", "OT"]].rename(
        columns={"timestamp": "target_timestamp", "OT": "target_ot"}
    )
    aligned = left.merge(right, on="target_timestamp", how="inner", sort=False)
    return _finite_pairs(aligned[load_variable], aligned["target_ot"])


def build_lag_correlation_records(
    frame: pd.DataFrame,
    load_variables: Sequence[str] = LOAD_BRANCHES,
    lags_hours: Sequence[int] = tuple(range(13)),
    methods: Sequence[CorrelationMethod] = ("pearson", "spearman"),
    min_pairs: int = 3,
) -> list[dict[str, object]]:
    """Return contract records with 6x13 matrices for each dataset/season/method."""
    set_seed()
    features = build_grid_features(frame)
    missing = set(load_variables).difference(features.columns)
    if missing:
        raise ValueError(f"Missing load variables: {sorted(missing)}")
    if any(lag < 0 for lag in lags_hours):
        raise ValueError("Lag hours must be non-negative")

    records: list[dict[str, object]] = []
    for dataset, dataset_frame in features.groupby("dataset", sort=True):
        ordered = dataset_frame.sort_values("timestamp", kind="stable")
        seasons = sorted(str(value) for value in ordered["season"].dropna().unique())
        for season in seasons:
            season_frame = ordered.loc[ordered["season"].eq(season)]
            for method in methods:
                matrix: list[list[float | None]] = []
                counts: list[list[int]] = []
                for load_variable in load_variables:
                    row: list[float | None] = []
                    count_row: list[int] = []
                    for lag_hour in lags_hours:
                        pairs = _lag_pairs(
                            ordered, season_frame, load_variable, int(lag_hour),
                        )
                        count_row.append(int(len(pairs)))
                        row.append(_correlate(pairs, method, min_pairs))
                    matrix.append(row)
                    counts.append(count_row)
                records.append({
                    "dataset": str(dataset),
                    "season": season,
                    "method": method,
                    "load_variables": list(load_variables),
                    "lags_hours": [int(value) for value in lags_hours],
                    "correlation_matrix": matrix,
                    "sample_counts": counts,
                })
    return records


def build_lag_matrix(
    frame: pd.DataFrame,
    load_variables: Sequence[str] = LOAD_BRANCHES,
    lags_hours: Sequence[int] = tuple(range(13)),
    min_pairs: int = 3,
) -> pd.DataFrame:
    """Return long-form lag matrix rows named in the current charter."""
    records = build_lag_correlation_records(
        frame,
        load_variables=load_variables,
        lags_hours=lags_hours,
        min_pairs=min_pairs,
    )
    rows: list[dict[str, object]] = []
    for record in records:
        variables = list(record["load_variables"])
        lags = list(record["lags_hours"])
        matrix = list(record["correlation_matrix"])
        counts = list(record["sample_counts"])
        for variable, values, sample_counts in zip(variables, matrix, counts):
            finite = [
                abs(value) if value is not None and np.isfinite(value) else np.nan
                for value in values
            ]
            peak = int(np.nanargmax(finite)) if np.isfinite(finite).any() else -1
            for idx, lag_hour in enumerate(lags):
                value = values[idx]
                abs_value = None if value is None else abs(float(value))
                rows.append({
                    "dataset": record["dataset"],
                    "season": record["season"],
                    "method": record["method"],
                    "load_variable": variable,
                    "lag_hour": int(lag_hour),
                    "correlation": value,
                    "abs_correlation": abs_value,
                    "sample_count": int(sample_counts[idx]),
                    "is_peak_abs": bool(idx == peak),
                })
    result = pd.DataFrame(rows, columns=LAG_MATRIX_SCHEMA.names)
    return _coerce_lag_matrix(result)


def _coerce_lag_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce lag rows to the exact Parquet contract dtypes."""
    result = frame.copy()
    for column in ("dataset", "season", "method", "load_variable"):
        result[column] = result[column].astype("string")
    result["lag_hour"] = result["lag_hour"].astype("int32")
    result["sample_count"] = result["sample_count"].astype("int32")
    result["is_peak_abs"] = result["is_peak_abs"].fillna(False).astype(bool)
    for column in ("correlation", "abs_correlation"):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float32"
        )
    finite = result["correlation"].dropna()
    if not finite.between(-1, 1).all():
        raise ValueError("Correlation values must be within [-1, 1]")
    return result


def save_lag_matrix(
    frame: pd.DataFrame,
    out: Path | str,
    *,
    source_hash: str,
    source_path: Path | str | None = None,
) -> Path:
    """Explicit legacy export for compatibility; not used by the engine or UI."""
    matrix = build_lag_matrix(frame)
    metadata = metadata_bytes(
        "lag_matrix",
        dataset_names(matrix),
        source_hash,
        {
            "definition": "corr(load(t), OT(t+k_hours))",
            "lag_hours": sorted(matrix["lag_hour"].unique().astype(int).tolist()),
            "methods": sorted(matrix["method"].unique().astype(str).tolist()),
            "min_pairs": 3,
            "peak_policy": "maximum_absolute_correlation_per_dataset_season_method_load",
        },
        {
            "rows": len(matrix),
            "null_correlations": int(matrix["correlation"].isna().sum()),
        },
    )
    table = pa.Table.from_pandas(
        matrix, schema=LAG_MATRIX_SCHEMA, preserve_index=False, safe=True,
    ).replace_schema_metadata(metadata)
    return atomic_write_parquet(table, out, source_path)


def save_lag_envelope(
    frame: pd.DataFrame, out: Path | str, *, source_hash: str,
    source_path: Path | str | None = None,
) -> Path:
    """Canonical 6x13 envelope; the optional Parquet view is derived separately."""
    return atomic_write_json({
        "schema_version": "2.0", "timezone": "unknown",
        "generated_at": utc_now_iso(), "seed": SEED,
        "source_hash": source_hash,
        "records": build_lag_correlation_records(frame),
    }, out, source_path)


def export_lag_correlation_artifact(
    input_path: Path | str = DEFAULT_FEATURE_PATH,
    out: Path | str = DEFAULT_LAG_JSON_PATH,
) -> dict[str, str]:
    """Export lag correlations from a clean/features source path."""
    set_seed(SEED)
    source = Path(input_path)
    frame = load_feature_input(source)
    output = save_lag_envelope(
        frame, out, source_hash=file_sha256(source), source_path=source,
    )
    return {"lag_correlation_matrix": str(output)}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for T0202 lag-correlation artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_LAG_JSON_PATH)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export_lag_correlation_artifact(args.input, args.out)))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Lag correlation export failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
