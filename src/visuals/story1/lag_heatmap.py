"""T0303b: Lag Cross-Correlation Heatmap — load vs OT lag for US-01.

What:  Heatmap with load variables on Y-axis and lag hours 0..12 on X-axis;
       colour encodes Pearson or Spearman correlation r(load(t), OT(t+k)).
Why:   Operational Manager needs to see which load branch leads OT and by how
       many hours, to anticipate overheating risk and adjust dispatch timing.
How:   Plotly heatmap with diverging colorscale centred at zero; peak lag
       annotated per load variable; season and method selectable.

Input contract: lag_matrix.parquet (or lag_correlation_matrix.json records)
  dataset, season, method, load_variable, lag_hour, correlation, is_peak_abs
Output: plotly.graph_objects.Figure — no Streamlit, no heavy computation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.data.constants import LOAD_BRANCHES

# Project colour palette
_COLOUR_OT = "#1E3A8A"
_COLOUR_USEFUL = "#0D9488"
_COLOUR_WARN = "#D97706"
_COLOUR_CRIT = "#DC2626"
_GRID_LINE = "#E2E8F0"

# Diverging scale: Crimson (neg) → White (zero) → Navy (pos)
_COLORSCALE_DIV = [
    [0.0, "#DC2626"],    # Crimson — strong negative
    [0.5, "#F8FAFC"],   # near-white — zero
    [1.0, "#1E3A8A"],   # Navy — strong positive
]

_LAG_HOURS = list(range(13))   # 0..12


def build_lag_heatmap(
    lag_df: pd.DataFrame,
    season: str | None = None,
    method: str = "pearson",
    dataset_label: str = "",
    annotate_peak: bool = True,
    height: int = 360,
    width: int = 720,
) -> go.Figure:
    """Return a lag cross-correlation heatmap figure.

    Parameters
    ----------
    lag_df:
        Slice of lag_matrix.parquet for a **single dataset**.
        Expected columns: season, method, load_variable, lag_hour, correlation,
        is_peak_abs (bool).
    season:
        'Dry' or 'Wet' — filter to this season; None uses all seasons (averaged).
    method:
        'pearson' or 'spearman' — selects the correlation method row.
    dataset_label:
        Source dataset name displayed in the figure title.
    annotate_peak:
        If True, mark the peak-|r| lag per load variable with a star symbol.
    height, width:
        Figure dimensions in pixels.
    """
    required = {"load_variable", "lag_hour", "correlation"}
    missing = required - set(lag_df.columns)
    if missing:
        raise ValueError(f"Missing lag columns: {sorted(missing)}")

    df = lag_df.copy()

    # Filter season
    if season is not None and "season" in df.columns:
        df = df[df["season"] == season]

    # Filter method
    if "method" in df.columns:
        df = df[df["method"] == method]

    if df.empty:
        raise ValueError("No data after filtering — check season/method parameters")

    # Build pivot: load_variable × lag_hour
    variables = [v for v in LOAD_BRANCHES if v in df["load_variable"].unique()]
    lags = sorted(df["lag_hour"].unique().tolist())

    z: list[list[float | None]] = []
    peak_marks: list[tuple[int, int]] = []   # (var_idx, lag_idx) for peak labels

    for var_idx, variable in enumerate(variables):
        var_data = df[df["load_variable"] == variable]
        row: list[float | None] = []
        peak_lag: int | None = None
        peak_abs = -1.0

        for lag_idx, lag in enumerate(lags):
            lag_row = var_data[var_data["lag_hour"] == lag]
            if lag_row.empty:
                row.append(None)
                continue
            corr = lag_row["correlation"].iloc[0]
            val = float(corr) if pd.notna(corr) and np.isfinite(float(corr)) else None
            row.append(val)
            if val is not None and abs(val) > peak_abs:
                peak_abs = abs(val)
                peak_lag = lag_idx

        z.append(row)
        if annotate_peak and peak_lag is not None:
            peak_marks.append((var_idx, peak_lag))

    # Build annotation text matrix
    text = []
    for var_idx, row in enumerate(z):
        text_row = []
        for lag_idx, val in enumerate(row):
            if (var_idx, lag_idx) in peak_marks:
                text_row.append("★")
            elif val is not None:
                text_row.append(f"{val:.2f}")
            else:
                text_row.append("")
        text.append(text_row)

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"Lag {k}h" for k in lags],
        y=variables,
        zmin=-1.0,
        zmid=0.0,
        zmax=1.0,
        colorscale=_COLORSCALE_DIV,
        text=text,
        texttemplate="%{text}",
        textfont={"size": 9},
        showscale=True,
        colorbar={
            "title": {"text": f"r ({method})", "side": "right"},
            "tickvals": [-1, -0.5, 0, 0.5, 1],
            "ticktext": ["−1", "−0.5", "0", "+0.5", "+1"],
            "tickfont": {"size": 10},
            "len": 0.9,
        },
        hovertemplate=(
            "Load: %{y}<br>Lag: %{x}<br>r = %{z:.3f}"
            "<extra>corr(load(t), OT(t+k))</extra>"
        ),
        xgap=2,
        ygap=2,
    ))

    season_label = f" — {season}" if season else ""
    method_label = method.capitalize()
    title_text = (
        f"{method_label} Lag Correlation: Load → OT{season_label}"
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
            "title": "Lag (hours): r(load(t), OT(t+k))",
            "gridcolor": _GRID_LINE,
            "showgrid": False,
        },
        yaxis={
            "title": "Load Variable",
            "gridcolor": _GRID_LINE,
            "showgrid": False,
            "categoryorder": "array",
            "categoryarray": variables,
        },
        margin={"l": 70, "r": 80, "t": 65, "b": 50},
    )

    # Annotation note: positive lag = load leads OT
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0, y=-0.12,
        text="★ = peak |r| per load variable. Positive lag: load(t) predicts OT(t+k).",
        showarrow=False,
        font={"size": 9, "color": _GRID_LINE.replace("E2E8F0", "64748B")},
        align="left",
    )

    return fig
