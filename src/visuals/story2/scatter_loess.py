"""T0402: Joint Scatter Plot + Non-linear LOESS Smoothing (US-02).

What:  Joint scatter plot of Oil Temperature (OT) on Y-axis vs a load branch on X-axis,
       stratified by thermal regime (Normal, Warning, Critical), with an overlaid
       non-linear LOESS smoothing curve.
Why:   Safety & Risk Monitor needs to diagnose non-linear saturation effects and identify
       load levels triggering disproportionate temperature rises.
How:   Plotly graph_objects Figure with points colour-coded by regime (Slate for Normal,
       Amber for Warning, Crimson for Critical), horizontal threshold lines at 85/95°C,
       and a LOESS non-linear trend line (using precomputed artifact or lightweight
       local regression fallback).

Input contract:
  frame: pd.DataFrame with at least ['OT', load_variable]
  load_variable: str, default 'HUFL'
  loess_df (optional): pd.DataFrame with [load_variable, 'loess_ot']
Output:
  plotly.graph_objects.Figure — interactive scatter with smooth curve, <2s render.
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
_COLOUR_NORMAL = "#64748B"    # Slate — Normal regime
_COLOUR_WARN = "#D97706"      # Amber — 85°C Warning
_COLOUR_CRIT = "#DC2626"      # Crimson — 95°C Critical
_COLOUR_TREND = "#1E3A8A"     # Navy — LOESS non-linear trend
_GRID_LINE = "#E2E8F0"        # Tufte grid line


def _compute_local_smooth(
    x_vals: np.ndarray, y_vals: np.ndarray, n_bins: int = 50
) -> tuple[np.ndarray, np.ndarray]:
    """Compute lightweight binned local regression when no LOESS artifact is supplied."""
    if len(x_vals) == 0:
        return np.array([]), np.array([])
    # Try statsmodels if available in the environment
    try:
        from statsmodels.nonparametric.smoothers_lowess import lowess

        # Downsample sample size to <= 500 for instant compute
        if len(x_vals) > 500:
            idx = np.linspace(0, len(x_vals) - 1, 500, dtype=int)
            x_s, y_s = x_vals[idx], y_vals[idx]
        else:
            x_s, y_s = x_vals, y_vals
        res = lowess(y_s, x_s, frac=0.3, return_sorted=True)
        return res[:, 0], res[:, 1]
    except ImportError:
        pass

    # Pure numpy fast binned median/mean fallback (<5ms)
    sort_idx = np.argsort(x_vals)
    xs = x_vals[sort_idx]
    ys = y_vals[sort_idx]

    # Partition into quantile bins
    bins = np.array_split(np.arange(len(xs)), min(n_bins, len(xs)))
    b_x = np.array([xs[b].mean() for b in bins if len(b) > 0])
    b_y = np.array([ys[b].mean() for b in bins if len(b) > 0])
    return b_x, b_y


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
    """Build Joint Scatter Plot with overlaid LOESS non-linear curve.

    Parameters
    ----------
    frame : pd.DataFrame
        DataFrame containing 'OT' and the specified load_variable.
    load_variable : str, default 'HUFL'
        The load branch on the X-axis (e.g. 'HUFL', 'HULL', 'MUFL', etc.).
    loess_df : pd.DataFrame | None, default None
        Optional precomputed LOESS dataframe with [load_variable, 'loess_ot'].
    dataset_label : str, default ""
        Dataset name for title display.
    season : str | None, default None
        Optional season tag for title display.
    height : int, default 450
        Figure height in pixels.
    width : int | None, default None
        Figure width in pixels.
    max_scatter_points : int, default 4000
        Maximum scatter points to render to preserve interactive responsiveness.

    Returns
    -------
    plotly.graph_objects.Figure
    """
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

    # Ensure thermal_regime column
    if "thermal_regime" not in df.columns:
        conditions = [
            df["OT"] >= CRITICAL_TEMP_THRESHOLD,
            df["OT"] >= WARNING_TEMP_THRESHOLD,
        ]
        choices = ["Critical", "Warning"]
        df["thermal_regime"] = np.select(conditions, choices, default="Normal")

    # Downsample points for scatter if too dense, but keep all Warning and Critical points
    normal_df = df[df["thermal_regime"] == "Normal"]
    warn_df = df[df["thermal_regime"] == "Warning"]
    crit_df = df[df["thermal_regime"] == "Critical"]

    if len(normal_df) > max_scatter_points:
        step = int(np.ceil(len(normal_df) / max_scatter_points))
        normal_sampled = normal_df.iloc[::step]
    else:
        normal_sampled = normal_df

    # 1. Normal points trace (Slate)
    if not normal_sampled.empty:
        fig.add_trace(
            go.Scattergl(
                x=normal_sampled[load_variable],
                y=normal_sampled["OT"],
                mode="markers",
                name="Bình thường (<85°C)",
                marker={
                    "color": _COLOUR_NORMAL,
                    "size": 4,
                    "opacity": 0.35,
                },
                hovertemplate=(
                    f"<b>Bình thường</b><br>{load_variable}: %{{x:.2f}}<br>OT: %{{y:.2f}} °C<extra></extra>"
                ),
            )
        )

    # 2. Warning points trace (Amber)
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

    # 3. Critical points trace (Crimson)
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

    # 4. Non-linear LOESS smoothing curve
    if loess_df is not None and not loess_df.empty and "loess_ot" in loess_df.columns:
        smooth_x = loess_df[load_variable].values
        smooth_y = loess_df["loess_ot"].values
    else:
        x_all = df[load_variable].to_numpy(dtype=float)
        y_all = df["OT"].to_numpy(dtype=float)
        smooth_x, smooth_y = _compute_local_smooth(x_all, y_all)

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

    # Add threshold reference lines
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
