"""Lightweight canonical JSON adapter for the existing lag heatmap consumer."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from src.data.constants import CADENCE_MINUTES, LOAD_BRANCHES, SCHEMA_VERSION


def lag_envelope_frame(payload: dict[str, Any]) -> pd.DataFrame:
    """Validate and reshape saved 6x13 records without statistical computation."""
    required = {
        "schema_version", "timezone", "generated_at", "seed", "source_hash",
        "records",
    }
    if set(payload) != required or payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Invalid lag envelope schema")
    if payload["timezone"] != "unknown":
        raise ValueError("Unexpected lag source timezone")
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for record in payload["records"]:
        key = (record["dataset"], record["season"], record["method"])
        if key in seen or key[0] not in CADENCE_MINUTES:
            raise ValueError("Duplicate or unknown lag dataset record")
        seen.add(key)
        if key[2] not in ("pearson", "spearman"):
            raise ValueError("Unknown lag correlation method")
        if record["load_variables"] != list(LOAD_BRANCHES):
            raise ValueError("Invalid lag load variable order")
        if record["lags_hours"] != list(range(13)):
            raise ValueError("Invalid lag hours")
        matrix, counts = record["correlation_matrix"], record["sample_counts"]
        if len(matrix) != 6 or len(counts) != 6:
            raise ValueError("Lag matrix must have six rows")
        for variable, values, samples in zip(LOAD_BRANCHES, matrix, counts):
            if len(values) != 13 or len(samples) != 13:
                raise ValueError("Lag matrix must have thirteen columns")
            for hour, value, count in zip(range(13), values, samples):
                if value is not None and (
                    not math.isfinite(value) or not -1 <= value <= 1
                ):
                    raise ValueError("Invalid lag coefficient")
                if type(count) is not int or count < 0:
                    raise ValueError("Invalid lag sample count")
                rows.append({
                    "dataset": key[0], "season": key[1], "method": key[2],
                    "load_variable": variable, "lag_hour": hour,
                    "correlation": value, "sample_count": count,
                })
    return pd.DataFrame(rows, columns=[
        "dataset", "season", "method", "load_variable", "lag_hour",
        "correlation", "sample_count",
    ]).astype({
        "dataset": "string", "season": "string", "method": "string",
        "load_variable": "string", "lag_hour": "int32",
        "correlation": "float32", "sample_count": "int32",
    })