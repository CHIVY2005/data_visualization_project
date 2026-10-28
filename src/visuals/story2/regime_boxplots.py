"""T0402: Thermal Regime Boxplots — Distribution by Safety Regimes (US-02).

What:  Box plots comparing the distribution of OT (or any load variable) grouped by
       thermal regime: Normal (<85°C), Warning [85°C, 95°C), and Critical (≥95°C).
Why:   Safety & Risk Monitor needs to evaluate distribution spread, median shifts,
       and extreme outlier behavior under normal versus elevated thermal stresses.
How:   Plotly graph_objects Figure with ordered boxes [Normal, Warning, Critical],
       using Navy/Slate for Normal, Amber for Warning, and Crimson for Critical.

Input contract:
  frame: pd.DataFrame with at least ['thermal_regime', variable] (variable defaults to 'OT')
Output:
  plotly.graph_objects.Figure — clean Tufte styling, <2s render.
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
_COLOUR_NORMAL = "#1E3A8A"    # Navy — Normal regime
_COLOUR_WARN = "#D97706"      # Amber — Warning
_COLOUR_CRIT = "#DC2626"      # Crimson — Critical
_GRID_LINE = "#E2E8F0"        # Tufte grid line

_REGIME_COLORS: dict[str, str] = {
    "Normal": _COLOUR_NORMAL,
    "Warning": _COLOUR_WARN,
    "Critical": _COLOUR_CRIT,
}

_REGIME_ORDER = ("Normal", "Warning", "Critical")


def build_regime_boxplots(
    frame: pd.DataFrame,
    variable: str = "OT",
    dataset_label: str = "",
    height: int = 400,
    width: int | None = None,
) -> go.Figure:
    """Build box plots of a variable across the three thermal regimes.

    Parameters
    ----------
    frame : pd.DataFrame
        DataFrame containing at least the variable to plot and optionally 'thermal_regime'.
    variable : str, default 'OT'
        The numeric variable to plot distributions for (e.g. 'OT', 'HUFL', 'total_useful_load').
    dataset_label : str, default ""
        Dataset name for title display.
    height : int, default 400
        Figure height in pixels.
    width : int | None, default None
        Figure width in pixels.

    Returns
    -------
    plotly.graph_objects.Figure
    """
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

    # Ensure thermal_regime is present
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

    # Add a box trace for each regime present in the data
    present_regimes = [r for r in _REGIME_ORDER if r in df["thermal_regime"].values]

    if not present_regimes:
        # Fallback if categories are custom/unknown
        present_regimes = sorted(df["thermal_regime"].unique().tolist())

    for regime in present_regimes:
        sub_df = df[df["thermal_regime"] == regime]
        color = _REGIME_COLORS.get(regime, "#64748B")
        count = len(sub_df)
        median_val = float(sub_df[variable].median()) if count > 0 else 0.0

        fig.add_trace(
            go.Box(
                y=sub_df[variable],
                name=f"{regime} (n={count:,})",
                marker_color=color,
                boxmean=True,  # displays mean as dashed line
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

    # Unit label
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

    # If variable is OT, add threshold reference lines
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
