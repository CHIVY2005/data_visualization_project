"""T0301/T0302: Operational Manager Chart Modules (US-01).

Artifact: src/visuals/charts_manager.py
Implements:
  - T0301: build_calendar_heatmap (daily/seasonal load cycle heatmap)
  - T0302a: build_stl_panels (4-panel STL decomposition: observed, trend, seasonal, residual)
  - T0302b: build_quantile_fan (hourly quantile fan chart with 50%, 80%, 95% empirical bands)

Input contract:
  - grid_features.parquet for Calendar Heatmap
  - load_profiles_stl.parquet for STL Panels
  - quantile_bands.parquet for Quantile Fan Chart
Output:
  - plotly.graph_objects.Figure — CPU-only, no Streamlit dependency, <2s render SLA.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    WARNING_TEMP_THRESHOLD,
)

# --- Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS) ---
_COLOUR_OT = "#1E3A8A"          # Navy — OT / primary data
_COLOUR_USEFUL = "#0D9488"      # Teal — useful load
_COLOUR_CONTEXT = "#64748B"     # Slate — context / secondary
_COLOUR_WARN = "#D97706"        # Amber — Warning threshold
_COLOUR_CRIT = "#DC2626"        # Crimson — Critical threshold
_COLOUR_RESIDUAL = "#94A3B8"    # Slate-400
_COLOUR_BAND = "#93C5FD"        # Blue for all band fills
_GRID_LINE = "#E2E8F0"          # Tufte main gridline colour

_COLORSCALE_OT: list[list[object]] = [
    [0.0, "#DBEAFE"],   # lightest blue (Normal)
    [0.6, _COLOUR_OT],  # Navy
    [0.8, _COLOUR_WARN],
    [1.0, _COLOUR_CRIT],
]
_COLORSCALE_LOAD: list[list[object]] = [
    [0.0, "#CCFBF1"],   # teal-50
    [0.5, _COLOUR_USEFUL],
    [1.0, "#134E4A"],   # teal-900
]

_BANDS: list[tuple[str, str, float, str]] = [
    ("q025", "q975", 0.14, "95% band"),
    ("q10",  "q90",  0.20, "80% band"),
    ("q25",  "q75",  0.28, "50% IQR"),
]


# ---------------------------------------------------------------------------
# T0301: Calendar Heatmap
# ---------------------------------------------------------------------------

def _daily_pivot(
    frame: pd.DataFrame,
    variable: str,
    agg: str = "mean",
) -> pd.DataFrame:
    """Aggregate one variable to (day-of-year × year) pivot for heatmap cells."""
    df = frame.copy()
    df["_date"] = df["timestamp"].dt.normalize()
    daily = (
        df.groupby("_date")[variable]
        .agg(agg)
        .reset_index()
        .rename(columns={"_date": "date", variable: "value"})
    )
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    daily["dom"] = daily["date"].dt.day  # day-of-month 1..31
    return daily


def build_calendar_heatmap(
    frame: pd.DataFrame,
    variable: str = "OT",
    agg: Literal["mean", "max", "min"] = "mean",
    dataset_label: str = "",
    height: int = 480,
    width: int = 900,
) -> go.Figure:
    """Return a calendar heatmap figure for one dataset/variable (T0301)."""
    if variable not in frame.columns:
        raise ValueError(f"Variable '{variable}' not found in frame")
    if frame.empty:
        raise ValueError("Frame must contain at least one sample")

    daily = _daily_pivot(frame, variable, agg)
    years = sorted(daily["year"].unique().tolist())
    n_years = len(years)

    is_ot = variable == "OT"
    colorscale = _COLORSCALE_OT if is_ot else _COLORSCALE_LOAD

    finite = daily["value"].replace([np.inf, -np.inf], np.nan).dropna()
    zmin = min(0.0, float(finite.min())) if len(finite) else 0.0
    zmax = max(100.0, float(finite.max())) if is_ot and len(finite) else (
        float(finite.max()) if len(finite) else 1.0)
    if zmin >= zmax:
        zmax = zmin + 1.0
    if is_ot:
        w = (WARNING_TEMP_THRESHOLD - zmin) / (zmax - zmin)
        c = (CRITICAL_TEMP_THRESHOLD - zmin) / (zmax - zmin)
        colorscale = [
            [0, "#DBEAFE"], [max(0, w - 1e-7), _COLOUR_OT],
            [w, _COLOUR_WARN], [max(w, c - 1e-7), _COLOUR_WARN],
            [c, _COLOUR_CRIT], [1, _COLOUR_CRIT],
        ]

    month_labels = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    fig = make_subplots(
        rows=1,
        cols=n_years,
        shared_yaxes=True,
        subplot_titles=[str(y) for y in years],
        horizontal_spacing=0.04,
    )

    for col_idx, year in enumerate(years, start=1):
        yr_data = daily[daily["year"] == year]
        z = np.full((31, 12), np.nan)
        for _, row in yr_data.iterrows():
            m = int(row["month"]) - 1
            d = int(row["dom"]) - 1
            val = row["value"]
            if 0 <= m < 12 and 0 <= d < 31:
                z[d, m] = val

        show_scale = col_idx == n_years

        heatmap = go.Heatmap(
            z=z,
            x=month_labels,
            y=list(range(1, 32)),
            zmin=zmin,
            zmax=zmax,
            colorscale=colorscale,
            showscale=show_scale,
            colorbar={
                "title": {"text": variable, "side": "right"},
                "tickfont": {"size": 11},
                "len": 0.85,
            },
            hovertemplate=(
                f"Year: {year}<br>Month: %{{x}}<br>Day: %{{y}}<br>"
                f"{variable}: %{{z:.2f}}<extra></extra>"
            ),
            xgap=1,
            ygap=1,
        )
        fig.add_trace(heatmap, row=1, col=col_idx)

    if is_ot:
        for threshold, colour, label in (
            (WARNING_TEMP_THRESHOLD, _COLOUR_WARN, "85°C Warning"),
            (CRITICAL_TEMP_THRESHOLD, _COLOUR_CRIT, "95°C Critical"),
        ):
            fig.add_annotation(
                xref="paper", yref="paper",
                x=1.02, y=(threshold - zmin) / max(zmax - zmin, 1),
                text=label, showarrow=False,
                font={"color": colour, "size": 10},
                align="left",
            )

    agg_label = {"mean": "Average", "max": "Peak", "min": "Minimum"}[agg]
    title_text = (
        f"{agg_label} Daily {variable} — Seasonal Cycle"
        + (f" [{dataset_label}]" if dataset_label else "")
    )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.5, "xanchor": "center",
            "font": {"size": 15, "color": "#1E293B"},
        },
        height=height,
        width=width,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 12},
        margin={"l": 50, "r": 120, "t": 60, "b": 50},
    )

    fig.update_yaxes(
        title_text="Day of Month",
        tickmode="linear", tick0=1, dtick=5,
        gridcolor=_GRID_LINE,
        showgrid=True,
        row=1, col=1,
    )
    for col_idx in range(1, n_years + 1):
        fig.update_xaxes(
            showgrid=False,
            tickfont={"size": 10},
            row=1, col=col_idx,
        )

    return fig


# ---------------------------------------------------------------------------
# T0302a: STL Decomposition Panels
# ---------------------------------------------------------------------------

def build_stl_panels(
    stl_df: pd.DataFrame,
    variable: str = "OT",
    dataset_label: str = "",
    height: int = 640,
    width: int = 960,
    max_points: int = 8760,
) -> go.Figure:
    """Return four-panel STL decomposition figure (T0302a)."""
    required = {"timestamp", "observed", "trend", "seasonal", "residual"}
    missing = required - set(stl_df.columns)
    if missing:
        raise ValueError(f"Missing STL columns: {sorted(missing)}")
    if stl_df.empty:
        raise ValueError("STL DataFrame must not be empty")

    df = stl_df[["timestamp", "observed", "trend", "seasonal", "residual"]].copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    if len(df) > max_points:
        step = max(1, len(df) // max_points)
        df = df.iloc[::step].reset_index(drop=True)

    is_ot = variable == "OT"
    line_colour = _COLOUR_OT if is_ot else _COLOUR_USEFUL
    trend_colour = _COLOUR_CONTEXT

    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.35, 0.25, 0.20, 0.20],
        vertical_spacing=0.04,
        subplot_titles=[
            f"Observed {variable}",
            "Trend",
            "Seasonal (daily)",
            "Residual",
        ],
    )

    ts = df["timestamp"]

    # Panel 1: Observed
    fig.add_trace(go.Scatter(
        x=ts, y=df["observed"],
        mode="lines",
        line={"color": line_colour, "width": 1.0},
        name="Observed",
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Observed: %{y:.2f}<extra></extra>",
    ), row=1, col=1)

    if is_ot:
        for threshold, colour, label in (
            (WARNING_TEMP_THRESHOLD, _COLOUR_WARN, "85°C Warning"),
            (CRITICAL_TEMP_THRESHOLD, _COLOUR_CRIT, "95°C Critical"),
        ):
            fig.add_hline(
                y=threshold,
                line={"color": colour, "dash": "dash", "width": 1.5},
                annotation_text=label,
                annotation_position="right",
                annotation_font={"color": colour, "size": 10},
                row=1, col=1,
            )

    # Panel 2: Trend
    fig.add_trace(go.Scatter(
        x=ts, y=df["trend"],
        mode="lines",
        line={"color": trend_colour, "width": 1.5},
        name="Trend",
        hovertemplate="%{x|%Y-%m-%d}<br>Trend: %{y:.2f}<extra></extra>",
    ), row=2, col=1)

    # Panel 3: Seasonal
    fig.add_trace(go.Scatter(
        x=ts, y=df["seasonal"],
        mode="lines",
        line={"color": line_colour, "width": 1.0, "dash": "dot"},
        name="Seasonal",
        opacity=0.8,
        hovertemplate="%{x|%H:%M}<br>Seasonal: %{y:.2f}<extra></extra>",
    ), row=3, col=1)
    fig.add_hline(y=0, line={"color": _GRID_LINE, "width": 1}, row=3, col=1)

    # Panel 4: Residual
    residual_pos = df["residual"].clip(lower=0)
    residual_neg = df["residual"].clip(upper=0)

    fig.add_trace(go.Bar(
        x=ts, y=residual_pos,
        marker_color=line_colour,
        opacity=0.55,
        name="Residual (+)",
        showlegend=False,
        hovertemplate="Residual: %{y:.2f}<extra></extra>",
    ), row=4, col=1)

    fig.add_trace(go.Bar(
        x=ts, y=residual_neg,
        marker_color=_COLOUR_CRIT,
        opacity=0.45,
        name="Residual (−)",
        showlegend=False,
        hovertemplate="Residual: %{y:.2f}<extra></extra>",
    ), row=4, col=1)

    fig.add_hline(y=0, line={"color": _GRID_LINE, "width": 1}, row=4, col=1)

    title_text = (
        f"STL Decomposition — {variable}"
        + (f" [{dataset_label}]" if dataset_label else "")
    )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.5, "xanchor": "center",
            "font": {"size": 14, "color": "#1E293B"},
        },
        height=height,
        width=width,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 11},
        margin={"l": 60, "r": 80, "t": 60, "b": 40},
        showlegend=False,
        hovermode="x unified",
    )

    for r in range(1, 5):
        fig.update_yaxes(gridcolor=_GRID_LINE, showgrid=True, zeroline=False, row=r, col=1)
        fig.update_xaxes(gridcolor=_GRID_LINE, showgrid=True, zeroline=False, row=r, col=1)

    fig.update_xaxes(title_text="Timestamp", row=4, col=1)
    return fig


# ---------------------------------------------------------------------------
# T0302b: Hourly Quantile Fan Chart
# ---------------------------------------------------------------------------

def build_quantile_fan(
    bands_df: pd.DataFrame,
    dataset: str | None = None,
    variable: str = "OT",
    season: str | None = None,
    dataset_label: str = "",
    show_mean: bool = True,
    height: int = 400,
    width: int = 700,
) -> go.Figure:
    """Return an hourly quantile fan chart for one variable/season (T0302b)."""
    required = {"hour", "mean", "q025", "q10", "q25", "q50", "q75", "q90", "q975"}
    missing = required - set(bands_df.columns)
    if missing:
        raise ValueError(f"Missing quantile columns: {sorted(missing)}")

    df = bands_df.copy()
    if dataset is not None and "dataset" in df.columns:
        df = df[df["dataset"] == dataset]
    if season is not None:
        if "season" not in df.columns:
            raise ValueError("season column required when season parameter is provided")
        df = df[df["season"] == season]
    if "variable" in df.columns:
        df = df[df["variable"] == variable]
    if df.empty:
        raise ValueError("No data after filtering — check variable/season parameters")

    df = df.sort_values("hour").reset_index(drop=True)
    hours = df["hour"].tolist()

    is_ot = variable == "OT"
    line_colour = _COLOUR_OT if is_ot else _COLOUR_USEFUL

    fig = go.Figure()

    for lower_col, upper_col, alpha, band_label in _BANDS:
        lower = df[lower_col].tolist()
        upper = df[upper_col].tolist()

        fig.add_trace(go.Scatter(
            x=hours + hours[::-1],
            y=upper + lower[::-1],
            fill="toself",
            fillcolor=f"rgba(147,197,253,{alpha})",
            line={"color": "rgba(0,0,0,0)"},
            hoverinfo="skip",
            showlegend=True,
            name=band_label,
        ))

    fig.add_trace(go.Scatter(
        x=hours,
        y=df["q50"].tolist(),
        mode="lines+markers",
        line={"color": line_colour, "width": 2.5},
        marker={"size": 5, "color": line_colour},
        name="Median (Q50)",
        hovertemplate="Hour: %{x}:00<br>Median: %{y:.2f}<extra></extra>",
    ))

    if show_mean:
        fig.add_trace(go.Scatter(
            x=hours,
            y=df["mean"].tolist(),
            mode="lines",
            line={"color": _COLOUR_CONTEXT, "width": 1.5, "dash": "dash"},
            name="Mean",
            hovertemplate="Hour: %{x}:00<br>Mean: %{y:.2f}<extra></extra>",
        ))

    if is_ot:
        for threshold, colour, label in (
            (WARNING_TEMP_THRESHOLD, _COLOUR_WARN, "85°C"),
            (CRITICAL_TEMP_THRESHOLD, _COLOUR_CRIT, "95°C"),
        ):
            fig.add_hline(
                y=threshold,
                line={"color": colour, "dash": "dot", "width": 1.2},
                annotation_text=label,
                annotation_position="right",
                annotation_font={"color": colour, "size": 9},
            )

    season_label = f" — {season}" if season else ""
    title_text = (
        f"Hourly {variable} Distribution{season_label}"
        + (f" [{dataset_label or dataset or ''}]" if (dataset_label or dataset) else "")
    )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.5, "xanchor": "center",
            "font": {"size": 14, "color": "#1E293B"},
        },
        height=height,
        width=width,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 12},
        margin={"l": 50, "r": 60, "t": 60, "b": 40},
        xaxis={
            "title": "Hour of Day",
            "tickmode": "linear",
            "tick0": 0, "dtick": 2,
            "range": [-0.5, 23.5],
            "gridcolor": _GRID_LINE,
            "showgrid": True,
        },
        yaxis={
            "title": f"{variable} (°C)" if is_ot else f"{variable} (Load)",
            "gridcolor": _GRID_LINE,
            "showgrid": True,
            "zeroline": False,
        },
        legend={
            "orientation": "h",
            "x": 0.5, "xanchor": "center",
            "y": -0.22,
            "font": {"size": 11},
        },
    )

    return fig
