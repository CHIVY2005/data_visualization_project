"""Approved T0501 foundation: one composition root, read-only versioned artifacts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data.constants import ARTIFACTS_DIR, DEFAULT_FEATURE_PATH
from src.visuals import (
    build_calendar_heatmap, build_stl_panels, build_quantile_fan,
    build_stacked_bar, build_lag_heatmap, compute_manager_kpis,
    build_ot_threshold_chart, build_barcode_rug, build_small_multiples,
    build_scatter_loess, build_regime_boxplots, compute_safety_kpis,
)
from src.visuals.filters import (
    FilterState, filter_features, filter_events, filter_profiles,
)


def artifact_version(path: Path) -> tuple[int, int]:
    """Use nanosecond mtime and size; distinct paths remain distinct cache keys."""
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


@st.cache_data(show_spinner=False)
def load_parquet(path: str, mtime: tuple[int, int]) -> pd.DataFrame:
    """No underscore args: source identity/version participates in hashing."""
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def load_stl(path: str, mtime: tuple[int, int]) -> pd.DataFrame:
    """Read the exact file, not the parent of its artifact directory."""
    return pd.read_parquet(path)


def read_artifact(path: Path, *, stl: bool = False) -> pd.DataFrame | None:
    if not path.is_file():
        st.warning(f"Missing artifact: {path.name}; run the offline engine")
        return None
    loader = load_stl if stl else load_parquet
    return loader(str(path.resolve()), artifact_version(path))


def metric_value(value: float | int | None) -> str:
    return "N/A" if value is None or pd.isna(value) else f"{value:,.2f}"


def render_story1(
    features: pd.DataFrame, profiles: pd.DataFrame | None,
    bands: pd.DataFrame | None, lag: pd.DataFrame | None, state: FilterState,
    variable: str, view: str,
) -> None:
    """Render only the selected analytical view; no eager hidden tab work."""
    kpis = compute_manager_kpis(features)
    cols = st.columns(3)
    for col, key in zip(cols, ("ot_mean", "ot_max", "warn_pct")):
        col.metric(key, metric_value(kpis[key]))
    if features.empty:
        st.info("No observed samples in the selected scope (Unknown, not zero)")
        return
    if view == "Calendar":
        st.plotly_chart(build_calendar_heatmap(features, variable=variable), width="stretch")
    elif view == "STL" and profiles is not None:
        selected = filter_profiles(profiles, state)
        selected = selected.loc[selected.record_type.eq("stl") &
                                selected.variable.eq(variable)]
        if selected.empty:
            st.info("No fitted STL samples in scope")
        else:
            st.plotly_chart(build_stl_panels(selected, variable=variable), width="stretch")
    elif view == "Historical Fan" and bands is not None:
        st.caption("Historical season reference; not recomputed for Date Range")
        seasons = [state.season] if state.season else sorted(bands.season.unique())
        for season in seasons:
            st.plotly_chart(build_quantile_fan(
                bands, dataset=state.dataset, variable=variable, season=season),
                width="stretch")
    elif view == "Composition":
        st.plotly_chart(build_stacked_bar(features), width="stretch")
    elif view == "Historical Lag" and lag is not None:
        st.caption("Historical season reference; not recomputed for Date Range")
        seasons = [state.season] if state.season else sorted(lag.season.unique())
        for season in seasons:
            st.plotly_chart(build_lag_heatmap(
                lag, dataset=state.dataset, season=season), width="stretch")


def render_story2(
    features: pd.DataFrame, events: pd.DataFrame | None,
    curves: pd.DataFrame | None, state: FilterState, variable: str, view: str,
) -> None:
    metrics = compute_safety_kpis(features, events)
    cols = st.columns(5)
    for col, key in zip(cols, ("max_ot", "warning_degree_hours",
                              "critical_degree_hours", "warning_duration_hours",
                              "critical_duration_hours")):
        col.metric(key, metric_value(metrics[key]))
    st.caption("Threshold metrics are separate. Boundary-crossing events excluded; no prorating.")
    if features.empty:
        st.info("No samples in selected scope")
        return
    if events is not None and events.empty:
        st.info("No complete observed breach events in scope")
    if view == "OT / Events":
        st.plotly_chart(build_ot_threshold_chart(features, events), width="stretch")
        st.plotly_chart(build_barcode_rug(events), width="stretch")
    elif view == "Small Multiples":
        st.plotly_chart(build_small_multiples(features, events), width="stretch")
    elif view == "Historical LOESS":
        reference = None
        if curves is not None:
            reference = curves.loc[
                curves.dataset.eq(state.dataset) & curves.load_variable.eq(variable) &
                curves.season.eq(state.season or "All")]
        st.caption("LOESS is a saved full-history/season reference, not a Date Range refit")
        st.plotly_chart(build_scatter_loess(
            features, load_variable=variable, loess_df=reference), width="stretch")
    elif view == "Regime Boxplots":
        st.plotly_chart(build_regime_boxplots(features), width="stretch")


def main() -> None:
    st.set_page_config(page_title="ETT Grid Analytics", layout="wide")
    st.title("ETT Grid Visual Analytics v2.0")
    st.caption("Historical analysis, not live/certified safety monitoring. "
               "Thresholds 85/95°C are project conventions.")
    all_features = read_artifact(DEFAULT_FEATURE_PATH)
    if all_features is None:
        return
    dataset = st.sidebar.selectbox("Dataset", sorted(all_features.dataset.unique()))
    data = all_features.loc[all_features.dataset.eq(dataset)]
    season_value = st.sidebar.selectbox("Season", ["All", *sorted(data.season.unique())])
    start_date, end_date = data.timestamp.min().date(), data.timestamp.max().date()
    dates = st.sidebar.date_input("Date Range", (start_date, end_date),
                                  min_value=start_date, max_value=end_date,
                                  key=f"dates_{dataset}")
    if len(dates) != 2:
        st.info("Select both start and end dates")
        return
    state = FilterState(dataset, None if season_value == "All" else season_value,
                        pd.Timestamp(dates[0]), pd.Timestamp(dates[1]) + pd.Timedelta(days=1))
    features = filter_features(all_features, state)
    story = st.sidebar.radio("Story", ["Story 1", "Story 2"])
    variable = st.sidebar.selectbox(
        "Variable", ["OT", "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL"])
    if story == "Story 1":
        view = st.sidebar.selectbox("View", [
            "Calendar", "STL", "Historical Fan", "Composition", "Historical Lag"])
        profiles = (read_artifact(ARTIFACTS_DIR / "load_profiles_stl.parquet", stl=True)
                    if view == "STL" else None)
        bands = (read_artifact(ARTIFACTS_DIR / "quantile_bands.parquet")
                 if view == "Historical Fan" else None)
        lag = (read_artifact(ARTIFACTS_DIR / "lag_matrix.parquet")
               if view == "Historical Lag" else None)
        render_story1(features, profiles, bands, lag, state, variable, view)
    else:
        view = st.sidebar.selectbox("View", [
            "OT / Events", "Small Multiples", "Historical LOESS", "Regime Boxplots"])
        events = read_artifact(ARTIFACTS_DIR / "thermal_breach_events.parquet")
        if events is not None:
            events = filter_events(events, state, all_features)
        curves = (read_artifact(ARTIFACTS_DIR / "loess_curves.parquet")
                  if view == "Historical LOESS" else None)
        render_story2(features, events, curves, state,
                      variable if variable != "OT" else "HUFL", view)


if __name__ == "__main__":
    main()