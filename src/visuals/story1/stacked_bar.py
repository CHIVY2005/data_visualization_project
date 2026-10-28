"""T0303a: 100% Stacked Bar — useful/unuseful load composition by hour for US-01.

What:  Stacked bar chart where each bar represents one hour; segments show the
       share of useful load (HUFL/MUFL/LUFL) vs unuseful load (HULL/MULL/LULL)
       within each voltage tier (High / Middle / Low).
Why:   Operational Manager needs to compare power factor across tiers and hours
       to identify maintenance priorities and dispatch adjustments.
How:   Plotly bar traces with 'relative' barmode (100% stacking via normalised
       fractions); faceted by voltage tier; season filter; direct labels for
       readability; no colour-only encoding (shape + label as backup).

Input contract: grid_features.parquet columns
  dataset, timestamp, hour, season, HUFL, HULL, MUFL, MULL, LUFL, LULL,
  HUFL_ratio, MUFL_ratio, LUFL_ratio (fractions 0..1)
Output: plotly.graph_objects.Figure — no Streamlit, no heavy computation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Project colour palette
_COLOUR_OT = "#1E3A8A"
_COLOUR_USEFUL = "#0D9488"
_COLOUR_CONTEXT = "#64748B"
_COLOUR_WARN = "#D97706"
_COLOUR_CRIT = "#DC2626"
_GRID_LINE = "#E2E8F0"

# Voltage tiers and their useful/unuseful column pairs
_TIERS: list[tuple[str, str, str]] = [
    ("High",   "HUFL", "HULL"),
    ("Middle", "MUFL", "MULL"),
    ("Low",    "LUFL", "LULL"),
]

# Teal shades for useful; slate shades for unuseful (per AGENTS colour rules)
_TIER_USEFUL_COLOURS = ["#0D9488", "#0F766E", "#14B8A6"]
_TIER_UNUSEFUL_COLOURS = ["#64748B", "#475569", "#94A3B8"]


def _hourly_mean_fraction(
    frame: pd.DataFrame, season: str | None, tier_pairs: list[tuple[str, str]],
) -> pd.DataFrame:
    """Compute mean fraction (useful / total) per hour for each tier.

    Returns DataFrame with columns: hour, tier, useful_frac, unuseful_frac.
    Invalid/negative loads → null (not forced to 100%).
    """
    df = frame.copy()
    if season is not None and "season" in df.columns:
        df = df[df["season"] == season]

    rows = []
    for tier_label, useful_col, unuseful_col in zip(
        [t[0] for t in _TIERS], [t[1] for t in _TIERS], [t[2] for t in _TIERS],
    ):
        if useful_col not in df.columns or unuseful_col not in df.columns:
            continue
        for hour in range(24):
            hour_data = df[df["hour"] == hour]
            useful_vals = pd.to_numeric(
                hour_data[useful_col], errors="coerce"
            ).clip(lower=0)
            unuseful_vals = pd.to_numeric(
                hour_data[unuseful_col], errors="coerce"
            ).clip(lower=0)
            total = useful_vals + unuseful_vals
            valid = (total > 0) & useful_vals.notna() & unuseful_vals.notna()
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
    """Return a 100% stacked bar chart of useful vs unuseful load by hour.

    Parameters
    ----------
    frame:
        Grid-features DataFrame for a **single** dataset.
    season:
        'Dry' or 'Wet' — filter to this season; None uses all seasons.
    dataset_label:
        Source dataset name in the figure title.
    show_all_tiers:
        If True, create three vertically stacked subplots (one per tier).
        If False, show only the tier specified by selected_tier.
    selected_tier:
        Active tier when show_all_tiers is False ('High', 'Middle', 'Low').
    height, width:
        Figure dimensions in pixels.
    """
    tier_pairs = [(t[1], t[2]) for t in _TIERS]
    summary = _hourly_mean_fraction(frame, season, tier_pairs)
    if summary.empty:
        raise ValueError("No data after filtering — check season parameter")

    tiers = [t[0] for t in _TIERS] if show_all_tiers else [selected_tier]
    n_rows = len(tiers)

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=[f"{t} Voltage Tier" for t in tiers],
    )

    for row_idx, tier in enumerate(tiers, start=1):
        tier_data = summary[summary["tier"] == tier].sort_values("hour")
        hours = tier_data["hour"].tolist()
        useful_fracs = tier_data["useful_frac"].tolist()
        unuseful_fracs = tier_data["unuseful_frac"].tolist()

        colour_idx = [t[0] for t in _TIERS].index(tier)
        useful_colour = _TIER_USEFUL_COLOURS[colour_idx]
        unuseful_colour = _TIER_UNUSEFUL_COLOURS[colour_idx]

        # Useful load segment (bottom)
        fig.add_trace(go.Bar(
            x=hours,
            y=[f * 100 for f in useful_fracs],
            name=f"Useful ({tier})",
            marker_color=useful_colour,
            hovertemplate=(
                f"Hour: %{{x}}:00<br>Useful: %{{y:.1f}}%"
                f"<extra>{tier} tier</extra>"
            ),
            legendgroup=tier,
            showlegend=(row_idx == 1 or not show_all_tiers),
        ), row=row_idx, col=1)

        # Unuseful load segment (top)
        fig.add_trace(go.Bar(
            x=hours,
            y=[f * 100 if not np.isnan(f) else 0 for f in unuseful_fracs],
            name=f"Unuseful ({tier})",
            marker_color=unuseful_colour,
            hovertemplate=(
                f"Hour: %{{x}}:00<br>Unuseful: %{{y:.1f}}%"
                f"<extra>{tier} tier</extra>"
            ),
            legendgroup=tier,
            showlegend=(row_idx == 1 or not show_all_tiers),
        ), row=row_idx, col=1)

        # Y-axis for this subplot
        fig.update_yaxes(
            title_text="Share (%)",
            range=[0, 101],
            tickvals=[0, 25, 50, 75, 100],
            gridcolor=_GRID_LINE,
            row=row_idx, col=1,
        )

    season_label = f" — {season} Season" if season else " — All Seasons"
    title_text = (
        f"Load Composition by Hour{season_label}"
        + (f" [{dataset_label}]" if dataset_label else "")
    )

    fig.update_layout(
        title={
            "text": title_text,
            "x": 0.5, "xanchor": "center",
            "font": {"size": 14, "color": "#1E293B"},
        },
        barmode="stack",
        height=height * n_rows // max(n_rows, 1) * n_rows,
        width=width,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font={"family": "Inter, Roboto, Arial, sans-serif", "size": 11},
        legend={
            "orientation": "h",
            "yanchor": "bottom", "y": 1.01, "x": 0,
            "font": {"size": 10},
        },
        margin={"l": 55, "r": 30, "t": 70, "b": 45},
    )

    fig.update_xaxes(
        title_text="Hour of Day",
        tickmode="linear", tick0=0, dtick=4,
        range=[-0.5, 23.5],
        gridcolor=_GRID_LINE,
        row=n_rows, col=1,
    )
    for row_idx in range(1, n_rows + 1):
        fig.update_xaxes(showgrid=False, row=row_idx, col=1)
    fig.update_xaxes(showgrid=True, gridcolor=_GRID_LINE, row=n_rows, col=1)

    return fig
