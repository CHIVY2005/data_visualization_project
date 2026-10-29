"""Build three isolated clean/features datasets, then atomic multi-dataset views.

No append-in-place and no raw writes. Dataset remains part of every key.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.preprocess_ett import run_pipeline, CLEAN_SCHEMA
from src.data.feature_builder import save_grid_features
from src.data.constants import ROOT, CADENCE_MINUTES, DEFAULT_CLEAN_PATH, DEFAULT_FEATURE_PATH
from src.analysis.common import atomic_write_parquet, metadata_bytes, file_sha256


def main() -> None:
    """Stage per-dataset artifacts before replacing the combined clean view."""
    paths = []
    hashes = {}
    for dataset in CADENCE_MINUTES:
        directory = ROOT / "data/processed/datasets" / dataset
        clean = directory / "clean_ett.parquet"
        run_pipeline(dataset, out_path=clean)
        save_grid_features(pd.read_parquet(clean), directory / "grid_features.parquet",
                           source_hash=file_sha256(clean), source_path=clean)
        paths.append(clean)
        hashes[dataset] = file_sha256(ROOT / f"data/raw/{dataset}.csv")
        print("PREPARED", dataset, flush=True)
    frame = pd.concat([pd.read_parquet(path) for path in paths], ignore_index=True)
    table = pa.Table.from_pandas(frame, schema=CLEAN_SCHEMA, preserve_index=False)
    import hashlib
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    metadata = metadata_bytes("clean_ett", list(CADENCE_MINUTES), digest,
                              {"source_hashes": hashes,
                               "merge_policy": "dataset_key_no_resampling"},
                              {"rows": len(frame)})
    atomic_write_parquet(table.replace_schema_metadata(metadata), DEFAULT_CLEAN_PATH)
    save_grid_features(frame, DEFAULT_FEATURE_PATH,
                       source_hash=file_sha256(DEFAULT_CLEAN_PATH),
                       source_path=DEFAULT_CLEAN_PATH)
    print("COMBINED", len(frame), "rows", flush=True)


if __name__ == "__main__":
    main()