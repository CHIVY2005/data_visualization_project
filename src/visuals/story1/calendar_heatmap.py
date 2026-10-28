"""T0301: Calendar Heatmap — daily/seasonal load cycle for US-01.

What:  One cell per day; colour encodes mean daily OT (or any load variable).
Why:   Operational Manager needs to spot seasonal cycles and maintenance windows.
How:   Plotly heatmap with month on X-axis, day-of-month on Y-axis, faceted by
       year; shared colour scale across facets; threshold annotation at 85/95°C
       for OT only.

Input contract:  grid_features.parquet columns
  dataset, timestamp, OT, HUFL, HULL, MUFL, MULL, LUFL, LULL,
  total_useful_load, total_unuseful_load, season (str: Dry/Wet), hour (int32)
Output: plotly.graph_objects.Figure — no Streamlit import, no heavy computation.
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


def _daily_pivot(
    frame: pd.DataFrame,
    variable: str,
    agg: str = "mean",
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Aggregate one variable to (day-of-year × year) pivot for heatmap cells.

    Returns
    -------
    pivot  : float32 DataFrame with year columns, day-of-month rows (1..31)
    months : Int32 Series aligned to pivot rows – calendar month (1..12)
    years  : sorted list of integer years
    """
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
    """Return a calendar heatmap figure for one dataset/variable.

    Parameters
    ----------
    frame:
        Grid-features DataFrame for a **single** dataset (filter before calling).
    variable:
        Column to visualise; must be numeric in frame.
    agg:
        Aggregation applied per calendar day: 'mean', 'max', or 'min'.
    dataset_label:
        Displayed in the title to identify the source dataset.
    height, width:
        Figure dimensions in pixels.
    """
    if variable not in frame.columns:
        raise ValueError(f"Variable '{variable}' not found in frame")
    if frame.empty:
        raise ValueError("Frame must contain at least one sample")

    daily = _daily_pivot(frame, variable, agg)
    years = sorted(daily["year"].unique().tolist())
    n_years = len(years)

    is_ot = variable == "OT"
    colorscale = _COLORSCALE_OT if is_ot else _COLORSCALE_LOAD

    # Compute shared colour range across all years
    finite = daily["value"].replace([np.inf, -np.inf], np.nan).dropna()
    zmin = float(finite.quantile(0.01)) if len(finite) else 0.0
    zmax = float(finite.quantile(0.99)) if len(finite) else 1.0
    if zmin >= zmax:
        zmax = zmin + 1.0

    # Month labels for x-axis
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
        # Build month × day-of-month matrix (12 × 31) with NaN for missing days
        z = np.full((31, 12), np.nan)
        text = np.full((31, 12), "", dtype=object)
        for _, row in yr_data.iterrows():
            m = int(row["month"]) - 1   # 0-indexed
            d = int(row["dom"]) - 1     # 0-indexed
            val = row["value"]
            if 0 <= m < 12 and 0 <= d < 31:
                z[d, m] = val
                text[d, m] = f"{val:.1f}" if not np.isnan(val) else ""

        show_scale = col_idx == n_years  # only rightmost column

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

    # Add threshold lines for OT only (Tufte: annotate context, not decoration)
    if is_ot:
        for threshold, colour, label in (
            (WARNING_TEMP_THRESHOLD, _COLOUR_WARN, "85°C Warning"),
            (CRITICAL_TEMP_THRESHOLD, _COLOUR_CRIT, "95°C Critical"),
        ):
            # Thresholds apply to the colour scale — add annotation strip
            fig.add_annotation(
                xref="paper", yref="paper",
                x=1.02, y=(threshold - zmin) / max(zmax - zmin, 1),
                text=label, showarrow=False,
                font={"color": colour, "size": 10},
                align="left",
            )

    # Build action title
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

    # Y-axis: day of month; X-axis: month label (shared)
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
