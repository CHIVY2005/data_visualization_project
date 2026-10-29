"""T0401: Safety & Risk Monitor Chart Modules (US-02).

Artifact: src/visuals/charts_safety.py
Implements:
  - T0401a: build_ot_threshold_chart (OT line chart with 85°C/95°C hazard bands,
            pop-out breach markers, and shaded breach spans)
  - T0401b: build_barcode_rug (Temporal barcode/rug plot of thermal breach events)

Input contract:
  - grid_features.parquet for OT Threshold Chart
  - thermal_breach_events.parquet for Barcode Rug Plot & shaded spans
Output:
  - plotly.graph_objects.Figure — CPU-only, responsive, <2s render SLA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    WARNING_TEMP_THRESHOLD,
)
from src.visuals.time_series import gap_preserving_frame

# Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS)
_COLOUR_OT = "#1E3A8A"        # Navy — OT line
_COLOUR_WARN = "#D97706"      # Amber — 85°C Warning
_COLOUR_CRIT = "#DC2626"      # Crimson — 95°C Critical
_GRID_LINE = "#E2E8F0"        # Tufte grid line
_BG_WARN = "rgba(217, 119, 6, 0.12)"   # Warning band fill
_BG_CRIT = "rgba(220, 38, 38, 0.18)"   # Critical band fill


# ---------------------------------------------------------------------------
# T0401a: OT Threshold Monitoring Chart
# ---------------------------------------------------------------------------

def build_ot_threshold_chart(
    frame: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    dataset_label: str = "",
    height: int = 440,
    width: int | None = None,
    max_points: int = 8760,
) -> go.Figure:
    """Build OT threshold monitoring chart with warning and critical regimes."""
    fig = go.Figure()

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

    df = frame.dropna(subset=["timestamp"]).sort_values("timestamp").copy()
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

    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    if "thermal_regime" not in df.columns:
        conditions = [
            df["OT"] >= CRITICAL_TEMP_THRESHOLD,
            df["OT"] >= WARNING_TEMP_THRESHOLD,
        ]
        choices = ["Critical", "Warning"]
        df["thermal_regime"] = np.select(conditions, choices, default="Normal")

    line_df = gap_preserving_frame(df, max_points)

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

    min_ot = float(df["OT"].min())
    max_ot = float(df["OT"].max())
    y_min = max(0.0, np.floor(min_ot - 5))
    y_max = max(105.0, np.ceil(max_ot + 5))

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


# ---------------------------------------------------------------------------
# T0401b: Barcode / Rug Plot
# ---------------------------------------------------------------------------

def build_barcode_rug(
    events_df: pd.DataFrame | None,
    threshold_c: float | None = None,
    dataset_label: str = "",
    height: int = 180,
    width: int | None = None,
    time_range: tuple[pd.Timestamp, pd.Timestamp] | None = None,
) -> go.Figure:
    """Build a Barcode/Rug plot for thermal breach incidents."""
    fig = go.Figure()
    prefix = f"[{dataset_label}] " if dataset_label else ""

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

    if not pd.api.types.is_datetime64_any_dtype(df["start_timestamp"]):
        df["start_timestamp"] = pd.to_datetime(df["start_timestamp"])
    if not pd.api.types.is_datetime64_any_dtype(df["end_timestamp"]):
        df["end_timestamp"] = pd.to_datetime(df["end_timestamp"])

    crit_events = df[df["threshold_c"] >= CRITICAL_TEMP_THRESHOLD]
    warn_events = df[
        (df["threshold_c"] >= WARNING_TEMP_THRESHOLD)
        & (df["threshold_c"] < CRITICAL_TEMP_THRESHOLD)
    ]

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
