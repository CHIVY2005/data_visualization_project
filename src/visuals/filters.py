"""Shared read-only filter semantics; reference aggregates retain their scope."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class FilterState:
    dataset: str
    season: str | None
    start: pd.Timestamp
    end: pd.Timestamp  # exclusive


def filter_features(frame: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    """Filter all observed samples with a single half-open scope."""
    mask = (frame.dataset.eq(state.dataset) & frame.timestamp.ge(state.start) &
            frame.timestamp.lt(state.end))
    if state.season:
        mask &= frame.season.eq(state.season)
    return frame.loc[mask].copy()


def filter_events(
    events: pd.DataFrame, state: FilterState, features: pd.DataFrame,
) -> pd.DataFrame:
    """Include only complete events supported inside scope, never prorate DH.

    Partial boundary events are excluded, explicitly surfaced by the caller.
    Exact clipping/reintegration requires an offline window-specific artifact.
    """
    candidates = events.loc[
        events.dataset.eq(state.dataset) & events.start_timestamp.ge(state.start) &
        events.end_timestamp.le(state.end)
    ]
    selected = filter_features(features, state)
    supported = set(selected.timestamp)
    rows = []
    for index, event in candidates.iterrows():
        dataset_samples = features.loc[
            features.dataset.eq(state.dataset) &
            features.timestamp.ge(event.start_timestamp) &
            features.timestamp.lt(event.end_timestamp)]
        if len(dataset_samples) and set(dataset_samples.timestamp).issubset(supported):
            rows.append(index)
    return candidates.loc[rows].copy()


def filter_profiles(frame: pd.DataFrame, state: FilterState) -> pd.DataFrame:
    """Filter timestamped STL and season-specific historical profile references."""
    mask = frame.dataset.eq(state.dataset)
    if "record_type" in frame:
        mask &= (frame.record_type.eq("profile") |
                 (frame.timestamp.ge(state.start) & frame.timestamp.lt(state.end)))
    if state.season:
        # STL season is null by canonical contract: derive a lightweight month bin.
        seasons = frame.timestamp.dt.month.isin([11, 12, 1, 2, 3, 4]).map(
            {True: "Dry", False: "Wet"})
        mask &= (frame.season.eq(state.season) |
                 (frame.timestamp.notna() & seasons.eq(state.season)))
    return frame.loc[mask].copy()