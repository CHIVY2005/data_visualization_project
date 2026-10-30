"""Three-dataset ETL, cadence and provenance counterexamples for T0205."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from scripts.preprocess_ett import content_hash, run_multi_pipeline
from scripts.run_statistical_engine import audit_artifacts, run_all_datasets
from src.analysis.common import raw_provenance
from src.analysis.lag_correlation import build_lag_correlation_records
from src.analysis.load_profiling import _stl_period, build_stl_records
from src.analysis.thermal_risk import build_thermal_breach_events, save_thermal_breach_events
from src.data.constants import (
    CADENCE_MINUTES, CLEAN_COLUMNS, DEFAULT_CLEAN_PATH, DEFAULT_FEATURE_PATH,
    DEFAULT_SYNC_AUDIT_PATH, EXPECTED_DATASET_ROWS, LOAD_BRANCHES, ROOT,
)
from src.data.feature_builder import build_grid_features


def synthetic_clean(n: int = 240) -> pd.DataFrame:
    """Same timestamps across stations, distinct delayed signals at each cadence."""
    from scripts.preprocess_ett import derive_measurements

    pieces = []
    for index, (dataset, cadence) in enumerate(CADENCE_MINUTES.items()):
        rng = np.random.default_rng(2026 + index)
        load = rng.normal(size=n).astype("float32")
        shift = 60 // cadence
        ot = np.full(n, np.nan, dtype="float32")
        if n > shift:
            ot[shift:] = load[:-shift] + 30
        frame = pd.DataFrame({
            "dataset": dataset,
            "timestamp": pd.date_range("2026-01-01", periods=n,
                                       freq=f"{cadence}min").astype("datetime64[ns]"),
            "OT": ot, **{variable: load + j for j, variable in enumerate(LOAD_BRANCHES)},
        })
        pieces.append(derive_measurements(frame))
    return pd.concat(pieces, ignore_index=True).loc[:, CLEAN_COLUMNS]


def write_raw(directory: Path, frame: pd.DataFrame) -> None:
    """Write private synthetic fixtures, never repository raw."""
    directory.mkdir()
    for dataset, group in frame.groupby("dataset"):
        columns = ["timestamp", "OT", *LOAD_BRANCHES]
        group.loc[:, columns].rename(columns={"timestamp": "date"}).to_csv(
            directory / f"{dataset}.csv", index=False,
        )


@pytest.mark.parametrize("dataset", CADENCE_MINUTES)
def test_lag_hour_exact_samples_and_gap_alignment(dataset: str) -> None:
    frame = synthetic_clean()
    group = frame.loc[frame.dataset.eq(dataset)].reset_index(drop=True)
    record = build_lag_correlation_records(
        group, load_variables=["HUFL"], lags_hours=[0, 1, 2], methods=["pearson"],
    )[0]
    assert np.nanargmax(np.abs(record["correlation_matrix"][0])) == 1
    assert record["correlation_matrix"][0][1] == pytest.approx(1, abs=1e-5)
    shift = 60 // CADENCE_MINUTES[dataset]
    assert record["sample_counts"][0][1] == len(group) - shift
    # Removing a timestamp must not shift neighbors into its physical position.
    gap = group.drop(index=30)
    record = build_lag_correlation_records(
        gap, load_variables=["HUFL"], lags_hours=[1], methods=["pearson"],
    )[0]
    assert record["correlation_matrix"][0][0] == pytest.approx(1, abs=1e-5)
    assert record["sample_counts"][0][0] == len(group) - shift - 2


def test_stl_period_and_multidataset_reconstruction() -> None:
    frame = synthetic_clean()
    assert {_stl_period(d) for d in CADENCE_MINUTES} == {24, 96}
    result = build_stl_records(frame, variables=["HUFL"])
    for dataset, group in result.groupby("dataset"):
        assert _stl_period(dataset) == (96 if dataset == "ETTm1" else 24)
        valid = group.dropna(subset=["trend"])
        assert not valid.empty
        np.testing.assert_allclose(valid.observed, valid.trend + valid.seasonal +
                                   valid.residual, atol=1e-5)


def test_multistation_events_cadence_and_no_fake_support(tmp_path: Path) -> None:
    frame = synthetic_clean(3)
    for dataset in CADENCE_MINUTES:
        frame.loc[frame.dataset.eq(dataset), "OT"] = [96, 100, 80]
    events = build_thermal_breach_events(frame)
    assert set(events.dataset) == set(CADENCE_MINUTES)
    for dataset, group in events.groupby("dataset"):
        delta = CADENCE_MINUTES[dataset] / 60
        assert group.duration_hours.eq(2 * delta).all()
        assert group.loc[group.threshold_c.eq(85), "degree_hours"].iloc[0] == 26 * delta
        assert group.loc[group.threshold_c.eq(95), "degree_hours"].iloc[0] == 6 * delta
    tail = frame.groupby("dataset", sort=False).head(1)
    assert build_thermal_breach_events(tail).empty
    gap = frame.groupby("dataset", sort=False).head(2).copy()
    gap.loc[gap.groupby("dataset").cumcount().eq(1), "timestamp"] += pd.Timedelta(hours=5)
    assert build_thermal_breach_events(gap).empty
    # Coverage metadata includes all input datasets even if only one has events.
    frame.loc[~frame.dataset.eq("ETTm1"), "OT"] = 20
    output = save_thermal_breach_events(frame, tmp_path / "events.parquet", source_hash="a"*64)
    assert json.loads(pq.read_schema(output).metadata[b"dataset"]) == sorted(CADENCE_MINUTES)


def test_synthetic_pipeline_atomic_lineage_and_no_cross_fill(tmp_path: Path) -> None:
    raw = tmp_path / "fixtures"
    frame = synthetic_clean(48)
    write_raw(raw, frame)
    before = raw_provenance(raw)
    clean = tmp_path / "clean.parquet"
    summary = run_multi_pipeline(raw, clean)
    assert summary["rows"] == 144
    features = build_grid_features(pd.read_parquet(clean))
    # Initial delayed OT nulls remain dataset-local, never interpolated.
    assert features.groupby("dataset").OT.apply(lambda s: s.isna().sum()).to_dict() == {
        "ETTh1": 1, "ETTh2": 1, "ETTm1": 4,
    }
    outputs = run_all_datasets(tmp_path / "processed", tmp_path / "artifacts", raw,
                               tmp_path / "audit.json", {d: 48 for d in CADENCE_MINUTES})
    assert Path(outputs["audit"]).exists()
    assert raw_provenance(raw) == before
    payload = json.loads(Path(outputs["audit"]).read_text())
    assert payload["status"] == "PASS"
    assert len(payload["artifacts"]) == 7
    # Corrupted ancestry must fail audit rather than silently relabeling it.
    path = Path(outputs["grid_features"])
    table = pq.read_table(path)
    metadata = dict(table.schema.metadata)
    metadata[b"raw_bundle_hash"] = b"0" * 64
    # Test fixture corruption only, still via the production atomic writer.
    from src.analysis.common import atomic_write_parquet
    atomic_write_parquet(table.replace_schema_metadata(metadata), path)
    with pytest.raises(ValueError):
        audit_artifacts(outputs["clean_ett"], path, tmp_path / "artifacts", raw,
                        tmp_path / "bad-audit.json")


def test_production_artifact_audit(tmp_path: Path) -> None:
    report = audit_artifacts(audit_path=tmp_path / "audit.json",
                             expected_rows=EXPECTED_DATASET_ROWS)
    assert report["status"] == "PASS"
    for name in (DEFAULT_CLEAN_PATH.name, DEFAULT_FEATURE_PATH.name):
        assert report["artifacts"][name]["dataset_rows"] == EXPECTED_DATASET_ROWS
    assert DEFAULT_SYNC_AUDIT_PATH.exists()


def test_raw_content_equivalence() -> None:
    expected = {
        "ETTh1": "f18de3ad269cef59bb07b5438d79bb3042d3be49bdeecf01c1cd6d29695ee066",
        "ETTh2": "a3dc2c597b9218c7ce1cd55eb77b283fd459a1d09d753063f944967dd6b9218b",
        "ETTm1": "6ce1759b1a18e3328421d5d75fadcb316c449fcd7cec32820c8dafda71986c9e",
    }
    for dataset, digest in expected.items():
        data = (ROOT / "data/raw" / f"{dataset}.csv").read_bytes()
        assert content_hash(data) == digest
        assert content_hash(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")) == digest


def test_atomic_json_failure_preserves_previous_and_stale_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.analysis.common as common

    out = tmp_path / "audit.json"
    common.atomic_write_json({"status": "old"}, out)
    before = out.read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("replace failure")

    monkeypatch.setattr(common.os, "replace", fail)
    with pytest.raises(OSError):
        common.atomic_write_json({"status": "new"}, out)
    assert out.read_bytes() == before
    temporary = out.with_name(out.name + ".tmp")
    assert not temporary.exists()
    temporary.write_bytes(b"owned-by-another-run")
    with pytest.raises(FileExistsError):
        common.atomic_write_json({"status": "new"}, out)
    assert temporary.read_bytes() == b"owned-by-another-run"
    assert out.read_bytes() == before