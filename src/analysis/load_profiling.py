"""T0201: STL decomposition and empirical hourly profile artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa

from src.analysis.common import (
    atomic_write_parquet,
    dataset_names,
    file_sha256,
    load_feature_input,
    metadata_bytes,
    set_seed,
)
from src.data.constants import (
    ANALYSIS_VARIABLES,
    CADENCE_MINUTES,
    DEFAULT_FEATURE_PATH,
    DEFAULT_HOURLY_QUANTILES_PATH,
    SEASON_CONVENTION,
    SEED,
)
from src.data.feature_builder import build_grid_features

LOAD_PROFILE_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("record_type", pa.string(), nullable=False),
    pa.field("variable", pa.string(), nullable=False),
    pa.field("timestamp", pa.timestamp("ns")),
    pa.field("season", pa.string()),
    pa.field("hour", pa.int32()),
    pa.field("observed", pa.float32()),
    pa.field("trend", pa.float32()),
    pa.field("seasonal", pa.float32()),
    pa.field("residual", pa.float32()),
    pa.field("mean", pa.float32()),
    pa.field("median", pa.float32()),
    pa.field("std", pa.float32()),
    pa.field("sample_count", pa.int32()),
])

QUANTILE_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("variable", pa.string(), nullable=False),
    pa.field("season", pa.string(), nullable=False),
    pa.field("hour", pa.int32(), nullable=False),
    pa.field("sample_count", pa.int32(), nullable=False),
    pa.field("mean", pa.float32()),
    pa.field("q025", pa.float32()),
    pa.field("q10", pa.float32()),
    pa.field("q25", pa.float32()),
    pa.field("q50", pa.float32()),
    pa.field("q75", pa.float32()),
    pa.field("q90", pa.float32()),
    pa.field("q975", pa.float32()),
])


def _stl_period(dataset: str) -> int:
    """Return daily seasonal period in samples for the dataset cadence."""
    cadence = CADENCE_MINUTES[dataset]
    if 1440 % cadence:
        raise ValueError(f"Dataset cadence does not divide one day: {dataset}")
    return 1440 // cadence


def _fit_stl_segment(values: pd.Series, period: int) -> tuple[pd.Series, ...]:
    """Fit statsmodels STL on one contiguous finite segment."""
    try:
        from statsmodels.tsa.seasonal import STL
    except ImportError as exc:
        raise RuntimeError("statsmodels is required for STL decomposition") from exc
    fit = STL(values.astype("float64"), period=period, robust=True).fit()
    return (
        pd.Series(fit.trend, index=values.index),
        pd.Series(fit.seasonal, index=values.index),
        pd.Series(fit.resid, index=values.index),
    )


def _decompose_one_series(
    group: pd.DataFrame, variable: str, dataset: str,
) -> pd.DataFrame:
    """Run STL without joining across gaps or missing observations."""
    expected_delta = pd.Timedelta(minutes=CADENCE_MINUTES[dataset])
    period = _stl_period(dataset)
    result = group[["dataset", "timestamp"]].copy()
    result["record_type"] = "stl"
    result["variable"] = variable
    result["season"] = pd.NA
    result["hour"] = pd.NA
    result["observed"] = pd.to_numeric(group[variable], errors="coerce")
    result["trend"] = np.nan
    result["seasonal"] = np.nan
    result["residual"] = np.nan
    result["mean"] = np.nan
    result["median"] = np.nan
    result["std"] = np.nan
    result["sample_count"] = pd.NA

    finite = result["observed"].notna() & np.isfinite(result["observed"])
    gap = group["timestamp"].diff().ne(expected_delta)
    segment = (gap | ~finite | ~finite.shift(fill_value=False)).cumsum()
    minimum = max(period * 2, period + 2)
    for _, segment_frame in result.loc[finite].groupby(segment[finite], sort=False):
        if len(segment_frame) < minimum:
            continue
        trend, seasonal, residual = _fit_stl_segment(
            segment_frame["observed"], period,
        )
        result.loc[segment_frame.index, "trend"] = trend
        result.loc[segment_frame.index, "seasonal"] = seasonal
        result.loc[segment_frame.index, "residual"] = residual
    return result


def build_stl_records(
    frame: pd.DataFrame,
    variables: Sequence[str] = ANALYSIS_VARIABLES,
) -> pd.DataFrame:
    """Return long-form STL records for each dataset/variable/timestamp."""
    set_seed()
    features = build_grid_features(frame)
    missing = set(variables).difference(features.columns)
    if missing:
        raise ValueError(f"Missing analysis variables: {sorted(missing)}")
    pieces: list[pd.DataFrame] = []
    for dataset, group in features.groupby("dataset", sort=True):
        ordered = group.sort_values("timestamp", kind="stable")
        for variable in variables:
            pieces.append(_decompose_one_series(ordered, variable, str(dataset)))
    if not pieces:
        return pd.DataFrame(columns=LOAD_PROFILE_SCHEMA.names)
    records = pd.concat(pieces, ignore_index=True)
    return _coerce_load_profile(records.loc[:, LOAD_PROFILE_SCHEMA.names])


def build_profile_records(
    frame: pd.DataFrame,
    variables: Sequence[str] = ANALYSIS_VARIABLES,
) -> pd.DataFrame:
    """Return seasonal/hourly mean, median, std and sample count records."""
    features = build_grid_features(frame)
    rows: list[dict[str, object]] = []
    for dataset in sorted(features["dataset"].unique()):
        data = features.loc[features["dataset"].eq(dataset)]
        seasons = sorted(str(value) for value in data["season"].dropna().unique())
        for variable in variables:
            for season in seasons:
                season_data = data.loc[data["season"].eq(season)]
                for hour in range(24):
                    values = pd.to_numeric(
                        season_data.loc[season_data["hour"].eq(hour), variable],
                        errors="coerce",
                    ).dropna()
                    rows.append({
                        "dataset": dataset,
                        "record_type": "profile",
                        "variable": variable,
                        "timestamp": pd.NaT,
                        "season": season,
                        "hour": hour,
                        "observed": np.nan,
                        "trend": np.nan,
                        "seasonal": np.nan,
                        "residual": np.nan,
                        "mean": values.mean() if len(values) else np.nan,
                        "median": values.median() if len(values) else np.nan,
                        "std": values.std(ddof=1) if len(values) > 1 else np.nan,
                        "sample_count": len(values),
                    })
    return _coerce_load_profile(pd.DataFrame(rows, columns=LOAD_PROFILE_SCHEMA.names))


def build_load_profiles_stl(
    frame: pd.DataFrame,
    variables: Sequence[str] = ANALYSIS_VARIABLES,
) -> pd.DataFrame:
    """Return one contract table containing both STL and profile records."""
    stl = build_stl_records(frame, variables)
    profiles = build_profile_records(frame, variables)
    return _coerce_load_profile(pd.concat([stl, profiles], ignore_index=True))


def build_quantile_bands(
    frame: pd.DataFrame,
    variables: Sequence[str] = ANALYSIS_VARIABLES,
) -> pd.DataFrame:
    """Return empirical hourly quantile bands by dataset, variable and season."""
    features = build_grid_features(frame)
    rows: list[dict[str, object]] = []
    for dataset in sorted(features["dataset"].unique()):
        data = features.loc[features["dataset"].eq(dataset)]
        seasons = sorted(str(value) for value in data["season"].dropna().unique())
        for variable in variables:
            for season in seasons:
                season_data = data.loc[data["season"].eq(season)]
                for hour in range(24):
                    values = pd.to_numeric(
                        season_data.loc[season_data["hour"].eq(hour), variable],
                        errors="coerce",
                    ).dropna()
                    item: dict[str, object] = {
                        "dataset": dataset,
                        "variable": variable,
                        "season": season,
                        "hour": hour,
                        "sample_count": len(values),
                        "mean": values.mean() if len(values) else np.nan,
                    }
                    quantiles = {
                        "q025": 0.025,
                        "q10": 0.10,
                        "q25": 0.25,
                        "q50": 0.50,
                        "q75": 0.75,
                        "q90": 0.90,
                        "q975": 0.975,
                    }
                    for name, q_value in quantiles.items():
                        item[name] = values.quantile(q_value) if len(values) else np.nan
                    rows.append(item)
    bands = pd.DataFrame(rows, columns=QUANTILE_SCHEMA.names)
    return _coerce_quantiles(bands)


def _coerce_load_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce nullable columns to the exact Parquet contract dtypes."""
    result = frame.copy()
    for column in ("dataset", "record_type", "variable", "season"):
        result[column] = result[column].astype("string")
    result["timestamp"] = pd.to_datetime(result["timestamp"]).astype("datetime64[ns]")
    result["hour"] = result["hour"].astype("Int32")
    result["sample_count"] = result["sample_count"].astype("Int32")
    for column in (
        "observed", "trend", "seasonal", "residual", "mean", "median", "std",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float32"
        )
    return result


def _coerce_quantiles(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce quantile table and verify monotonic finite bands where present."""
    result = frame.copy()
    for column in ("dataset", "variable", "season"):
        result[column] = result[column].astype("string")
    result["hour"] = result["hour"].astype("int32")
    result["sample_count"] = result["sample_count"].astype("int32")
    numeric = ("mean", "q025", "q10", "q25", "q50", "q75", "q90", "q975")
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float32"
        )
    ordered = result[["q025", "q10", "q25", "q50", "q75", "q90", "q975"]]
    finite = ordered.notna().all(axis=1)
    if finite.any() and (ordered.loc[finite].diff(axis=1).iloc[:, 1:] < 0).any().any():
        raise ValueError("Quantile bands must be non-decreasing")
    return result


def save_hourly_quantiles(
    frame: pd.DataFrame,
    out: Path | str = DEFAULT_HOURLY_QUANTILES_PATH,
    *,
    source_hash: str,
    source_path: Path | str | None = None,
) -> Path:
    """Build and save the T0201 empirical hourly quantile artifact."""
    bands = build_quantile_bands(frame)
    metadata = metadata_bytes(
        "hourly_quantiles",
        dataset_names(bands),
        source_hash,
        {
            "season_convention": SEASON_CONVENTION,
            "variables": list(ANALYSIS_VARIABLES),
            "quantile_method": "pandas_default_linear",
            "bands": {"iqr": ["q25", "q75"], "80": ["q10", "q90"], "95": ["q025", "q975"]},
        },
        {"rows": len(bands), "empty_bins": int(bands["sample_count"].eq(0).sum())},
    )
    table = pa.Table.from_pandas(
        bands, schema=QUANTILE_SCHEMA, preserve_index=False, safe=True,
    ).replace_schema_metadata(metadata)
    return atomic_write_parquet(table, out, source_path)


def export_load_profiling_artifacts(
    input_path: Path | str = DEFAULT_FEATURE_PATH,
    out_dir: Path | str = DEFAULT_HOURLY_QUANTILES_PATH.parent,
) -> dict[str, str]:
    """Export the T0201 artifact named in the current project charter."""
    set_seed(SEED)
    source = Path(input_path)
    frame = load_feature_input(source)
    digest = file_sha256(source)
    directory = Path(out_dir)
    quantile_path = save_hourly_quantiles(
        frame, directory / DEFAULT_HOURLY_QUANTILES_PATH.name,
        source_hash=digest, source_path=source,
    )
    return {
        "hourly_quantiles": str(quantile_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for T0201 offline artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_HOURLY_QUANTILES_PATH.parent)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export_load_profiling_artifacts(args.input, args.out)))
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Load profiling export failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
