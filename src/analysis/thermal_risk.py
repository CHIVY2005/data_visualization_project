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
    LOAD_BRANCHES,
    WARNING_TEMP_THRESHOLD,
)
from src.data.feature_builder import build_grid_features

ZSCORE_COLUMNS = tuple(f"{variable}_z_score" for variable in LOAD_BRANCHES)
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
    """Build and save the T0203 breach_events.parquet artifact."""
    events = build_thermal_breach_events(frame)
    metadata = metadata_bytes(
        "thermal_breach_events",
        dataset_names(events) if not events.empty else dataset_names(build_grid_features(frame)),
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
