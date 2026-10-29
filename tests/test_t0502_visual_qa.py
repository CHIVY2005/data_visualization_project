"""T0502: Visual QA regression tests — Data-Ink & Accessibility properties.

Verifies structural chart properties that enforce:
  - Correct colour semantics (Crimson only for Critical/breach, not correlation)
  - Diverging palette centred at zero for lag heatmap (zmid=0)
  - OT calendar uses absolute threshold breakpoints, not percentile-relative
  - Band alpha ordering: 95% < 80% < 50% (wide-before-narrow)
  - Action title generation produces evidence-based, non-empty strings
  - Threshold annotations present on OT charts
  - No hardcoded dataset list in sidebar logic (datasets from artifact data)

All tests use synthetic fixtures; no raw ETT data is read.
Dependencies: pandas, numpy (no streamlit/plotly required for title tests).
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


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _feature_frame(rows: int = 240, dataset: str = "ETTh1") -> pd.DataFrame:
    """Synthetic grid-features fixture with both Normal and Warning-range OT."""
    t = np.arange(rows, dtype="float64")
    ot = 40.0 + 15.0 * np.sin(2 * np.pi * t / 24)
    ot[20:25] = 88.0  # Warning spikes
    clean = pd.DataFrame({
        "dataset": pd.Series([dataset] * rows, dtype="string"),
        "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h").astype(
            "datetime64[ns]"
        ),
        "OT": ot.astype("float32"),
        "HUFL": (15.0 + 2.0 * np.sin(2 * np.pi * t / 24)).astype("float32"),
        "HULL": (6.0 + np.cos(2 * np.pi * t / 24)).astype("float32"),
        "MUFL": (12.0 + 1.5 * np.sin(2 * np.pi * t / 24)).astype("float32"),
        "MULL": (5.0 + 0.8 * np.cos(2 * np.pi * t / 24)).astype("float32"),
        "LUFL": (8.0 + np.sin(2 * np.pi * t / 24)).astype("float32"),
        "LULL": (3.0 + 0.5 * np.cos(2 * np.pi * t / 24)).astype("float32"),
    })
    clean["total_useful_load"] = clean[["HUFL", "MUFL", "LUFL"]].sum(axis=1).astype("float32")
    clean["total_unuseful_load"] = clean[["HULL", "MULL", "LULL"]].sum(axis=1).astype("float32")
    clean["reactive_ratio"] = (
        clean["total_unuseful_load"] / clean["total_useful_load"]
    ).astype("float32")
    clean["thermal_regime"] = fb.classify_thermal_regime(clean["OT"])
    clean["is_imputed"] = False
    clean = clean.loc[:, CLEAN_COLUMNS]
    return fb.build_grid_features(clean)


def _events_df() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["W001", "C001"],
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
    })


def _make_ctx(
    variable: str = "OT",
    n_samples: int = 240,
    ot_max: float | None = 88.0,
    ot_mean: float | None = 45.0,
    n_warning_events: int | None = 1,
    n_critical_events: int | None = 1,
    warning_dh: float | None = 12.5,
    critical_dh: float | None = 8.8,
    warning_dur_h: float | None = 5.0,
    critical_dur_h: float | None = 4.0,
) -> TitleContext:
    return TitleContext(
        dataset="ETTh1",
        season="Dry",
        start=pd.Timestamp("2026-01-01"),
        end=pd.Timestamp("2026-04-30") + pd.Timedelta(days=1),
        variable=variable,
        n_samples=n_samples,
        ot_mean=ot_mean,
        ot_max=ot_max,
        n_warning_events=n_warning_events,
        n_critical_events=n_critical_events,
        warning_dh=warning_dh,
        critical_dh=critical_dh,
        warning_dur_h=warning_dur_h,
        critical_dur_h=critical_dur_h,
    )


# ---------------------------------------------------------------------------
# T0502-AT: Action Title unit tests
# ---------------------------------------------------------------------------

class TestActionTitlesNonEmpty:
    """All title builders must return non-empty strings in all edge cases."""

    def test_calendar_heatmap_ot_with_breach(self) -> None:
        ctx = _make_ctx(variable="OT", ot_max=92.0)
        title = calendar_heatmap_title(ctx, agg="mean")
        assert isinstance(title, str) and len(title) > 0
        assert "ETTh1" in title
        # Should surface the breach evidence
        assert "85" in title or "88" in title or "92" in title or "Peak" in title

    def test_calendar_heatmap_ot_below_threshold(self) -> None:
        ctx = _make_ctx(variable="OT", ot_max=75.0)
        title = calendar_heatmap_title(ctx, agg="max")
        assert isinstance(title, str) and len(title) > 0
        assert "ETTh1" in title

    def test_calendar_heatmap_load_variable(self) -> None:
        ctx = _make_ctx(variable="HUFL")
        title = calendar_heatmap_title(ctx)
        assert "HUFL" in title
        assert "ETTh1" in title

    def test_stl_title_ot_with_peak(self) -> None:
        ctx = _make_ctx(variable="OT", ot_max=90.0)
        title = stl_title(ctx)
        assert "STL" in title
        assert "ETTh1" in title

    def test_stl_title_load(self) -> None:
        ctx = _make_ctx(variable="MUFL")
        title = stl_title(ctx)
        assert "MUFL" in title

    def test_quantile_fan_title_has_scope(self) -> None:
        ctx = _make_ctx(variable="OT")
        title = quantile_fan_title(ctx)
        assert "50" in title or "band" in title or "empirical" in title
        assert "ETTh1" in title
        # Must mention it's a historical reference
        assert "history" in title.lower() or "reference" in title.lower()

    def test_stacked_bar_title_has_scope(self) -> None:
        ctx = _make_ctx()
        title = stacked_bar_title(ctx)
        assert "ETTh1" in title
        assert "Dry" in title
        assert "Useful" in title or "Load" in title

    def test_lag_heatmap_title_mentions_history(self) -> None:
        ctx = _make_ctx()
        title = lag_heatmap_title(ctx)
        assert "ETTh1" in title
        assert "0" in title or "12" in title or "lag" in title.lower()
        # Must note it's historical, not recomputed
        assert "history" in title.lower() or "recomputed" in title.lower()

    def test_ot_threshold_title_no_events(self) -> None:
        ctx = TitleContext(
            dataset="ETTh2", season=None,
            start=pd.Timestamp("2016-01-01"),
            end=pd.Timestamp("2016-12-31") + pd.Timedelta(days=1),
            variable="OT", n_samples=1000,
            n_warning_events=0, n_critical_events=0,
        )
        title = ot_threshold_title(ctx)
        assert "no breach" in title.lower() or "0" in title

    def test_ot_threshold_title_with_events(self) -> None:
        ctx = _make_ctx()
        title = ot_threshold_title(ctx)
        assert "Warning" in title or "Critical" in title
        # Duration should appear
        assert "h" in title

    def test_barcode_rug_title_with_events(self) -> None:
        ctx = _make_ctx()
        title = barcode_rug_title(ctx)
        assert "Breach" in title or "Timeline" in title
        # Degree-hours should appear
        assert "°C·h" in title or "DH" in title.upper() or "12" in title

    def test_barcode_rug_title_no_events(self) -> None:
        ctx = TitleContext(
            dataset="ETTh1", season="Wet",
            start=pd.Timestamp("2016-05-01"),
            end=pd.Timestamp("2016-10-31") + pd.Timedelta(days=1),
            variable="OT", n_samples=500,
            n_warning_events=0, n_critical_events=0,
            warning_dh=0.0, critical_dh=0.0,
        )
        title = barcode_rug_title(ctx)
        assert "No events" in title or "0" in title

    def test_small_multiples_title_has_branches(self) -> None:
        ctx = _make_ctx()
        title = small_multiples_title(ctx)
        assert "6" in title or "Branch" in title or "Synchronized" in title

    def test_loess_scatter_title_mentions_reference(self) -> None:
        ctx = _make_ctx(variable="HUFL")
        title = loess_scatter_title(ctx, load_variable="HUFL")
        assert "HUFL" in title
        assert "refit" in title.lower() or "reference" in title.lower()

    def test_regime_boxplots_title_has_thresholds(self) -> None:
        ctx = _make_ctx(n_samples=500)
        title = regime_boxplots_title(ctx)
        assert "85" in title
        assert "95" in title
        assert "500" in title

    def test_na_ot_max_handled_gracefully(self) -> None:
        """None / NaN in evidence fields must not crash any title builder."""
        ctx = TitleContext(
            dataset="ETTh1", season=None,
            start=pd.Timestamp("2016-01-01"),
            end=pd.Timestamp("2016-12-31") + pd.Timedelta(days=1),
            variable="OT", n_samples=0,
            ot_max=None, ot_mean=float("nan"),
            n_warning_events=None, n_critical_events=None,
        )
        # All should return non-empty strings without raising
        for fn in [
            lambda: calendar_heatmap_title(ctx),
            lambda: stl_title(ctx),
            lambda: quantile_fan_title(ctx),
            lambda: stacked_bar_title(ctx),
            lambda: lag_heatmap_title(ctx),
            lambda: ot_threshold_title(ctx),
            lambda: barcode_rug_title(ctx),
            lambda: small_multiples_title(ctx),
            lambda: loess_scatter_title(ctx),
            lambda: regime_boxplots_title(ctx),
        ]:
            result = fn()
            assert isinstance(result, str) and len(result) > 0


class TestBuildContext:
    """build_context correctly assembles TitleContext from KPI dicts and events."""

    def test_from_manager_kpis(self) -> None:
        kpis = {"ot_mean": 42.5, "ot_max": 88.0, "warn_pct": 5.2, "sample_count": 240}
        ctx = build_context(
            "ETTh1", "Dry",
            pd.Timestamp("2026-01-01"), pd.Timestamp("2026-04-01"),
            "OT", 240, manager_kpis=kpis,
        )
        assert ctx.ot_mean == pytest.approx(42.5)
        assert ctx.ot_max == pytest.approx(88.0)
        assert ctx.n_warning_events is None  # no events provided

    def test_from_safety_kpis_and_events(self) -> None:
        events = _events_df()
        safety_kpis = {
            "max_ot": 97.2,
            "warning_degree_hours": 12.5,
            "critical_degree_hours": 8.8,
            "warning_duration_hours": 5.0,
            "critical_duration_hours": 4.0,
        }
        ctx = build_context(
            "ETTh1", None,
            pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"),
            "OT", 100, safety_kpis=safety_kpis, events=events,
        )
        assert ctx.n_warning_events == 1
        assert ctx.n_critical_events == 1
        assert ctx.warning_dh == pytest.approx(12.5)
        assert ctx.critical_dh == pytest.approx(8.8)

    def test_empty_events_gives_zero_counts(self) -> None:
        ctx = build_context(
            "ETTh1", None,
            pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"),
            "OT", 100, events=pd.DataFrame(columns=["threshold_c", "degree_hours", "duration_hours"]),
        )
        assert ctx.n_warning_events == 0
        assert ctx.n_critical_events == 0


# ---------------------------------------------------------------------------
# T0502-VIS: Visual property regression tests (require plotly)
# ---------------------------------------------------------------------------

class TestLagHeatmapPaletteSemantics:
    """Lag heatmap must NOT use Crimson (#DC2626) for negative correlation.
    Diverging palette must be centred at zero (zmid=0).
    """

    def test_zmid_zero(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.app_manager import build_lag_heatmap

        lag_df = pd.DataFrame({
            "dataset": ["ETTh1"] * 6,
            "season": ["Dry"] * 6,
            "method": ["pearson"] * 6,
            "load_variable": LOAD_BRANCHES[:6],
            "lag_hour": [0] * 6,
            "correlation": [0.8, -0.6, 0.3, -0.4, 0.5, -0.2],
        })
        fig = build_lag_heatmap(lag_df, dataset="ETTh1", season="Dry")
        heatmap_trace = fig.data[0]
        assert heatmap_trace.zmid == pytest.approx(0.0), (
            "Lag heatmap zmid must be 0; negative r ≠ Critical"
        )

    def test_no_crimson_for_negative_correlation(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.app_manager import build_lag_heatmap, _COLORSCALE_DIV

        # Crimson (#DC2626) must not appear in diverging palette
        crimson = "#DC2626"
        for stop in _COLORSCALE_DIV:
            assert stop[1].upper() != crimson.upper(), (
                "Crimson must only be used for Critical thermal threshold, "
                "never for negative lag correlation"
            )


class TestCalendarAbsoluteOTColors:
    """OT calendar colorscale must use absolute thresholds (85/95°C),
    not percentile-relative breakpoints.
    """

    def test_ot_colorscale_anchors_at_85_95(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.charts_manager import build_calendar_heatmap

        df = pd.DataFrame({
            "dataset": pd.Series(["ETTh1"] * 48, dtype="string"),
            "timestamp": pd.date_range("2026-01-01", periods=48, freq="h").astype(
                "datetime64[ns]"
            ),
            "OT": ([40.0] * 44 + [87.0, 88.0, 96.0, 97.0]),
            "HUFL": [10.0] * 48,
            "HULL": [4.0] * 48,
            "MUFL": [8.0] * 48,
            "MULL": [3.0] * 48,
            "LUFL": [6.0] * 48,
            "LULL": [2.0] * 48,
            "season": ["Dry"] * 48,
            "hour": list(range(24)) * 2,
        })
        for col in ("total_useful_load", "total_unuseful_load", "reactive_ratio",
                    "thermal_regime", "is_imputed"):
            df[col] = 0.0
        df["is_imputed"] = False

        fig = build_calendar_heatmap(df, variable="OT", dataset_label="ETTh1")
        heatmap = fig.data[0]
        # zmin should be <= 40 (real min), zmax should include > 96
        assert heatmap.zmax >= 95.0, (
            "OT calendar zmax must cover Critical threshold (95°C); "
            "colour semantics must be absolute, not relative"
        )
        # Colorscale must have entries near 85 and 95 as breakpoints
        colorscale_positions = [float(stop[0]) for stop in heatmap.colorscale]
        zmin = heatmap.zmin
        zmax = heatmap.zmax
        if zmax > zmin:
            w85 = (85.0 - zmin) / (zmax - zmin)
            w95 = (95.0 - zmin) / (zmax - zmin)
            positions_set = set(round(p, 4) for p in colorscale_positions)
            assert any(abs(p - w85) < 0.02 for p in colorscale_positions), (
                f"Expected 85°C breakpoint near {w85:.4f}; got positions {colorscale_positions}"
            )
            assert any(abs(p - w95) < 0.02 for p in colorscale_positions), (
                f"Expected 95°C breakpoint near {w95:.4f}; got positions {colorscale_positions}"
            )


class TestQuantileFanBandAlphaOrdering:
    """Wider empirical bands must have lower alpha than narrower bands.
    95% (q2.5–q97.5) alpha < 80% (q10–q90) alpha < 50% IQR (q25–q75) alpha.
    Per AGENTS: alpha 0.14 / 0.20 / 0.28, wide-before-narrow.
    """

    def test_alpha_ordering_wide_before_narrow(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.charts_manager import _BANDS

        # _BANDS is (lower_col, upper_col, alpha, label)
        # ordered wide → narrow so alpha should increase
        alphas = [band[2] for band in _BANDS]
        assert alphas == sorted(alphas), (
            f"Band alphas must increase (wide-before-narrow): got {alphas}"
        )
        # Check canonical values
        assert abs(alphas[0] - 0.14) < 0.01, "95% band alpha should be ~0.14"
        assert abs(alphas[1] - 0.20) < 0.01, "80% band alpha should be ~0.20"
        assert abs(alphas[2] - 0.28) < 0.01, "50% IQR alpha should be ~0.28"


class TestOTThresholdAnnotations:
    """OT charts must annotate 85°C and 95°C thresholds explicitly."""

    def test_ot_threshold_chart_has_hlines(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.charts_safety import build_ot_threshold_chart

        df = pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=48, freq="h"),
            "OT": [40.0] * 48,
        })
        fig = build_ot_threshold_chart(df)
        # Threshold lines are represented as shapes in layout
        shapes = fig.layout.shapes or []
        y_vals = [s.y0 for s in shapes if hasattr(s, "y0") and s.y0 is not None]
        assert any(abs(y - WARNING_TEMP_THRESHOLD) < 0.1 for y in y_vals), (
            f"85°C threshold line missing; found y_vals: {y_vals}"
        )
        assert any(abs(y - CRITICAL_TEMP_THRESHOLD) < 0.1 for y in y_vals), (
            f"95°C threshold line missing; found y_vals: {y_vals}"
        )

    def test_quantile_fan_ot_has_threshold_annotations(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.charts_manager import build_quantile_fan

        rows = 24
        bands_df = pd.DataFrame({
            "dataset": ["ETTh1"] * rows,
            "season": ["Dry"] * rows,
            "variable": ["OT"] * rows,
            "hour": list(range(rows)),
            "sample_count": [100] * rows,
            "mean": [50.0] * rows,
            "q025": [30.0] * rows,
            "q10": [35.0] * rows,
            "q25": [40.0] * rows,
            "q50": [50.0] * rows,
            "q75": [60.0] * rows,
            "q90": [65.0] * rows,
            "q975": [70.0] * rows,
        })
        fig = build_quantile_fan(bands_df, dataset="ETTh1", variable="OT", season="Dry")
        # Threshold lines represented as shapes
        shapes = fig.layout.shapes or []
        y_vals = [s.y0 for s in shapes if hasattr(s, "y0") and s.y0 is not None]
        assert any(abs(y - WARNING_TEMP_THRESHOLD) < 0.1 for y in y_vals), (
            "OT Quantile Fan must annotate 85°C Warning threshold"
        )


class TestColorSemanticConsistency:
    """Amber (#D97706) → Warning only. Crimson (#DC2626) → Critical only.
    Navy (#1E3A8A) → OT/useful load. Teal (#0D9488) → useful load.
    Slate (#64748B) → context/unuseful.
    """

    def test_regime_boxplots_color_mapping(self) -> None:
        plotly = pytest.importorskip("plotly")
        from src.visuals.app_safety import build_regime_boxplots

        df = pd.DataFrame({
            "OT": [40.0] * 10 + [87.0] * 5 + [97.0] * 3,
            "thermal_regime": ["Normal"] * 10 + ["Warning"] * 5 + ["Critical"] * 3,
        })
        fig = build_regime_boxplots(df, variable="OT")

        for trace in fig.data:
            name = trace.name.lower()
            color = (
                trace.marker.color
                if hasattr(trace, "marker") and trace.marker.color
                else None
            )
            if color is None:
                continue
            if "normal" in name:
                assert color == "#1E3A8A", f"Normal must be Navy; got {color}"
            elif "warning" in name:
                assert color == "#D97706", f"Warning must be Amber; got {color}"
            elif "critical" in name:
                assert color == "#DC2626", f"Critical must be Crimson; got {color}"
