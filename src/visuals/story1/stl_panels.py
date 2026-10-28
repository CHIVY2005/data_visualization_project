"""T0302a: STL Decomposition Panels — trend/seasonal/residual for US-01.

What:  Multi-panel line chart: observed | trend | seasonal | residual for one
       variable/dataset, optionally filtered by season.
Why:   Operational Manager needs to see long-term trend and intra-day cycle
       separately from noise, to schedule maintenance in low-trend periods.
How:   Four vertically stacked subplots with shared X (time axis); threshold
       shading on observed panel for OT; residual range as bar chart.

Input contract:  load_profiles_stl.parquet (record_type == 'stl')
  dataset, variable, timestamp, observed, trend, seasonal, residual
Output: plotly.graph_objects.Figure — no Streamlit, no heavy computation.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

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
_COLOUR_RESIDUAL = "#94A3B8"
_GRID_LINE = "#E2E8F0"


def build_stl_panels(
    stl_df: pd.DataFrame,
    variable: str = "OT",
    dataset_label: str = "",
    height: int = 640,
    width: int = 960,
    max_points: int = 8760,
) -> go.Figure:
    """Return four-panel STL decomposition figure.

    Parameters
    ----------
    stl_df:
        Slice of load_profiles_stl.parquet with record_type == 'stl'.
        Expected columns: timestamp, observed, trend, seasonal, residual.
        Pass a **single dataset/variable** subset; do not mix datasets.
    variable:
        Label used in panel titles and colour selection.
    dataset_label:
        Source dataset name displayed in the overall title.
    height, width:
        Figure dimensions in pixels.
    max_points:
        Downsample to at most this many points for render performance.
        Downsampling uses uniform striding — preserves temporal density.
    """
    required = {"timestamp", "observed", "trend", "seasonal", "residual"}
    missing = required - set(stl_df.columns)
    if missing:
        raise ValueError(f"Missing STL columns: {sorted(missing)}")
    if stl_df.empty:
        raise ValueError("STL DataFrame must not be empty")

    df = stl_df[["timestamp", "observed", "trend", "seasonal", "residual"]].copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Uniform striding for render performance (preserves temporal structure)
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

    # --- Panel 1: Observed ---
    fig.add_trace(go.Scatter(
        x=ts, y=df["observed"],
        mode="lines",
        line={"color": line_colour, "width": 1.0},
        name="Observed",
        hovertemplate="%{x|%Y-%m-%d %H:%M}<br>Observed: %{y:.2f}<extra></extra>",
    ), row=1, col=1)

    # OT threshold shading on observed panel only
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

    # --- Panel 2: Trend ---
    fig.add_trace(go.Scatter(
        x=ts, y=df["trend"],
        mode="lines",
        line={"color": trend_colour, "width": 1.5},
        name="Trend",
        hovertemplate="%{x|%Y-%m-%d}<br>Trend: %{y:.2f}<extra></extra>",
    ), row=2, col=1)

    # --- Panel 3: Seasonal ---
    fig.add_trace(go.Scatter(
        x=ts, y=df["seasonal"],
        mode="lines",
        line={"color": line_colour, "width": 1.0, "dash": "dot"},
        name="Seasonal",
        opacity=0.8,
        hovertemplate="%{x|%H:%M}<br>Seasonal: %{y:.2f}<extra></extra>",
    ), row=3, col=1)

    # Zero reference for seasonal
    fig.add_hline(y=0, line={"color": _GRID_LINE, "width": 1}, row=3, col=1)

    # --- Panel 4: Residual ---
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

    title_text = (
        f"STL Decomposition — {variable}"
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
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 11},
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.01, "x": 0},
        margin={"l": 60, "r": 80, "t": 70, "b": 40},
        barmode="overlay",
    )

    # Shared X-axis label on bottom panel only
    fig.update_xaxes(showgrid=True, gridcolor=_GRID_LINE)
    fig.update_yaxes(showgrid=True, gridcolor=_GRID_LINE, zeroline=False)
    fig.update_xaxes(title_text="Time", row=4, col=1)

    return fig
