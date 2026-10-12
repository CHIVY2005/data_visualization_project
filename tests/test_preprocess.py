"""
tests/test_preprocess.py
------------------------
Unit and regression test suite for scripts/preprocess_ett.py.
Compliant with Project Constitution (AGENTS.md).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAW_DATA_PATH = Path("data/raw/ETTh1.csv")
PARQUET_PATH = Path("data/processed/clean_ett.parquet")
SCALER_PATH = Path("data/processed/scaler_params.json")

EXPECTED_COLUMNS = [
    "date",
    "HUFL",
    "HULL",
    "MUFL",
    "MULL",
    "LUFL",
    "LULL",
    "OT",
    "hour",
    "day_of_week",
    "day",
    "month",
    "hour_norm",
    "day_of_week_norm",
    "day_norm",
    "month_norm",
    "split",
    "HUFL_scaled",
    "HULL_scaled",
    "MUFL_scaled",
    "MULL_scaled",
    "LUFL_scaled",
    "LULL_scaled",
    "OT_scaled",
]

NUMERICAL_FEATURES = ["HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL", "OT"]


def test_parquet_file_exists():
    """Verify that clean_ett.parquet exists in data/processed/."""
    assert PARQUET_PATH.is_file(), f"Parquet artifact missing: {PARQUET_PATH}"


def test_scaler_json_exists():
    """Verify that scaler_params.json exists in data/processed/."""
    assert SCALER_PATH.is_file(), f"Scaler JSON artifact missing: {SCALER_PATH}"


def test_clean_parquet_schema():
    """Verify schema, columns, and data types of clean_ett.parquet."""
    df = pd.read_parquet(PARQUET_PATH)
    assert len(df) == 17420, f"Expected 17,420 rows, got {len(df)}"

    for col in EXPECTED_COLUMNS:
        assert col in df.columns, f"Missing expected column '{col}' in clean_ett.parquet"

    # Datetime type check
    assert pd.api.types.is_datetime64_any_dtype(df["date"]), "Column 'date' must be datetime64[ns]"

    # Monotonicity check
    assert df["date"].is_monotonic_increasing, "Timestamps in 'date' must be strictly increasing"

    # Numeric precision check
    for col in NUMERICAL_FEATURES:
        assert df[col].dtype == np.float32, f"Column '{col}' must be float32"
        assert df[f"{col}_scaled"].dtype == np.float32, f"Column '{col}_scaled' must be float32"


def test_data_hygiene_zero_nulls_and_infs():
    """Verify zero NaN, null, and infinite values in processed dataset."""
    df = pd.read_parquet(PARQUET_PATH)
    null_counts = df.isna().sum().sum()
    assert null_counts == 0, f"Detected {null_counts} null values in clean dataset"

    numeric_cols = [c for c in df.columns if c not in ["date", "split"]]
    inf_counts = np.isinf(df[numeric_cols].to_numpy()).sum()
    assert inf_counts == 0, f"Detected {inf_counts} infinite values in numeric columns"


def test_chronological_split_integrity():
    """Verify Informer AAAI-21 chronological split counts (12/4/4 months)."""
    df = pd.read_parquet(PARQUET_PATH)
    split_counts = df["split"].value_counts()

    assert split_counts["train"] == 8640, f"Expected 8640 train rows, got {split_counts['train']}"
    assert split_counts["val"] == 2880, f"Expected 2880 val rows, got {split_counts['val']}"
    assert split_counts["test"] == 5900, f"Expected 5900 test rows, got {split_counts['test']}"

    # Verify temporal non-overlap
    train_max_date = df[df["split"] == "train"]["date"].max()
    val_min_date = df[df["split"] == "val"]["date"].min()
    val_max_date = df[df["split"] == "val"]["date"].max()
    test_min_date = df[df["split"] == "test"]["date"].min()

    assert train_max_date < val_min_date, "Train split leaks into validation split"
    assert val_max_date < test_min_date, "Validation split leaks into test split"


def test_scaler_parameters_and_normalization():
    """Verify scaler parameters and strict no data leakage normalization."""
    with open(SCALER_PATH, "r", encoding="utf-8") as f:
        scaler_data = json.load(f)

    assert scaler_data["dataset"] == "ETTh1"
    assert scaler_data["target"] == "OT"
    assert scaler_data["train_rows"] == 8640

    df = pd.read_parquet(PARQUET_PATH)
    train_df = df[df["split"] == "train"]

    for col in NUMERICAL_FEATURES:
        assert col in scaler_data["features"]
        mean_p = scaler_data["features"][col]["mean"]
        std_p = scaler_data["features"][col]["std"]

        assert std_p > 0.0, f"Standard deviation of {col} must be strictly positive"

        # Check that scaled train values have approximately mean 0 and std 1
        train_scaled = train_df[f"{col}_scaled"].to_numpy()
        assert np.isclose(train_scaled.mean(), 0.0, atol=1e-3), f"{col}_scaled mean is not ~0"
        assert np.isclose(train_scaled.std(), 1.0, atol=1e-3), f"{col}_scaled std is not ~1"


def test_raw_data_untouched():
    """Verify that RED ZONE raw data is completely unmodified."""
    import hashlib

    expected_sha256 = "f18de3ad269cef59bb07b5438d79bb3042d3be49bdeecf01c1cd6d29695ee066"
    with open(RAW_DATA_PATH, "rb") as f:
        actual_sha256 = hashlib.sha256(f.read()).hexdigest()

    assert actual_sha256 == expected_sha256, "RED ZONE VIOLATION: Raw ETTh1.csv has been modified!"
