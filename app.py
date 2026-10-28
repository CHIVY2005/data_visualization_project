"""Streamlit entry point — ETT Power Grid Visual Analytics Dashboard.

Serves two User Stories from pre-computed Parquet/JSON artifacts:
  Story 1 (WP03): Operational Manager — load cycles, STL, quantile fan,
                  load composition, lag heatmap.
  Story 2 (WP04): Safety & Risk Monitor — OT events, small multiples,
                  scatter + LOESS, regime boxplots. (placeholder)

UI contract (AGENTS §STRICT:DECOUPLE):
  - Only reads Parquet/JSON artifacts; no STL/quantile/lag computation here.
  - Light slicing (filter by dataset, season, variable) is permitted.
  - st.cache_data caches by artifact path + mtime for session isolation.
  - Target load/render/filter < 2 s on representative data (SLA not yet measured).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data.constants import (
    ANALYSIS_VARIABLES,
    ARTIFACTS_DIR,
    DEFAULT_CLEAN_PATH,
    DEFAULT_FEATURE_PATH,
    DEFAULT_HOURLY_QUANTILES_PATH,
    DEFAULT_LAG_MATRIX_PATH,
    LOAD_BRANCHES,
    MEASUREMENTS,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ETT Power Grid Analytics",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": (
            "ETT_GRID_VIS_2026 v2.0 · CPU-only · "
            "Trực quan hóa dữ liệu lịch sử, không phải hệ thống giám sát trực tiếp."
        )
    },
)

# ---------------------------------------------------------------------------
# Artifact loaders (cached per path + mtime)
# ---------------------------------------------------------------------------

def _mtime(path: Path) -> float:
    """Return file mtime for cache invalidation; 0 if file absent."""
    return path.stat().st_mtime if path.exists() else 0.0


@st.cache_data(show_spinner=False)
def load_features(_path: Path, _mtime: float) -> pd.DataFrame | None:
    """Load grid_features.parquet; return None if file absent."""
    if not _path.exists():
        return None
    return pd.read_parquet(_path)


@st.cache_data(show_spinner=False)
def load_quantile_bands(_path: Path, _mtime: float) -> pd.DataFrame | None:
    """Load hourly_quantiles.parquet; return None if file absent."""
    if not _path.exists():
        return None
    return pd.read_parquet(_path)


@st.cache_data(show_spinner=False)
def load_lag_matrix(_path: Path, _mtime: float) -> pd.DataFrame | None:
    """Load lag_matrix.parquet; return None if file absent."""
    if not _path.exists():
        return None
    return pd.read_parquet(_path)


@st.cache_data(show_spinner=False)
def load_stl(_path: Path, _mtime: float) -> pd.DataFrame | None:
    """Load load_profiles_stl.parquet (record_type == 'stl'); None if absent."""
    stl_path = _path.parent / "load_profiles_stl.parquet"
    if not stl_path.exists():
        return None
    df = pd.read_parquet(stl_path)
    if "record_type" in df.columns:
        df = df[df["record_type"] == "stl"]
    return df


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------

FEATURE_PATH = DEFAULT_FEATURE_PATH
QUANTILE_PATH = DEFAULT_HOURLY_QUANTILES_PATH
LAG_PATH = DEFAULT_LAG_MATRIX_PATH
STL_PATH = ARTIFACTS_DIR  # directory; load_stl resolves the file name


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

def render_sidebar() -> dict[str, str | list[str]]:
    """Render sidebar filters and return selection dict."""
    st.sidebar.image(
        "https://img.shields.io/badge/ETT_GRID_VIS-2026-1E3A8A",
        use_column_width=False,
    )
    st.sidebar.title("⚡ ETT Grid Analytics")
    st.sidebar.caption("v2.0 · CPU-only · Historical data")

    story = st.sidebar.radio(
        "Dashboard View",
        options=["Story 1 — Operational Manager", "Story 2 — Safety & Risk Monitor"],
        index=0,
        key="story_selector",
    )

    st.sidebar.divider()
    st.sidebar.subheader("Filters")

    dataset = st.sidebar.selectbox(
        "Dataset",
        options=["ETTh1", "ETTh2", "ETTm1"],
        index=0,
        key="dataset_selector",
    )

    season = st.sidebar.selectbox(
        "Season",
        options=["All", "Dry", "Wet"],
        index=0,
        key="season_selector",
    )

    variable = st.sidebar.selectbox(
        "Variable (STL / Fan / Calendar)",
        options=list(ANALYSIS_VARIABLES),
        index=0,  # OT is first
        key="variable_selector",
    )

    st.sidebar.divider()
    st.sidebar.caption(
        "⚠️ Ngưỡng 85/95°C là quy ước phân tích dự án, "
        "không phải tiêu chuẩn kỹ thuật phổ quát."
    )

    return {
        "story": story,
        "dataset": dataset,
        "season": season if season != "All" else None,
        "variable": variable,
    }


# ---------------------------------------------------------------------------
# Story 1: Operational Manager Dashboard
# ---------------------------------------------------------------------------

def render_story1(filters: dict[str, str | list[str] | None]) -> None:
    """Render WP03 — Operational Manager view."""
    dataset: str = str(filters["dataset"])
    season: str | None = filters.get("season")  # type: ignore[assignment]
    variable: str = str(filters["variable"])

    st.header("📊 Operational Manager Dashboard")
    st.caption(
        "Chu kỳ phụ tải ngày/mùa, tỷ trọng tải hữu ích/vô công và độ trễ nhiệt."
    )

    # --- Load artifacts ---
    features = load_features(FEATURE_PATH, _mtime(FEATURE_PATH))
    quantile_bands = load_quantile_bands(QUANTILE_PATH, _mtime(QUANTILE_PATH))
    lag_matrix = load_lag_matrix(LAG_PATH, _mtime(LAG_PATH))
    stl_df = load_stl(STL_PATH, _mtime(STL_PATH / "load_profiles_stl.parquet")
                      if (STL_PATH / "load_profiles_stl.parquet").exists() else 0.0)

    # Artifact availability banners
    missing = []
    if features is None:
        missing.append("`data/processed/grid_features.parquet`")
    if quantile_bands is None:
        missing.append("`output/artifacts/hourly_quantiles.parquet`")
    if lag_matrix is None:
        missing.append("`output/artifacts/lag_matrix.parquet`")
    if stl_df is None:
        missing.append("`output/artifacts/load_profiles_stl.parquet`")

    if missing:
        st.warning(
            "**Một số artifacts chưa được sinh.** "
            "Chạy `python scripts/run_statistical_engine.py` để tạo chúng trước.\n\n"
            "Thiếu: " + ", ".join(missing),
            icon="⚠️",
        )

    # Slice features by dataset
    feat_ds: pd.DataFrame | None = None
    if features is not None:
        feat_ds = features[features["dataset"] == dataset].copy()
        if feat_ds.empty:
            st.error(f"Không có dữ liệu cho dataset `{dataset}` trong artifact.")
            feat_ds = None

    # ------------------------------------------------------------------
    # KPI row
    # ------------------------------------------------------------------
    st.subheader("📈 KPI tổng quan")
    kpi_cols = st.columns(4)
    if feat_ds is not None:
        season_data = feat_ds[feat_ds["season"] == season] if season else feat_ds
        kpi_cols[0].metric(
            "Số mẫu",
            f"{len(season_data):,}",
            help="Tổng số mẫu sau lọc mùa",
        )
        ot_mean = season_data["OT"].mean() if "OT" in season_data.columns else float("nan")
        kpi_cols[1].metric(
            "OT trung bình (°C)",
            f"{ot_mean:.1f}" if pd.notna(ot_mean) else "N/A",
        )
        ot_max = season_data["OT"].max() if "OT" in season_data.columns else float("nan")
        kpi_cols[2].metric(
            "OT cực đại (°C)",
            f"{ot_max:.1f}" if pd.notna(ot_max) else "N/A",
        )
        warn_pct = (
            season_data["OT"].ge(85).sum() / max(len(season_data), 1) * 100
        )
        kpi_cols[3].metric(
            "Tỷ lệ OT ≥ 85°C (%)",
            f"{warn_pct:.1f}%",
            help="Warning + Critical samples",
        )
    else:
        for col in kpi_cols:
            col.metric("—", "N/A")

    st.divider()

    # ------------------------------------------------------------------
    # T0301: Calendar Heatmap
    # ------------------------------------------------------------------
    st.subheader("🗓️ T0301 — Calendar Heatmap")
    with st.expander("Xem biểu đồ", expanded=True):
        if feat_ds is not None:
            from src.visuals.charts_manager import build_calendar_heatmap
            agg_choice = st.radio(
                "Phép tổng hợp theo ngày",
                options=["mean", "max", "min"],
                horizontal=True,
                key="cal_agg",
            )
            try:
                fig_cal = build_calendar_heatmap(
                    feat_ds,
                    variable=variable,
                    agg=agg_choice,  # type: ignore[arg-type]
                    dataset_label=dataset,
                    height=460,
                    width=900,
                )
                st.plotly_chart(fig_cal, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Calendar Heatmap: {exc}")
        else:
            st.info("Chưa có dữ liệu — kiểm tra artifact.")

    # ------------------------------------------------------------------
    # T0302a: STL Panels
    # ------------------------------------------------------------------
    st.subheader("📉 T0302 — STL Decomposition")
    with st.expander("Xem biểu đồ", expanded=False):
        if stl_df is not None:
            from src.visuals.charts_manager import build_stl_panels
            stl_slice = stl_df[
                (stl_df["dataset"] == dataset) & (stl_df["variable"] == variable)
            ]
            if stl_slice.empty:
                st.info(f"Không có STL record cho dataset={dataset}, variable={variable}.")
            else:
                try:
                    fig_stl = build_stl_panels(
                        stl_slice,
                        variable=variable,
                        dataset_label=dataset,
                        height=640,
                    )
                    st.plotly_chart(fig_stl, use_container_width=True)
                except Exception as exc:
                    st.error(f"Lỗi vẽ STL panels: {exc}")
        else:
            st.info("load_profiles_stl.parquet chưa có — chạy Statistical Engine.")

    # ------------------------------------------------------------------
    # T0302b: Quantile Fan
    # ------------------------------------------------------------------
    st.subheader("🌀 T0302 — Hourly Quantile Fan")
    with st.expander("Xem biểu đồ", expanded=False):
        if quantile_bands is not None:
            from src.visuals.charts_manager import build_quantile_fan
            # Filter to dataset if column exists
            qb = quantile_bands.copy()
            if "dataset" in qb.columns:
                qb = qb[qb["dataset"] == dataset]
            try:
                fig_fan = build_quantile_fan(
                    qb,
                    variable=variable,
                    season=season,
                    dataset_label=dataset,
                    height=400,
                )
                st.plotly_chart(fig_fan, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Quantile Fan: {exc}")
        else:
            st.info("hourly_quantiles.parquet chưa có — chạy Statistical Engine.")

    # ------------------------------------------------------------------
    # T0303a: 100% Stacked Bar
    # ------------------------------------------------------------------
    st.subheader("📊 T0303 — Load Composition (100% Stacked Bar)")
    with st.expander("Xem biểu đồ", expanded=False):
        if feat_ds is not None:
            from src.visuals.app_manager import build_stacked_bar
            all_tiers = st.checkbox("Hiện cả 3 cấp áp", value=True, key="all_tiers")
            tier_choice = "High"
            if not all_tiers:
                tier_choice = st.selectbox(
                    "Cấp áp", ["High", "Middle", "Low"], key="tier_select"
                )
            try:
                fig_bar = build_stacked_bar(
                    feat_ds,
                    season=season,
                    dataset_label=dataset,
                    show_all_tiers=all_tiers,
                    selected_tier=tier_choice,
                    height=360,
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Stacked Bar: {exc}")
        else:
            st.info("Chưa có dữ liệu features.")

    # ------------------------------------------------------------------
    # T0303b: Lag Heatmap
    # ------------------------------------------------------------------
    st.subheader("🔥 T0303 — Lag Cross-Correlation Heatmap")
    with st.expander("Xem biểu đồ", expanded=False):
        if lag_matrix is not None:
            from src.visuals.app_manager import build_lag_heatmap
            lag_ds = lag_matrix.copy()
            if "dataset" in lag_ds.columns:
                lag_ds = lag_ds[lag_ds["dataset"] == dataset]
            method_choice = st.radio(
                "Phương pháp tương quan",
                options=["pearson", "spearman"],
                horizontal=True,
                key="lag_method",
            )
            try:
                fig_lag = build_lag_heatmap(
                    lag_ds,
                    season=season,
                    method=method_choice,
                    dataset_label=dataset,
                    height=360,
                )
                st.plotly_chart(fig_lag, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Lag Heatmap: {exc}")
        else:
            st.info("lag_matrix.parquet chưa có — chạy Statistical Engine.")


# ---------------------------------------------------------------------------
# Story 2: Safety & Risk Monitor (placeholder — WP04)
# ---------------------------------------------------------------------------

def render_story2(filters: dict[str, str | list[str] | None]) -> None:
    """Render WP04 — Safety & Risk Monitor placeholder."""
    st.header("🛡️ Safety & Risk Monitor Dashboard")
    st.info(
        "**WP04 (T0401–T0403) — Đang phát triển.**\n\n"
        "Biểu đồ Story 2 sẽ bao gồm: OT threshold line/shading, "
        "Barcode/Rug events, Synchronized Small Multiples (6 nhánh tải), "
        "Joint Scatter + LOESS, Regime Boxplots.",
        icon="🚧",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Render the dashboard based on sidebar selection."""
    filters = render_sidebar()
    story: str = str(filters["story"])

    if "Story 1" in story:
        render_story1(filters)
    else:
        render_story2(filters)

    # Footer
    st.divider()
    st.caption(
        "ETT_GRID_VIS_2026 v2.0 · Dữ liệu lịch sử ETT · "
        "Dashboard này không phải hệ thống giám sát trực tiếp hoặc an toàn được chứng nhận. "
        "Ngưỡng 85/95°C là quy ước phân tích dự án."
    )


if __name__ == "__main__":
    main()
