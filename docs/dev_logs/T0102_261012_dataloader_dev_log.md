# T0102 Development Log — 2026-10-12

## Completed

- Verified the T0101 Parquet has 24 columns, 17,420 rows, no nulls, and split counts of 8,640 train / 2,880 validation / 5,900 test.
- Verified `scaler_params.json` contains train-only mean/std parameters for all seven ETT variables.
- Added the split-aware `Dataset_ETT_hour` and `get_data_loader` with scaled/raw value selection, normalized time marks, decoder context, and fixed seed.
- Added unit tests for window slicing, univariate raw values, loader policies, invalid split rejection, and production split sizes.

## Smoke-test batch counts

For `batch_size=32`, `seq_len=96`, and `label_len=48`:

| Horizon | Train windows / batches | Validation windows / batches | Test windows / batches |
| ---: | ---: | ---: | ---: |
| 24 | 8,521 / 266 | 2,761 / 87 | 5,781 / 181 |
| 168 | 8,377 / 261 | 2,617 / 82 | 5,637 / 177 |

Train drops the incomplete batch; validation and test retain it. Shapes, `float32`, and finite values are checked for all six split/horizon combinations.

## Readiness

The `.venv` smoke test completed with exit code 0, and `pytest tests/test_dataloader.py -q` passed all 5 tests. The loader interface is ready for Task T0301 / T0303.
