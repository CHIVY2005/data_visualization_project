"""WP03 Plotly visualization modules — read-only artifact consumers.

Canonical Charter Modules:
  - charts_manager: T0301 Calendar Heatmap + T0302 STL Panels & Hourly Quantile Fan
  - app_manager:    T0303 100% Stacked Bar + Lag Cross-Correlation Heatmap & Manager KPIs
"""

from src.visuals.app_manager import (
    build_lag_heatmap,
    build_stacked_bar,
    compute_manager_kpis,
)
from src.visuals.charts_manager import (
    build_calendar_heatmap,
    build_quantile_fan,
    build_stl_panels,
)

__all__ = [
    "build_calendar_heatmap",
    "build_stl_panels",
    "build_quantile_fan",
    "build_stacked_bar",
    "build_lag_heatmap",
    "compute_manager_kpis",
]
