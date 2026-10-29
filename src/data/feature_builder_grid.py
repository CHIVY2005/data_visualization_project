"""Module Feature Engineering cho bộ dữ liệu ETT Grid."""

from typing import List
import numpy as np
import pandas as pd


def add_grid_features(
    df: pd.DataFrame, time_col: str = "date"
) -> pd.DataFrame:
    """Tạo các đặc trưng phái sinh ngành điện và chế độ nhiệt."""
    data = df.copy()

    # Đảm bảo datetime
    if not np.issubdtype(data[time_col].dtype, np.datetime64):
        data[time_col] = pd.to_datetime(data[time_col])

    # 1. Tổng tải hữu ích và vô ích qua 3 cấp áp (High, Middle, Low)
    data["total_useful_load"] = data["HUFL"] + data["MUFL"] + data["LUFL"]
    data["total_unuseful_load"] = data["HULL"] + data["MULL"] + data["LULL"]

    # 2. Tỷ lệ vô công / hữu công (reactive_ratio) tránh chia cho 0
    data["reactive_ratio"] = data["total_unuseful_load"] / (
        data["total_useful_load"].abs() + 1e-5
    )

    # 3. Đặc trưng thời gian chu kỳ
    data["hour"] = data[time_col].dt.hour
    data["dayofweek"] = data[time_col].dt.dayofweek
    data["month"] = data[time_col].dt.month

    # Phân loại mùa (12, 1, 2: Đông; 3, 4, 5: Xuân; 6, 7, 8: Hè; 9, 10, 11: Thu)
    season_map = {
        12: "Winter",
        1: "Winter",
        2: "Winter",
        3: "Spring",
        4: "Spring",
        5: "Spring",
        6: "Summer",
        7: "Summer",
        8: "Summer",
        9: "Autumn",
        10: "Autumn",
        11: "Autumn",
    }
    data["season"] = data["month"].map(season_map)

    # 4. Phân loại chế độ nhiệt an toàn (Stevens Ordinal Scale)
    conditions = [
        (data["OT"] < 85.0),
        (data["OT"] >= 85.0) & (data["OT"] < 95.0),
        (data["OT"] >= 95.0),
    ]
    choices = ["Normal", "Warning", "Critical"]
    data["thermal_regime"] = np.select(conditions, choices, default="Normal")

    # 5. Mức độ vượt ngưỡng (Degree-Hours Exceedance)
    data["exceedance_85"] = np.maximum(0.0, data["OT"] - 85.0)
    data["exceedance_95"] = np.maximum(0.0, data["OT"] - 95.0)

    return data