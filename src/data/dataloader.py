"""ETT hourly dataset and sliding-window DataLoader utilities."""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader, Dataset

try:
    from src.data.constants import (
        DEFAULT_BATCH_SIZE,
        DEFAULT_DATA_PATH,
        DEFAULT_SIZE,
        NUMERICAL_FEATURES,
        SEED,
        SPLITS,
        TIME_MARK_COLUMNS,
    )
except ModuleNotFoundError:
    # Support both package imports and ``python src/data/dataloader.py``.
    from constants import (
        DEFAULT_BATCH_SIZE,
        DEFAULT_DATA_PATH,
        DEFAULT_SIZE,
        NUMERICAL_FEATURES,
        SEED,
        SPLITS,
        TIME_MARK_COLUMNS,
    )

LOGGER = logging.getLogger(__name__)


class Dataset_ETT_hour(Dataset[Tuple[torch.Tensor, ...]]):
    """Hourly ETT data partitioned by T0101 with Informer-style windows."""

    def __init__(
        self,
        data_path: str = DEFAULT_DATA_PATH,
        flag: str = "train",
        size: Tuple[int, int, int] = DEFAULT_SIZE,
        features: str = "M",
        target: str = "OT",
        scale: bool = True,
    ) -> None:
        if flag not in SPLITS:
            raise ValueError(f"flag must be one of {SPLITS}; got {flag!r}")
        if len(size) != 3:
            raise ValueError("size must contain (seq_len, label_len, pred_len)")
        self.seq_len, self.label_len, self.pred_len = size
        if self.seq_len <= 0 or self.pred_len <= 0:
            raise ValueError("seq_len and pred_len must be positive")
        if self.label_len < 0 or self.label_len > self.seq_len:
            raise ValueError("label_len must be between zero and seq_len")
        if features not in ("M", "S"):
            raise ValueError("features must be 'M' (multivariate) or 'S' (univariate)")
        if target not in NUMERICAL_FEATURES:
            raise ValueError(f"target must be one of {NUMERICAL_FEATURES}")

        path = Path(data_path)
        if not path.is_file():
            raise FileNotFoundError(f"ETT parquet artifact does not exist: {path}")

        frame = pd.read_parquet(path)
        required_columns = {"split", *TIME_MARK_COLUMNS}
        value_columns = (
            (target,) if features == "S" else NUMERICAL_FEATURES
        )
        selected_columns = tuple(
            f"{column}_scaled" if scale else column for column in value_columns
        )
        required_columns.update(selected_columns)
        missing_columns = sorted(required_columns.difference(frame.columns))
        if missing_columns:
            raise ValueError(f"Parquet artifact is missing columns: {missing_columns}")

        self.flag = flag
        self.features = features
        self.target = target
        self.scale = scale
        partition = frame.loc[frame["split"] == flag]
        if partition.empty:
            raise ValueError(f"No rows found for split {flag!r} in {path}")

        self.data_x = partition.loc[:, selected_columns].to_numpy(
            dtype=np.float32, copy=True
        )
        self.data_stamp = partition.loc[:, TIME_MARK_COLUMNS].to_numpy(
            dtype=np.float32, copy=True
        )
        if not np.isfinite(self.data_x).all():
            raise ValueError(f"Non-finite values found in {selected_columns}")
        if not np.isfinite(self.data_stamp).all():
            raise ValueError(f"Non-finite values found in {TIME_MARK_COLUMNS}")
        if len(self.data_x) < self.seq_len + self.pred_len:
            raise ValueError(
                f"Split {flag!r} has {len(self.data_x)} rows; at least "
                f"{self.seq_len + self.pred_len} are required for a window"
            )

    def __len__(self) -> int:
        """Return the number of complete encoder and forecast windows."""
        return len(self.data_x) - self.seq_len - self.pred_len + 1

    def __getitem__(self, index: int) -> Tuple[torch.Tensor, ...]:
        """Return encoder values, decoder values, and their time marks."""
        if index < 0 or index >= len(self):
            raise IndexError(f"window index out of range: {index}")
        s_begin = index
        s_end = s_begin + self.seq_len
        r_begin = s_end - self.label_len
        r_end = s_end + self.pred_len

        seq_x = torch.from_numpy(self.data_x[s_begin:s_end])
        seq_y = torch.from_numpy(self.data_x[r_begin:r_end])
        seq_x_mark = torch.from_numpy(self.data_stamp[s_begin:s_end])
        seq_y_mark = torch.from_numpy(self.data_stamp[r_begin:r_end])
        return seq_x, seq_y, seq_x_mark, seq_y_mark


def get_data_loader(
    data_path: str = DEFAULT_DATA_PATH,
    flag: str = "train",
    batch_size: int = DEFAULT_BATCH_SIZE,
    seq_len: int = DEFAULT_SIZE[0],
    label_len: int = DEFAULT_SIZE[1],
    pred_len: int = DEFAULT_SIZE[2],
    features: str = "M",
    target: str = "OT",
    scale: bool = True,
    num_workers: int = 0,
    drop_last: Optional[bool] = None,
) -> Tuple[Dataset_ETT_hour, DataLoader]:
    """Create an ETT dataset and loader with time-series-safe split policy."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if num_workers < 0:
        raise ValueError("num_workers cannot be negative")
    dataset = Dataset_ETT_hour(
        data_path=data_path,
        flag=flag,
        size=(seq_len, label_len, pred_len),
        features=features,
        target=target,
        scale=scale,
    )
    is_train = flag == "train"
    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=is_train,
        drop_last=is_train if drop_last is None else drop_last,
        num_workers=num_workers,
        generator=torch.Generator().manual_seed(SEED),
    )
    return dataset, loader


def _run_smoke_test() -> None:
    """Check one batch from each split for both configured smoke horizons."""
    expected_rows = {"train": 8640, "val": 2880, "test": 5900}
    for pred_len in (24, 168):
        for flag in SPLITS:
            dataset, loader = get_data_loader(flag=flag, pred_len=pred_len)
            if len(dataset.data_x) != expected_rows[flag]:
                raise AssertionError(
                    f"{flag} split has {len(dataset.data_x)} rows; "
                    f"expected {expected_rows[flag]}"
                )
            batch = next(iter(loader))
            expected_shapes = (
                (DEFAULT_BATCH_SIZE, DEFAULT_SIZE[0], len(NUMERICAL_FEATURES)),
                (
                    DEFAULT_BATCH_SIZE,
                    DEFAULT_SIZE[1] + pred_len,
                    len(NUMERICAL_FEATURES),
                ),
                (DEFAULT_BATCH_SIZE, DEFAULT_SIZE[0], len(TIME_MARK_COLUMNS)),
                (
                    DEFAULT_BATCH_SIZE,
                    DEFAULT_SIZE[1] + pred_len,
                    len(TIME_MARK_COLUMNS),
                ),
            )
            for tensor, shape in zip(batch, expected_shapes):
                if tuple(tensor.shape) != shape:
                    raise AssertionError(
                        f"{flag} pred_len={pred_len}: expected {shape}, "
                        f"got {tuple(tensor.shape)}"
                    )
                if tensor.dtype != torch.float32 or not torch.isfinite(tensor).all():
                    raise AssertionError(
                        f"{flag} pred_len={pred_len}: batch has invalid values"
                    )
            LOGGER.info(
                "%s pred_len=%d: windows=%d batches=%d",
                flag,
                pred_len,
                len(dataset),
                len(loader),
            )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    _run_smoke_test()
