"""Module phân rã chuỗi thời gian (STL) và tính toán dải phân vị thực nghiệm lịch sử."""

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL


def compute_hourly_quantiles(
    df: pd.DataFrame,
    quantiles: List[float] = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95],
) -> pd.DataFrame:
    """Tính toán dải phân vị lịch sử của OT và tổng tải theo khung giờ x mùa."""
    target_cols = ["OT", "total_useful_load", "total_unuseful_load"]

    records = []
    for (season, hour), group in df.groupby(["season", "hour"]):
        row = {"season": season, "hour": hour}
        for col in target_cols:
            for q in quantiles:
                q_label = f"{col}_q{int(q*100):02d}"
                row[q_label] = group[col].quantile(q)
            row[f"{col}_mean"] = group[col].mean()
            row[f"{col}_std"] = group[col].std()
        records.append(row)

    return pd.DataFrame(records).sort_values(["season", "hour"]).reset_index(
        drop=True
    )


def compute_stl_decomposition(
    df: pd.DataFrame,
    col: str = "OT",
    period: int = 24,
) -> pd.DataFrame:
    """Phân rã chuỗi thời gian thành Trend, Seasonal, Residual."""
    res = STL(df[col], period=period, robust=True).fit()
    decomp_df = pd.DataFrame(
        {
            "date": df["date"],
            "observed": df[col],
            "trend": res.trend,
            "seasonal": res.seasonal,
            "residual": res.resid,
        }
    )
    return decomp_df