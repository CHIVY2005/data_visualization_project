"""WP03 + WP04 Plotly visualization modules — read-only artifact consumers.

Canonical Charter Modules:
  - charts_manager: T0301 Calendar Heatmap + T0302 STL Panels & Hourly Quantile Fan
  - app_manager:    T0303 100% Stacked Bar + Lag Cross-Correlation Heatmap & Manager KPIs
  - charts_safety:  T0401 OT Threshold Monitoring Chart + Barcode Rug Plot
  - app_safety:     T0402 Synchronized Small Multiples + Joint Scatter LOESS & Regime Boxplots
  - action_titles:  T0502 Evidence-based dynamic Action Titles per FilterState
"""

from src.visuals.action_titles import (
    TitleContext,
    build_context,
    calendar_heatmap_title,
    stl_title,
    quantile_fan_title,
    stacked_bar_title,
    lag_heatmap_title,
    ot_threshold_title,
    barcode_rug_title,
    small_multiples_title,
    loess_scatter_title,
    regime_boxplots_title,
)
from src.visuals.app_manager import (
    build_lag_heatmap,
    build_stacked_bar,
    compute_manager_kpis,
)
from src.visuals.app_safety import (
    build_regime_boxplots,
    build_scatter_loess,
    build_small_multiples,
    compute_safety_kpis,
)
from src.visuals.charts_manager import (
    build_calendar_heatmap,
    build_quantile_fan,
    build_stl_panels,
)
from src.visuals.charts_safety import (
    build_barcode_rug,
    build_ot_threshold_chart,
)

__all__ = [
    # Story 1 (Manager)
    "build_calendar_heatmap",
    "build_stl_panels",
    "build_quantile_fan",
    "build_stacked_bar",
    "build_lag_heatmap",
    "compute_manager_kpis",
    # Story 2 (Safety)
    "build_ot_threshold_chart",
    "build_barcode_rug",
    "build_small_multiples",
    "build_scatter_loess",
    "build_regime_boxplots",
    "compute_safety_kpis",
    # T0502 Action Titles
    "TitleContext",
    "build_context",
    "calendar_heatmap_title",
    "stl_title",
    "quantile_fan_title",
    "stacked_bar_title",
    "lag_heatmap_title",
    "ot_threshold_title",
    "barcode_rug_title",
    "small_multiples_title",
    "loess_scatter_title",
    "regime_boxplots_title",
]
