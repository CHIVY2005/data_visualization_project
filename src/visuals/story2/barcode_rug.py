"""T0401: Barcode / Rug Plot for Thermal Breach Events (US-02).

What:  Temporal barcode/rug plot displaying thermal violation events along a timeline.
Why:   Safety & Risk Monitor needs a compact barcode strip to instantly locate when
       breaches occurred, identify clustering in time, and assess violation density.
How:   Plotly graph_objects Figure displaying events as vertical tick markers / bars
       at event start timestamps, segmented into Warning (85°C) and Critical (95°C)
       regimes, with duration, peak OT, and degree-hours hover tooltips.

Input contract:
  events_df: pd.DataFrame with at least:
      ['event_id', 'threshold_c', 'start_timestamp', 'end_timestamp',
       'duration_hours', 'peak_ot', 'degree_hours']
Output:
  plotly.graph_objects.Figure — lightweight, responsive, <2s render.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    WARNING_TEMP_THRESHOLD,
)

# Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS)
_COLOUR_WARN = "#D97706"      # Amber — 85°C Warning
_COLOUR_CRIT = "#DC2626"      # Crimson — 95°C Critical
_GRID_LINE = "#E2E8F0"        # Tufte grid line


def build_barcode_rug(
    events_df: pd.DataFrame | None,
    threshold_c: float | None = None,
    dataset_label: str = "",
    height: int = 180,
    width: int | None = None,
    time_range: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> go.Figure:
    """Build a Barcode/Rug plot for thermal breach incidents.

    Parameters
    ----------
    events_df : pd.DataFrame | None
        DataFrame containing breach events (from breach_events.parquet).
    threshold_c : float | None, default None
        Optional filter: 85.0 for Warning only, 95.0 for Critical only, or None for both.
    dataset_label : str, default ""
        Dataset identifier for title display.
    height : int, default 180
        Figure height in pixels.
    width : int | None, default None
        Figure width in pixels (None for responsive container).
    time_range : tuple[pd.Timestamp, pd.Timestamp] | None, default None
        Optional (min_time, max_time) to align X-axis with other charts.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()

    prefix = f"[{dataset_label}] " if dataset_label else ""

    # Check for empty or missing data
    if events_df is None or events_df.empty:
        fig.add_annotation(
            text="Không ghi nhận sự kiện vượt ngưỡng nhiệt độ nào (An toàn).",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 13, "color": "#64748B"},
        )
        fig.update_layout(
            title={
                "text": f"<b>{prefix}Thanh Barcode sự cố vi phạm: Không có sự kiện</b>",
                "x": 0.01,
                "y": 0.95,
                "font": {"size": 13, "color": "#1E293B"},
            },
            height=height,
            width=width,
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
            yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        )
        return fig

    df = events_df.copy()

    # Filter by threshold if specified
    if threshold_c is not None:
        df = df[df["threshold_c"] == threshold_c]

    if df.empty:
        fig.add_annotation(
            text=f"Không có sự kiện vượt ngưỡng {threshold_c}°C.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 13, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    # Ensure datetime dtype
    if not pd.api.types.is_datetime64_any_dtype(df["start_timestamp"]):
        df["start_timestamp"] = pd.to_datetime(df["start_timestamp"])
    if not pd.api.types.is_datetime64_any_dtype(df["end_timestamp"]):
        df["end_timestamp"] = pd.to_datetime(df["end_timestamp"])

    # Separate into Warning (85°C) and Critical (95°C)
    crit_events = df[df["threshold_c"] >= CRITICAL_TEMP_THRESHOLD]
    warn_events = df[
        (df["threshold_c"] >= WARNING_TEMP_THRESHOLD)
        & (df["threshold_c"] < CRITICAL_TEMP_THRESHOLD)
    ]

    # Two lanes: Y=1 for Warning, Y=2 for Critical
    # Warning Rug markers
    if not warn_events.empty:
        fig.add_trace(
            go.Scatter(
                x=warn_events["start_timestamp"],
                y=[1] * len(warn_events),
                mode="markers",
                name=f"Cảnh báo ≥85°C ({len(warn_events)})",
                marker={
                    "color": _COLOUR_WARN,
                    "symbol": "line-ns-open",
                    "size": 22,
                    "line": {"width": 2, "color": _COLOUR_WARN},
                },
                customdata=warn_events[
                    ["event_id", "duration_hours", "peak_ot", "degree_hours"]
                ],
                hovertemplate=(
                    "<b>SỰ KIỆN CẢNH BÁO</b><br>"
                    "Mã: %{customdata[0]}<br>"
                    "Bắt đầu: %{x|%Y-%m-%d %H:%M}<br>"
                    "Thời lượng: %{customdata[1]:.2f} giờ<br>"
                    "Đỉnh nhiệt: %{customdata[2]:.2f} °C<br>"
                    "Áp lực nhiệt: %{customdata[3]:.2f} °C·h<extra></extra>"
                ),
            )
        )

    # Critical Rug markers
    if not crit_events.empty:
        fig.add_trace(
            go.Scatter(
                x=crit_events["start_timestamp"],
                y=[2] * len(crit_events),
                mode="markers",
                name=f"Nguy cấp ≥95°C ({len(crit_events)})",
                marker={
                    "color": _COLOUR_CRIT,
                    "symbol": "line-ns-open",
                    "size": 26,
                    "line": {"width": 2.5, "color": _COLOUR_CRIT},
                },
                customdata=crit_events[
                    ["event_id", "duration_hours", "peak_ot", "degree_hours"]
                ],
                hovertemplate=(
                    "<b>SỰ KIỆN NGUY CẤP</b><br>"
                    "Mã: %{customdata[0]}<br>"
                    "Bắt đầu: %{x|%Y-%m-%d %H:%M}<br>"
                    "Thời lượng: %{customdata[1]:.2f} giờ<br>"
                    "Đỉnh nhiệt: %{customdata[2]:.2f} °C<br>"
                    "Áp lực nhiệt: %{customdata[3]:.2f} °C·h<extra></extra>"
                ),
            )
        )

    # Action title
    tot_events = len(df)
    n_crit = len(crit_events)
    n_warn = len(warn_events)
    action_title = (
        f"<b>{prefix}Thanh Barcode sự cố nhiệt: {tot_events:,} đợt vi phạm "
        f"({n_crit} nguy cấp ≥95°C, {n_warn} cảnh báo ≥85°C)</b>"
    )

    xaxis_cfg: dict[str, object] = {
        "title": "Thời gian quan sát",
        "showgrid": True,
        "gridcolor": _GRID_LINE,
        "zeroline": False,
    }
    if time_range is not None:
        xaxis_cfg["range"] = list(time_range)

    fig.update_layout(
        title={
            "text": action_title,
            "x": 0.01,
            "y": 0.96,
            "font": {"size": 13, "color": "#1E293B"},
        },
        xaxis=xaxis_cfg,
        yaxis={
            "tickvals": [1, 2],
            "ticktext": ["Cảnh báo (85°C)", "Nguy cấp (95°C)"],
            "range": [0.4, 2.6],
            "showgrid": False,
            "zeroline": False,
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1.0,
            "bgcolor": "rgba(255, 255, 255, 0.8)",
        },
        margin={"l": 110, "r": 30, "t": 45, "b": 35},
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        height=height,
        width=width,
        hovermode="closest",
    )

    return fig
