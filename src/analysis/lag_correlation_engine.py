"""Module tính toán ma trận tương quan trễ (Lag Cross-Correlation) giữa phụ tải và OT."""

from typing import Dict, List, Optional
import numpy as np
import pandas as pd


def compute_lag_correlation(
    df: pd.DataFrame,
    target_col: str = "OT",
    load_cols: Optional[List[str]] = None,
    max_lag: int = 12,
    step_multiplier: int = 1,
) -> pd.DataFrame:
    """Tính toán tương quan trễ Pearson giữa các nhánh tải ở t và OT ở t + k.

    Với ETTm1 (15 phút), step_multiplier=4 để quy đổi tương ứng 12 giờ (48 bước).
    """
    if load_cols is None:
        load_cols = ["HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL"]

    results = []
    effective_max_lag = max_lag * step_multiplier

    for lag_hr in range(max_lag + 1):
        actual_shift = lag_hr * step_multiplier
        # Shift target OT về phía trước tương đương với tải ở t và OT ở t + lag
        shifted_ot = df[target_col].shift(-actual_shift)

        row = {"lag_hours": lag_hr}
        for col in load_cols:
            corr = df[col].corr(shifted_ot)
            row[col] = round(corr, 4) if pd.notnull(corr) else 0.0

        results.append(row)

    lag_matrix_df = pd.DataFrame(results)

    # Đánh dấu đỉnh trễ cực đại (Peak thermal inertia) cho từng nhánh tải
    for col in load_cols:
        peak_idx = lag_matrix_df[col].abs().idxmax()
        lag_matrix_df[f"{col}_is_peak"] = lag_matrix_df.index == peak_idx

    return lag_matrix_df