"""T0301/T0302/T0303: Unit tests for Story 1 Plotly chart modules.

All tests use synthetic fixtures; no raw ETT data is read.
Dependencies: plotly, pandas, numpy (no statsmodels/streamlit required).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.data.constants import (
    CLEAN_COLUMNS,
    CRITICAL_TEMP_THRESHOLD,
    LOAD_BRANCHES,
    WARNING_TEMP_THRESHOLD,
)
from src.data import feature_builder as fb


# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

def _feature_frame(rows: int = 240, dataset: str = "ETTh1") -> pd.DataFrame:
    """Build a grid-features fixture without touching repository raw data."""
    t = np.arange(rows, dtype="float64")
    daily = np.sin(2 * np.pi * t / 24)
    clean = pd.DataFrame({
        "dataset": pd.Series([dataset] * rows, dtype="string"),
        "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h").astype(
            "datetime64[ns]"
        ),
        "OT": (30 + 5 * daily).astype("float32"),
        "HUFL": (10 + daily).astype("float32"),
        "HULL": (5 + daily * 0.5).astype("float32"),
        "MUFL": (8 + daily * 0.8).astype("float32"),
        "MULL": (4 + daily * 0.4).astype("float32"),
        "LUFL": (6 + daily * 0.6).astype("float32"),
        "LULL": (3 + daily * 0.3).astype("float32"),
    })
    clean["total_useful_load"] = clean[["HUFL", "MUFL", "LUFL"]].sum(
        axis=1
    ).astype("float32")
    clean["total_unuseful_load"] = clean[["HULL", "MULL", "LULL"]].sum(
        axis=1
    ).astype("float32")
    clean["reactive_ratio"] = (
        clean["total_unuseful_load"] / clean["total_useful_load"]
    ).astype("float32")
    clean["thermal_regime"] = fb.classify_thermal_regime(clean["OT"])
    clean["is_imputed"] = False
    clean = clean.loc[:, CLEAN_COLUMNS]
    return fb.build_grid_features(clean)


def _stl_df(rows: int = 240, variable: str = "OT") -> pd.DataFrame:
    """Minimal synthetic STL record (record_type == 'stl')."""
    t = np.arange(rows, dtype="float64")
    observed = 30 + 5 * np.sin(2 * np.pi * t / 24)
    trend = 30 + 0.01 * t
    seasonal = 5 * np.sin(2 * np.pi * t / 24)
    residual = observed - trend - seasonal
    return pd.DataFrame({
        "dataset": pd.Series(["ETTh1"] * rows, dtype="string"),
        "record_type": "stl",
        "variable": variable,
        "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h").astype(
            "datetime64[ns]"
        ),
        "season": pd.NA,
        "hour": pd.NA,
        "observed": observed.astype("float32"),
        "trend": trend.astype("float32"),
        "seasonal": seasonal.astype("float32"),
        "residual": residual.astype("float32"),
        "mean": np.nan,
        "median": np.nan,
        "std": np.nan,
        "sample_count": pd.NA,
    })


def _quantile_bands_df(variable: str = "OT", season: str = "Dry") -> pd.DataFrame:
    """Synthetic hourly quantile bands for one variable/season (24 rows)."""
    rows = []
    for hour in range(24):
        base = 30 + 3 * np.sin(2 * np.pi * hour / 24)
        rows.append({
            "dataset": "ETTh1",
            "variable": variable,
            "season": season,
            "hour": hour,
            "sample_count": 100,
            "mean": float(base),
            "q025": float(base - 5),
            "q10":  float(base - 3.5),
            "q25":  float(base - 2),
            "q50":  float(base),
            "q75":  float(base + 2),
            "q90":  float(base + 3.5),
            "q975": float(base + 5),
        })
    return pd.DataFrame(rows)


def _lag_df(season: str = "Dry", method: str = "pearson") -> pd.DataFrame:
    """Synthetic lag matrix DataFrame for 6 load variables × 13 lags."""
    rows = []
    for variable in LOAD_BRANCHES:
        peak_idx = 3  # simulated peak at lag 3
        for lag in range(13):
            corr = float(np.sin(np.pi * lag / 12))  # monotone shape
            abs_corr = abs(corr)
            rows.append({
                "dataset": "ETTh1",
                "season": season,
                "method": method,
                "load_variable": variable,
                "lag_hour": lag,
                "correlation": corr,
                "abs_correlation": abs_corr,
                "sample_count": 200,
                "is_peak_abs": (lag == peak_idx),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# T0301: Calendar Heatmap
# ---------------------------------------------------------------------------

class TestT0301CalendarHeatmap:
    """T0301: calendar_heatmap.build_calendar_heatmap."""

    @pytest.fixture(autouse=True)
    def _import(self) -> None:
        pytest.importorskip("plotly")
        from src.visuals.story1 import calendar_heatmap as cm
        self.cm = cm

    def test_returns_figure(self) -> None:
        frame = _feature_frame(rows=240)
        fig = self.cm.build_calendar_heatmap(frame, variable="OT")
        assert fig is not None
        assert hasattr(fig, "data"), "Expected a Plotly Figure"

    def test_has_heatmap_trace(self) -> None:
        frame = _feature_frame(rows=240)
        fig = self.cm.build_calendar_heatmap(frame, variable="OT")
        import plotly.graph_objects as go
        trace_types = [type(t) for t in fig.data]
        assert go.Heatmap in trace_types

    def test_title_contains_variable(self) -> None:
        frame = _feature_frame(rows=240)
        fig = self.cm.build_calendar_heatmap(frame, variable="HUFL")
        title = fig.layout.title.text
        assert "HUFL" in title

    def test_raises_on_unknown_variable(self) -> None:
        frame = _feature_frame(rows=120)
        with pytest.raises(ValueError, match="not found"):
            self.cm.build_calendar_heatmap(frame, variable="NONEXISTENT")

    def test_raises_on_empty_frame(self) -> None:
        frame = _feature_frame(rows=240).iloc[:0]
        with pytest.raises(ValueError, match="at least one sample"):
            self.cm.build_calendar_heatmap(frame)

    def test_dataset_label_in_title(self) -> None:
        frame = _feature_frame(rows=240)
        fig = self.cm.build_calendar_heatmap(
            frame, variable="OT", dataset_label="ETTh1"
        )
        assert "ETTh1" in fig.layout.title.text


# ---------------------------------------------------------------------------
# T0302a: STL Panels
# ---------------------------------------------------------------------------

class TestT0302STLPanels:
    """T0302: stl_panels.build_stl_panels."""

    @pytest.fixture(autouse=True)
    def _import(self) -> None:
        pytest.importorskip("plotly")
        from src.visuals.story1 import stl_panels as sp
        self.sp = sp

    def test_returns_figure(self) -> None:
        df = _stl_df(rows=240)
        fig = self.sp.build_stl_panels(df, variable="OT")
        assert fig is not None
        assert hasattr(fig, "data")

    def test_four_panels_exist(self) -> None:
        """Observed, Trend, Seasonal, Residual panels should all be present."""
        import plotly.graph_objects as go
        df = _stl_df(rows=240)
        fig = self.sp.build_stl_panels(df, variable="OT")
        # Four subplots means at least 4 traces (scatter + bars)
        assert len(fig.data) >= 4

    def test_raises_on_missing_column(self) -> None:
        df = _stl_df(rows=240).drop(columns=["trend"])
        with pytest.raises(ValueError, match="Missing STL columns"):
            self.sp.build_stl_panels(df)

    def test_raises_on_empty_df(self) -> None:
        df = _stl_df(rows=240).iloc[:0]
        with pytest.raises(ValueError, match="not be empty"):
            self.sp.build_stl_panels(df)

    def test_downsampling_does_not_crash(self) -> None:
        """Large dataframe: max_points=50 should stride without error."""
        df = _stl_df(rows=500)
        fig = self.sp.build_stl_panels(df, variable="OT", max_points=50)
        assert fig is not None

    def test_title_contains_variable_and_label(self) -> None:
        df = _stl_df(rows=240, variable="HUFL")
        fig = self.sp.build_stl_panels(df, variable="HUFL", dataset_label="ETTh2")
        title = fig.layout.title.text
        assert "HUFL" in title
        assert "ETTh2" in title


# ---------------------------------------------------------------------------
# T0302b: Quantile Fan
# ---------------------------------------------------------------------------

class TestT0302QuantileFan:
    """T0302: quantile_fan.build_quantile_fan."""

    @pytest.fixture(autouse=True)
    def _import(self) -> None:
        pytest.importorskip("plotly")
        from src.visuals.story1 import quantile_fan as qf
        self.qf = qf

    def test_returns_figure(self) -> None:
        df = _quantile_bands_df(variable="OT", season="Dry")
        fig = self.qf.build_quantile_fan(df, variable="OT", season="Dry")
        assert fig is not None
        assert hasattr(fig, "data")

    def test_has_24_hour_range(self) -> None:
        """Median trace must cover hours 0..23."""
        import plotly.graph_objects as go
        df = _quantile_bands_df()
        fig = self.qf.build_quantile_fan(df, variable="OT", season="Dry")
        scatter_traces = [t for t in fig.data if isinstance(t, go.Scatter)]
        # Median trace should have 24 x-values
        median_trace = next(
            (t for t in scatter_traces if "Median" in (t.name or "")), None
        )
        assert median_trace is not None
        assert len(median_trace.x) == 24

    def test_raises_on_missing_quantile_column(self) -> None:
        df = _quantile_bands_df().drop(columns=["q50"])
        with pytest.raises(ValueError, match="Missing quantile columns"):
            self.qf.build_quantile_fan(df)

    def test_raises_on_empty_after_filter(self) -> None:
        df = _quantile_bands_df(season="Dry")
        with pytest.raises(ValueError, match="No data after filtering"):
            self.qf.build_quantile_fan(df, variable="OT", season="Wet")

    def test_ot_threshold_lines_added(self) -> None:
        """OT fan must include Warning/Critical threshold lines."""
        import plotly.graph_objects as go
        df = _quantile_bands_df(variable="OT")
        fig = self.qf.build_quantile_fan(df, variable="OT", season="Dry")
        # Threshold lines are added via add_hline → layout shapes
        shapes = fig.layout.shapes or []
        y_values = {float(s.y0) for s in shapes if hasattr(s, "y0")}
        assert WARNING_TEMP_THRESHOLD in y_values or any(
            abs(y - WARNING_TEMP_THRESHOLD) < 0.01 for y in y_values
        ), "Warning threshold line expected"

    def test_mean_line_hidden_when_disabled(self) -> None:
        import plotly.graph_objects as go
        df = _quantile_bands_df()
        fig = self.qf.build_quantile_fan(
            df, variable="OT", season="Dry", show_mean=False
        )
        scatter_names = [t.name for t in fig.data if isinstance(t, go.Scatter)]
        assert not any("Mean" in (n or "") for n in scatter_names)


# ---------------------------------------------------------------------------
# T0303a: 100% Stacked Bar
# ---------------------------------------------------------------------------

class TestT0303StackedBar:
    """T0303: stacked_bar.build_stacked_bar."""

    @pytest.fixture(autouse=True)
    def _import(self) -> None:
        pytest.importorskip("plotly")
        from src.visuals.story1 import stacked_bar as sb
        self.sb = sb

    def test_returns_figure(self) -> None:
        frame = _feature_frame(rows=240)
        fig = self.sb.build_stacked_bar(frame)
        assert fig is not None
        assert hasattr(fig, "data")

    def test_barmode_is_stack(self) -> None:
        frame = _feature_frame(rows=240)
        fig = self.sb.build_stacked_bar(frame)
        assert fig.layout.barmode == "stack"

    def test_season_filter(self) -> None:
        frame = _feature_frame(rows=480)
        fig_dry = self.sb.build_stacked_bar(frame, season="Dry")
        assert fig_dry is not None

    def test_single_tier_mode(self) -> None:
        import plotly.graph_objects as go
        frame = _feature_frame(rows=240)
        fig = self.sb.build_stacked_bar(
            frame, show_all_tiers=False, selected_tier="High"
        )
        bar_traces = [t for t in fig.data if isinstance(t, go.Bar)]
        # Only High tier: useful + unuseful = 2 traces
        assert len(bar_traces) == 2

    def test_raises_on_empty_after_filter(self) -> None:
        frame = _feature_frame(rows=240)
        # No rows will have season='NoSeason'
        with pytest.raises(ValueError, match="No data after filtering"):
            self.sb.build_stacked_bar(frame, season="NoSeason")

    def test_title_contains_season(self) -> None:
        frame = _feature_frame(rows=480)
        fig = self.sb.build_stacked_bar(frame, season="Wet", dataset_label="ETTh1")
        title = fig.layout.title.text
        assert "Wet" in title
        assert "ETTh1" in title


# ---------------------------------------------------------------------------
# T0303b: Lag Heatmap
# ---------------------------------------------------------------------------

class TestT0303LagHeatmap:
    """T0303: lag_heatmap.build_lag_heatmap."""

    @pytest.fixture(autouse=True)
    def _import(self) -> None:
        pytest.importorskip("plotly")
        from src.visuals.story1 import lag_heatmap as lh
        self.lh = lh

    def test_returns_figure(self) -> None:
        df = _lag_df()
        fig = self.lh.build_lag_heatmap(df, season="Dry", method="pearson")
        assert fig is not None
        assert hasattr(fig, "data")

    def test_heatmap_z_shape(self) -> None:
        """Z matrix must be 6 variables × 13 lags."""
        import plotly.graph_objects as go
        df = _lag_df()
        fig = self.lh.build_lag_heatmap(df, season="Dry", method="pearson")
        hm = next(t for t in fig.data if isinstance(t, go.Heatmap))
        z = hm.z
        assert len(z) == 6, f"Expected 6 load variables, got {len(z)}"
        assert len(z[0]) == 13, f"Expected 13 lags, got {len(z[0])}"

    def test_raises_on_missing_column(self) -> None:
        df = _lag_df().drop(columns=["correlation"])
        with pytest.raises(ValueError, match="Missing lag columns"):
            self.lh.build_lag_heatmap(df)

    def test_raises_on_empty_after_filter(self) -> None:
        df = _lag_df(season="Dry")
        with pytest.raises(ValueError, match="No data after filtering"):
            self.lh.build_lag_heatmap(df, season="Wet", method="pearson")

    def test_spearman_method_filter(self) -> None:
        df = pd.concat([_lag_df(method="pearson"), _lag_df(method="spearman")])
        fig = self.lh.build_lag_heatmap(df, season="Dry", method="spearman")
        assert fig is not None

    def test_colorscale_diverges_around_zero(self) -> None:
        """Colorscale midpoint should be 0 (zmid=0)."""
        import plotly.graph_objects as go
        df = _lag_df()
        fig = self.lh.build_lag_heatmap(df, season="Dry")
        hm = next(t for t in fig.data if isinstance(t, go.Heatmap))
        assert hm.zmid == 0.0

    def test_colorbar_range(self) -> None:
        import plotly.graph_objects as go
        df = _lag_df()
        fig = self.lh.build_lag_heatmap(df, season="Dry")
        hm = next(t for t in fig.data if isinstance(t, go.Heatmap))
        assert hm.zmin == -1.0
        assert hm.zmax == 1.0
