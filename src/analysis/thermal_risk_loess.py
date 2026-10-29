"""Module phân tích rủi ro nhiệt, tính toán sự cố vượt ngưỡng và tiền tính toán LOESS."""

import os
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from statsmodels.nonparametric.smoothers_lowess import lowess


def extract_breach_events(
    df: pd.DataFrame,
    threshold: float = 85.0,
    time_col: str = "date",
    freq_hours: float = 1.0,
) -> pd.DataFrame:
    """Trích xuất danh sách các đợt sự cố liên tục vượt ngưỡng không bị double-count."""
    data = df.sort_values(time_col).copy()
    data["is_breach"] = data["OT"] >= threshold

    # Định danh các cụm khối sự cố liên tục (Contiguous event grouping)
    data["event_id"] = (data["is_breach"] != data["is_breach"].shift()).cumsum()
    breach_data = data[data["is_breach"]]

    if breach_data.empty:
        return pd.DataFrame(
            columns=[
                "event_id",
                "start_time",
                "end_time",
                "duration_hours",
                "max_ot",
                "mean_ot",
                "degree_hours",
                "dominant_load_culprit",
                "culprit_zscore",
            ]
        )

    load_cols = ["HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL"]
    global_means = data[load_cols].mean()
    global_stds = data[load_cols].std().replace(0, 1e-5)

    events = []
    for event_id, group in breach_data.groupby("event_id"):
        start_time = group[time_col].iloc[0]
        end_time = group[time_col].iloc[-1]
        duration = len(group) * freq_hours
        max_ot = group["OT"].max()
        mean_ot = group["OT"].mean()
        # Tích lũy độ-giờ (Degree-Hours): diện tích phần vượt ngưỡng
        degree_hours = ((group["OT"] - threshold) * freq_hours).sum()

        # Tính Z-Score của 6 biến phụ tải tại tâm sự cố (thời điểm đỉnh OT)
        peak_idx = group["OT"].idxmax()
        peak_row = group.loc[peak_idx]
        z_scores = {
            col: (peak_row[col] - global_means[col]) / global_stds[col]
            for col in load_cols
        }

        # Xác định nhánh tải có Z-Score đột biến cao nhất
        culprit = max(z_scores, key=z_scores.get)
        culprit_z = z_scores[culprit]

        events.append(
            {
                "event_id": event_id,
                "start_time": start_time,
                "end_time": end_time,
                "duration_hours": duration,
                "max_ot": max_ot,
                "mean_ot": mean_ot,
                "degree_hours": degree_hours,
                "dominant_load_culprit": culprit,
                "culprit_zscore": culprit_z,
            }
        )

    return pd.DataFrame(events)


def precompute_loess_curves(
    df: pd.DataFrame,
    load_cols: Optional[List[str]] = None,
    frac: float = 0.3,
    n_points: int = 100,
) -> pd.DataFrame:
    """T0204: Tiền tính toán đường cong LOESS cho 6 biến tải đối chiếu OT

    theo từng mùa và từng chế độ nhiệt. Lưu tọa độ làm mịn (x, y) để Streamlit vẽ tức thì.
    """
    if load_cols is None:
        load_cols = ["HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL"]

    loess_records = []
    seasons = df["season"].unique()
    regimes = ["All", "Normal", "Warning", "Critical"]

    for season in seasons:
        season_df = df[df["season"] == season]
        for regime in regimes:
            sub_df = (
                season_df
                if regime == "All"
                else season_df[season_df["thermal_regime"] == regime]
            )
            if len(sub_df) < 15:
                continue

            for col in load_cols:
                x_raw = sub_df[col].values
                y_raw = sub_df["OT"].values

                # Loại bỏ NaN nếu có
                valid_mask = np.isfinite(x_raw) & np.isfinite(y_raw)
                if valid_mask.sum() < 15:
                    continue

                x_valid = x_raw[valid_mask]
                y_valid = y_raw[valid_mask]

                # Fit Lowess
                fitted = lowess(
                    y_valid,
                    x_valid,
                    frac=frac,
                    it=3,
                    return_sorted=True,
                )

                # Rút gọn xuống n_points đều nhau để giảm dung lượng file
                if len(fitted) > n_points:
                    indices = np.linspace(
                        0, len(fitted) - 1, n_points, dtype=int
                    )
                    fitted_sample = fitted[indices]
                else:
                    fitted_sample = fitted

                for pt in fitted_sample:
                    loess_records.append(
                        {
                            "season": season,
                            "thermal_regime": regime,
                            "feature": col,
                            "feature_val": pt[0],
                            "loess_ot": pt[1],
                        }
                    )

    return pd.DataFrame(loess_records)