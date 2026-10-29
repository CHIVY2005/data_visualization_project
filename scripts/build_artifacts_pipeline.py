"""Script tự động hóa ETL và trích xuất đồng loạt toàn bộ Artifacts cho cả 3 trạm (T0205)."""

import json
import os
import sys
import numpy as np
import pandas as pd

# Thêm thư mục gốc vào path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.analysis.lag_correlation import compute_lag_correlation
from src.analysis.load_profiling import (
    compute_hourly_quantiles,
    compute_stl_decomposition,
)
from src.analysis.thermal_risk import (
    extract_breach_events,
    precompute_loess_curves,
)
from src.data.feature_builder import add_grid_features

DATA_DIR = "data/processed/datasets"
OUTPUT_DIR = "output/artifacts"


def process_station(
    station_id: str, is_15min: bool = False
) -> None:
    print(f"\n================ ĐANG XỬ LÝ TRẠM: {station_id} ================")
    raw_path = os.path.join(DATA_DIR, station_id, "clean_ett.parquet")
    if not os.path.exists(raw_path):
        # Fallback thử đọc file csv nếu chưa có parquet
        csv_fallback = f"data/{station_id}.csv"
        if os.path.exists(csv_fallback):
            df_raw = pd.read_csv(csv_fallback)
        else:
            print(f"⚠️ Không tìm thấy file dữ liệu cho {station_id}")
            return
    else:
        df_raw = pd.read_parquet(raw_path)

    # 1. Feature Engineering
    df_featured = add_grid_features(df_raw, time_col="date")
    station_out_dir = os.path.join(OUTPUT_DIR, station_id)
    os.makedirs(station_out_dir, exist_ok=True)

    # Lưu clean_ett kèm features
    df_featured.to_parquet(
        os.path.join(station_out_dir, "clean_ett.parquet"), index=False
    )
    print(f"-> Đã lưu clean_ett.parquet ({len(df_featured)} dòng)")

    # 2. Hourly / Seasonal Quantiles
    quantiles_df = compute_hourly_quantiles(df_featured)
    quantiles_df.to_parquet(
        os.path.join(station_out_dir, "quantile_bands.parquet"), index=False
    )
    print("-> Đã lưu quantile_bands.parquet")

    # 3. STL Decomposition
    period = 96 if is_15min else 24
    stl_df = compute_stl_decomposition(df_featured, col="OT", period=period)
    stl_df.to_parquet(
        os.path.join(station_out_dir, "load_profiles_stl.parquet"), index=False
    )
    print("-> Đã lưu load_profiles_stl.parquet")

    # 4. Lag Correlation (với ETTm1 nhân hệ số 4)
    step_mult = 4 if is_15min else 1
    lag_df = compute_lag_correlation(
        df_featured, max_lag=12, step_multiplier=step_mult
    )
    lag_json = lag_df.to_dict(orient="records")
    with open(
        os.path.join(station_out_dir, "lag_correlation_matrix.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(lag_json, f, indent=2)
    print("-> Đã lưu lag_correlation_matrix.json")

    # 5. Thermal Breach Events
    freq_hours = 0.25 if is_15min else 1.0
    breach_df = extract_breach_events(
        df_featured, threshold=85.0, freq_hours=freq_hours
    )
    breach_df.to_parquet(
        os.path.join(station_out_dir, "thermal_breach_events.parquet"),
        index=False,
    )
    print(
        f"-> Đã lưu thermal_breach_events.parquet ({len(breach_df)} đợt sự cố)"
    )

    # 6. T0204: Tiền tính toán đường cong LOESS
    print("-> Đang tiền tính toán LOESS đa biến...")
    loess_df = precompute_loess_curves(df_featured)
    loess_df.to_parquet(
        os.path.join(station_out_dir, "loess_curves.parquet"), index=False
    )
    print(f"-> Đã lưu loess_curves.parquet ({len(loess_df)} tọa độ làm mịn)")


if __name__ == "__main__":
    process_station("ETTh1", is_15min=False)
    process_station("ETTh2", is_15min=False)
    process_station("ETTm1", is_15min=True)
    print("\n✅ HOÀN THÀNH TOÀN BỘ PIPELINE ARTIFACTS CHO 3 TRẠM!")