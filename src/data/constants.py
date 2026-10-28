"""Shared physical-data contracts; seasons are project month bins, not climate."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = 2026
SCHEMA_VERSION = "2.0"
WARNING_TEMP_THRESHOLD = 85.0
CRITICAL_TEMP_THRESHOLD = 95.0
CADENCE_MINUTES = {"ETTh1": 60, "ETTh2": 60, "ETTm1": 15}
MEASUREMENTS = ("OT", "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL")
USEFUL_LOADS = ("HUFL", "MUFL", "LUFL")
UNUSEFUL_LOADS = ("HULL", "MULL", "LULL")
TOTAL_COLUMNS = ("total_useful_load", "total_unuseful_load")
FLOAT_COLUMNS = (*MEASUREMENTS, *TOTAL_COLUMNS, "reactive_ratio")
CLEAN_COLUMNS = (
    "dataset", "timestamp", *MEASUREMENTS, *TOTAL_COLUMNS,
    "reactive_ratio", "thermal_regime", "is_imputed",
)
TEMPORAL_COLUMNS = (
    "hour", "day_of_week", "day_name", "is_weekend", "month", "season",
)
SHARE_COLUMNS = ("HUFL_ratio", "MUFL_ratio", "LUFL_ratio")
FEATURE_COLUMNS = (*CLEAN_COLUMNS, *TEMPORAL_COLUMNS, *SHARE_COLUMNS)
DRY_MONTHS = (11, 12, 1, 2, 3, 4)
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SEASON_CONVENTION = "project_month_bins_Dry_Nov_Apr_Wet_May_Oct_not_verified_climate"
DEFAULT_CLEAN_PATH = ROOT / "data" / "processed" / "clean_ett.parquet"
DEFAULT_FEATURE_PATH = ROOT / "data" / "processed" / "grid_features.parquet"
