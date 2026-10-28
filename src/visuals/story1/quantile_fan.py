"""T0302b: Hourly Quantile Fan Chart — empirical distribution by hour for US-01.

What:  Fan chart with 50%/80%/95% empirical bands + median + mean per hour.
Why:   Operational Manager needs to see typical load range and uncertainty for
       each hour-of-day, filtered by season, to plan dispatch schedules.
How:   Plotly filled-area traces (wide band first, narrow last) with median
       and mean lines; shared axes allow multiple variables in facet mode.

Input contract:  quantile_bands.parquet / hourly_quantiles.parquet
  dataset, variable, season, hour, sample_count,
  mean, q025, q10, q25, q50, q75, q90, q975
Output: plotly.graph_objects.Figure — no Streamlit, no heavy computation.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    WARNING_TEMP_THRESHOLD,
)

# Project colour palette
_COLOUR_OT = "#1E3A8A"
_COLOUR_USEFUL = "#0D9488"
_COLOUR_CONTEXT = "#64748B"
_COLOUR_WARN = "#D97706"
_COLOUR_CRIT = "#DC2626"
_COLOUR_BAND = "#93C5FD"   # Blue for all band fills
_GRID_LINE = "#E2E8F0"

# Band definitions: (lower_col, upper_col, alpha, label)
_BANDS: list[tuple[str, str, float, str]] = [
    ("q025", "q975", 0.14, "95% band"),
    ("q10",  "q90",  0.20, "80% band"),
    ("q25",  "q75",  0.28, "50% IQR"),
]


def build_quantile_fan(
    bands_df: pd.DataFrame,
    variable: str = "OT",
    season: str | None = None,
    dataset_label: str = "",
    show_mean: bool = True,
    height: int = 400,
    width: int = 700,
) -> go.Figure:
    """Return an hourly quantile fan chart for one variable/season.

    Parameters
    ----------
    bands_df:
        Slice of hourly_quantiles.parquet (or quantile_bands.parquet).
        Pass a **single dataset** subset; filter by variable and season
        before calling, or supply season parameter for auto-filtering.
    variable:
        Variable displayed (used for title and colour selection).
    season:
        'Dry' or 'Wet' — if provided, filter bands_df automatically.
        If None, caller must have already filtered to one season.
    dataset_label:
        Source dataset name displayed in the figure title.
    show_mean:
        Whether to overlay the mean line (distinct from median).
    height, width:
        Figure dimensions in pixels.
    """
    required = {"hour", "mean", "q025", "q10", "q25", "q50", "q75", "q90", "q975"}
    missing = required - set(bands_df.columns)
    if missing:
        raise ValueError(f"Missing quantile columns: {sorted(missing)}")

    df = bands_df.copy()
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

    # Draw bands wide-to-narrow (Tufte: enclosure for context, not decoration)
    for lower_col, upper_col, alpha, band_label in _BANDS:
        lower = df[lower_col].tolist()
        upper = df[upper_col].tolist()

        # Upper envelope
        fig.add_trace(go.Scatter(
            x=hours + hours[::-1],
            y=upper + lower[::-1],
            fill="toself",
            fillcolor=f"rgba(147,197,253,{alpha})",   # #93C5FD with alpha
            line={"color": "rgba(0,0,0,0)"},
            hoverinfo="skip",
            showlegend=True,
            name=band_label,
        ))

    # Median line — primary signal
    fig.add_trace(go.Scatter(
        x=hours,
        y=df["q50"].tolist(),
        mode="lines+markers",
        line={"color": line_colour, "width": 2.5},
        marker={"size": 5, "color": line_colour},
        name="Median (Q50)",
        hovertemplate="Hour: %{x}:00<br>Median: %{y:.2f}<extra></extra>",
    ))

    # Mean line — distinct from median, avoids confusion
    if show_mean:
        fig.add_trace(go.Scatter(
            x=hours,
            y=df["mean"].tolist(),
            mode="lines",
            line={"color": _COLOUR_CONTEXT, "width": 1.5, "dash": "dash"},
            name="Mean",
            hovertemplate="Hour: %{x}:00<br>Mean: %{y:.2f}<extra></extra>",
        ))

    # OT threshold lines (annotation only — not decorative)
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
        xaxis={
            "title": "Hour of Day",
            "tickmode": "linear", "tick0": 0, "dtick": 4,
            "range": [-0.5, 23.5],
            "gridcolor": _GRID_LINE, "showgrid": True,
        },
        yaxis={
            "title": variable,
            "gridcolor": _GRID_LINE, "showgrid": True,
            "zeroline": False,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom", "y": 1.01, "x": 0,
            "font": {"size": 10},
        },
        margin={"l": 55, "r": 60, "t": 65, "b": 45},
        hovermode="x unified",
    )

    return fig
