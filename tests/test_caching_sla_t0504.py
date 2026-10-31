"""Cache identity, invalidation, copy isolation and latency regression tests."""

from __future__ import annotations

import os
import time
import json
import hashlib
from pathlib import Path

import pandas as pd

from src.visuals import cache_manager as cache


def test_cache_hit_avoids_io_and_returns_isolated_frames(
    tmp_path: Path, monkeypatch,
) -> None:
    path = tmp_path / "one.parquet"
    pd.DataFrame({"dataset": ["ETTh1"], "value": [1]}).to_parquet(path)
    calls = 0
    actual = cache._read_parquet

    def counted(source: str) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return actual(source)

    monkeypatch.setattr(cache, "_read_parquet", counted)
    cache.clear_artifact_caches()
    version = cache.artifact_version(path)
    first = cache.load_parquet(str(path.resolve()), version)
    first.loc[0, "value"] = 99
    second = cache.load_parquet(str(path.resolve()), version)
    assert calls == 1
    assert second.loc[0, "value"] == 1
    assert first is not second


def test_dataset_paths_never_share_stale_cache(
    tmp_path: Path,
) -> None:
    paths = {}
    for dataset, count, value in [("ETTh1", 3, 11), ("ETTh2", 5, 22), ("ETTm1", 7, 33)]:
        path = tmp_path / f"{dataset}.parquet"
        pd.DataFrame({"dataset": [dataset] * count, "value": [value] * count}).to_parquet(path)
        paths[dataset] = path
    cache.clear_artifact_caches()
    first = cache.load_artifact(paths["ETTh1"])
    second = cache.load_artifact(paths["ETTh2"])
    third = cache.load_artifact(paths["ETTm1"])
    assert (len(first), len(second), len(third)) == (3, 5, 7)
    assert (first.dataset.unique()[0], second.dataset.unique()[0],
            third.dataset.unique()[0]) == ("ETTh1", "ETTh2", "ETTm1")
    assert (first.value.iloc[0], second.value.iloc[0], third.value.iloc[0]) == (11, 22, 33)


def test_version_change_invalidates_even_same_size_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.parquet"
    pd.DataFrame({"value": [1]}).to_parquet(path)
    cache.clear_artifact_caches()
    old_version = cache.artifact_version(path)
    original = cache.load_parquet(str(path.resolve()), old_version)
    pd.DataFrame({"value": [2]}).to_parquet(path)
    # Force a distinct nanosecond timestamp even if filesystem resolution is coarse.
    os.utime(path, ns=(old_version[0] + 2_000_000_000, old_version[0] + 2_000_000_000))
    new_version = cache.artifact_version(path)
    assert new_version != old_version
    updated = cache.load_parquet(str(path.resolve()), new_version)
    assert original.value.iloc[0] == 1
    assert updated.value.iloc[0] == 2


def test_production_dataset_switch_isolated_and_warm_read_is_fast() -> None:
    from src.data.constants import DEFAULT_FEATURE_PATH

    # Production features contain all three dataset identities and are the UI base.
    cache.clear_artifact_caches()
    started = time.perf_counter()
    frame = cache.load_artifact(DEFAULT_FEATURE_PATH)
    cold_seconds = time.perf_counter() - started
    version = cache.artifact_version(DEFAULT_FEATURE_PATH)
    started = time.perf_counter()
    warm = cache.load_parquet(str(DEFAULT_FEATURE_PATH.resolve()), version)
    warm_seconds = time.perf_counter() - started
    assert len(frame) == 104520 and warm.equals(frame)
    assert frame.groupby("dataset").size().to_dict() == {
        "ETTh1": 17420, "ETTh2": 17420, "ETTm1": 69680,
    }
    assert warm_seconds < 0.25
    assert cold_seconds >= 0


def test_every_streamlit_cache_key_is_public_and_path_versioned() -> None:
    import ast

    source = Path(__file__).resolve().parents[1] / "src/visuals/cache_manager.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "cache_data"
                for decorator in node.decorator_list):
            names = [arg.arg for arg in node.args.args]
            assert names and all(not name.startswith("_") for name in names)
            assert "path" in names and "version" in names


def test_benchmark_evidence_matches_existing_artifacts_and_timing_report() -> None:
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root / "audit/performance_sla_benchmark.json").read_text())
    report = (root / "audit/performance_sla_benchmark.md").read_text(encoding="utf-8")
    assert len(evidence["artifacts"]) == 6
    for item in evidence["artifacts"].values():
        path = Path(item["path"])
        assert path.stat().st_size == item["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    app = evidence["streamlit_apptest_server_side"]
    assert app["exceptions"] == 0
    assert "NOT MEASURED" in report
    assert f"{evidence['loader_six_artifacts']['cold_seconds']:.4f}s" in report
    assert "browser_paint_included" in app and not app["browser_paint_included"]