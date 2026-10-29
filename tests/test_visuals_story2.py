"""T0401/T0402: Unit tests for Story 2 Plotly chart modules (Safety & Risk Monitor).

All tests use synthetic fixtures; no raw ETT data is read.
Dependencies: plotly, pandas, numpy.
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
from src.visuals.charts_safety import (
    build_barcode_rug,
    build_ot_threshold_chart,
)
from src.visuals.app_safety import (
    build_regime_boxplots,
    build_scatter_loess,
    build_small_multiples,
)


# ---------------------------------------------------------------------------
# Shared synthetic fixtures
# ---------------------------------------------------------------------------

def _feature_frame(rows: int = 240, dataset: str = "ETTh1") -> pd.DataFrame:
    """Build a synthetic grid-features fixture with normal, warning, and critical OT."""
    t = np.arange(rows, dtype="float64")
    # Base sine wave + spikes to trigger Warning (>=85) and Critical (>=95)
    ot = 40.0 + 15.0 * np.sin(2 * np.pi * t / 24)
    # Inject breach spikes
    ot[20:25] = 88.0   # Warning
    ot[50:54] = 97.0   # Critical

    clean = pd.DataFrame({
        "dataset": pd.Series([dataset] * rows, dtype="string"),
        "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h").astype(
            "datetime64[ns]"
        ),
        "OT": ot.astype("float32"),
        "HUFL": (15 + 2 * np.sin(2 * np.pi * t / 24)).astype("float32"),
        "HULL": (6 + np.cos(2 * np.pi * t / 24)).astype("float32"),
        "MUFL": (12 + 1.5 * np.sin(2 * np.pi * t / 24)).astype("float32"),
        "MULL": (5 + 0.8 * np.cos(2 * np.pi * t / 24)).astype("float32"),
        "LUFL": (8 + np.sin(2 * np.pi * t / 24)).astype("float32"),
        "LULL": (3 + 0.5 * np.cos(2 * np.pi * t / 24)).astype("float32"),
    })
    clean["total_useful_load"] = clean[["HUFL", "MUFL", "LUFL"]].sum(axis=1).astype("float32")
    clean["total_unuseful_load"] = clean[["HULL", "MULL", "LULL"]].sum(axis=1).astype("float32")
    clean["reactive_ratio"] = (
        clean["total_unuseful_load"] / clean["total_useful_load"]
    ).astype("float32")
    clean["thermal_regime"] = fb.classify_thermal_regime(clean["OT"])
    clean["is_imputed"] = False
    clean = clean.loc[:, CLEAN_COLUMNS]
    clean["season"] = "Dry"
    clean["hour"] = clean["timestamp"].dt.hour.astype("int32")
    return clean


def _breach_events_df() -> pd.DataFrame:
    """Build a synthetic breach_events fixture."""
    return pd.DataFrame({
        "event_id": ["EV_001", "EV_002"],
        "dataset": ["ETTh1", "ETTh1"],
        "threshold_c": [85.0, 95.0],
        "thermal_regime": ["Warning", "Critical"],
        "start_timestamp": pd.to_datetime(["2026-01-01 20:00", "2026-01-03 02:00"]),
        "end_timestamp": pd.to_datetime(["2026-01-02 01:00", "2026-01-03 06:00"]),
        "duration_hours": [5.0, 4.0],
        "peak_ot": [88.5, 97.2],
        "degree_hours": [12.5, 8.8],
        "sample_count": [5, 4],
        "is_right_censored": [False, False],
        "event_center_timestamp": pd.to_datetime(["2026-01-01 22:30", "2026-01-03 04:00"]),
    })


# ---------------------------------------------------------------------------
# T0401: OT Threshold Monitoring Chart tests
# ---------------------------------------------------------------------------

class TestT0401OTThresholdChart:
    """Tests for build_ot_threshold_chart."""

    def test_returns_figure_with_valid_data(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        df = _feature_frame(100)
        events = _breach_events_df()
        fig = build_ot_threshold_chart(df, events_df=events, dataset_label="ETTh1")

        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1  # Continuous OT line + pop-outs
        # Check first trace is OT line
        assert fig.data[0].name == "OT (°C)"
        # Check title exists
        assert "Giám sát nhiệt độ dầu" in fig.layout.title.text

    def test_handles_empty_or_missing_columns(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        empty_fig = build_ot_threshold_chart(pd.DataFrame())
        assert isinstance(empty_fig, go.Figure)
        assert len(empty_fig.layout.annotations) > 0

        bad_df = pd.DataFrame({"some_col": [1, 2, 3]})
        bad_fig = build_ot_threshold_chart(bad_df)
        assert isinstance(bad_fig, go.Figure)
        assert len(bad_fig.layout.annotations) > 0

    def test_handles_all_normal_temperatures(self) -> None:
        pytest.importorskip("plotly")
        df = _feature_frame(50)
        df["OT"] = 35.0  # All normal (<85)
        fig = build_ot_threshold_chart(df)
        assert "dưới ngưỡng cảnh báo" in fig.layout.title.text
        # Only continuous line, no popout markers
        assert len(fig.data) == 1

    def test_downsampling_large_frame(self) -> None:
        pytest.importorskip("plotly")
        # 10,000 rows
        large_df = _feature_frame(240)
        large_df = pd.concat([large_df] * 50, ignore_index=True)
        large_df["timestamp"] = pd.date_range(
            "2026-01-01", periods=len(large_df), freq="h")
        fig = build_ot_threshold_chart(large_df, max_points=1000)
        # Primary line has at most ~1000 points
        assert len(fig.data[0].x) <= 1200


# ---------------------------------------------------------------------------
# T0401: Barcode / Rug Plot tests
# ---------------------------------------------------------------------------

class TestT0401BarcodeRug:
    """Tests for build_barcode_rug."""

    def test_returns_figure_with_events(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        events = _breach_events_df()
        fig = build_barcode_rug(events, dataset_label="ETTh1")

        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 2  # Warning lane + Critical lane
        assert "Barcode" in fig.layout.title.text

    def test_threshold_filter(self) -> None:
        pytest.importorskip("plotly")
        events = _breach_events_df()
        # Filter only 95°C Critical
        fig = build_barcode_rug(events, threshold_c=95.0)
        assert len(fig.data) == 1
        assert "Nguy cấp" in fig.data[0].name

    def test_handles_none_or_empty_events(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        fig_none = build_barcode_rug(None)
        assert isinstance(fig_none, go.Figure)
        assert len(fig_none.layout.annotations) > 0

        fig_empty = build_barcode_rug(pd.DataFrame())
        assert isinstance(fig_empty, go.Figure)
        assert len(fig_empty.layout.annotations) > 0


# ---------------------------------------------------------------------------
# T0402: Six Synchronized Small Multiples tests
# ---------------------------------------------------------------------------

class TestT0402SmallMultiples:
    """Tests for build_small_multiples."""

    def test_returns_six_subplots(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        df = _feature_frame(100)
        events = _breach_events_df()
        fig = build_small_multiples(df, events_df=events, dataset_label="ETTh1")

        assert isinstance(fig, go.Figure)
        # Should have 6 traces for the 6 load branches
        assert len(fig.data) == 6
        # Traces match LOAD_BRANCHES
        trace_names = [t.name for t in fig.data]
        for branch in LOAD_BRANCHES:
            assert branch in trace_names

    def test_handles_missing_branch_columns(self) -> None:
        pytest.importorskip("plotly")
        bad_df = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=10, freq="h")})
        fig = build_small_multiples(bad_df)
        assert len(fig.layout.annotations) > 0


# ---------------------------------------------------------------------------
# T0402: Joint Scatter + LOESS tests
# ---------------------------------------------------------------------------

class TestT0402ScatterLoess:
    """Tests for build_scatter_loess."""

    def test_returns_figure_with_scatter_and_trend(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        df = _feature_frame(150)
        fig = build_scatter_loess(df, load_variable="HUFL", dataset_label="ETTh1")

        assert isinstance(fig, go.Figure)
        # Missing offline curve must not trigger computation during render.
        assert len(fig.data) >= 2
        trace_names = [t.name for t in fig.data]
        assert not any("LOESS" in name for name in trace_names)
        assert any("offline engine" in a.text for a in fig.layout.annotations)

    def test_precomputed_loess_df(self) -> None:
        pytest.importorskip("plotly")
        df = _feature_frame(100)
        precomputed = pd.DataFrame({
            "HUFL": np.linspace(10, 20, 30),
            "loess_ot": np.linspace(40, 60, 30),
        })
        fig = build_scatter_loess(df, load_variable="HUFL", loess_df=precomputed)
        trend_trace = [t for t in fig.data if "LOESS" in t.name][0]
        assert len(trend_trace.x) == 30

    def test_handles_missing_variable(self) -> None:
        pytest.importorskip("plotly")
        df = _feature_frame(50)
        fig = build_scatter_loess(df, load_variable="NON_EXISTENT")
        assert len(fig.layout.annotations) > 0


# ---------------------------------------------------------------------------
# T0402: Thermal Regime Boxplots tests
# ---------------------------------------------------------------------------

class TestT0402RegimeBoxplots:
    """Tests for build_regime_boxplots."""

    def test_returns_boxplots_by_regime(self) -> None:
        pytest.importorskip("plotly")
        import plotly.graph_objects as go

        df = _feature_frame(100)
        fig = build_regime_boxplots(df, variable="OT", dataset_label="ETTh1")

        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1
        # Check Box trace type
        assert fig.data[0].type == "box"
        assert "Normal" in fig.data[0].name

    def test_custom_load_variable(self) -> None:
        pytest.importorskip("plotly")
        df = _feature_frame(100)
        fig = build_regime_boxplots(df, variable="HUFL")
        assert "HUFL" in fig.layout.title.text

    def test_handles_empty_frame(self) -> None:
        pytest.importorskip("plotly")
        fig = build_regime_boxplots(pd.DataFrame(), variable="OT")
        assert len(fig.layout.annotations) > 0
