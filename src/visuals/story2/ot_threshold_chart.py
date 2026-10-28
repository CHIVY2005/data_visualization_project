"""T0401: OT Threshold Monitoring Chart with 85°C/95°C Regimes for US-02.

What:  Line chart of Oil Temperature (OT) across time with horizontal threshold lines
       at 85°C (Warning) and 95°C (Critical), background hazard shading, and pop-out
       breach markers.
Why:   Safety & Risk Monitor (US-02) needs to instantly identify when and where OT
       approached or exceeded thermal limits and inspect breach severity.
How:   Plotly graph_objects Figure with Navy OT trajectory, Amber dashed 85°C line,
       Crimson dashed 95°C line, semi-transparent background shading for Warning [85, 95)
       and Critical [95, max] zones, and pop-out scatter markers for breach events.

Input contract:
  frame: pd.DataFrame with at least ['timestamp', 'OT']
  events_df (optional): pd.DataFrame from breach_events.parquet with
      ['start_timestamp', 'end_timestamp', 'threshold_c', 'peak_ot', 'duration_hours']
Output:
  plotly.graph_objects.Figure — self-contained, no UI compute, <2s render.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    WARNING_TEMP_THRESHOLD,
)

# Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS)
_COLOUR_OT = "#1E3A8A"        # Navy — OT line
_COLOUR_WARN = "#D97706"      # Amber — 85°C Warning
_COLOUR_CRIT = "#DC2626"      # Crimson — 95°C Critical
_GRID_LINE = "#E2E8F0"        # Tufte grid line
_BG_WARN = "rgba(217, 119, 6, 0.12)"   # Warning band fill
_BG_CRIT = "rgba(220, 38, 38, 0.18)"   # Critical band fill


def build_ot_threshold_chart(
    frame: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    dataset_label: str = "",
    height: int = 440,
    width: int | None = None,
    max_points: int = 8760,
) -> go.Figure:
    """Build OT threshold monitoring chart with warning and critical regimes.

    Parameters
    ----------
    frame : pd.DataFrame
        DataFrame containing at least 'timestamp' and 'OT'.
    events_df : pd.DataFrame | None, default None
        Optional DataFrame of thermal breach events with 'start_timestamp',
        'end_timestamp', 'threshold_c', 'peak_ot'.
    dataset_label : str, default ""
        Dataset name for title display (e.g. 'ETTh1').
    height : int, default 440
        Figure height in pixels.
    width : int | None, default None
        Figure width in pixels (None for responsive container).
    max_points : int, default 8760
        Maximum time points to plot for the continuous line to ensure <2s SLA.
        Breach points are never decimated.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()

    # Validate inputs
    required = {"timestamp", "OT"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        fig.add_annotation(
            text="Không có dữ liệu nhiệt độ dầu (OT) để hiển thị.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    df = frame.dropna(subset=["timestamp", "OT"]).sort_values("timestamp").copy()
    if df.empty:
        fig.add_annotation(
            text="Không có dữ liệu hợp lệ sau khi lọc.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Determine thermal regime if not present
    if "thermal_regime" not in df.columns:
        conditions = [
            df["OT"] >= CRITICAL_TEMP_THRESHOLD,
            df["OT"] >= WARNING_TEMP_THRESHOLD,
        ]
        choices = ["Critical", "Warning"]
        df["thermal_regime"] = np.select(conditions, choices, default="Normal")

    # Downsample background continuous line if dataset is very large
    n_points = len(df)
    if n_points > max_points:
        step = int(np.ceil(n_points / max_points))
        line_df = df.iloc[::step]
    else:
        line_df = df

    # Primary OT continuous line
    fig.add_trace(
        go.Scatter(
            x=line_df["timestamp"],
            y=line_df["OT"],
            mode="lines",
            name="OT (°C)",
            line={"color": _COLOUR_OT, "width": 1.5},
            customdata=line_df["thermal_regime"],
            hovertemplate=(
                "<b>Thời gian:</b> %{x|%Y-%m-%d %H:%M}<br>"
                "<b>Nhiệt độ dầu (OT):</b> %{y:.2f} °C<br>"
                "<b>Chế độ:</b> %{customdata}<extra></extra>"
            ),
        )
    )

    # Pop-out markers for Warning breach points (85°C <= OT < 95°C)
    warn_df = df[
        (df["OT"] >= WARNING_TEMP_THRESHOLD) & (df["OT"] < CRITICAL_TEMP_THRESHOLD)
    ]
    if not warn_df.empty:
        fig.add_trace(
            go.Scatter(
                x=warn_df["timestamp"],
                y=warn_df["OT"],
                mode="markers",
                name="Cảnh báo (≥85°C)",
                marker={
                    "color": _COLOUR_WARN,
                    "size": 5,
                    "symbol": "circle",
                    "line": {"color": "#FFFFFF", "width": 0.5},
                },
                hovertemplate=(
                    "<b>Cảnh báo vượt ngưỡng</b><br>"
                    "Thời gian: %{x|%Y-%m-%d %H:%M}<br>"
                    "OT: %{y:.2f} °C<extra></extra>"
                ),
            )
        )

    # Pop-out markers for Critical breach points (OT >= 95°C)
    crit_df = df[df["OT"] >= CRITICAL_TEMP_THRESHOLD]
    if not crit_df.empty:
        fig.add_trace(
            go.Scatter(
                x=crit_df["timestamp"],
                y=crit_df["OT"],
                mode="markers",
                name="Nguy cấp (≥95°C)",
                marker={
                    "color": _COLOUR_CRIT,
                    "size": 7,
                    "symbol": "diamond",
                    "line": {"color": "#FFFFFF", "width": 0.8},
                },
                hovertemplate=(
                    "<b>NGUY CẤP VƯỢT NGƯỠNG</b><br>"
                    "Thời gian: %{x|%Y-%m-%d %H:%M}<br>"
                    "OT: %{y:.2f} °C<extra></extra>"
                ),
            )
        )

    # Add shaded breach event spans if events_df is provided
    if events_df is not None and not events_df.empty:
        for _, ev in events_df.iterrows():
            th = float(ev.get("threshold_c", WARNING_TEMP_THRESHOLD))
            color = _BG_CRIT if th >= CRITICAL_TEMP_THRESHOLD else _BG_WARN
            fig.add_vrect(
                x0=ev["start_timestamp"],
                x1=ev["end_timestamp"],
                fillcolor=color,
                layer="below",
                line_width=0,
            )

    # Calculate y-axis bounds
    min_ot = float(df["OT"].min())
    max_ot = float(df["OT"].max())
    y_min = max(0.0, np.floor(min_ot - 5))
    y_max = max(105.0, np.ceil(max_ot + 5))

    # Add background shaded horizontal bands for Warning and Critical zones
    fig.add_hrect(
        y0=WARNING_TEMP_THRESHOLD,
        y1=CRITICAL_TEMP_THRESHOLD,
        fillcolor=_BG_WARN,
        layer="below",
        line_width=0,
    )
    fig.add_hrect(
        y0=CRITICAL_TEMP_THRESHOLD,
        y1=y_max,
        fillcolor=_BG_CRIT,
        layer="below",
        line_width=0,
    )

    # Add horizontal threshold reference lines
    fig.add_hline(
        y=WARNING_TEMP_THRESHOLD,
        line_dash="dash",
        line_color=_COLOUR_WARN,
        line_width=1.2,
        annotation_text="Ngưỡng cảnh báo: 85°C",
        annotation_position="top left",
        annotation_font={"size": 11, "color": _COLOUR_WARN},
    )
    fig.add_hline(
        y=CRITICAL_TEMP_THRESHOLD,
        line_dash="dot",
        line_color=_COLOUR_CRIT,
        line_width=1.5,
        annotation_text="Ngưỡng nguy cấp: 95°C",
        annotation_position="top left",
        annotation_font={"size": 11, "color": _COLOUR_CRIT, "family": "Arial-Bold"},
    )

    # Action title
    n_warn = len(warn_df)
    n_crit = len(crit_df)
    prefix = f"[{dataset_label}] " if dataset_label else ""
    if n_crit > 0:
        title_text = (
            f"<b>{prefix}Giám sát nhiệt độ dầu: Phát hiện {n_crit:,} điểm nguy cấp (≥95°C) "
            f"và {n_warn:,} điểm cảnh báo (≥85°C)</b>"
        )
    elif n_warn > 0:
        title_text = (
            f"<b>{prefix}Giám sát nhiệt độ dầu: Không có nguy cấp; {n_warn:,} điểm cảnh báo (≥85°C)</b>"
        )
    else:
        title_text = (
            f"<b>{prefix}Giám sát nhiệt độ dầu: Toàn bộ mẫu duy trì dưới ngưỡng cảnh báo 85°C</b>"
        )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.01,
            "y": 0.96,
            "font": {"size": 14, "color": "#1E293B"},
        },
        xaxis={
            "title": "Thời gian quan sát",
            "showgrid": True,
            "gridcolor": _GRID_LINE,
            "zeroline": False,
        },
        yaxis={
            "title": "Nhiệt độ dầu OT (°C)",
            "range": [y_min, y_max],
            "showgrid": True,
            "gridcolor": _GRID_LINE,
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
        margin={"l": 50, "r": 30, "t": 70, "b": 45},
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        height=height,
        width=width,
        hovermode="x unified",
    )

    return fig
