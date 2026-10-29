"""T0502 — Evidence-based Action Titles generator.

Each chart must have a title that reflects:
- What data is shown (dataset, season, variable, date window)
- What the chart evidences (pattern, threshold breaches, composition)

Per AGENTS §CODE & VISUALIZATION STANDARDS:
  "Action Titles có bằng chứng theo bộ lọc; thiếu dữ liệu → tiêu đề trung thực,
   không bịa insight."

All functions return plain strings; no Streamlit import.
Caller formats the final markdown heading (e.g. with st.markdown).

Thresholds 85/95°C are project conventions, not certified standards.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TitleContext:
    """Structured evidence carried into title generation.

    dataset:   ETTh1 / ETTh2 / ETTm1
    season:    "Dry" | "Wet" | None (= All)
    start:     inclusive timestamp
    end:       exclusive timestamp
    variable:  "OT" | "HUFL" | ... | "LULL"
    n_samples: number of observed rows in the filtered scope
    """

    dataset: str
    season: str | None
    start: pd.Timestamp
    end: pd.Timestamp
    variable: str
    n_samples: int

    # Optional evidence fields (pass None when unavailable)
    ot_mean: float | None = None
    ot_max: float | None = None
    warn_pct: float | None = None       # fraction ≥85°C, already in [0,1] * 100
    n_warning_events: int | None = None
    n_critical_events: int | None = None
    warning_dh: float | None = None
    critical_dh: float | None = None
    warning_dur_h: float | None = None
    critical_dur_h: float | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scope_tag(ctx: TitleContext) -> str:
    """Compact scope label: 'ETTh1 · Dry · 2016-01-01 → 2016-06-30'."""
    season = ctx.season or "All seasons"
    start = ctx.start.strftime("%Y-%m-%d")
    end = (ctx.end - pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # re-make inclusive
    return f"{ctx.dataset} · {season} · {start} → {end}"


def _na(val: float | None) -> bool:
    """True when value is None or NaN."""
    return val is None or (isinstance(val, float) and math.isnan(val))


def _fmt(val: float, decimals: int = 1, suffix: str = "") -> str:
    return f"{val:.{decimals}f}{suffix}"


# ---------------------------------------------------------------------------
# Per-chart title builders
# ---------------------------------------------------------------------------

def calendar_heatmap_title(ctx: TitleContext, agg: str = "mean") -> str:
    """Action title for Calendar Heatmap (T0301)."""
    agg_word = {"mean": "Average", "max": "Peak", "min": "Minimum"}.get(agg, agg.title())
    scope = _scope_tag(ctx)

    if ctx.variable == "OT":
        if not _na(ctx.ot_max) and ctx.ot_max >= 85:  # type: ignore[operator]
            evidence = (
                f"Peak OT reached {_fmt(ctx.ot_max, 1)}°C "  # type: ignore[arg-type]
                f"(≥85°C Warning threshold) in scope"
            )
        elif not _na(ctx.ot_mean):
            evidence = f"Mean OT = {_fmt(ctx.ot_mean, 1)}°C across scope"  # type: ignore[arg-type]
        else:
            evidence = "OT distribution shown; no breach evidence in scope"
        return f"{agg_word} Daily OT — {evidence} [{scope}]"

    return f"{agg_word} Daily {ctx.variable} — Seasonal cycle [{scope}]"


def stl_title(ctx: TitleContext) -> str:
    """Action title for STL Decomposition panels (T0302a)."""
    scope = _scope_tag(ctx)
    if ctx.variable == "OT":
        if not _na(ctx.ot_max) and ctx.ot_max >= 85:  # type: ignore[operator]
            peak = _fmt(ctx.ot_max, 1)  # type: ignore[arg-type]
            return (
                f"OT STL Decomposition — Peak {peak}°C; "
                f"trend + daily seasonality separated [{scope}]"
            )
        return (
            f"OT STL Decomposition — Trend and daily cycle below 85°C [{scope}]"
        )
    return f"STL Decomposition — {ctx.variable} [{scope}]"


def quantile_fan_title(ctx: TitleContext) -> str:
    """Action title for Hourly Quantile Fan (T0302b)."""
    season_str = ctx.season or "all seasons"
    if ctx.variable == "OT":
        return (
            f"Hourly OT Distribution — Historical 50/80/95% empirical bands, "
            f"{ctx.dataset} {season_str} "
            f"(full-history reference; bands fixed, not Date Range re-computed)"
        )
    return (
        f"Hourly {ctx.variable} Distribution — 50/80/95% empirical bands, "
        f"{ctx.dataset} {season_str} (full-history reference)"
    )


def stacked_bar_title(ctx: TitleContext) -> str:
    """Action title for 100% Stacked Bar (T0303a)."""
    scope = _scope_tag(ctx)
    return (
        f"Load Composition by Hour — Useful vs Unuseful share across 3 voltage tiers "
        f"[{scope}]"
    )


def lag_heatmap_title(ctx: TitleContext) -> str:
    """Action title for Lag Cross-Correlation Heatmap (T0303b)."""
    season_str = ctx.season or "all seasons"
    return (
        f"Lag Correlation r(load(t), OT(t+k)) — Loads lead OT by 0–12 h, "
        f"{ctx.dataset} {season_str} "
        f"(full-history Pearson; not recomputed for Date Range)"
    )


def ot_threshold_title(ctx: TitleContext) -> str:
    """Action title for OT Threshold Monitoring chart (T0401a)."""
    scope = _scope_tag(ctx)
    if not _na(ctx.n_warning_events):
        n_warn = ctx.n_warning_events or 0
        n_crit = ctx.n_critical_events or 0
        if n_warn == 0 and n_crit == 0:
            evidence = "no breach events in scope"
        else:
            parts = []
            if n_warn:
                wdur = (
                    f" ({_fmt(ctx.warning_dur_h)}h)"
                    if not _na(ctx.warning_dur_h) and ctx.warning_dur_h  # type: ignore[operator]
                    else ""
                )
                parts.append(f"{n_warn} Warning{wdur}")
            if n_crit:
                cdur = (
                    f" ({_fmt(ctx.critical_dur_h)}h)"
                    if not _na(ctx.critical_dur_h) and ctx.critical_dur_h  # type: ignore[operator]
                    else ""
                )
                parts.append(f"{n_crit} Critical{cdur}")
            evidence = "events: " + ", ".join(parts)
    else:
        evidence = "events unavailable (run engine)"
    return f"OT Threshold Monitoring — {evidence} [{scope}]"


def barcode_rug_title(ctx: TitleContext) -> str:
    """Action title for Barcode/Rug temporal breach plot (T0401b)."""
    scope = _scope_tag(ctx)
    n_warn = ctx.n_warning_events
    n_crit = ctx.n_critical_events
    if n_warn is not None and n_crit is not None:
        total = n_warn + n_crit
        if total == 0:
            return f"Thermal Breach Timeline — No events in scope [{scope}]"
        wdh = (
            f", {_fmt(ctx.warning_dh)}°C·h"
            if not _na(ctx.warning_dh) and ctx.warning_dh  # type: ignore[operator]
            else ""
        )
        cdh = (
            f", {_fmt(ctx.critical_dh)}°C·h"
            if not _na(ctx.critical_dh) and ctx.critical_dh  # type: ignore[operator]
            else ""
        )
        return (
            f"Thermal Breach Timeline — {n_warn} Warning{wdh} · "
            f"{n_crit} Critical{cdh} (complete events only) [{scope}]"
        )
    return f"Thermal Breach Timeline — Events artifact unavailable [{scope}]"


def small_multiples_title(ctx: TitleContext) -> str:
    """Action title for Synchronized Small Multiples (T0402a)."""
    scope = _scope_tag(ctx)
    if not _na(ctx.n_warning_events):
        n_ev = (ctx.n_warning_events or 0) + (ctx.n_critical_events or 0)
        ev_str = f"; {n_ev} breach events highlighted" if n_ev else "; no breach events"
    else:
        ev_str = ""
    return (
        f"6-Branch Load Surveillance — Synchronized time axis (zoom/pan all){ev_str} "
        f"[{scope}]"
    )


def loess_scatter_title(ctx: TitleContext, load_variable: str = "HUFL") -> str:
    """Action title for Joint Scatter + LOESS (T0402b)."""
    season_str = ctx.season or "all seasons"
    return (
        f"OT vs {load_variable} Scatter — Non-linear LOESS reference, "
        f"{ctx.dataset} {season_str} "
        f"(saved full-history curve; not a Date Range refit)"
    )


def regime_boxplots_title(ctx: TitleContext) -> str:
    """Action title for Thermal Regime Boxplots (T0402c)."""
    scope = _scope_tag(ctx)
    var = ctx.variable
    n = ctx.n_samples
    return (
        f"{var} Distribution by Thermal Regime — "
        f"Normal / Warning (≥85°C) / Critical (≥95°C) across {n:,} samples [{scope}]"
    )


# ---------------------------------------------------------------------------
# Convenience: build TitleContext from KPI dicts
# ---------------------------------------------------------------------------

def build_context(
    state_dataset: str,
    state_season: str | None,
    state_start: pd.Timestamp,
    state_end: pd.Timestamp,
    variable: str,
    n_samples: int,
    manager_kpis: dict | None = None,
    safety_kpis: dict | None = None,
    events: "pd.DataFrame | None" = None,
) -> TitleContext:
    """Assemble TitleContext from filter state + KPI dicts + events DataFrame.

    manager_kpis: output of compute_manager_kpis()
    safety_kpis: output of compute_safety_kpis()
    events: filtered thermal_breach_events DataFrame
    """
    mk = manager_kpis or {}
    sk = safety_kpis or {}

    n_warn: int | None = None
    n_crit: int | None = None
    warn_dh: float | None = None
    crit_dh: float | None = None
    warn_dur: float | None = None
    crit_dur: float | None = None

    if events is not None:
        n_warn = int((events["threshold_c"] == 85.0).sum())
        n_crit = int((events["threshold_c"] == 95.0).sum())
        warn_ev = events.loc[events["threshold_c"] == 85.0]
        crit_ev = events.loc[events["threshold_c"] == 95.0]
        warn_dh = float(warn_ev["degree_hours"].sum()) if not warn_ev.empty else 0.0
        crit_dh = float(crit_ev["degree_hours"].sum()) if not crit_ev.empty else 0.0
        warn_dur = float(warn_ev["duration_hours"].sum()) if not warn_ev.empty else 0.0
        crit_dur = float(crit_ev["duration_hours"].sum()) if not crit_ev.empty else 0.0

    return TitleContext(
        dataset=state_dataset,
        season=state_season,
        start=state_start,
        end=state_end,
        variable=variable,
        n_samples=n_samples,
        ot_mean=mk.get("ot_mean"),
        ot_max=mk.get("ot_max"),
        warn_pct=mk.get("warn_pct"),
        n_warning_events=n_warn,
        n_critical_events=n_crit,
        warning_dh=warn_dh,
        critical_dh=crit_dh,
        warning_dur_h=warn_dur,
        critical_dur_h=crit_dur,
    )
