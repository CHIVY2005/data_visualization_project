"""T0501 — App Integration & Composition Root.

ETT Power Grid Visual Analytics Dashboard v2.0
Serves two User Stories from pre-computed Parquet/JSON artifacts only.

Story 1 (WP03 — Operational Manager — US-01):
    Calendar Heatmap · STL Panels · Hourly Quantile Fan
    100% Stacked Bar · Lag Cross-Correlation Heatmap

Story 2 (WP04 — Safety & Risk Monitor — US-02):
    OT Threshold Line/Shading · Barcode/Rug · Synchronized Small Multiples
    Joint Scatter + LOESS · Thermal Regime Boxplots

UI contract [STRICT:DECOUPLE]:
- Single st.set_page_config call inside main(); no side-effects on import.
- Reads only pre-computed Parquet/JSON artifacts; zero STL/quantile/lag/LOESS
  computation in the render path.
- Light slicing (filter by dataset, season, date range) is permitted.
- Artifact loaders cache by (str path, mtime_ns, size) — cache invalidates
  automatically when the offline engine regenerates a file.
- Dataset options are derived from actual artifact content, never hardcoded.
- Fan/lag/LOESS are full-history/season references; not recomputed for Date Range.
- Events: only complete events fully inside the selected scope are included;
  boundary-crossing events are excluded with a caption, no pro-rating of DH.
- Target SLA: load/render/filter < 2 s on representative data (not yet measured
  for all configs; cold-start depends on artifact sizes and machine).

Governance [AGENTS v2.0]:
- Thresholds 85/95°C are project analysis conventions, not certified standards.
- This dashboard is a historical analytics tool, not live/certified safety monitoring.
- SEED = 2026 (used by offline engine; not needed in UI).
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import streamlit as st

from src.data.constants import (
    ARTIFACTS_DIR,
    DEFAULT_FEATURE_PATH,
    LOAD_BRANCHES,
    MEASUREMENTS,
)
from src.visuals import (
    build_calendar_heatmap,
    build_lag_heatmap,
    build_quantile_fan,
    build_regime_boxplots,
    build_scatter_loess,
    build_small_multiples,
    build_stacked_bar,
    build_stl_panels,
    build_barcode_rug,
    build_ot_threshold_chart,
    compute_manager_kpis,
    compute_safety_kpis,
)
from src.visuals.action_titles import (
    TitleContext,
    build_context,
    calendar_heatmap_title,
    stl_title,
    quantile_fan_title,
    stacked_bar_title,
    lag_heatmap_title,
    ot_threshold_title,
    barcode_rug_title,
    small_multiples_title,
    loess_scatter_title,
    regime_boxplots_title,
)
from src.visuals.filters import (
    FilterState,
    filter_events,
    filter_features,
    filter_profiles,
)

# ---------------------------------------------------------------------------
# Artifact paths (canonical names per AGENTS v2.0)
# ---------------------------------------------------------------------------

_PATH_FEATURES = DEFAULT_FEATURE_PATH
_PATH_STL = ARTIFACTS_DIR / "load_profiles_stl.parquet"
_PATH_QUANTILE_BANDS = ARTIFACTS_DIR / "quantile_bands.parquet"
_PATH_LAG_MATRIX = ARTIFACTS_DIR / "lag_matrix.parquet"
_PATH_EVENTS = ARTIFACTS_DIR / "thermal_breach_events.parquet"
_PATH_LOESS = ARTIFACTS_DIR / "loess_curves.parquet"

# ---------------------------------------------------------------------------
# Versioned artifact loaders — cached per (path, mtime_ns, size)
# ---------------------------------------------------------------------------


def _artifact_version(path: Path) -> tuple[int, int]:
    """Return (mtime_ns, size) as an immutable cache key."""
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return 0, 0


@st.cache_data(show_spinner=False)
def _load_parquet(path: str, version: tuple[int, int]) -> pd.DataFrame:
    """Cache by path identity and version; no underscore args (all participate in hashing)."""
    return pd.read_parquet(path)


@st.cache_data(show_spinner=False)
def _load_stl(path: str, version: tuple[int, int]) -> pd.DataFrame:
    """Dedicated loader for STL artifact to keep its own cache slot."""
    return pd.read_parquet(path)


def _read_artifact(
    path: Path,
    *,
    label: str = "",
    stl: bool = False,
    silent: bool = False,
) -> pd.DataFrame | None:
    """Load a pre-computed artifact with version-aware caching.

    Returns None when the file is absent or empty, with appropriate UI notice.
    Missing artifact is distinct from a valid empty artifact (e.g. zero breach events).
    """
    if not path.is_file():
        if not silent:
            name = label or path.name
            st.warning(
                f"⚠️ Artifact **{name}** not found — run the offline engine first: "
                "`python scripts/run_statistical_engine.py`",
                icon="📂",
            )
        return None
    version = _artifact_version(path)
    loader = _load_stl if stl else _load_parquet
    df = loader(str(path.resolve()), version)
    if df is None or df.empty:
        if not silent:
            st.info(f"ℹ️ Artifact **{label or path.name}** loaded but contains no rows.")
        return None
    return df


# ---------------------------------------------------------------------------
# Metric formatting helpers
# ---------------------------------------------------------------------------


def _fmt_float(value: float | int | None, decimals: int = 2, suffix: str = "") -> str:
    """Format a numeric metric; return 'N/A' for missing/NaN."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:,.{decimals}f}{suffix}"


def _fmt_int(value: int | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:,}"


# ---------------------------------------------------------------------------
# Story 1 — Operational Manager (US-01)
# ---------------------------------------------------------------------------

_STORY1_VIEWS = [
    "Calendar Heatmap",
    "STL Decomposition",
    "Historical Quantile Fan",
    "Load Composition",
    "Historical Lag Correlation",
]

_STORY1_VIEW_HINTS: dict[str, str] = {
    "Calendar Heatmap": "Daily-seasonal load cycle overview per variable.",
    "STL Decomposition": "Trend + seasonal + residual panels (windowed by date range).",
    "Historical Quantile Fan": (
        "Full-history empirical bands (50%/80%/95%) by season & hour. "
        "Not recomputed for the selected Date Range."
    ),
    "Load Composition": (
        "100% stacked bar: useful vs unuseful load share by hour (3 voltage tiers). "
        "Windowed by date range."
    ),
    "Historical Lag Correlation": (
        "Pearson cross-correlation r(load(t), OT(t+k)) for k=0..12 h. "
        "Full-history/season reference; not recomputed for Date Range."
    ),
}


def _render_story1_kpis(features: pd.DataFrame) -> None:
    kpis = compute_manager_kpis(features)
    _render_story1_kpis_from_dict(kpis)


def _render_story1_kpis_from_dict(kpis: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🌡️ OT Mean", _fmt_float(kpis.get("ot_mean"), suffix=" °C"))
    c2.metric("🔥 OT Max", _fmt_float(kpis.get("ot_max"), suffix=" °C"))
    c3.metric("⚠️ Warning Rate (≥85°C)", _fmt_float(kpis.get("warn_pct"), suffix=" %"))
    c4.metric("📊 Samples", _fmt_int(kpis.get("sample_count")))


def render_story1(
    features: pd.DataFrame,
    state: FilterState,
    variable: str,
    view: str,
) -> None:
    """Render only the selected analytical view; no eager hidden-tab computation."""
    st.subheader("📈 Story 1 — Operational Manager")
    kpis = compute_manager_kpis(features)
    _render_story1_kpis_from_dict(kpis)

    hint = _STORY1_VIEW_HINTS.get(view, "")
    if hint:
        st.caption(hint)

    if features.empty:
        st.info(
            "No observed samples in the selected scope — "
            "thermal regime and OT statistics are Unknown (not zero)."
        )
        return

    # Build shared title context (no events for Story 1)
    ctx = build_context(
        state.dataset, state.season, state.start, state.end,
        variable, len(features), manager_kpis=kpis,
    )

    if view == "Calendar Heatmap":
        st.markdown(f"##### {calendar_heatmap_title(ctx)}")
        fig = build_calendar_heatmap(
            features, variable=variable, dataset_label=state.dataset
        )
        st.plotly_chart(fig, use_container_width=True)

    elif view == "STL Decomposition":
        profiles = _read_artifact(_PATH_STL, label="load_profiles_stl", stl=True)
        if profiles is not None:
            selected = filter_profiles(profiles, state)
            selected = selected.loc[
                selected.record_type.eq("stl") & selected.variable.eq(variable)
            ]
            if selected.empty:
                st.info(
                    "No STL samples in the selected date scope for "
                    f"variable **{variable}**. Try widening the Date Range."
                )
            else:
                st.markdown(f"##### {stl_title(ctx)}")
                fig = build_stl_panels(
                    selected, variable=variable, dataset_label=state.dataset
                )
                st.plotly_chart(fig, use_container_width=True)

    elif view == "Historical Quantile Fan":
        bands = _read_artifact(_PATH_QUANTILE_BANDS, label="quantile_bands")
        if bands is not None:
            seasons = (
                [state.season] if state.season
                else sorted(bands.season.unique().tolist())
            )
            for season in seasons:
                fan_ctx = TitleContext(
                    dataset=state.dataset, season=season,
                    start=state.start, end=state.end,
                    variable=variable, n_samples=len(features),
                )
                st.markdown(f"##### {quantile_fan_title(fan_ctx)}")
                fig = build_quantile_fan(
                    bands, dataset=state.dataset, variable=variable,
                    season=season, dataset_label=state.dataset,
                )
                st.plotly_chart(fig, use_container_width=True)

    elif view == "Load Composition":
        st.markdown(f"##### {stacked_bar_title(ctx)}")
        fig = build_stacked_bar(
            features, season=state.season, dataset_label=state.dataset
        )
        st.plotly_chart(fig, use_container_width=True)

    elif view == "Historical Lag Correlation":
        lag = _read_artifact(_PATH_LAG_MATRIX, label="lag_matrix")
        if lag is not None:
            seasons = (
                [state.season] if state.season
                else sorted(lag.season.unique().tolist())
            )
            for season in seasons:
                lag_ctx = TitleContext(
                    dataset=state.dataset, season=season,
                    start=state.start, end=state.end,
                    variable=variable, n_samples=len(features),
                )
                st.markdown(f"##### {lag_heatmap_title(lag_ctx)}")
                fig = build_lag_heatmap(
                    lag, dataset=state.dataset, season=season,
                    dataset_label=state.dataset,
                )
                st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Story 2 — Safety & Risk Monitor (US-02)
# ---------------------------------------------------------------------------

_STORY2_VIEWS = [
    "OT Threshold & Events",
    "Synchronized Small Multiples",
    "Historical LOESS Scatter",
    "Thermal Regime Boxplots",
]

_STORY2_VIEW_HINTS: dict[str, str] = {
    "OT Threshold & Events": (
        "OT line with 85/95°C hazard shading + Barcode rug of thermal breach events "
        "fully inside the selected scope."
    ),
    "Synchronized Small Multiples": (
        "6 synchronized load-branch panels with breach event highlighting. "
        "Shared X-axis: zoom/pan applies to all subplots simultaneously."
    ),
    "Historical LOESS Scatter": (
        "Joint scatter (OT vs load branch) coloured by thermal regime + "
        "saved full-history LOESS reference curve. "
        "Not a Date Range refit — select a different branch via Variable."
    ),
    "Thermal Regime Boxplots": (
        "Distribution of a variable across Normal / Warning / Critical regimes "
        "in the selected scope."
    ),
}


def _render_story2_kpis(
    features: pd.DataFrame, events: pd.DataFrame | None
) -> None:
    metrics = compute_safety_kpis(features, events)
    _render_story2_kpis_from_dict(features, metrics)


def _render_story2_kpis_from_dict(
    features: pd.DataFrame, metrics: dict
) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🔥 OT Max", _fmt_float(metrics.get("max_ot"), suffix=" °C"))
    c2.metric("⚠️ Warning DH (≥85°C)", _fmt_float(metrics.get("warning_degree_hours"), suffix=" °C·h"))
    c3.metric("🚨 Critical DH (≥95°C)", _fmt_float(metrics.get("critical_degree_hours"), suffix=" °C·h"))
    c4.metric("⏱️ Warning Duration", _fmt_float(metrics.get("warning_duration_hours"), suffix=" h"))
    c5.metric("⏱️ Critical Duration", _fmt_float(metrics.get("critical_duration_hours"), suffix=" h"))
    st.caption(
        "Degree-Hours and Duration are per threshold (Warning ≥85°C / Critical ≥95°C) — "
        "not summed across thresholds. "
        "Only complete events fully inside the Date Range scope are counted; "
        "boundary-crossing events are excluded (no pro-rating of DH)."
    )


def render_story2(
    features: pd.DataFrame,
    all_features: pd.DataFrame,
    state: FilterState,
    variable: str,
    view: str,
) -> None:
    """Render only the selected analytical view; events loaded once, shared across sub-renders."""
    st.subheader("🛡️ Story 2 — Safety & Risk Monitor")

    events_raw = _read_artifact(_PATH_EVENTS, label="thermal_breach_events", silent=True)
    events: pd.DataFrame | None = None
    if events_raw is not None:
        events = filter_events(events_raw, state, all_features)
    elif not _PATH_EVENTS.is_file():
        st.warning(
            "⚠️ Thermal breach events artifact not found — run the offline engine: "
            "`python scripts/run_statistical_engine.py`",
            icon="📂",
        )

    _render_story2_kpis(features, events)

    hint = _STORY2_VIEW_HINTS.get(view, "")
    if hint:
        st.caption(hint)

    if features.empty:
        st.info("No samples in the selected scope.")
        return

    if events is not None and events.empty:
        st.info(
            "No complete observed breach events fully inside the selected scope. "
            "Boundary-crossing events are excluded — try widening the Date Range."
        )

    # Resolve load variable for LOESS/scatter (OT is not a load branch)
    load_var = variable if variable in LOAD_BRANCHES else "HUFL"

    # Build shared title context with safety KPIs + events evidence
    safety_kpis = compute_safety_kpis(features, events)
    ctx = build_context(
        state.dataset, state.season, state.start, state.end,
        variable, len(features),
        safety_kpis=safety_kpis,
        events=events,
    )

    if view == "OT Threshold & Events":
        st.markdown(f"##### {ot_threshold_title(ctx)}")
        fig_ot = build_ot_threshold_chart(
            features, events, dataset_label=state.dataset
        )
        st.plotly_chart(fig_ot, use_container_width=True)
        st.markdown(f"##### {barcode_rug_title(ctx)}")
        fig_rug = build_barcode_rug(events, dataset_label=state.dataset)
        st.plotly_chart(fig_rug, use_container_width=True)

    elif view == "Synchronized Small Multiples":
        st.markdown(f"##### {small_multiples_title(ctx)}")
        fig = build_small_multiples(
            features, events, dataset_label=state.dataset
        )
        st.plotly_chart(fig, use_container_width=True)

    elif view == "Historical LOESS Scatter":
        curves = _read_artifact(_PATH_LOESS, label="loess_curves", silent=True)
        reference: pd.DataFrame | None = None
        if curves is not None:
            season_key = state.season or "All"
            mask = (
                curves.dataset.eq(state.dataset)
                & curves.load_variable.eq(load_var)
                & curves.season.eq(season_key)
            )
            reference = curves.loc[mask]
            if reference.empty:
                reference = None
        if curves is None and not _PATH_LOESS.is_file():
            st.info(
                "LOESS reference curves not found — run the offline engine "
                "to generate `loess_curves.parquet`. Scatter plot shown without curve."
            )
        st.markdown(f"##### {loess_scatter_title(ctx, load_variable=load_var)}")
        fig = build_scatter_loess(
            features,
            load_variable=load_var,
            loess_df=reference,
            dataset_label=state.dataset,
            season=state.season,
        )
        st.plotly_chart(fig, use_container_width=True)

    elif view == "Thermal Regime Boxplots":
        st.markdown(f"##### {regime_boxplots_title(ctx)}")
        fig = build_regime_boxplots(
            features, variable=variable, dataset_label=state.dataset
        )
        st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Sidebar — shared filter controls
# ---------------------------------------------------------------------------


def _build_sidebar(  # noqa: PLR0914
    all_features: pd.DataFrame,
) -> tuple[str, str | None, object, str, str, str]:
    """Build sidebar controls; return (dataset, season, dates, story, view, variable).

    Dataset and season options are derived from actual artifact content (not hardcoded).
    """
    st.sidebar.title("⚡ ETT Grid Analytics")
    st.sidebar.caption("v2.0 · Historical analysis · CPU-only")
    st.sidebar.markdown("---")

    # --- Dataset ---
    available_datasets = sorted(all_features["dataset"].unique().tolist())
    dataset = st.sidebar.selectbox(
        "🗂️ Dataset",
        available_datasets,
        help="Select ETT dataset (ETTh1 = 1h; ETTh2 = 1h; ETTm1 = 15 min)",
    )
    data_for_dataset = all_features.loc[all_features["dataset"].eq(dataset)]

    # --- Season ---
    available_seasons = sorted(data_for_dataset["season"].dropna().unique().tolist())
    season_options = ["All", *available_seasons]
    season_value = st.sidebar.selectbox(
        "🌿 Season",
        season_options,
        help="Dry = Nov–Apr · Wet = May–Oct (project month bins, not verified climate)",
    )
    season: str | None = None if season_value == "All" else season_value

    # --- Date Range ---
    min_date = data_for_dataset["timestamp"].min().date()
    max_date = data_for_dataset["timestamp"].max().date()
    dates = st.sidebar.date_input(
        "📅 Date Range",
        (min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key=f"dates_{dataset}",
        help="Select [start, end] window; events are filtered to complete intervals inside.",
    )

    st.sidebar.markdown("---")

    # --- Story ---
    story = st.sidebar.radio(
        "📖 User Story",
        ["Story 1 — Operational", "Story 2 — Safety"],
        help=(
            "Story 1 (US-01): Load cycles, STL, quantile bands, composition, lag. "
            "Story 2 (US-02): OT events, small multiples, LOESS, regime boxplots."
        ),
    )

    # --- View ---
    views = _STORY1_VIEWS if "Story 1" in story else _STORY2_VIEWS
    view = st.sidebar.selectbox("🔭 View", views)

    # --- Variable ---
    variable_options = list(MEASUREMENTS)  # OT + 6 load branches
    variable = st.sidebar.selectbox(
        "📐 Variable",
        variable_options,
        help=(
            "Active variable for Calendar, STL, Fan, Boxplots. "
            "For LOESS Scatter: OT is fixed as Y-axis; select a load branch (HUFL..LULL). "
            "OT auto-mapped to HUFL for load-branch charts."
        ),
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "⚠️ **Disclaimer**: 85/95°C are project analysis thresholds, "
        "not certified engineering standards. "
        "This tool is for historical analytics only."
    )

    return (
        dataset,
        season,
        dates,
        story,
        view,
        variable,
    )


# ---------------------------------------------------------------------------
# Composition root
# ---------------------------------------------------------------------------


def main() -> None:
    """Single composition root — st.set_page_config called exactly once here."""
    st.set_page_config(
        page_title="ETT Power Grid Analytics",
        page_icon="⚡",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Report a bug": "https://github.com/CHIVY2005/data_visualization_project/issues",
            "About": (
                "**ETT_GRID_VIS_2026 v2.0** — CPU-only historical analytics dashboard.\n\n"
                "Thresholds 85/95°C are project analysis conventions, not certified standards.\n"
                "This is a historical analytics tool, not live safety monitoring."
            ),
        },
    )

    # ---- Header ----
    st.title("⚡ ETT Power Grid Visual Analytics")
    st.caption(
        "**ETT_GRID_VIS_2026 v2.0** · Historical analysis, not live/certified safety monitoring. "
        "Thresholds 85/95°C are project analysis conventions."
    )

    # ---- Load base artifact ----
    with st.spinner("Loading feature artifact…"):
        all_features = _read_artifact(_PATH_FEATURES, label="grid_features")

    if all_features is None:
        st.error(
            "❌ Feature artifact **grid_features.parquet** not found. "
            "Run the pipeline first:\n\n"
            "```powershell\n"
            "python scripts/prepare_all_datasets.py\n"
            "python scripts/run_statistical_engine.py "
            "--input data/processed/grid_features.parquet --out output/artifacts\n"
            "```",
        )
        st.stop()

    # ---- Sidebar filters ----
    dataset, season, dates, story, view, variable = _build_sidebar(all_features)

    # ---- Validate date range ----
    if not isinstance(dates, (list, tuple)) or len(dates) != 2:
        st.info("📅 Please select both a start **and** end date in the sidebar.")
        st.stop()

    start_ts = pd.Timestamp(dates[0])
    end_ts = pd.Timestamp(dates[1]) + pd.Timedelta(days=1)  # end is exclusive

    state = FilterState(
        dataset=dataset,
        season=season,
        start=start_ts,
        end=end_ts,
    )

    # ---- Filter features to scope ----
    features = filter_features(all_features, state)

    # ---- Scope summary bar ----
    n_samples = len(features)
    scope_parts = [f"**{dataset}**", f"Season: {season or 'All'}",
                   f"{dates[0]} → {dates[1]}", f"{n_samples:,} samples"]
    st.info("🔍 Scope: " + " · ".join(scope_parts))

    # ---- Dispatch to story renderer ----
    if "Story 1" in story:
        render_story1(features, state, variable, view)
    else:
        render_story2(features, all_features, state, variable, view)


if __name__ == "__main__":
    main()