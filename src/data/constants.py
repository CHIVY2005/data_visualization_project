"""Shared T0102 artifact and sliding-window configuration."""

from typing import Final, Tuple

SEED: Final[int] = 2026
DEFAULT_DATA_PATH: Final[str] = "data/processed/clean_ett.parquet"
DEFAULT_SIZE: Final[Tuple[int, int, int]] = (96, 48, 24)
DEFAULT_BATCH_SIZE: Final[int] = 32
SPLITS: Final[Tuple[str, ...]] = ("train", "val", "test")
NUMERICAL_FEATURES: Final[Tuple[str, ...]] = (
    "HUFL", "HULL", "MUFL", "MULL", "LUFL", "LULL", "OT",
)
TIME_FEATURES: Final[Tuple[str, ...]] = (
    "hour", "day_of_week", "day", "month",
)
TIME_MARK_COLUMNS: Final[Tuple[str, ...]] = tuple(
    f"{column}_norm" for column in TIME_FEATURES
)
ARTIFACT_COLUMNS: Final[Tuple[str, ...]] = (
    "date", *NUMERICAL_FEATURES, *TIME_FEATURES, *TIME_MARK_COLUMNS,
    "split", *(f"{column}_scaled" for column in NUMERICAL_FEATURES),
)
TIME_MARK_MIN: Final[float] = -0.5
TIME_MARK_MAX: Final[float] = 0.5
HOURLY_FREQUENCY: Final[str] = "1h"
SMOKE_HORIZONS: Final[Tuple[int, ...]] = (24, 168)
WORKER_SEED_MODULUS: Final[int] = 2**32
