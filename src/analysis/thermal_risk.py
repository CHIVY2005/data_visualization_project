"""T0203: thermal breach events and load Z-scores at event centers."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
from statsmodels.nonparametric.smoothers_lowess import lowess

from src.analysis.common import (
    atomic_write_parquet,
    dataset_names,
    file_sha256,
    load_feature_input,
    metadata_bytes,
    set_seed,
)
from src.data.constants import (
    CADENCE_MINUTES,
    CRITICAL_TEMP_THRESHOLD,
    DEFAULT_BREACH_EVENTS_PATH,
    DEFAULT_FEATURE_PATH,
    DEFAULT_LOESS_PATH,
    LOAD_BRANCHES,
    LOESS_FRAC,
    LOESS_GRID_POINTS,
    LOESS_ITERATIONS,
    LOESS_MIN_SAMPLES,
    LOESS_REGIMES,
    WARNING_TEMP_THRESHOLD,
)
from src.data.feature_builder import build_grid_features

ZSCORE_COLUMNS = tuple(f"{variable}_z_score" for variable in LOAD_BRANCHES)
LOESS_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("load_feature", pa.string(), nullable=False),
    pa.field("scope_type", pa.string(), nullable=False),
    pa.field("scope_value", pa.string(), nullable=False),
    pa.field("x_load", pa.float32(), nullable=False),
    pa.field("y_ot_smooth", pa.float32(), nullable=False),
    pa.field("sample_count", pa.int32(), nullable=False),
])


def compute_loess_curves(
    df: pd.DataFrame, frac: float = LOESS_FRAC,
    n_grid: int = LOESS_GRID_POINTS,
) -> pd.DataFrame:
    """Fit six independent load–OT LOWESS references offline on finite pairs.

    Scopes are separate all/season/regime views, not season×regime fits.
    Full observations (including repeated loads) enter each fit. Only the
    resulting coordinates are interpolated to a compact evenly spaced grid.
    """
    if not np.isfinite(frac) or not 0 < frac <= 1:
        raise ValueError("frac must be finite and in (0, 1]")
    if type(n_grid) is not int or not 100 <= n_grid <= 200:
        raise ValueError("n_grid must be an integer between 100 and 200")
    set_seed()
    features = build_grid_features(df)
    rows: list[dict[str, object]] = []
    for dataset, group in features.groupby("dataset", sort=True):
        scopes: list[tuple[str, str, pd.DataFrame]] = [("all", "ALL", group)]
        scopes.extend(("season", str(season), sub) for season, sub in
                      group.groupby("season", sort=True))
        scopes.extend(("thermal_regime", regime,
                       group.loc[group.thermal_regime.eq(regime)])
                      for regime in LOESS_REGIMES)
        for scope_type, scope_value, subset in scopes:
            for variable in LOAD_BRANCHES:
                pairs = subset[[variable, "OT"]].replace(
                    [np.inf, -np.inf], np.nan,
                ).dropna().astype("float64").sort_values(
                    [variable, "OT"], kind="stable",
                )
                if (len(pairs) < LOESS_MIN_SAMPLES or
                        pairs[variable].nunique() < 2 or pairs.OT.nunique() < 2):
                    continue
                curve = lowess(
                    endog=pairs.OT.to_numpy(), exog=pairs[variable].to_numpy(),
                    frac=frac, it=LOESS_ITERATIONS, return_sorted=True,
                )
                if not np.isfinite(curve).all():
                    continue
                # Repeated x values remain weighted in fitting, not interpolation.
                knots = pd.DataFrame(curve, columns=["x", "y"]).groupby(
                    "x", sort=True,
                ).y.mean()
                grid = np.linspace(knots.index.min(), knots.index.max(), n_grid)
                smooth = np.interp(grid, knots.index.to_numpy(), knots.to_numpy())
                grid32, smooth32 = grid.astype("float32"), smooth.astype("float32")
                if not (np.isfinite(grid32).all() and np.isfinite(smooth32).all()):
                    continue
                for x, y in zip(grid32, smooth32):
                    rows.append({
                        "dataset": str(dataset), "load_feature": variable,
                        "scope_type": scope_type, "scope_value": scope_value,
                        "x_load": x, "y_ot_smooth": y,
                        "sample_count": len(pairs),
                    })
    return pd.DataFrame(rows, columns=LOESS_SCHEMA.names).astype({
        "dataset": "string", "load_feature": "string", "scope_type": "string",
        "scope_value": "string", "x_load": "float32",
        "y_ot_smooth": "float32", "sample_count": "int32",
    })


def save_loess_curves(
    frame: pd.DataFrame, out: Path | str = DEFAULT_LOESS_PATH, *,
    source_hash: str, source_path: Path | str | None = None,
    frac: float = LOESS_FRAC, n_grid: int = LOESS_GRID_POINTS,
) -> Path:
    """Atomically export the T0204 seven-column contract with provenance."""
    curves = compute_loess_curves(frame, frac, n_grid)
    metadata = metadata_bytes(
        "loess_curves", dataset_names(frame), source_hash,
        {"frac": frac, "it": LOESS_ITERATIONS, "grid_points": n_grid,
         "min_samples": LOESS_MIN_SAMPLES, "fit_sampling": "all_finite_pairs",
         "scope_types": ["all", "season", "thermal_regime"],
         "reference_scope": "historical_not_date_range_refit",
         "zero_variance_policy": "skip_constant_load_or_ot",
         "grid_policy": "linear_interpolation_of_mean_fitted_y_at_duplicate_x"},
        {"rows": len(curves),
         "valid_groups": len(curves) // n_grid,
         "unsupported_policy": "omit_groups_with_insufficient_or_nonfinite_fit"},
    )
    table = pa.Table.from_pandas(
        curves, schema=LOESS_SCHEMA, preserve_index=False, safe=True,
    ).replace_schema_metadata(metadata)
    return atomic_write_parquet(table, out, source_path)


THERMAL_BREACH_SCHEMA = pa.schema([
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("event_id", pa.string(), nullable=False),
    pa.field("threshold_c", pa.float32(), nullable=False),
    pa.field("thermal_regime", pa.string(), nullable=False),
    pa.field("start_timestamp", pa.timestamp("ns"), nullable=False),
    pa.field("end_timestamp", pa.timestamp("ns"), nullable=False),
    pa.field("duration_hours", pa.float32(), nullable=False),
    pa.field("peak_ot", pa.float32(), nullable=False),
    pa.field("degree_hours", pa.float32(), nullable=False),
    pa.field("sample_count", pa.int32(), nullable=False),
    pa.field("is_right_censored", pa.bool_(), nullable=False),
])


@dataclass(frozen=True)
class _OpenEvent:
    """Mutable-free container for one candidate breach interval."""

    rows: tuple[int, ...]
    censored: bool


def _threshold_regime(threshold: float) -> str:
    """Map project threshold to the display regime name."""
    if threshold >= CRITICAL_TEMP_THRESHOLD:
        return "Critical"
    if threshold >= WARNING_TEMP_THRESHOLD:
        return "Warning"
    raise ValueError("Unsupported threshold")


def _zscore_lookup(
    dataset_frame: pd.DataFrame, load_variables: Sequence[str] = LOAD_BRANCHES,
) -> pd.DataFrame:
    """Compute dataset-level load Z-scores without altering source units."""
    scores = dataset_frame[["timestamp"]].copy()
    for variable in load_variables:
        values = pd.to_numeric(dataset_frame[variable], errors="coerce").astype(
            "float64"
        )
        std = values.std(ddof=1)
        if pd.isna(std) or std == 0:
            scores[f"{variable}_z_score"] = np.nan
        else:
            scores[f"{variable}_z_score"] = (values - values.mean()) / std
    return scores


def _center_timestamp(event_frame: pd.DataFrame) -> pd.Timestamp:
    """Choose the observed timestamp nearest the event midpoint."""
    start = event_frame["timestamp"].iloc[0]
    end = event_frame["timestamp"].iloc[-1]
    midpoint = start + (end - start) / 2
    distances = (event_frame["timestamp"] - midpoint).abs()
    return event_frame.loc[distances.idxmin(), "timestamp"]


def _iter_breach_events(
    dataset_frame: pd.DataFrame, threshold: float,
) -> list[_OpenEvent]:
    """Segment breaches; below-threshold closes, gap/missing censors."""
    cadence = pd.Timedelta(minutes=CADENCE_MINUTES[str(dataset_frame["dataset"].iloc[0])])
    rows: list[int] = []
    events: list[_OpenEvent] = []
    previous_time: pd.Timestamp | None = None
    for index, row in dataset_frame.iterrows():
        timestamp = row["timestamp"]
        ot = pd.to_numeric(row["OT"], errors="coerce")
        gap = previous_time is not None and timestamp - previous_time != cadence
        missing = pd.isna(ot) or not np.isfinite(ot)
        breach = (not missing) and float(ot) >= threshold
        if rows and (gap or missing):
            events.append(_OpenEvent(tuple(rows), True))
            rows = []
        if breach:
            rows.append(int(index))
        elif rows:
            events.append(_OpenEvent(tuple(rows), False))
            rows = []
        previous_time = timestamp
    if rows:
        events.append(_OpenEvent(tuple(rows), True))
    return events


def build_thermal_breach_events(
    frame: pd.DataFrame,
    thresholds: Sequence[float] = (WARNING_TEMP_THRESHOLD, CRITICAL_TEMP_THRESHOLD),
) -> pd.DataFrame:
    """Return breach intervals with degree-hours and event-center load Z-scores."""
    set_seed()
    features = build_grid_features(frame)
    rows: list[dict[str, object]] = []
    for dataset, dataset_frame in features.groupby("dataset", sort=True):
        ordered = dataset_frame.sort_values("timestamp", kind="stable").reset_index(
            drop=True
        )
        cadence_hours = CADENCE_MINUTES[str(dataset)] / 60.0
        zscores = _zscore_lookup(ordered)
        for threshold in thresholds:
            regime = _threshold_regime(float(threshold))
            for number, event in enumerate(_iter_breach_events(ordered, threshold), 1):
                event_frame = ordered.loc[list(event.rows)]
                # A left-held sample has support only if the next finite OT
                # observation is exactly one cadence away. Never extrapolate.
                supported = []
                for index in event.rows:
                    if index + 1 >= len(ordered):
                        continue
                    nxt = ordered.iloc[index + 1]
                    if (nxt.timestamp - ordered.iloc[index].timestamp ==
                            pd.Timedelta(hours=cadence_hours)
                            and pd.notna(nxt.OT) and np.isfinite(nxt.OT)):
                        supported.append(index)
                if not supported:
                    continue
                support_frame = ordered.loc[supported]
                end_timestamp = support_frame.timestamp.iloc[-1] + pd.Timedelta(
                    hours=cadence_hours)
                degree_hours = (
                    pd.to_numeric(support_frame["OT"], errors="coerce") - threshold
                ).clip(lower=0).sum() * cadence_hours
                item: dict[str, object] = {
                    "dataset": str(dataset),
                    "event_id": f"{dataset}-{regime.lower()}-{number:04d}",
                    "threshold_c": np.float32(threshold),
                    "thermal_regime": regime,
                    "start_timestamp": event_frame["timestamp"].iloc[0],
                    "end_timestamp": end_timestamp,
                    "duration_hours": np.float32(len(support_frame) * cadence_hours),
                    "peak_ot": np.float32(event_frame["OT"].max()),
                    "degree_hours": np.float32(degree_hours),
                    "sample_count": int(len(support_frame)),
                    "is_right_censored": bool(event.censored),
                }
                rows.append(item)
    return _coerce_events(pd.DataFrame(rows, columns=THERMAL_BREACH_SCHEMA.names))


def _coerce_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce empty and non-empty event tables to the exact schema dtypes."""
    result = frame.copy()
    for column in ("dataset", "event_id", "thermal_regime"):
        result[column] = result[column].astype("string")
    for column in ("start_timestamp", "end_timestamp"):
        result[column] = pd.to_datetime(result[column]).astype("datetime64[ns]")
    for column in (
        "threshold_c", "duration_hours", "peak_ot", "degree_hours",
    ):
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float32"
        )
    result["sample_count"] = result["sample_count"].fillna(0).astype("int32")
    result["is_right_censored"] = result["is_right_censored"].fillna(False).astype(bool)
    if not result.empty:
        if (result["duration_hours"] <= 0).any():
            raise ValueError("Thermal event duration must be positive")
        if (result["peak_ot"] < result["threshold_c"]).any():
            raise ValueError("Thermal event peak must meet threshold")
        if (result["degree_hours"] < 0).any():
            raise ValueError("Thermal event degree-hours must be non-negative")
    return result


def save_thermal_breach_events(
    frame: pd.DataFrame,
    out: Path | str = DEFAULT_BREACH_EVENTS_PATH,
    *,
    source_hash: str,
    source_path: Path | str | None = None,
) -> Path:
    """Build and save the canonical thermal_breach_events.parquet artifact."""
    events = build_thermal_breach_events(frame)
    metadata = metadata_bytes(
        "thermal_breach_events",
        dataset_names(frame),
        source_hash,
        {
            "thresholds_c": [WARNING_TEMP_THRESHOLD, CRITICAL_TEMP_THRESHOLD],
            "degree_hours": "sum(max(OT-threshold,0) * cadence_hours)",
            "support_policy": "next_finite_observation_exact_cadence_no_extrapolation",
        },
        {
            "rows": len(events),
            "critical_events": int(events["thermal_regime"].eq("Critical").sum()),
            "warning_events": int(events["thermal_regime"].eq("Warning").sum()),
        },
    )
    table = pa.Table.from_pandas(
        events, schema=THERMAL_BREACH_SCHEMA, preserve_index=False, safe=True,
    ).replace_schema_metadata(metadata)
    return atomic_write_parquet(table, out, source_path)


def export_thermal_risk_artifact(
    input_path: Path | str = DEFAULT_FEATURE_PATH,
    out: Path | str = DEFAULT_BREACH_EVENTS_PATH,
) -> dict[str, str]:
    """Export thermal breach events from a clean/features source path."""
    set_seed()
    source = Path(input_path)
    frame = load_feature_input(source)
    output = save_thermal_breach_events(
        frame, out, source_hash=file_sha256(source), source_path=source,
    )
    return {"breach_events": str(output)}


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for T0203 thermal-risk artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_BREACH_EVENTS_PATH)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(export_thermal_risk_artifact(args.input, args.out)))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Thermal risk export failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
