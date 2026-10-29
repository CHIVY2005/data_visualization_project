"""T0303: Operational Manager Dashboard & Chart Modules (US-01).

Artifact: src/visuals/app_manager.py
Implements:
  - T0303a: build_stacked_bar (100% Stacked Bar: Useful vs Unuseful load by hour across 3 voltage tiers)
  - T0303b: build_lag_heatmap (Lag cross-correlation heatmap with peak |r| annotation)
  - compute_manager_kpis (KPI cards calculation for dispatchers)

Input contract:
  - grid_features.parquet for Stacked Bar
  - lag_matrix.parquet / lag_correlation_matrix.json for Lag Heatmap
Output:
  - plotly.graph_objects.Figure — CPU-only, clean Tufte aesthetics, <2s render SLA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from src.data.constants import LOAD_BRANCHES

# --- Project colour palette (AGENTS §CODE & VISUALIZATION STANDARDS) ---
_COLOUR_OT = "#1E3A8A"          # Navy
_COLOUR_USEFUL = "#0D9488"      # Teal
_COLOUR_CONTEXT = "#64748B"     # Slate
_COLOUR_WARN = "#D97706"        # Amber
_COLOUR_CRIT = "#DC2626"        # Crimson
_GRID_LINE = "#E2E8F0"          # Tufte grid line

_TIERS: list[tuple[str, str, str]] = [
    ("High",   "HUFL", "HULL"),
    ("Middle", "MUFL", "MULL"),
    ("Low",    "LUFL", "LULL"),
]
_TIER_USEFUL_COLOURS = ["#0D9488", "#0F766E", "#14B8A6"]
_TIER_UNUSEFUL_COLOURS = ["#64748B", "#475569", "#94A3B8"]

_COLORSCALE_DIV = [
    [0.0, "#B45309"],    # Brown/orange — negative association, not thermal alert
    [0.5, "#F8FAFC"],    # near-white — zero
    [1.0, "#1E3A8A"],    # Navy — strong positive
]


# ---------------------------------------------------------------------------
# T0303a: 100% Stacked Bar
# ---------------------------------------------------------------------------

def _hourly_mean_fraction(
    frame: pd.DataFrame,
    season: str | None,
) -> pd.DataFrame:
    """Compute mean fraction (useful / total) per hour for each voltage tier."""
    df = frame.copy()
    if season is not None and "season" in df.columns:
        df = df[df["season"] == season]

    rows = []
    for tier_label, useful_col, unuseful_col in _TIERS:
        if useful_col not in df.columns or unuseful_col not in df.columns:
            continue
        for hour in range(24):
            hour_data = df[df["hour"] == hour]
            useful_vals = pd.to_numeric(
                hour_data[useful_col], errors="coerce"
            )
            unuseful_vals = pd.to_numeric(
                hour_data[unuseful_col], errors="coerce"
            )
            total = useful_vals + unuseful_vals
            valid = ((total > 0) & useful_vals.ge(0) & unuseful_vals.ge(0)
                     & np.isfinite(useful_vals) & np.isfinite(unuseful_vals))
            if valid.any():
                useful_frac = (useful_vals[valid] / total[valid]).mean()
                unuseful_frac = 1.0 - float(useful_frac)
            else:
                useful_frac = np.nan
                unuseful_frac = np.nan
            rows.append({
                "hour": hour,
                "tier": tier_label,
                "useful_frac": float(useful_frac),
                "unuseful_frac": float(unuseful_frac),
            })
    return pd.DataFrame(rows)


def build_stacked_bar(
    frame: pd.DataFrame,
    season: str | None = None,
    dataset_label: str = "",
    show_all_tiers: bool = True,
    selected_tier: str = "High",
    height: int = 380,
    width: int = 760,
) -> go.Figure:
    """Return a 100% stacked bar chart of useful vs unuseful load by hour (T0303a)."""
    required = {"hour", "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing load columns for stacked bar: {sorted(missing)}")
    if frame.empty:
        raise ValueError("Frame must contain at least one sample")
    if season is not None and not frame["season"].eq(season).any():
        raise ValueError("No data after filtering — check season")

    frac_df = _hourly_mean_fraction(frame, season)
    if frac_df.empty:
        raise ValueError("No valid fraction data computed — check input frame values")

    tiers_to_plot = [t[0] for t in _TIERS] if show_all_tiers else [selected_tier]
    n_tiers = len(tiers_to_plot)

    fig = make_subplots(
        rows=1,
        cols=n_tiers,
        shared_yaxes=True,
        subplot_titles=[f"{t} Voltage Tier" for t in tiers_to_plot],
        horizontal_spacing=0.06,
    )
    selected = frame if season is None else frame.loc[frame.season.eq(season)]
    invalid = sum(int(((selected[u] < 0) | (selected[v] < 0) |
                       (selected[u] + selected[v] <= 0) |
                       selected[u].isna() | selected[v].isna()).sum())
                  for _, u, v in _TIERS)
    if invalid:
        fig.add_annotation(text=f"Quality: {invalid:,} invalid tier-samples excluded; no clipping",
                           xref="paper", yref="paper", x=0, y=-0.25,
                           showarrow=False)

    hours = list(range(24))

    for col_idx, tier_name in enumerate(tiers_to_plot, start=1):
        tier_data = frac_df[frac_df["tier"] == tier_name].sort_values("hour")
        tier_idx = [t[0] for t in _TIERS].index(tier_name)
        useful_colour = _TIER_USEFUL_COLOURS[tier_idx]
        unuseful_colour = _TIER_UNUSEFUL_COLOURS[tier_idx]

        u_frac = tier_data["useful_frac"].tolist()
        un_frac = tier_data["unuseful_frac"].tolist()

        show_legend = col_idx == 1

        fig.add_trace(go.Bar(
            x=hours,
            y=u_frac,
            name="Useful Load",
            marker_color=useful_colour,
            showlegend=show_legend,
            hovertemplate=(
                f"{tier_name} Voltage<br>Hour: %{{x}}:00<br>"
                "Useful: %{y:.1%}<extra></extra>"
            ),
        ), row=1, col=col_idx)

        fig.add_trace(go.Bar(
            x=hours,
            y=un_frac,
            name="Unuseful Load",
            marker_color=unuseful_colour,
            showlegend=show_legend,
            hovertemplate=(
                f"{tier_name} Voltage<br>Hour: %{{x}}:00<br>"
                "Unuseful: %{y:.1%}<extra></extra>"
            ),
        ), row=1, col=col_idx)

        fig.add_hline(
            y=0.5,
            line={"color": "white", "dash": "dot", "width": 1},
            row=1, col=col_idx,
        )

    season_label = f" — {season}" if season else ""
    title_text = (
        f"Hourly Load Composition: Useful vs Unuseful (100% Stacked){season_label}"
        + (f" [{dataset_label}]" if dataset_label else "")
    )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.5, "xanchor": "center",
            "font": {"size": 14, "color": "#1E293B"},
        },
        barmode="stack",
        height=height,
        width=width,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 11},
        margin={"l": 60, "r": 40, "t": 60, "b": 50},
        legend={
            "orientation": "h",
            "x": 0.5, "xanchor": "center",
            "y": -0.18,
            "font": {"size": 11},
        },
    )

    for c in range(1, n_tiers + 1):
        fig.update_xaxes(
            title_text="Hour" if c == (n_tiers // 2 + 1) else "",
            tickmode="linear", tick0=0, dtick=4,
            range=[-0.5, 23.5],
            gridcolor=_GRID_LINE,
            showgrid=False,
            row=1, col=c,
        )
    fig.update_yaxes(
        title_text="Load Share",
        tickformat=".0%",
        range=[0, 1],
        gridcolor=_GRID_LINE,
        showgrid=True,
        row=1, col=1,
    )

    return fig


# ---------------------------------------------------------------------------
# T0303b: Lag Cross-Correlation Heatmap
# ---------------------------------------------------------------------------

def build_lag_heatmap(
    lag_df: pd.DataFrame,
    dataset: str | None = None,
    season: str | None = None,
    method: str = "pearson",
    dataset_label: str = "",
    annotate_peak: bool = True,
    height: int = 360,
    width: int = 720,
) -> go.Figure:
    """Return a lag cross-correlation heatmap figure (T0303b)."""
    required = {"load_variable", "lag_hour", "correlation"}
    missing = required - set(lag_df.columns)
    if missing:
        raise ValueError(f"Missing lag columns: {sorted(missing)}")

    df = lag_df.copy()
    if dataset is not None and "dataset" in df.columns:
        df = df[df["dataset"] == dataset]
    if season is not None and "season" in df.columns:
        df = df[df["season"] == season]
    if "method" in df.columns:
        df = df[df["method"] == method]
    if df.empty:
        raise ValueError("No data after filtering — check season/method parameters")

    variables = [v for v in LOAD_BRANCHES if v in df["load_variable"].unique()]
    lags = sorted(df["lag_hour"].unique().tolist())

    z: list[list[float | None]] = []
    peak_marks: list[tuple[int, int]] = []

    for var_idx, variable in enumerate(variables):
        var_data = df[df["load_variable"] == variable]
        row: list[float | None] = []
        peak_lag: int | None = None
        peak_abs = -1.0

        for lag_idx, lag in enumerate(lags):
            lag_row = var_data[var_data["lag_hour"] == lag]
            if not lag_row.empty:
                val = float(lag_row["correlation"].iloc[0])
                if np.isnan(val):
                    row.append(None)
                else:
                    row.append(val)
                    if abs(val) > peak_abs:
                        peak_abs = abs(val)
                        peak_lag = lag_idx
            else:
                row.append(None)

        z.append(row)
        if annotate_peak and peak_lag is not None and peak_abs > 0.05:
            peak_marks.append((var_idx, peak_lag))

    x_labels = [f"k={lag}h" for lag in lags]
    y_labels = variables

    fig = go.Figure()

    fig.add_trace(go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        zmin=-1.0,
        zmax=1.0,
        zmid=0.0,
        colorscale=_COLORSCALE_DIV,
        colorbar={
            "title": {"text": "r", "side": "right"},
            "tickvals": [-1.0, -0.5, 0.0, 0.5, 1.0],
            "tickfont": {"size": 10},
            "len": 0.9,
        },
        hovertemplate=(
            "Load: %{y}<br>Lag: %{x}<br>"
            "r(load(t), OT(t+k)): %{z:.3f}<extra></extra>"
        ),
        xgap=2,
        ygap=2,
    ))

    # Star annotation for peak |r| per variable
    for var_idx, lag_idx in peak_marks:
        val = z[var_idx][lag_idx]
        text_val = f"★\n{val:.2f}" if val is not None else "★"
        fig.add_annotation(
            x=x_labels[lag_idx],
            y=y_labels[var_idx],
            text=text_val,
            showarrow=False,
            font={"size": 10, "color": "white" if abs(val or 0) > 0.5 else "#1E293B"},
        )

    season_label = f" — {season}" if season else ""
    title_text = (
        f"Lag Cross-Correlation Heatmap: r(load(t), OT(t+k)){season_label}"
        + (f" [{dataset_label or dataset or ''}]" if (dataset_label or dataset) else "")
    )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.5, "xanchor": "center",
            "font": {"size": 13, "color": "#1E293B"},
        },
        height=height,
        width=width,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 11},
        margin={"l": 80, "r": 80, "t": 60, "b": 50},
        xaxis={
            "title": "Lag k (hours OT leads after load)",
            "showgrid": False,
            "zeroline": False,
        },
        yaxis={
            "title": "Load Variable",
            "autorange": "reversed",
            "showgrid": False,
            "zeroline": False,
        },
    )

    return fig


# ---------------------------------------------------------------------------
# Operational Manager KPIs Helper
# ---------------------------------------------------------------------------

def compute_manager_kpis(
    frame: pd.DataFrame,
    season: str | None = None,
) -> dict[str, float | int]:
    """Calculate operational KPIs for dispatchers."""
    df = frame.copy()
    if season and "season" in df.columns:
        df = df[df["season"] == season]

    total_samples = len(df)
    ot_mean = float(df["OT"].mean()) if (total_samples > 0 and "OT" in df.columns) else float("nan")
    ot_max = float(df["OT"].max()) if (total_samples > 0 and "OT" in df.columns) else float("nan")
    warn_count = int(df["OT"].ge(85).sum()) if (total_samples > 0 and "OT" in df.columns) else 0
    valid_ot = df["OT"].notna().sum() if "OT" in df else 0
    warn_pct = warn_count / valid_ot * 100 if valid_ot else float("nan")

    return {
        "sample_count": total_samples,
        "ot_mean": ot_mean,
        "ot_max": ot_max,
        "warn_count": warn_count,
        "warn_pct": warn_pct,
    }
