"""Offline T0204 LOESS export delegation and event Z-score diagnostics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from src.analysis.common import atomic_write_parquet, dataset_names, metadata_bytes
from src.data.constants import LOAD_BRANCHES
from src.analysis.thermal_risk import save_loess_curves


def save_diagnostics(
    frame: pd.DataFrame, events: pd.DataFrame, out_dir: Path, *,
    source_hash: str, source_path: Path,
    include_loess: bool = True,
) -> dict[str, Path]:
    """Delegate T0204 reference fitting, unless already exported by the engine.

    LOESS scopes are historical references, never date-filtered refits.
    Z-scores use event support samples versus dataset mean/std (ddof=1),
    not a causal score. Constant/insufficient branches remain null.
    """
    zrows = []
    for dataset, group in frame.groupby("dataset", sort=True):
        for event in events.loc[events.dataset.eq(dataset)].itertuples():
            support = group.loc[group.timestamp.ge(event.start_timestamp) &
                                group.timestamp.lt(event.end_timestamp)]
            for variable in LOAD_BRANCHES:
                std = group[variable].std(ddof=1)
                score = ((support[variable].mean() - group[variable].mean()) / std
                         if pd.notna(std) and std > 0 else np.nan)
                zrows.append({"dataset": dataset, "event_id": event.event_id,
                              "load_variable": variable, "z_score": score})
    zschema = pa.schema([
        pa.field("dataset", pa.string()), pa.field("event_id", pa.string()),
        pa.field("load_variable", pa.string()), pa.field("z_score", pa.float32()),
    ])
    outputs = {}
    if include_loess:
        outputs["loess_curves"] = save_loess_curves(
            frame, out_dir / "loess_curves.parquet",
            source_hash=source_hash, source_path=source_path,
        )
    for name, data, schema in (
        ("event_load_zscores", pd.DataFrame(zrows, columns=zschema.names), zschema),
    ):
        metadata = metadata_bytes(name, dataset_names(frame), source_hash,
                                  {"zscore": "event_mean_vs_dataset_mean_std_ddof1"},
                                  {"rows": len(data)})
        table = pa.Table.from_pandas(data, schema=schema, preserve_index=False)
        outputs[name] = atomic_write_parquet(
            table.replace_schema_metadata(metadata), out_dir / f"{name}.parquet",
            source_path)
    return outputs