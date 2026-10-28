"""Shared artifact IO and validation helpers for offline WP02 analytics."""

from __future__ import annotations

import hashlib
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.data.constants import (
    CLEAN_COLUMNS,
    FEATURE_COLUMNS,
    ROOT,
    SCHEMA_VERSION,
    SEED,
)
from src.data.feature_builder import build_grid_features


def set_seed(seed: int = SEED) -> None:
    """Seed deterministic NumPy/random paths; WP02 is CPU-only."""
    random.seed(seed)
    np.random.seed(seed)


def file_sha256(path: Path | str) -> str:
    """Return SHA-256 of artifact/source bytes without mutating the file."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc_now_iso() -> str:
    """Return an auditable UTC timestamp with explicit offset."""
    return datetime.now(timezone.utc).isoformat()


def safe_output_path(out: Path | str, source_path: Path | str | None = None) -> Path:
    """Reject protected destinations and aliases before writing artifacts."""
    destination = Path(out).resolve()
    protected = (ROOT / "data" / "raw", ROOT / "docs")
    for directory in protected:
        resolved = directory.resolve()
        if destination == resolved or destination.is_relative_to(resolved):
            raise ValueError("Output targets a protected directory")
    if destination.exists() and not destination.is_file():
        raise ValueError("Output must be a file")
    if source_path is not None:
        source = Path(source_path).resolve()
        if destination == source:
            raise ValueError("Output aliases source")
        if destination.exists() and source.exists() and destination.samefile(source):
            raise ValueError("Output aliases source")
    return destination


def atomic_write_parquet(
    table: pa.Table, out: Path | str, source_path: Path | str | None = None,
) -> Path:
    """Write Parquet through an exclusive temp file and verified replace."""
    destination = safe_output_path(out, source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    owns_tmp = False
    try:
        with temporary.open("xb") as handle:
            owns_tmp = True
            pq.write_table(table, handle, compression="snappy")
            handle.flush()
            os.fsync(handle.fileno())
        if not pq.read_table(temporary).equals(table, check_metadata=True):
            raise ValueError("Parquet round-trip verification failed")
        safe_output_path(destination, source_path)
        os.replace(temporary, destination)
    finally:
        if owns_tmp and temporary.exists():
            temporary.unlink()
    return destination


def atomic_write_json(
    payload: Mapping[str, Any], out: Path | str,
    source_path: Path | str | None = None,
) -> Path:
    """Write JSON atomically with NaN/Infinity rejected by the encoder."""
    destination = safe_output_path(out, source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    owns_tmp = False
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            owns_tmp = True
            handle.write(data)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        json.loads(temporary.read_text(encoding="utf-8"))
        safe_output_path(destination, source_path)
        os.replace(temporary, destination)
    finally:
        if owns_tmp and temporary.exists():
            temporary.unlink()
    return destination


def metadata_bytes(
    artifact_type: str, datasets: Sequence[str], source_hash: str,
    parameters: Mapping[str, Any], quality_audit: Mapping[str, Any],
) -> dict[bytes, bytes]:
    """Build common Parquet metadata for reproducible offline artifacts."""
    if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
        raise ValueError("source_hash must be lowercase SHA-256")
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "dataset": json.dumps(sorted(datasets), sort_keys=True, allow_nan=False),
        "seed": str(SEED),
        "source_hash": source_hash,
        "source_hash_algorithm": "sha256_source_file_bytes",
        "generated_at": utc_now_iso(),
        "timezone": "unknown",
        "parameters": json.dumps(parameters, sort_keys=True, allow_nan=False),
        "quality_audit": json.dumps(quality_audit, sort_keys=True, allow_nan=False),
    }
    return {key.encode("utf-8"): value.encode("utf-8") for key, value in metadata.items()}


def load_feature_input(path: Path | str) -> pd.DataFrame:
    """Load a clean or feature artifact and return the fixed WP02 feature frame."""
    frame = pd.read_parquet(path)
    columns = set(frame.columns)
    if columns not in (set(CLEAN_COLUMNS), set(FEATURE_COLUMNS)):
        raise ValueError("Expected clean or grid-feature v2.0 input")
    return build_grid_features(frame)


def dataset_names(frame: pd.DataFrame) -> list[str]:
    """Return sorted dataset names as plain strings for metadata."""
    return sorted(str(value) for value in frame["dataset"].dropna().unique())
