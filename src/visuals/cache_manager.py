"""Version-aware cached readers for precomputed dashboard artifacts.

Only file IO and the canonical lag JSON reshape live here. Statistical engines
remain offline. Streamlit includes every public cache-key argument in hashing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.visuals.lag_artifact import lag_envelope_frame


def artifact_version(path: Path | str) -> tuple[int, int]:
    """Return nanosecond mtime and file size; missing paths have no cache version."""
    stat = Path(path).stat()
    return stat.st_mtime_ns, stat.st_size


def _read_parquet(path: str) -> pd.DataFrame:
    """Uncached implementation, separated to make cache behavior testable."""
    return pd.read_parquet(path)


def _read_lag_json(path: str) -> pd.DataFrame:
    """Read and reshape the canonical small lag envelope, without fitting."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return lag_envelope_frame(payload)


@st.cache_data(show_spinner=False, max_entries=32)
def load_parquet(path: str, version: tuple[int, int]) -> pd.DataFrame:
    """Cache Parquet by resolved path plus (mtime_ns, size)."""
    # The version is intentionally consumed for static analyzers; Streamlit hashes it.
    if len(version) != 2:
        raise ValueError("Artifact version must be (mtime_ns, size)")
    return _read_parquet(path)


@st.cache_data(show_spinner=False, max_entries=8)
def load_lag_json(path: str, version: tuple[int, int]) -> pd.DataFrame:
    """Cache the canonical lag envelope by path and file version."""
    if len(version) != 2:
        raise ValueError("Artifact version must be (mtime_ns, size)")
    return _read_lag_json(path)


def load_artifact(path: Path | str) -> pd.DataFrame:
    """Load a canonical/supplementary Parquet or lag JSON artifact."""
    resolved = Path(path).resolve()
    version = artifact_version(resolved)
    loader = load_lag_json if resolved.suffix.lower() == ".json" else load_parquet
    return loader(str(resolved), version)


def clear_artifact_caches() -> None:
    """Clear process caches; intended for deterministic benchmarks/tests."""
    load_parquet.clear()
    load_lag_json.clear()