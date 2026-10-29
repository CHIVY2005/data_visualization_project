"""Light, gap-preserving slices for Plotly lines (no statistical computation)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.data.constants import CADENCE_MINUTES, MEASUREMENTS


def gap_preserving_frame(frame: pd.DataFrame, max_points: int = 4000) -> pd.DataFrame:
    """Downsample within contiguous segments; retain null and temporal breaks."""
    result = frame.dropna(subset=["timestamp"]).sort_values("timestamp").copy()
    if result.empty:
        return result
    datasets = result.dataset.unique() if "dataset" in result else ["ETTh1"]
    if len(datasets) != 1:
        raise ValueError("Select exactly one dataset for a time-series chart")
    cadence = pd.Timedelta(minutes=CADENCE_MINUTES[str(datasets[0])])
    numeric = result.select_dtypes(include="number").columns
    measured = [column for column in MEASUREMENTS if column in result]
    invalid = result[measured].isna().any(axis=1)
    gap = result.timestamp.diff().ne(cadence)
    segment = (gap | invalid | invalid.shift(fill_value=False)).cumsum()
    pieces = []
    stride = max(1, int(np.ceil(len(result) / max_points)))
    for _, group in result.groupby(segment, sort=False):
        selected = group.iloc[::stride]
        if group.index[-1] not in selected.index:
            selected = pd.concat([selected, group.iloc[[-1]]])
        if pieces:
            separator = group.iloc[[0]].copy()
            separator[numeric] = np.nan
            pieces.append(separator)
        pieces.append(selected)
    return pd.concat(pieces, ignore_index=True)