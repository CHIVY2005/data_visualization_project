"""Streamlit entry point — ETT Power Grid Visual Analytics Dashboard.

Serves two User Stories from pre-computed Parquet/JSON artifacts:
  Story 1 (WP03): Operational Manager — load cycles, STL, quantile fan,
                  load composition, lag heatmap.
  Story 2 (WP04): Safety & Risk Monitor — OT events, small multiples,
                  scatter + LOESS, regime boxplots.

UI contract (AGENTS §STRICT:DECOUPLE):
  - Only reads Parquet/JSON artifacts; no STL/quantile/lag computation here.
  - Light slicing (filter by dataset, season, variable) is permitted.
  - st.cache_data caches by artifact path + mtime for session isolation.
  - Target load/render/filter < 2 s on representative data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.data.constants import (
    ANALYSIS_VARIABLES,
    ARTIFACTS_DIR,
    DEFAULT_BREACH_EVENTS_PATH,
    DEFAULT_CLEAN_PATH,
    DEFAULT_FEATURE_PATH,
    DEFAULT_HOURLY_QUANTILES_PATH,
    DEFAULT_LAG_MATRIX_PATH,
    LOAD_BRANCHES,
    MEASUREMENTS,
)
from src.visuals.story1 import (
    build_calendar_heatmap,
    build_lag_heatmap,
    build_quantile_fan,
    build_stacked_bar,
    build_stl_panels,
)
from src.visuals.story2 import (
    build_barcode_rug,
    build_ot_threshold_chart,
    build_regime_boxplots,
    build_scatter_loess,
    build_small_multiples,
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


@st.cache_data(show_spinner=False)
def load_breach_events(_path: Path, _mtime: float) -> pd.DataFrame | None:
    """Load breach_events.parquet; return None if file absent."""
    if not _path.exists():
        return None
    return pd.read_parquet(_path)


# ---------------------------------------------------------------------------
# Artifact paths
# ---------------------------------------------------------------------------

FEATURE_PATH = DEFAULT_FEATURE_PATH
QUANTILE_PATH = DEFAULT_HOURLY_QUANTILES_PATH
LAG_PATH = DEFAULT_LAG_MATRIX_PATH
STL_PATH = ARTIFACTS_DIR
BREACH_PATH = DEFAULT_BREACH_EVENTS_PATH


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

def render_sidebar() -> dict[str, str | list[str] | None]:
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

    load_branch = "HUFL"
    rug_threshold = "Tất cả (≥85°C & ≥95°C)"
    if "Story 2" in story:
        st.sidebar.divider()
        st.sidebar.subheader("Safety & Risk Filters")
        load_branch = st.sidebar.selectbox(
            "Load Variable (Scatter / Boxplot)",
            options=list(LOAD_BRANCHES),
            index=0,
            key="load_branch_selector",
        )
        rug_threshold = st.sidebar.selectbox(
            "Barcode Threshold Filter",
            options=["Tất cả (≥85°C & ≥95°C)", "Chỉ cảnh báo (≥85°C)", "Chỉ nguy cấp (≥95°C)"],
            index=0,
            key="rug_threshold_selector",
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
        "load_branch": load_branch,
        "rug_threshold": rug_threshold,
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
    stl_df = load_stl(
        STL_PATH,
        _mtime(STL_PATH / "load_profiles_stl.parquet")
        if (STL_PATH / "load_profiles_stl.parquet").exists()
        else 0.0,
    )

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

    # KPI row
    st.subheader("📈 KPI tổng quan")
    kpi_cols = st.columns(4)
    if feat_ds is not None:
        season_data = feat_ds[feat_ds["season"] == season] if season else feat_ds
        kpi_cols[0].metric(
            "Số mẫu",
            f"{len(season_data):,}",
            help="Tổng số mẫu sau lọc mùa",
        )
        ot_mean = (
            season_data["OT"].mean() if "OT" in season_data.columns else float("nan")
        )
        kpi_cols[1].metric(
            "OT trung bình (°C)",
            f"{ot_mean:.1f}" if pd.notna(ot_mean) else "N/A",
        )
        ot_max = (
            season_data["OT"].max() if "OT" in season_data.columns else float("nan")
        )
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
            help="Tỷ lệ mẫu nằm trong vùng cảnh báo hoặc nguy cấp",
        )
    else:
        for col in kpi_cols:
            col.metric("—", "N/A")

    # Tabs for Story 1 charts
    tab1, tab2, tab3 = st.tabs([
        "1. Chu kỳ & Phân rã (Calendar + STL)",
        "2. Dải phân vị giờ (Statistical Fan)",
        "3. Tỷ trọng tải & Trễ nhiệt (Stacked + Lag)",
    ])

    with tab1:
        st.subheader("Calendar Heatmap (T0301)")
        st.caption(
            f"Phân phối giá trị trung bình ngày của `{variable}` theo tuần và ngày trong tháng."
        )
        if feat_ds is not None:
            try:
                fig_cal = build_calendar_heatmap(
                    feat_ds,
                    variable=variable,
                    dataset_label=dataset,
                    width=900,
                )
                st.plotly_chart(fig_cal, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Calendar Heatmap: {exc}")
        else:
            st.info("grid_features.parquet chưa có — xem hướng dẫn chạy pipeline.")

        st.subheader("STL Decomposition Panels (T0302a)")
        st.caption(
            f"Phân rã chuỗi thời gian của `{variable}` thành Xu hướng, Mùa vụ (24h/96b) và Phần dư."
        )
        if stl_df is not None:
            try:
                stl_sub = stl_df[
                    (stl_df["dataset"] == dataset) & (stl_df["variable"] == variable)
                ]
                fig_stl = build_stl_panels(
                    stl_sub,
                    variable=variable,
                    dataset_label=dataset,
                )
                st.plotly_chart(fig_stl, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ STL Panels: {exc}")
        else:
            st.info("load_profiles_stl.parquet chưa có — chạy Statistical Engine.")

    with tab2:
        st.subheader("Hourly Quantile Fan Chart (T0302b)")
        st.caption(
            f"Dải phân vị lịch sử 95% (q025–q975), 80% (q10–q90) và 50% (q25–q75) theo 24 giờ."
        )
        if quantile_bands is not None:
            try:
                fig_fan = build_quantile_fan(
                    quantile_bands,
                    dataset=dataset,
                    variable=variable,
                    season=season,
                )
                st.plotly_chart(fig_fan, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Quantile Fan Chart: {exc}")
        else:
            st.info("hourly_quantiles.parquet chưa có — chạy Statistical Engine.")

    with tab3:
        st.subheader("100% Stacked Bar — Tỷ trọng phụ tải 3 cấp điện áp (T0303a)")
        st.caption(
            "Cơ cấu phụ tải Hữu công vs Vô công qua 3 cấp điện áp (Cao/Trung/Hạ thế) theo giờ trong ngày."
        )
        if feat_ds is not None:
            try:
                fig_bar = build_stacked_bar(
                    feat_ds,
                    season=season,
                    dataset_label=dataset,
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ 100% Stacked Bar: {exc}")
        else:
            st.info("grid_features.parquet chưa có — chạy feature pipeline.")

        st.subheader("Lag Cross-Correlation Heatmap (T0303b)")
        st.caption(
            "Hệ số tương quan chéo giữa 6 nhánh tải và nhiệt độ dầu OT ở các độ trễ 0–12 giờ."
        )
        if lag_matrix is not None:
            try:
                fig_lag = build_lag_heatmap(
                    lag_matrix,
                    dataset=dataset,
                    season=season or "Dry",
                )
                st.plotly_chart(fig_lag, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Lag Heatmap: {exc}")
        else:
            st.info("lag_matrix.parquet chưa có — chạy Statistical Engine.")


# ---------------------------------------------------------------------------
# Story 2: Safety & Risk Monitor (WP04)
# ---------------------------------------------------------------------------

def render_story2(filters: dict[str, str | list[str] | None]) -> None:
    """Render WP04 — Safety & Risk Monitor view."""
    dataset: str = str(filters["dataset"])
    season: str | None = filters.get("season")  # type: ignore[assignment]
    load_branch: str = str(filters.get("load_branch", "HUFL"))
    rug_choice: str = str(filters.get("rug_threshold", "Tất cả (≥85°C & ≥95°C)"))

    rug_th: float | None = None
    if "85°C" in rug_choice and "95°C" not in rug_choice:
        rug_th = 85.0
    elif "95°C" in rug_choice and "85°C" not in rug_choice:
        rug_th = 95.0

    st.header("🛡️ Safety & Risk Monitor Dashboard")
    st.caption(
        "Giám sát vi phạm nhiệt độ dầu OT (≥85°C / ≥95°C), chuỗi sự cố vi phạm (Barcode), "
        "đối chiếu 6 nhánh phụ tải và chẩn đoán tương quan phi tuyến LOESS."
    )

    # --- Load artifacts ---
    features = load_features(FEATURE_PATH, _mtime(FEATURE_PATH))
    events_all = load_breach_events(BREACH_PATH, _mtime(BREACH_PATH))

    # Artifact availability banners
    missing = []
    if features is None:
        missing.append("`data/processed/grid_features.parquet`")
    if events_all is None:
        missing.append("`output/artifacts/breach_events.parquet`")

    if missing:
        st.warning(
            "**Một số artifacts chưa được sinh.** "
            "Chạy pipeline tiền xử lý và Statistical Engine để tạo chúng.\n\n"
            "Thiếu: " + ", ".join(missing),
            icon="⚠️",
        )

    # Slice features by dataset & season
    feat_ds: pd.DataFrame | None = None
    if features is not None:
        feat_ds = features[features["dataset"] == dataset].copy()
        if season and "season" in feat_ds.columns:
            feat_ds = feat_ds[feat_ds["season"] == season].copy()
        if feat_ds.empty:
            st.error(f"Không có dữ liệu cho dataset `{dataset}` (mùa: {season or 'All'}).")
            feat_ds = None

    # Slice breach events by dataset
    ev_ds: pd.DataFrame | None = None
    if events_all is not None:
        ev_ds = events_all[events_all["dataset"] == dataset].copy()
        if ev_ds.empty:
            ev_ds = None

    # ------------------------------------------------------------------
    # KPI row (Safety Metrics)
    # ------------------------------------------------------------------
    st.subheader("⚠️ Chỉ số An toàn & Áp lực Nhiệt")
    kpi_cols = st.columns(4)

    total_events = len(ev_ds) if ev_ds is not None else 0
    crit_events = (
        len(ev_ds[ev_ds["threshold_c"] >= 95.0]) if ev_ds is not None else 0
    )
    max_ot = (
        feat_ds["OT"].max()
        if (feat_ds is not None and "OT" in feat_ds.columns)
        else float("nan")
    )
    tot_degree_hours = (
        ev_ds["degree_hours"].sum()
        if (ev_ds is not None and "degree_hours" in ev_ds.columns)
        else 0.0
    )

    kpi_cols[0].metric(
        "Tổng đợt vi phạm",
        f"{total_events:,}",
        help="Tổng số đợt vượt ngưỡng 85°C hoặc 95°C",
    )
    kpi_cols[1].metric(
        "Đợt nguy cấp (≥95°C)",
        f"{crit_events:,}",
        help="Số đợt nhiệt độ vượt ngưỡng nguy cấp 95°C",
    )
    kpi_cols[2].metric(
        "Đỉnh nhiệt OT (°C)",
        f"{max_ot:.1f} °C" if pd.notna(max_ot) else "N/A",
        help="Nhiệt độ dầu cao nhất ghi nhận trong tập dữ liệu",
    )
    kpi_cols[3].metric(
        "Áp lực nhiệt tích lũy (°C·h)",
        f"{tot_degree_hours:.1f}",
        help="Tổng Degree-Hours: Σ max(OT - threshold, 0) × Δt",
    )

    # ------------------------------------------------------------------
    # Charts organized in tabs
    # ------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs([
        "1. Giám sát OT & Barcode Vi phạm (T0401)",
        "2. Synchronized Small Multiples (T0402)",
        "3. Chẩn đoán Tương quan LOESS & Boxplots (T0402)",
    ])

    with tab1:
        st.subheader("Diễn biến Nhiệt độ dầu & Ngưỡng An toàn (T0401)")
        st.caption(
            "Vùng màu Hổ phách: Cảnh báo [85°C - 95°C); Vùng màu Đỏ sẫm: Nguy cấp [≥95°C)."
        )
        if feat_ds is not None:
            try:
                fig_ot = build_ot_threshold_chart(
                    feat_ds, events_df=ev_ds, dataset_label=dataset
                )
                st.plotly_chart(fig_ot, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ OT Threshold Chart: {exc}")
        else:
            st.info("Chưa có dữ liệu grid_features để vẽ biểu đồ OT.")

        st.subheader("Thanh Barcode Định vị Sự cố Vi phạm (T0401)")
        st.caption("Mỗi vạch đứng thể hiện một đợt vượt ngưỡng nhiệt độ trên dòng thời gian.")
        try:
            fig_rug = build_barcode_rug(
                ev_ds, threshold_c=rug_th, dataset_label=dataset
            )
            st.plotly_chart(fig_rug, use_container_width=True)
        except Exception as exc:
            st.error(f"Lỗi vẽ Barcode Rug Plot: {exc}")

    with tab2:
        st.subheader("Synchronized Small Multiples — 6 Nhánh Phụ tải (T0402)")
        st.caption(
            "6 đồ thị tải Cao/Trung/Hạ thế được liên kết trục thời gian (Shared X-axis). "
            "Kéo phóng to (zoom) hoặc di chuyển (pan) trên bất kỳ đồ thị nào sẽ đồng bộ toàn bộ."
        )
        if feat_ds is not None:
            try:
                fig_multiples = build_small_multiples(
                    feat_ds, events_df=ev_ds, dataset_label=dataset
                )
                st.plotly_chart(fig_multiples, use_container_width=True)
            except Exception as exc:
                st.error(f"Lỗi vẽ Synchronized Small Multiples: {exc}")
        else:
            st.info("Chưa có dữ liệu grid_features để vẽ Small Multiples.")

    with tab3:
        st.subheader("Chẩn đoán Tương quan Phi tuyến LOESS & Phân phối Chế độ (T0402)")
        st.caption(
            f"Phân tích hành vi nhiệt theo mức phụ tải nhánh **{load_branch}** "
            "và so sánh phân phối giữa các chế độ nhiệt (Normal · Warning · Critical)."
        )
        if feat_ds is not None:
            col_scatter, col_box = st.columns(2)
            with col_scatter:
                try:
                    fig_scatter = build_scatter_loess(
                        feat_ds,
                        load_variable=load_branch,
                        dataset_label=dataset,
                        season=season,
                    )
                    st.plotly_chart(fig_scatter, use_container_width=True)
                except Exception as exc:
                    st.error(f"Lỗi vẽ Joint Scatter + LOESS: {exc}")

            with col_box:
                box_var = st.selectbox(
                    "Biến hiển thị trên Boxplot",
                    options=["OT", *LOAD_BRANCHES],
                    index=0,
                    key="box_var_selector",
                )
                try:
                    fig_box = build_regime_boxplots(
                        feat_ds, variable=box_var, dataset_label=dataset
                    )
                    st.plotly_chart(fig_box, use_container_width=True)
                except Exception as exc:
                    st.error(f"Lỗi vẽ Regime Boxplots: {exc}")
        else:
            st.info("Chưa có dữ liệu grid_features để thực hiện chẩn đoán LOESS & Boxplots.")


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
