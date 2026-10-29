"""T0402: Safety & Risk Monitor Dashboard & Chart Modules (US-02).

Artifact: src/visuals/app_safety.py
Implements:
  - T0402a: build_small_multiples (6 synchronized subplots for HUFL..LULL sharing an interactive time axis)
  - T0402b: build_scatter_loess (Joint scatter of OT vs load branch with non-linear LOESS curve)
  - T0402c: build_regime_boxplots (Distribution box plots partitioned by Normal, Warning, Critical regimes)
  - compute_safety_kpis (Safety KPI metrics calculation for safety officers)

Input contract:
  - grid_features.parquet for Small Multiples, Scatter + LOESS, Regime Boxplots
  - thermal_breach_events.parquet for thermal breach intervals and stress metrics
Output:
  - plotly.graph_objects.Figure — interactive shared-axis zoom/pan, <2s render SLA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.visuals.time_series import gap_preserving_frame

from src.data.constants import (
    CRITICAL_TEMP_THRESHOLD,
    LOAD_BRANCHES,
    USEFUL_LOADS,
    WARNING_TEMP_THRESHOLD,
)

# Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS)
_COLOUR_NORMAL = "#1E3A8A"    # Navy
_COLOUR_USEFUL = "#0D9488"    # Teal
_COLOUR_UNUSEFUL = "#64748B"  # Slate
_COLOUR_WARN = "#D97706"      # Amber
_COLOUR_CRIT = "#DC2626"      # Crimson
_COLOUR_TREND = "#1E3A8A"     # Navy trend
_GRID_LINE = "#E2E8F0"        # Tufte grid line
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

_REGIME_COLORS: dict[str, str] = {
    "Normal": _COLOUR_NORMAL,
    "Warning": _COLOUR_WARN,
    "Critical": _COLOUR_CRIT,
}

_REGIME_ORDER = ("Normal", "Warning", "Critical")


# ---------------------------------------------------------------------------
# T0402a: Synchronized Small Multiples
# ---------------------------------------------------------------------------

def build_small_multiples(
    frame: pd.DataFrame,
    events_df: pd.DataFrame | None = None,
    dataset_label: str = "",
    height: int = 800,
    width: int | None = None,
    max_points: int = 8760,
) -> go.Figure:
    """Build 6 synchronized small multiple subplots with shared time X-axis (T0402a)."""
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

    df = frame.dropna(subset=["timestamp"]).sort_values("timestamp").copy()
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

    df = gap_preserving_frame(df, max_points)

    subplot_titles = [_BRANCH_DESCRIPTIONS.get(b, b) for b in LOAD_BRANCHES]

    fig = make_subplots(
        rows=6,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        subplot_titles=subplot_titles,
    )

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

        fig.update_yaxes(
            showgrid=True,
            gridcolor=_GRID_LINE,
            zeroline=True,
            zerolinecolor="#CBD5E1",
            zerolinewidth=1,
            row=idx,
            col=1,
        )

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


# ---------------------------------------------------------------------------
# T0402b: Joint Scatter + LOESS Smoothing
# ---------------------------------------------------------------------------

def build_scatter_loess(
    frame: pd.DataFrame,
    load_variable: str = "HUFL",
    loess_df: pd.DataFrame | None = None,
    dataset_label: str = "",
    season: str | None = None,
    height: int = 450,
    width: int | None = None,
    max_scatter_points: int = 4000,
) -> go.Figure:
    """Build Joint Scatter Plot with overlaid LOESS non-linear curve (T0402b)."""
    fig = go.Figure()

    required = {"OT", load_variable}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        fig.add_annotation(
            text=f"Thiếu cột OT hoặc {load_variable} để vẽ biểu đồ phân tán.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    df = frame.dropna(subset=["OT", load_variable]).copy()
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

    if "thermal_regime" not in df.columns:
        conditions = [
            df["OT"] >= CRITICAL_TEMP_THRESHOLD,
            df["OT"] >= WARNING_TEMP_THRESHOLD,
        ]
        choices = ["Critical", "Warning"]
        df["thermal_regime"] = np.select(conditions, choices, default="Normal")

    normal_df = df[df["thermal_regime"] == "Normal"]
    warn_df = df[df["thermal_regime"] == "Warning"]
    crit_df = df[df["thermal_regime"] == "Critical"]

    if len(normal_df) > max_scatter_points:
        step = int(np.ceil(len(normal_df) / max_scatter_points))
        normal_sampled = normal_df.iloc[::step]
    else:
        normal_sampled = normal_df

    if not normal_sampled.empty:
        fig.add_trace(
            go.Scattergl(
                x=normal_sampled[load_variable],
                y=normal_sampled["OT"],
                mode="markers",
                name="Bình thường (<85°C)",
                marker={
                    "color": _COLOUR_UNUSEFUL,
                    "size": 4,
                    "opacity": 0.35,
                },
                hovertemplate=(
                    f"<b>Bình thường</b><br>{load_variable}: %{{x:.2f}}<br>OT: %{{y:.2f}} °C<extra></extra>"
                ),
            )
        )

    if not warn_df.empty:
        fig.add_trace(
            go.Scatter(
                x=warn_df[load_variable],
                y=warn_df["OT"],
                mode="markers",
                name=f"Cảnh báo ≥85°C ({len(warn_df)})",
                marker={
                    "color": _COLOUR_WARN,
                    "size": 6,
                    "symbol": "circle",
                    "line": {"color": "#FFFFFF", "width": 0.5},
                },
                hovertemplate=(
                    f"<b>Cảnh báo</b><br>{load_variable}: %{{x:.2f}}<br>OT: %{{y:.2f}} °C<extra></extra>"
                ),
            )
        )

    if not crit_df.empty:
        fig.add_trace(
            go.Scatter(
                x=crit_df[load_variable],
                y=crit_df["OT"],
                mode="markers",
                name=f"Nguy cấp ≥95°C ({len(crit_df)})",
                marker={
                    "color": _COLOUR_CRIT,
                    "size": 8,
                    "symbol": "diamond",
                    "line": {"color": "#FFFFFF", "width": 0.8},
                },
                hovertemplate=(
                    f"<b>NGUY CẤP</b><br>{load_variable}: %{{x:.2f}}<br>OT: %{{y:.2f}} °C<extra></extra>"
                ),
            )
        )

    if loess_df is not None and not loess_df.empty and "loess_ot" in loess_df.columns:
        smooth_x = loess_df[
            "load_value" if "load_value" in loess_df else load_variable
        ].values
        smooth_y = loess_df["loess_ot"].values
    else:
        smooth_x, smooth_y = np.array([]), np.array([])
        fig.add_annotation(text="LOESS reference unavailable — run offline engine",
                           xref="paper", yref="paper", x=0, y=1.1,
                           showarrow=False)

    if len(smooth_x) > 0:
        fig.add_trace(
            go.Scatter(
                x=smooth_x,
                y=smooth_y,
                mode="lines",
                name="Đường hồi quy phi tuyến (LOESS)",
                line={"color": _COLOUR_TREND, "width": 2.5},
                hovertemplate=(
                    f"<b>LOESS Trend</b><br>{load_variable}: %{{x:.2f}}<br>OT kỳ vọng: %{{y:.2f}} °C<extra></extra>"
                ),
            )
        )

    fig.add_hline(
        y=WARNING_TEMP_THRESHOLD,
        line_dash="dash",
        line_color=_COLOUR_WARN,
        line_width=1.2,
        annotation_text="Ngưỡng 85°C",
        annotation_position="bottom right",
        annotation_font={"size": 10, "color": _COLOUR_WARN},
    )
    fig.add_hline(
        y=CRITICAL_TEMP_THRESHOLD,
        line_dash="dot",
        line_color=_COLOUR_CRIT,
        line_width=1.5,
        annotation_text="Ngưỡng 95°C",
        annotation_position="bottom right",
        annotation_font={"size": 10, "color": _COLOUR_CRIT},
    )

    prefix = f"[{dataset_label}] " if dataset_label else ""
    season_str = f" ({season})" if season else ""
    action_title = (
        f"<b>{prefix}Joint Scatter & LOESS: Tương quan phi tuyến giữa OT và {load_variable}{season_str}</b>"
    )

    fig.update_layout(
        title={
            "text": action_title,
            "x": 0.01,
            "y": 0.96,
            "font": {"size": 13, "color": "#1E293B"},
        },
        xaxis={
            "title": f"Tải {load_variable}",
            "showgrid": True,
            "gridcolor": _GRID_LINE,
            "zeroline": False,
        },
        yaxis={
            "title": "Nhiệt độ dầu OT (°C)",
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
        margin={"l": 50, "r": 30, "t": 60, "b": 45},
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        height=height,
        width=width,
        hovermode="closest",
    )

    return fig


# ---------------------------------------------------------------------------
# T0402c: Thermal Regime Boxplots
# ---------------------------------------------------------------------------

def build_regime_boxplots(
    frame: pd.DataFrame,
    variable: str = "OT",
    dataset_label: str = "",
    height: int = 400,
    width: int | None = None,
) -> go.Figure:
    """Build box plots of a variable across the three thermal regimes (T0402c)."""
    fig = go.Figure()

    if frame is None or frame.empty or variable not in frame.columns:
        fig.add_annotation(
            text=f"Không có dữ liệu cho biến '{variable}' để vẽ biểu đồ hộp.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    df = frame.dropna(subset=[variable]).copy()
    if df.empty:
        fig.add_annotation(
            text="Không có bản ghi hợp lệ sau khi loại bỏ giá trị khuyết.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
            font={"size": 14, "color": "#64748B"},
        )
        fig.update_layout(height=height, width=width)
        return fig

    if "thermal_regime" not in df.columns:
        if "OT" in df.columns:
            conditions = [
                df["OT"] >= CRITICAL_TEMP_THRESHOLD,
                df["OT"] >= WARNING_TEMP_THRESHOLD,
            ]
            choices = ["Critical", "Warning"]
            df["thermal_regime"] = np.select(conditions, choices, default="Normal")
        else:
            df["thermal_regime"] = "Normal"

    present_regimes = [r for r in _REGIME_ORDER if r in df["thermal_regime"].values]
    if not present_regimes:
        present_regimes = sorted(df["thermal_regime"].unique().tolist())

    for regime in present_regimes:
        sub_df = df[df["thermal_regime"] == regime]
        color = _REGIME_COLORS.get(regime, "#64748B")
        count = len(sub_df)

        fig.add_trace(
            go.Box(
                y=sub_df[variable],
                name=f"{regime} (n={count:,})",
                marker_color=color,
                boxmean=True,
                boxpoints="outliers",
                jitter=0.2,
                pointpos=-1.6,
                hoverinfo="all",
                customdata=[count] * count,
                hovertemplate=(
                    f"<b>Chế độ {regime}</b><br>"
                    f"{variable}: %{{y:.2f}}<extra></extra>"
                ),
            )
        )

    unit = "°C" if variable == "OT" else "Tải"
    prefix = f"[{dataset_label}] " if dataset_label else ""
    action_title = (
        f"<b>{prefix}Phân phối {variable} theo 3 chế độ nhiệt (Normal · Warning · Critical)</b>"
    )

    fig.update_layout(
        title={
            "text": action_title,
            "x": 0.01,
            "y": 0.96,
            "font": {"size": 13, "color": "#1E293B"},
        },
        xaxis={
            "title": "Chế độ nhiệt độ",
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={
            "title": f"{variable} ({unit})",
            "showgrid": True,
            "gridcolor": _GRID_LINE,
            "zeroline": False,
        },
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        height=height,
        width=width,
        margin={"l": 55, "r": 25, "t": 60, "b": 45},
        showlegend=False,
    )

    if variable == "OT":
        fig.add_hline(
            y=WARNING_TEMP_THRESHOLD,
            line_dash="dash",
            line_color=_COLOUR_WARN,
            line_width=1.2,
            annotation_text="85°C",
            annotation_position="right",
            annotation_font={"size": 10, "color": _COLOUR_WARN},
        )
        fig.add_hline(
            y=CRITICAL_TEMP_THRESHOLD,
            line_dash="dot",
            line_color=_COLOUR_CRIT,
            line_width=1.5,
            annotation_text="95°C",
            annotation_position="right",
            annotation_font={"size": 10, "color": _COLOUR_CRIT},
        )

    return fig


# ---------------------------------------------------------------------------
# Safety KPIs Helper
# ---------------------------------------------------------------------------

def compute_safety_kpis(
    feat_ds: pd.DataFrame | None,
    ev_ds: pd.DataFrame | None,
) -> dict[str, float | int]:
    """Calculate safety KPIs (events, critical count, peak OT, accumulated degree-hours)."""
    total_events = len(ev_ds) if ev_ds is not None else 0
    crit_events = (
        len(ev_ds[ev_ds["threshold_c"] >= 95.0]) if ev_ds is not None else 0
    )
    max_ot = (
        float(feat_ds["OT"].max())
        if (feat_ds is not None and "OT" in feat_ds.columns and len(feat_ds) > 0)
        else float("nan")
    )
    metrics = {
        "total_events": total_events,
        "crit_events": crit_events,
        "max_ot": max_ot,
    }
    for threshold, prefix in ((85.0, "warning"), (95.0, "critical")):
        sub = ev_ds.loc[ev_ds.threshold_c.eq(threshold)] if ev_ds is not None else None
        for column in ("degree_hours", "duration_hours"):
            metrics[f"{prefix}_{column}"] = (
                float(sub[column].sum()) if sub is not None else float("nan"))
    return metrics
