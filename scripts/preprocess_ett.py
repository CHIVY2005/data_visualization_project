#!/usr/bin/env python3
"""
scripts/preprocess_ett.py
-------------------------
Production-ready Data Preprocessing Pipeline for ETT Benchmarks:
- ETTh1, ETTh2 (Hourly granularity, delta_t = 1 hour)
- ETTm1, ETTm2 (15-minute granularity, delta_t = 15 minutes)

Compliant with Project Constitution (AGENTS.md):
- 🔴 RED ZONE: Strictly read-only access to `data/raw/*`.
- 🟢 GREEN ZONE: Outputs standardized parquet and scaler JSON into `data/processed/`.
- 🟡 AMBER ZONE: Uses verified packages in `.venv` (pandas, numpy, pyarrow, etc.).
- Reproducibility: Global SEED = 2026.
- Strict No Data Leakage: Scaler parameters (mean, std) fitted exclusively on Train split.
- Chronological Split: 12 months Train / 4 months Validation / remaining Test (Informer AAAI-21).
- Time Covariates: Raw and normalized temporal position features for Informer embeddings.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Tuple

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ==============================================================================
# PROJECT CONSTANTS & TECHNICAL SPECIFICATIONS (AGENTS.md)
# ==============================================================================

SEED: Final[int] = 2026

STANDARD_COLUMNS: Final[Tuple[str, ...]] = (
    "date",
    "HUFL",
    "HULL",
    "MUFL",
    "MULL",
    "LUFL",
    "LULL",
    "OT",
)

NUMERICAL_FEATURES: Final[Tuple[str, ...]] = (
    "HUFL",
    "HULL",
    "MUFL",
    "MULL",
    "LUFL",
    "LULL",
    "OT",
)

DEFAULT_TARGET: Final[str] = "OT"
CRITICAL_TEMP_THRESHOLD: Final[float] = 95.0
WARNING_TEMP_THRESHOLD: Final[float] = 80.0

# Chronological split definitions (Informer: 12 months train, 4 months val)
# 1 month is standardized to 30 days
HOURLY_STEPS_PER_MONTH: Final[int] = 30 * 24        # 720 steps per month
SUBHOURLY_STEPS_PER_MONTH: Final[int] = 30 * 24 * 4  # 2,880 steps per month (15m)

HOURLY_TRAIN_MONTHS: Final[int] = 12
HOURLY_VAL_MONTHS: Final[int] = 4

DEFAULT_RAW_DIR: Final[str] = "data/raw"
DEFAULT_OUTPUT_PARQUET: Final[str] = "data/processed/clean_ett.parquet"
DEFAULT_SCALER_JSON: Final[str] = "data/processed/scaler_params.json"


# ==============================================================================
# REPRODUCIBILITY & LOGGING SETUP
# ==============================================================================

def set_seed(seed: int = SEED) -> None:
    """Set global seeds to guarantee experiment reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def setup_logger(name: str = "preprocess_ett", verbose: bool = False) -> logging.Logger:
    """Configure standardized logger with clean ISO-like timestamps."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


# ==============================================================================
# METADATA & DATASET CONFIGURATION
# ==============================================================================

@dataclass(frozen=True)
class GranularityConfig:
    """Configuration specification based on dataset temporal frequency."""
    label: str
    expected_freq: pd.Timedelta
    freq_seconds: int
    train_rows: int
    val_rows: int
    is_subhourly: bool


def resolve_granularity(dataset_name: str) -> GranularityConfig:
    """
    Resolve frequency parameters and train/val row cuts from dataset name.
    
    Parameters
    ----------
    dataset_name : str
        Canonical dataset identifier (e.g., 'ETTh1', 'ETTh2', 'ETTm1', 'ETTm2').
        
    Returns
    -------
    GranularityConfig
        Structured configuration for frequency and split boundaries.
    """
    clean_name = dataset_name.strip().replace(".csv", "").upper()
    
    if clean_name.startswith("ETTH"):
        # Hourly dataset (1 hour steps)
        train_rows = HOURLY_TRAIN_MONTHS * HOURLY_STEPS_PER_MONTH       # 8,640
        val_rows = HOURLY_VAL_MONTHS * HOURLY_STEPS_PER_MONTH           # 2,880
        return GranularityConfig(
            label="Hourly",
            expected_freq=pd.Timedelta(hours=1),
            freq_seconds=3600,
            train_rows=train_rows,
            val_rows=val_rows,
            is_subhourly=False,
        )
    elif clean_name.startswith("ETTM"):
        # 15-minute dataset (15 min steps)
        train_rows = HOURLY_TRAIN_MONTHS * SUBHOURLY_STEPS_PER_MONTH   # 34,560
        val_rows = HOURLY_VAL_MONTHS * SUBHOURLY_STEPS_PER_MONTH       # 11,520
        return GranularityConfig(
            label="15-Minute",
            expected_freq=pd.Timedelta(minutes=15),
            freq_seconds=900,
            train_rows=train_rows,
            val_rows=val_rows,
            is_subhourly=True,
        )
    else:
        # Default fallback to hourly if unrecognized
        logging.getLogger("preprocess_ett").warning(
            "Unrecognized dataset prefix '%s'. Falling back to Hourly configuration.",
            clean_name,
        )
        train_rows = HOURLY_TRAIN_MONTHS * HOURLY_STEPS_PER_MONTH
        val_rows = HOURLY_VAL_MONTHS * HOURLY_STEPS_PER_MONTH
        return GranularityConfig(
            label="Hourly (Default)",
            expected_freq=pd.Timedelta(hours=1),
            freq_seconds=3600,
            train_rows=train_rows,
            val_rows=val_rows,
            is_subhourly=False,
        )


# ==============================================================================
# PIPELINE FUNCTIONS
# ==============================================================================

def load_and_audit_raw_data(
    raw_path: Path,
    expected_freq: pd.Timedelta,
    target_col: str = DEFAULT_TARGET,
    logger: Optional[logging.Logger] = None,
) -> pd.DataFrame:
    """
    Load raw ETT dataset strictly in read-only mode, audit data hygiene, and cast types.
    
    Audits performed:
    1. Schema presence: Verify all 8 standard columns exist.
    2. Date parsing: Parse to RFC3339 datetime64[ns] and sort monotonically.
    3. Duplicate check: Identify any duplicate timestamps.
    4. Continuity audit: Check time step consistency with expected frequency.
    5. Missing / Anomaly audit: Zero NaN/Null/Inf verification on all features.
    6. Type casting: Cast 7 numerical variables to float32.
    """
    log = logger or logging.getLogger("preprocess_ett")
    
    if not raw_path.is_file():
        raise FileNotFoundError(f"Raw data file not found at: {raw_path}")
        
    log.info("Loading raw dataset from (READ-ONLY): %s", raw_path)
    # Strictly read without modifying original file
    df = pd.read_csv(raw_path)
    log.info("Raw data loaded successfully: shape=%s, memory=%.2f MB", df.shape, df.memory_usage().sum() / (1024 * 1024))
    
    # 1. Schema Validation
    missing_cols = [c for c in STANDARD_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Raw data violates standard schema. Missing columns: {missing_cols}")
        
    if target_col not in df.columns:
        raise ValueError(f"Target variable '{target_col}' not found in dataframe columns: {df.columns.tolist()}")

    # 2. Date Standardization & Monotonic Ordering
    log.info("Auditing temporal index and monotonicity...")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    
    null_dates = df["date"].isna().sum()
    if null_dates > 0:
        raise ValueError(f"Found {null_dates} unparseable timestamps in 'date' column.")
        
    # Cast explicitly to datetime64[ns]
    df["date"] = df["date"].astype("datetime64[ns]")
    
    # Sort chronologically
    df = df.sort_values(by="date", ascending=True).reset_index(drop=True)
    
    # 3. Duplicate Timestamp Audit
    duplicate_count = df["date"].duplicated().sum()
    if duplicate_count > 0:
        log.warning("Detected %d duplicate timestamps in raw dataset! Removing duplicates...", duplicate_count)
        df = df.drop_duplicates(subset=["date"], keep="first").reset_index(drop=True)
    else:
        log.info("Duplicate check PASSED: Zero duplicate timestamps found.")

    # 4. Continuity & Step Uniformity Audit
    time_diffs = df["date"].diff().dropna()
    unique_steps = time_diffs.unique()
    log.info("Temporal step audit: observed deltas = %s", [str(td) for td in unique_steps])
    
    if len(unique_steps) == 1 and unique_steps[0] == expected_freq:
        log.info("Step uniformity check PASSED: perfectly uniform delta_t = %s", expected_freq)
    else:
        gap_count = (time_diffs != expected_freq).sum()
        log.warning(
            "Temporal step discontinuity detected: %d intervals differ from expected %s.",
            gap_count,
            expected_freq,
        )

    # 5. Missing Values & Anomaly Audit
    log.info("Auditing missing values (NaN/Null/Empty) and infinite values (Inf/-Inf)...")
    null_audit = df[list(STANDARD_COLUMNS)].isna().sum()
    total_nulls = null_audit.sum()
    if total_nulls > 0:
        log.warning("Detected null values: %s. Applying forward-fill / backward-fill imputation.", null_audit.to_dict())
        df = df.ffill().bfill()
    else:
        log.info("Missing value audit PASSED: Zero null values across all %d standard columns.", len(STANDARD_COLUMNS))

    # Check infinite values
    num_cols = [c for c in NUMERICAL_FEATURES if c in df.columns]
    inf_count = np.isinf(df[num_cols].to_numpy()).sum()
    if inf_count > 0:
        raise ValueError(f"Detected {inf_count} infinite values (+inf / -inf) in numerical features.")
    else:
        log.info("Infinite value audit PASSED: Zero infinite values detected.")

    # 6. Numerical Precision Casting (float32 for PyTorch tensors)
    log.info("Casting numerical features to float32...")
    for col in num_cols:
        df[col] = df[col].astype(np.float32)

    # Check physical safety boundaries for target OT
    if target_col in df.columns:
        ot_series = df[target_col]
        breach_count = (ot_series >= CRITICAL_TEMP_THRESHOLD).sum()
        warning_count = ((ot_series >= WARNING_TEMP_THRESHOLD) & (ot_series < CRITICAL_TEMP_THRESHOLD)).sum()
        log.info(
            "Target '%s' physical boundaries audit: min=%.2f°C, max=%.2f°C, mean=%.2f°C. Warning(>=80°C)=%d, Critical(>=95°C)=%d",
            target_col,
            float(ot_series.min()),
            float(ot_series.max()),
            float(ot_series.mean()),
            int(warning_count),
            int(breach_count),
        )

    return df


def extract_time_covariates(df: pd.DataFrame, is_subhourly: bool = False) -> pd.DataFrame:
    """
    Extract temporal covariates for Informer positional and temporal embeddings.
    
    Generates both raw integer coordinates and scaled coordinates normalized to [-0.5, 0.5]:
    - hour (0-23) & hour_norm
    - day_of_week (0-6, Monday=0) & day_of_week_norm
    - day (1-31) & day_norm
    - month (1-12) & month_norm
    - [Optional for 15-minute data]: minute (0-59) & minute_norm
    """
    dt_series = df["date"].dt
    
    # Raw integer features
    df["hour"] = dt_series.hour.astype(np.int32)
    df["day_of_week"] = dt_series.dayofweek.astype(np.int32)
    df["day"] = dt_series.day.astype(np.int32)
    df["month"] = dt_series.month.astype(np.int32)
    
    # Normalized features bounded in [-0.5, 0.5]
    df["hour_norm"] = ((df["hour"] / 23.0) - 0.5).astype(np.float32)
    df["day_of_week_norm"] = ((df["day_of_week"] / 6.0) - 0.5).astype(np.float32)
    df["day_norm"] = (((df["day"] - 1.0) / 30.0) - 0.5).astype(np.float32)
    df["month_norm"] = (((df["month"] - 1.0) / 11.0) - 0.5).astype(np.float32)

    if is_subhourly:
        df["minute"] = dt_series.minute.astype(np.int32)
        df["minute_norm"] = ((df["minute"] / 59.0) - 0.5).astype(np.float32)

    return df


def assign_chronological_splits(
    df: pd.DataFrame,
    train_rows: int,
    val_rows: int,
    logger: Optional[logging.Logger] = None,
) -> pd.DataFrame:
    """
    Partition dataset into Train / Validation / Test sets chronologically.
    
    Strictly follows Informer AAAI-21:
    - Train: First 12 months (indices 0 to train_rows - 1).
    - Validation: Next 4 months (indices train_rows to train_rows + val_rows - 1).
    - Test: Remaining records to the end of the observation window.
    
    Assigns an in-place categorical 'split' column.
    """
    log = logger or logging.getLogger("preprocess_ett")
    total_rows = len(df)
    
    min_required = train_rows + val_rows
    if total_rows < min_required:
        raise ValueError(
            f"Insufficient records for standard split. Required at least {min_required}, but dataset has {total_rows}."
        )

    split_arr = np.empty(total_rows, dtype=object)
    split_arr[:train_rows] = "train"
    split_arr[train_rows : train_rows + val_rows] = "val"
    split_arr[train_rows + val_rows :] = "test"
    
    df["split"] = pd.Categorical(split_arr, categories=["train", "val", "test"], ordered=True)
    
    train_count = (df["split"] == "train").sum()
    val_count = (df["split"] == "val").sum()
    test_count = (df["split"] == "test").sum()
    
    log.info(
        "Chronological split assigned: Total=%d | Train=%d (%.1f%%) | Val=%d (%.1f%%) | Test=%d (%.1f%%)",
        total_rows,
        train_count,
        (train_count / total_rows) * 100,
        val_count,
        (val_count / total_rows) * 100,
        test_count,
        (test_count / total_rows) * 100,
    )
    
    # Log temporal boundaries for each split
    for split_name in ["train", "val", "test"]:
        sub_df = df[df["split"] == split_name]
        log.info(
            "Split '%s': start=%s | end=%s | rows=%d",
            split_name,
            sub_df["date"].iloc[0].strftime("%Y-%m-%d %H:%M:%S"),
            sub_df["date"].iloc[-1].strftime("%Y-%m-%d %H:%M:%S"),
            len(sub_df),
        )

    return df


def fit_scaler_and_normalize(
    df: pd.DataFrame,
    features: List[str],
    dataset_name: str,
    target_col: str,
    logger: Optional[logging.Logger] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Compute StandardScaler parameters (mean, std) exclusively on the Train split.
    
    Guarantees zero data leakage:
    - Fits mu_train and sigma_train only where split == 'train'.
    - Scales Train, Val, and Test using mu_train and sigma_train.
    - Appends scaled features as '{col}_scaled' (float32).
    - Retains pristine raw features in physical units for dashboards & EDA.
    
    Returns
    -------
    Tuple[pd.DataFrame, Dict[str, Any]]
        Transformed DataFrame with scaled columns, and dictionary of scaler parameters.
    """
    log = logger or logging.getLogger("preprocess_ett")
    log.info("Fitting StandardScaler on TRAIN split only (Strict No Data Leakage)...")

    train_mask = df["split"] == "train"
    train_df = df.loc[train_mask]
    
    scaler_dict: Dict[str, Dict[str, float]] = {}
    
    for col in features:
        train_vals = train_df[col].to_numpy(dtype=np.float64)
        mean_val = float(np.mean(train_vals))
        std_val = float(np.std(train_vals, ddof=0))
        
        # Defensive check against division by zero
        if std_val < 1e-8:
            log.warning("Feature '%s' has near-zero standard deviation (%.6e). Setting std to 1.0.", col, std_val)
            std_val = 1.0

        scaler_dict[col] = {
            "mean": round(mean_val, 6),
            "std": round(std_val, 6),
        }
        
        # Compute normalized values across all splits
        scaled_vals = (df[col].to_numpy(dtype=np.float64) - mean_val) / std_val
        df[f"{col}_scaled"] = scaled_vals.astype(np.float32)

    log.info("StandardScaler fitted successfully for %d numerical features.", len(features))
    for col, params in scaler_dict.items():
        log.debug("Scaler '%s': mean=%.4f, std=%.4f", col, params["mean"], params["std"])

    scaler_artifact: Dict[str, Any] = {
        "dataset": dataset_name,
        "target": target_col,
        "fitted_on": "train",
        "train_rows": int(train_mask.sum()),
        "features": scaler_dict,
        "metadata": {
            "seed": SEED,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "critical_threshold_95c": CRITICAL_TEMP_THRESHOLD,
            "warning_threshold_80c": WARNING_TEMP_THRESHOLD,
        },
    }

    return df, scaler_artifact


def export_artifacts(
    df: pd.DataFrame,
    parquet_path: Path,
    scaler_path: Path,
    scaler_artifact: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Export processed clean dataset to Parquet and scaler parameters to JSON.
    
    Uses PyArrow engine with Snappy compression for Parquet.
    """
    log = logger or logging.getLogger("preprocess_ett")
    
    # 1. Ensure target directories exist
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    scaler_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 2. Export Scaler Parameters JSON
    log.info("Exporting scaler parameters to: %s", scaler_path)
    with open(scaler_path, "w", encoding="utf-8") as f:
        json.dump(scaler_artifact, f, indent=2, ensure_ascii=False)
    log.info("Scaler JSON written: %.2f KB", scaler_path.stat().st_size / 1024.0)

    # 3. Export Clean Parquet
    log.info("Exporting clean dataset to Parquet: %s", parquet_path)
    # PyArrow export with snappy compression
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, parquet_path, compression="snappy")
    
    file_size_mb = parquet_path.stat().st_size / (1024.0 * 1024.0)
    log.info("Parquet export completed successfully: %.2f MB", file_size_mb)


# ==============================================================================
# CLI ARGUMENT PARSER & ORCHESTRATION
# ==============================================================================

def parse_args() -> argparse.Namespace:
    """Parse command line arguments for preprocess_ett.py."""
    parser = argparse.ArgumentParser(
        description="Preprocess and sanitize ETT time-series datasets for Informer forecasting.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data",
        type=str,
        default="ETTh1",
        help="Target dataset name (ETTh1, ETTh2, ETTm1, ETTm2).",
    )
    parser.add_argument(
        "--raw_dir",
        type=str,
        default=DEFAULT_RAW_DIR,
        help="Path to raw dataset directory containing source CSV files.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=DEFAULT_OUTPUT_PARQUET,
        help="Output path for the clean Parquet file.",
    )
    parser.add_argument(
        "--scaler_out",
        type=str,
        default=DEFAULT_SCALER_JSON,
        help="Output path for the scaler parameters JSON file.",
    )
    parser.add_argument(
        "--target",
        type=str,
        default=DEFAULT_TARGET,
        help="Name of the forecast target variable.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SEED,
        help="Random seed for reproducibility.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logging.",
    )
    return parser.parse_args()


def run_pipeline(
    dataset_name: str = "ETTh1",
    raw_dir: str = DEFAULT_RAW_DIR,
    out_path: str = DEFAULT_OUTPUT_PARQUET,
    scaler_out_path: str = DEFAULT_SCALER_JSON,
    target_col: str = DEFAULT_TARGET,
    seed: int = SEED,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Programmatic entrypoint for the complete preprocessing pipeline.
    """
    start_time = time.perf_counter()
    logger = setup_logger("preprocess_ett", verbose=verbose)
    logger.info("=" * 70)
    logger.info("STARTING ETT DATA PREPROCESSING PIPELINE (Task T0101)")
    logger.info("=" * 70)

    # 1. Reproducibility
    set_seed(seed)
    logger.info("Global seed initialized to: %d", seed)

    # 2. Granularity Resolution
    gran_cfg = resolve_granularity(dataset_name)
    logger.info(
        "Dataset '%s' resolved to: %s (delta_t=%s, train_rows=%d, val_rows=%d)",
        dataset_name,
        gran_cfg.label,
        gran_cfg.expected_freq,
        gran_cfg.train_rows,
        gran_cfg.val_rows,
    )

    # 3. Locate Raw CSV
    clean_ds_name = dataset_name.strip()
    if not clean_ds_name.endswith(".csv"):
        clean_ds_name = f"{clean_ds_name}.csv"
    raw_file = Path(raw_dir) / clean_ds_name
    
    parquet_dest = Path(out_path)
    scaler_dest = Path(scaler_out_path)

    # 4. Load, Audit, and Clean Raw Data
    df = load_and_audit_raw_data(
        raw_path=raw_file,
        expected_freq=gran_cfg.expected_freq,
        target_col=target_col,
        logger=logger,
    )

    # 5. Extract Time Covariates
    logger.info("Extracting temporal covariates (hour, day_of_week, day, month, normalized)...")
    df = extract_time_covariates(df, is_subhourly=gran_cfg.is_subhourly)

    # 6. Assign Chronological Splits
    df = assign_chronological_splits(
        df=df,
        train_rows=gran_cfg.train_rows,
        val_rows=gran_cfg.val_rows,
        logger=logger,
    )

    # 7. Fit Scaler (No Data Leakage) & Normalize
    feature_list = [c for c in NUMERICAL_FEATURES if c in df.columns]
    df, scaler_artifact = fit_scaler_and_normalize(
        df=df,
        features=feature_list,
        dataset_name=dataset_name,
        target_col=target_col,
        logger=logger,
    )

    # 8. Export Artifacts
    export_artifacts(
        df=df,
        parquet_path=parquet_dest,
        scaler_path=scaler_dest,
        scaler_artifact=scaler_artifact,
        logger=logger,
    )

    # 9. Verify Output Integrity
    logger.info("Verifying exported Parquet file integrity...")
    df_verify = pd.read_parquet(parquet_dest)
    elapsed_sec = time.perf_counter() - start_time
    
    summary = {
        "status": "SUCCESS",
        "dataset": dataset_name,
        "total_records": len(df_verify),
        "total_columns": len(df_verify.columns),
        "columns": df_verify.columns.tolist(),
        "splits": df_verify["split"].value_counts().to_dict(),
        "parquet_size_bytes": parquet_dest.stat().st_size,
        "scaler_size_bytes": scaler_dest.stat().st_size,
        "elapsed_seconds": round(elapsed_sec, 3),
    }

    logger.info("=" * 70)
    logger.info(
        "PREPROCESSING COMPLETED IN %.3f SECONDS. Shape: %s, Columns: %d",
        elapsed_sec,
        df_verify.shape,
        len(df_verify.columns),
    )
    logger.info("Output Parquet: %s (%.2f MB)", parquet_dest, summary["parquet_size_bytes"] / (1024 * 1024))
    logger.info("Output Scaler:  %s (%.2f KB)", scaler_dest, summary["scaler_size_bytes"] / 1024)
    logger.info("=" * 70)

    return summary


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    try:
        run_pipeline(
            dataset_name=args.data,
            raw_dir=args.raw_dir,
            out_path=args.out,
            scaler_out_path=args.scaler_out,
            target_col=args.target,
            seed=args.seed,
            verbose=args.verbose,
        )
        return 0
    except Exception as exc:
        logging.getLogger("preprocess_ett").error("Pipeline execution failed: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""
Lệnh thực thi

python scripts/preprocess_ett.py --data ETTh1 --out data/processed/clean_ett.parquet

"""