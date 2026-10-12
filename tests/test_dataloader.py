"""Unit tests for ETT sliding windows and split-aware DataLoaders."""

from pathlib import Path
import json
import sys
from typing import Dict

import numpy as np
import pandas as pd
import pytest
import torch

# Ensure the workspace package is importable when pytest is launched via its
# console entry point, whose sys.path may begin at tests/ in this environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.data.dataloader import Dataset_ETT_hour, get_data_loader
from src.data.constants import ARTIFACT_COLUMNS, NUMERICAL_FEATURES, TIME_FEATURES


@pytest.fixture
def parquet_path(tmp_path: Path) -> Path:
    """Write a small, deterministic T0101-shaped parquet artifact."""
    row_count = 30
    data: Dict[str, object] = {
        "split": ["train"] * 12 + ["val"] * 9 + ["test"] * 9,
    }
    for feature_index, column in enumerate(NUMERICAL_FEATURES):
        values = np.arange(row_count, dtype=np.float32) + feature_index * 100
        data[column] = values
        data[f"{column}_scaled"] = values / np.float32(10)
    for column_index, column in enumerate(TIME_FEATURES):
        data[f"{column}_norm"] = np.linspace(
            -0.5, 0.5, row_count, dtype=np.float32
        ) + np.float32(column_index)
    path = tmp_path / "clean_ett.parquet"
    pd.DataFrame(data).to_parquet(path)
    return path


def test_dataset_window_shapes_and_values(parquet_path: Path) -> None:
    """Verify decoder context/horizon slicing and all output dimensions."""
    dataset = Dataset_ETT_hour(
        str(parquet_path), flag="train", size=(4, 2, 3), scale=True
    )
    assert len(dataset) == 6
    seq_x, seq_y, seq_x_mark, seq_y_mark = dataset[0]
    assert seq_x.shape == (4, 7)
    assert seq_y.shape == (5, 7)
    assert seq_x_mark.shape == (4, 4)
    assert seq_y_mark.shape == (5, 4)
    assert all(tensor.dtype == torch.float32 for tensor in (
        seq_x, seq_y, seq_x_mark, seq_y_mark
    ))
    torch.testing.assert_close(seq_y[:, 0], torch.tensor([0.2, 0.3, 0.4, 0.5, 0.6]))


def test_unscaled_univariate_target(parquet_path: Path) -> None:
    """Select only the requested raw target when features='S'."""
    dataset = Dataset_ETT_hour(
        str(parquet_path), flag="val", size=(4, 2, 3),
        features="S", target="OT", scale=False,
    )
    seq_x, seq_y, _, _ = dataset[0]
    assert seq_x.shape == (4, 1)
    assert seq_y.shape == (5, 1)
    torch.testing.assert_close(seq_x[:, 0], torch.tensor([612.0, 613.0, 614.0, 615.0]))


def test_loader_split_order_and_drop_policy(parquet_path: Path) -> None:
    """Keep validation/test ordered and retain their incomplete final batch."""
    _, train_loader = get_data_loader(
        str(parquet_path), flag="train", batch_size=4,
        seq_len=4, label_len=2, pred_len=3,
    )
    val_dataset, val_loader = get_data_loader(
        str(parquet_path), flag="val", batch_size=2,
        seq_len=4, label_len=2, pred_len=3,
    )
    assert train_loader.drop_last is True
    assert val_loader.drop_last is False
    assert len(val_loader) == 2
    first_batch = next(iter(val_loader))[0]
    torch.testing.assert_close(first_batch[:, 0, 0], torch.tensor([1.2, 1.3]))
    assert len(val_dataset) == 3


def test_invalid_split_is_rejected(parquet_path: Path) -> None:
    """Reject unsupported partition names instead of silently loading data."""
    with pytest.raises(ValueError, match="flag must be one of"):
        Dataset_ETT_hour(str(parquet_path), flag="validation")


def test_production_artifact_partition_schema() -> None:
    """Check T0101 partition counts and standard-horizon batch dimensions."""
    artifact = Path("data/processed/clean_ett.parquet")
    if not artifact.is_file():
        pytest.skip("T0101 production parquet is not available")
    frame = pd.read_parquet(artifact)
    assert tuple(frame.columns) == ARTIFACT_COLUMNS
    assert frame["split"].value_counts().to_dict() == {
        "train": 8640, "val": 2880, "test": 5900,
    }
    scaler_path = artifact.parent / "scaler_params.json"
    assert scaler_path.is_file()
    with scaler_path.open(encoding="utf-8") as scaler_file:
        scaler = json.load(scaler_file)
    assert set(scaler["features"]) == set(NUMERICAL_FEATURES)
    for flag, row_count in (("train", 8640), ("val", 2880), ("test", 5900)):
        dataset, loader = get_data_loader(flag=flag, pred_len=24)
        assert len(dataset.data_x) == row_count
        assert next(iter(loader))[0].shape == (32, 96, 7)
