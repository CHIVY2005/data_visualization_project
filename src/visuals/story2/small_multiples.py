"""T0402: Six Synchronized Small Multiples for Grid Load Branches (US-02).

What:  Six vertically stacked subplots (HUFL, HULL, MUFL, MULL, LUFL, LULL)
       sharing a synchronized time X-axis.
Why:   Safety & Risk Monitor needs to inspect all six load branches in lockstep during
       thermal excursions to formulate failure hypotheses without screen clutter.
How:   Plotly make_subplots with rows=6, cols=1, shared_xaxes=True, with Teal for
       useful loads and Slate for unuseful loads. Optional vertical shading across all
       panels for thermal breach intervals.

Input contract:
  frame: pd.DataFrame containing ['timestamp', 'HUFL', 'HULL', 'MUFL', 'MULL', 'LUFL', 'LULL']
  events_df (optional): pd.DataFrame from breach_events.parquet
Output:
  plotly.graph_objects.Figure — interactive shared-axis zoom/pan, <2s render.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    LOAD_BRANCHES,
    USEFUL_LOADS,
)

# Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS)
_COLOUR_USEFUL = "#0D9488"      # Teal — useful loads (HUFL, MUFL, LUFL)
_COLOUR_UNUSEFUL = "#64748B"    # Slate — unuseful loads (HULL, MULL, LULL)
_GRID_LINE = "#E2E8F0"          # Tufte grid line
_BG_WARN = "rgba(217, 119, 6, 0.12)"   # Warning band
_BG_CRIT = "rgba(220, 38, 38, 0.18)"   # Critical band

_BRANCH_DESCRIPTIONS: dict[str, str] = {
    "HUFL": "HUFL (Cao thế - Hữu công)",
    "HULL": "HULL (Cao thế - Vô công)",
    "MUFL": "MUFL (Trung thế - Hữu công)",
    "MULL": "MULL (Trung thế - Vô công)",
    "LUFL": "LUFL (Hạ thế - Hữu công)",
    "LULL": "LULL (Hạ thế - Vô công)",
}


def build_small_multiples(
    frame: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    dataset_label: str = "",
    height: int = 800,
    width: int | None = None,
    max_points: int = 8760,
) -> go.Figure:
    """Build 6 synchronized small multiple subplots with shared time X-axis.

    Parameters
    ----------
    frame : pd.DataFrame
        DataFrame containing 'timestamp' and the 6 load branches.
    events_df : pd.DataFrame | None, default None
        Optional DataFrame with breach events to highlight intervals.
    dataset_label : str, default ""
        Dataset name for title display.
    height : int, default 800
        Figure height in pixels.
    width : int | None, default None
        Figure width in pixels (None for responsive container).
    max_points : int, default 8760
        Max points to plot per trace to keep render responsive.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    required = {"timestamp", *LOAD_BRANCHES}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        fig = go.Figure()
        fig.add_annotation(
            text="Thiếu dữ liệu các nhánh phụ tải (HUFL..LULL) để hiển thị Small Multiples.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    df = frame.dropna(subset=["timestamp", *LOAD_BRANCHES]).sort_values("timestamp").copy()
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="Không có bản ghi hợp lệ sau khi lọc dữ liệu.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Decimate if needed
    n_points = len(df)
    if n_points > max_points:
        step = int(np.ceil(n_points / max_points))
        df = df.iloc[::step]

    # Subplot titles
    subplot_titles = [_BRANCH_DESCRIPTIONS.get(b, b) for b in LOAD_BRANCHES]

    fig = make_subplots(
        rows=6,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        subplot_titles=subplot_titles,
    )

    # Plot each branch
    for idx, branch in enumerate(LOAD_BRANCHES, start=1):
        is_useful = branch in USEFUL_LOADS
        color = _COLOUR_USEFUL if is_useful else _COLOUR_UNUSEFUL
        type_str = "Hữu công" if is_useful else "Vô công"

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df[branch],
                mode="lines",
                name=branch,
                line={"color": color, "width": 1.2},
                showlegend=False,
                hovertemplate=(
                    f"<b>{branch} ({type_str})</b>: %{{y:.2f}}<br>"
                    "Thời gian: %{x|%Y-%m-%d %H:%M}<extra></extra>"
                ),
            ),
            row=idx,
            col=1,
        )

        # Subtle zero line and grid for each subplot
        fig.update_yaxes(
            showgrid=True,
            gridcolor=_GRID_LINE,
            zeroline=True,
            zerolinecolor="#CBD5E1",
            zerolinewidth=1,
            row=idx,
            col=1,
        )

    # Add breach span shading across all subplots if events_df is provided
    if events_df is not None and not events_df.empty:
        for _, ev in events_df.iterrows():
            th = float(ev.get("threshold_c", 85.0))
            color = _BG_CRIT if th >= CRITICAL_TEMP_THRESHOLD else _BG_WARN
            for r in range(1, 7):
                fig.add_vrect(
                    x0=ev["start_timestamp"],
                    x1=ev["end_timestamp"],
                    fillcolor=color,
                    layer="below",
                    line_width=0,
                    row=r,
                    col=1,
                )

    prefix = f"[{dataset_label}] " if dataset_label else ""
    fig.update_layout(
        title={
            "text": (
                f"<b>{prefix}Synchronized Small Multiples: Đối chiếu đồng thời 6 nhánh tải "
                f"(Đồng bộ trục thời gian — Zoom/Pan toàn bộ)</b>"
            ),
            "x": 0.01,
            "y": 0.985,
            "font": {"size": 13.5, "color": "#1E293B"},
        },
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        height=height,
        width=width,
        margin={"l": 55, "r": 25, "t": 60, "b": 40},
        hovermode="x unified",
    )

    # Style subplot titles to be clean and compact
    for ann in fig["layout"]["annotations"]:
        ann["font"] = {"size": 11, "color": "#475569"}
        ann["x"] = 0.01
        ann["xanchor"] = "left"

    fig.update_xaxes(
        showgrid=True,
        gridcolor=_GRID_LINE,
        row=6,
        col=1,
        title_text="Thời gian quan sát (Đồng bộ toàn bộ nhánh)",
    )

    return fig
