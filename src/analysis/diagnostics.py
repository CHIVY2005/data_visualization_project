"""Offline diagnostic contracts: window-specific LOESS and event Z-scores."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
from statsmodels.nonparametric.smoothers_lowess import lowess

from src.analysis.common import atomic_write_parquet, dataset_names, metadata_bytes
from src.data.constants import LOAD_BRANCHES

LOESS_SCHEMA = pa.schema([
    pa.field("dataset", pa.string()), pa.field("season", pa.string()),
    pa.field("load_variable", pa.string()), pa.field("load_value", pa.float32()),
    pa.field("loess_ot", pa.float32()), pa.field("sample_count", pa.int32()),
    pa.field("start_timestamp", pa.timestamp("ns")),
    pa.field("end_timestamp", pa.timestamp("ns")),
])


def save_diagnostics(
    frame: pd.DataFrame, events: pd.DataFrame, out_dir: Path, *,
    source_hash: str, source_path: Path,
) -> dict[str, Path]:
    """Fit full-history/season curves outside UI; no refit after date filtering.

    LOESS is explicitly a historical reference for its saved support window.
    Z-scores use event support samples versus dataset mean/std (ddof=1),
    not a causal score. Constant/insufficient branches remain null.
    """
    rows = []
    zrows = []
    for dataset, group in frame.groupby("dataset", sort=True):
        for season in ["All", *sorted(group.season.unique())]:
            sub = group if season == "All" else group.loc[group.season.eq(season)]
            for variable in LOAD_BRANCHES:
                pairs = sub[[variable, "OT"]].replace(
                    [np.inf, -np.inf], np.nan).dropna().sort_values(variable)
                if len(pairs) < 3 or pairs[variable].nunique() < 2:
                    continue
                # Deterministic representative fit, then fixed grid reduction.
                sampled = pairs.iloc[np.linspace(
                    0, len(pairs) - 1, min(1000, len(pairs)), dtype=int)]
                curve = lowess(sampled.OT, sampled[variable], frac=0.3,
                               return_sorted=True)
                curve = curve[np.linspace(0, len(curve) - 1,
                                          min(200, len(curve)), dtype=int)]
                for x, y in curve:
                    rows.append({"dataset": dataset, "season": season,
                                 "load_variable": variable, "load_value": x,
                                 "loess_ot": y, "sample_count": len(pairs),
                                 "start_timestamp": sub.timestamp.min(),
                                 "end_timestamp": sub.timestamp.max()})
        for event in events.loc[events.dataset.eq(dataset)].itertuples():
            support = group.loc[group.timestamp.ge(event.start_timestamp) &
                                group.timestamp.lt(event.end_timestamp)]
            for variable in LOAD_BRANCHES:
                std = group[variable].std(ddof=1)
                score = ((support[variable].mean() - group[variable].mean()) / std
                         if pd.notna(std) and std > 0 else np.nan)
                zrows.append({"dataset": dataset, "event_id": event.event_id,
                              "load_variable": variable, "z_score": score})
    loess = pd.DataFrame(rows, columns=LOESS_SCHEMA.names)
    zschema = pa.schema([
        pa.field("dataset", pa.string()), pa.field("event_id", pa.string()),
        pa.field("load_variable", pa.string()), pa.field("z_score", pa.float32()),
    ])
    outputs = {}
    for name, data, schema in (
        ("loess_curves", loess, LOESS_SCHEMA),
        ("event_load_zscores", pd.DataFrame(zrows, columns=zschema.names), zschema),
    ):
        metadata = metadata_bytes(name, dataset_names(frame), source_hash,
                                  {"loess_frac": 0.3, "max_fit_samples": 1000,
                                   "reference_scope": "saved_full_history_or_season",
                                   "zscore": "event_mean_vs_dataset_mean_std_ddof1"},
                                  {"rows": len(data)})
        table = pa.Table.from_pandas(data, schema=schema, preserve_index=False)
        outputs[name] = atomic_write_parquet(
            table.replace_schema_metadata(metadata), out_dir / f"{name}.parquet",
            source_path)
    return outputs