"""Run WP02 offline statistical analytics and export UI-ready artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.lag_correlation import save_lag_envelope
from src.analysis.load_profiling import save_hourly_quantiles, save_load_profiles_stl
from src.analysis.diagnostics import save_diagnostics
from src.analysis.common import (
    file_sha256, load_feature_input, set_seed, raw_provenance,
    attach_raw_lineage, atomic_write_json, atomic_write_parquet, utc_now_iso,
)
from src.analysis.thermal_risk import (
    save_thermal_breach_events, build_thermal_breach_events, save_loess_curves,
)
from src.data.constants import (
    DEFAULT_FEATURE_PATH,
    DEFAULT_CLEAN_PATH,
    DEFAULT_STL_PATH,
    DEFAULT_SYNC_AUDIT_PATH,
    CADENCE_MINUTES,
    EXPECTED_DATASET_ROWS,
    ROOT,
    LOAD_BRANCHES,
    DEFAULT_BREACH_EVENTS_PATH,
    DEFAULT_HOURLY_QUANTILES_PATH,
    DEFAULT_LAG_JSON_PATH,
    DEFAULT_LOESS_PATH,
    SEED,
)


def run_engine(
    input_path: Path | str = DEFAULT_FEATURE_PATH,
    out_dir: Path | str = DEFAULT_HOURLY_QUANTILES_PATH.parent,
) -> dict[str, str]:
    """Export T0201/T0202/T0203 artifacts from clean/features input."""
    set_seed(SEED)
    source = Path(input_path)
    frame = load_feature_input(source)
    digest = file_sha256(source)
    directory = Path(out_dir)
    outputs = {
        "loess_curves": save_loess_curves(
            frame, directory / DEFAULT_LOESS_PATH.name,
            source_hash=digest, source_path=source,
        ),
        "load_profiles_stl": save_load_profiles_stl(
            frame, directory / "load_profiles_stl.parquet",
            source_hash=digest, source_path=source,
        ),
        "quantile_bands": save_hourly_quantiles(
            frame,
            directory / DEFAULT_HOURLY_QUANTILES_PATH.name,
            source_hash=digest,
            source_path=source,
        ),
        "lag_correlation_matrix": save_lag_envelope(
            frame, directory / DEFAULT_LAG_JSON_PATH.name,
            source_hash=digest, source_path=source,
        ),
        "thermal_breach_events": save_thermal_breach_events(
            frame,
            directory / DEFAULT_BREACH_EVENTS_PATH.name,
            source_hash=digest,
            source_path=source,
        ),
    }
    outputs.update(save_diagnostics(
        frame, build_thermal_breach_events(frame), directory,
        source_hash=digest, source_path=source,
        include_loess=False,
    ))
    return {key: str(value) for key, value in outputs.items()}


def audit_artifacts(
    clean_path: Path | str = DEFAULT_CLEAN_PATH,
    features_path: Path | str = DEFAULT_FEATURE_PATH,
    out_dir: Path | str = DEFAULT_STL_PATH.parent,
    raw_dir: Path | str = ROOT / "data/raw",
    audit_path: Path | str = DEFAULT_SYNC_AUDIT_PATH,
    expected_rows: dict[str, int] | None = None,
) -> dict[str, object]:
    """Validate contracts, arithmetic and direct/raw lineage; fail closed on drift.

    Preserve canonical lag root keys. Its coverage/quality/raw ancestry live in
    this audit, while source_hash continues identifying the immediate input.
    """
    from scripts.preprocess_ett import CLEAN_SCHEMA
    from src.data.feature_builder import FEATURE_SCHEMA, build_grid_features
    from src.analysis.load_profiling import LOAD_PROFILE_SCHEMA, QUANTILE_SCHEMA
    from src.analysis.thermal_risk import LOESS_SCHEMA, THERMAL_BREACH_SCHEMA

    provenance = raw_provenance(raw_dir)
    datasets = sorted(CADENCE_MINUTES)
    clean_path, features_path, directory = Path(clean_path), Path(features_path), Path(out_dir)
    entries: dict[str, object] = {}
    frames: dict[str, pd.DataFrame] = {}
    contracts = [
        (clean_path, CLEAN_SCHEMA), (features_path, FEATURE_SCHEMA),
        (directory / DEFAULT_STL_PATH.name, LOAD_PROFILE_SCHEMA),
        (directory / DEFAULT_HOURLY_QUANTILES_PATH.name, QUANTILE_SCHEMA),
        (directory / DEFAULT_BREACH_EVENTS_PATH.name, THERMAL_BREACH_SCHEMA),
        (directory / DEFAULT_LOESS_PATH.name, LOESS_SCHEMA),
    ]
    feature_hash = file_sha256(features_path)
    for path, schema in contracts:
        table = pq.read_table(path)
        if not table.schema.equals(schema, check_metadata=False):
            raise ValueError(f"Schema mismatch: {path.name}")
        metadata = {k.decode(): v.decode() for k, v in (table.schema.metadata or {}).items()
                    if k != b"pandas"}
        required = {"schema_version", "seed", "generated_at", "source_hash",
                    "dataset", "timezone", "parameters", "quality_audit",
                    "raw_source_hashes", "raw_bundle_hash", "raw_bundle_algorithm"}
        if not required.issubset(metadata):
            raise ValueError(f"Missing provenance: {path.name}")
        if (metadata["schema_version"] != "2.0" or metadata["seed"] != str(SEED)
                or metadata["timezone"] != "unknown"):
            raise ValueError(f"Invalid version/seed/timezone: {path.name}")
        generated = datetime.fromisoformat(metadata["generated_at"])
        if generated.utcoffset() != timezone.utc.utcoffset(generated):
            raise ValueError("generated_at must be UTC")
        if json.loads(metadata["dataset"]) != datasets:
            raise ValueError(f"Missing metadata dataset coverage: {path.name}")
        if (json.loads(metadata["raw_source_hashes"]) != provenance["raw_source_hashes"]
                or metadata["raw_bundle_hash"] != provenance["raw_bundle_hash"]
                or metadata["raw_bundle_algorithm"] != provenance["raw_bundle_algorithm"]):
            raise ValueError(f"Raw lineage mismatch: {path.name}")
        expected_hash = (provenance["raw_bundle_hash"] if path == clean_path else
                         file_sha256(clean_path) if path == features_path else feature_hash)
        if metadata["source_hash"] != expected_hash:
            raise ValueError(f"Immediate source_hash mismatch: {path.name}")
        json.loads(metadata["parameters"])
        json.loads(metadata["quality_audit"])
        for field in table.schema:
            column = table[field.name]
            if not field.nullable and column.null_count:
                raise ValueError(f"Null nonnullable {path.name}/{field.name}")
            if pa.types.is_floating(field.type):
                values = column.to_numpy(zero_copy_only=False)
                if np.isinf(values).any() or (not field.nullable and np.isnan(values).any()):
                    raise ValueError(f"Nonfinite {path.name}/{field.name}")
        frame = table.to_pandas()
        counts = {d: int(frame.dataset.eq(d).sum()) for d in datasets}
        if path.name != DEFAULT_BREACH_EVENTS_PATH.name and set(frame.dataset) != set(datasets):
            raise ValueError(f"Missing row dataset coverage: {path.name}")
        entries[path.name] = {
            "path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256_bytes": file_sha256(path), "rows": len(frame),
            "columns": table.schema.names,
            "dtypes": {f.name: str(f.type) for f in table.schema},
            "dataset_rows": counts, "metadata": metadata,
            "null_counts": {f.name: table[f.name].null_count for f in table.schema},
        }
        frames[path.name] = frame
    clean, features = frames[clean_path.name], frames[features_path.name]
    for frame in (clean, features):
        if expected_rows is not None and frame.groupby("dataset").size().to_dict() != expected_rows:
            raise ValueError("Unexpected clean/features dataset row counts")
        build_grid_features(frame)  # validates dataset-local keys and cadence
    pd.testing.assert_frame_equal(
        build_grid_features(clean), features, check_dtype=False,
    )
    # Compare clean physical observations against fresh read-only CSV snapshots.
    from scripts.preprocess_ett import load_clean_dataset
    for dataset in datasets:
        raw_clean, _ = load_clean_dataset(Path(raw_dir) / f"{dataset}.csv", dataset)
        pd.testing.assert_frame_equal(
            clean.loc[clean.dataset.eq(dataset)].reset_index(drop=True), raw_clean,
            check_dtype=False,
        )
    from src.data.constants import ANALYSIS_VARIABLES
    bands = frames[DEFAULT_HOURLY_QUANTILES_PATH.name]
    quantiles = ["q025", "q10", "q25", "q50", "q75", "q90", "q975"]
    if (bands[quantiles].diff(axis=1).iloc[:, 1:] < 0).any().any():
        raise ValueError("Quantile nesting failed")
    if bands.duplicated(["dataset", "variable", "season", "hour"]).any():
        raise ValueError("Duplicate quantile keys")
    if not bands.sample_count.ge(0).all() or not bands.hour.between(0, 23).all():
        raise ValueError("Invalid quantile count/hour")
    if bands.loc[bands.sample_count.eq(0), ["mean", *quantiles]].notna().any().any():
        raise ValueError("Empty quantile bins must retain null statistics")
    if bands.loc[bands.sample_count.gt(0), ["mean", *quantiles]].isna().any().any():
        raise ValueError("Observed quantile bins must have finite statistics")
    if not bands.groupby(["dataset", "variable", "season"]).hour.apply(
            lambda values: set(values) == set(range(24))).all():
        raise ValueError("Missing hourly quantile bins")
    expected_bins = {
        (dataset, variable, season, hour)
        for dataset, group in features.groupby("dataset")
        for variable in ANALYSIS_VARIABLES for season in group.season.unique()
        for hour in range(24)
    }
    if set(bands[["dataset", "variable", "season", "hour"]].itertuples(index=False, name=None)) != expected_bins:
        raise ValueError("Incomplete quantile dataset/variable/season/hour coverage")
    profiles = frames[DEFAULT_STL_PATH.name]
    if set(profiles.record_type) != {"stl", "profile"}:
        raise ValueError("Invalid/missing STL/profile record types")
    profile_metadata = entries[DEFAULT_STL_PATH.name]["metadata"]
    if json.loads(profile_metadata["parameters"])["daily_period"] != {
            d: 1440 // minutes for d, minutes in CADENCE_MINUTES.items()}:
        raise ValueError("Incorrect daily STL period metadata")
    stl = profiles.loc[profiles.record_type.eq("stl")]
    if stl.timestamp.isna().any() or stl[["season", "hour", "mean", "median", "std", "sample_count"]].notna().any().any():
        raise ValueError("Invalid STL applicability fields")
    profile_rows = profiles.loc[profiles.record_type.eq("profile")]
    if profile_rows[["season", "hour", "sample_count"]].isna().any().any():
        raise ValueError("Missing profile keys/counts")
    if profile_rows[["timestamp", "observed", "trend", "seasonal", "residual"]].notna().any().any():
        raise ValueError("Invalid profile applicability fields")
    valid = stl.dropna(subset=["observed", "trend", "seasonal", "residual"])
    if not np.allclose(valid.observed, valid.trend + valid.seasonal + valid.residual,
                       atol=1e-4, rtol=1e-5):
        raise ValueError("STL reconstruction failed")
    for mask, keys in [(profiles.record_type.eq("stl"), ["dataset", "variable", "timestamp"]),
                       (profiles.record_type.eq("profile"), ["dataset", "variable", "season", "hour"])]:
        if profiles.loc[mask].duplicated(keys).any():
            raise ValueError("Duplicate profile/STL keys")
    if set(profile_rows[["dataset", "variable", "season", "hour"]].itertuples(index=False, name=None)) != expected_bins:
        raise ValueError("Incomplete hourly profile coverage")
    for dataset, group in features.groupby("dataset"):
        for variable in ANALYSIS_VARIABLES:
            records = stl.loc[stl.dataset.eq(dataset) & stl.variable.eq(variable)]
            if not records.timestamp.reset_index(drop=True).equals(group.timestamp.reset_index(drop=True)):
                raise ValueError("Incomplete STL observation timestamp coverage")
    events = frames[DEFAULT_BREACH_EVENTS_PATH.name]
    if (events.duplicated(["dataset", "event_id"]).any()
            or not events.threshold_c.isin([85, 95]).all()
            or not events.duration_hours.gt(0).all()
            or not events.degree_hours.ge(0).all()
            or not events.peak_ot.ge(events.threshold_c).all()):
        raise ValueError("Invalid thermal events")
    for dataset, group in events.groupby("dataset"):
        support = group.sample_count * (CADENCE_MINUTES[dataset] / 60)
        duration = (group.end_timestamp - group.start_timestamp).dt.total_seconds() / 3600
        if (not group.sample_count.gt(0).all()
                or not np.allclose(support, group.duration_hours)
                or not np.allclose(duration, group.duration_hours)):
            raise ValueError("Thermal event support/cadence mismatch")
    if not events.thermal_regime.eq(events.threshold_c.map({85: "Warning", 95: "Critical"})).all():
        raise ValueError("Thermal threshold/regime mismatch")
    curves = frames[DEFAULT_LOESS_PATH.name]
    if curves.duplicated(["dataset", "load_feature", "scope_type", "scope_value", "x_load"]).any():
        raise ValueError("Duplicate LOESS keys")
    if not curves.scope_type.isin(["all", "season", "thermal_regime"]).all():
        raise ValueError("Invalid LOESS scope type")
    if not curves.load_feature.isin(LOAD_BRANCHES).all() or not curves.sample_count.ge(10).all():
        raise ValueError("Invalid LOESS feature/sample count")
    from src.data.constants import LOESS_GRID_POINTS
    curve_groups = curves.groupby(["dataset", "load_feature", "scope_type", "scope_value"])
    if (not curve_groups.size().eq(LOESS_GRID_POINTS).all()
            or not curve_groups.sample_count.nunique().eq(1).all()
            or not all(group.x_load.is_monotonic_increasing for _, group in curve_groups)):
        raise ValueError("Invalid LOESS grid/support")
    path = directory / DEFAULT_LAG_JSON_PATH.name
    def reject_constant(value: str) -> None:
        raise ValueError(f"Nonstandard JSON number: {value}")
    payload = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    if set(payload) != {"schema_version", "timezone", "generated_at", "seed", "source_hash", "records"}:
        raise ValueError("Invalid lag root schema")
    if (payload["schema_version"] != "2.0" or payload["seed"] != SEED
            or payload["timezone"] != "unknown" or payload["source_hash"] != feature_hash):
        raise ValueError("Invalid lag provenance")
    generated = datetime.fromisoformat(payload["generated_at"])
    if generated.utcoffset() != timezone.utc.utcoffset(generated):
        raise ValueError("Lag generated_at must be UTC")
    seen = set()
    for record in payload["records"]:
        key = (record["dataset"], record["season"], record["method"])
        if key in seen or key[0] not in datasets or key[2] not in {"pearson", "spearman"}:
            raise ValueError("Invalid/duplicate lag record")
        seen.add(key)
        if record["load_variables"] != list(LOAD_BRANCHES) or record["lags_hours"] != list(range(13)):
            raise ValueError("Lag variable/hour order mismatch")
        matrix, counts = record["correlation_matrix"], record["sample_counts"]
        if np.shape(matrix) != (6, 13) or np.shape(counts) != (6, 13):
            raise ValueError("Lag shape mismatch")
        if any(x is not None and (not np.isfinite(x) or not -1 <= x <= 1)
               for row in matrix for x in row):
            raise ValueError("Invalid lag coefficient")
        if any(type(x) is not int or x < 0 for row in counts for x in row):
            raise ValueError("Invalid lag counts")
    expected_records = {
        (dataset, season, method)
        for dataset, group in features.groupby("dataset")
        for season in group.season.unique()
        for method in ("pearson", "spearman")
    }
    if seen != expected_records:
        raise ValueError("Lag missing dataset/season/method coverage")
    entries[path.name] = {
        "path": str(path.resolve()), "bytes": path.stat().st_size,
        "sha256_bytes": file_sha256(path), "rows": len(payload["records"]),
        "columns": list(payload), "dtypes": {k: type(v).__name__ for k, v in payload.items()},
        "dataset_rows": {d: sum(r["dataset"] == d for r in payload["records"]) for d in datasets},
        "metadata": {k: v for k, v in payload.items() if k != "records"},
        "raw_lineage": provenance,
        "quality_audit": {"records": len(seen), "matrix_shape": [6, 13]},
    }
    if raw_provenance(raw_dir) != provenance:
        raise ValueError("Raw changed during audit")
    report = {"task": "T0205", "schema_version": "2.0", "seed": SEED,
              "generated_at": utc_now_iso(), "status": "PASS", **provenance,
              "dataset": datasets, "artifacts": entries,
              "checks": {"raw_equivalence": True, "dataset_cadence": True,
                         "quantile_nesting_q025_to_q975": True,
                         "stl_reconstruction": True, "finite_nullable_policy": True,
                         "direct_and_raw_lineage": True},
              "quality_audit": {
                  "dataset_rows": clean.groupby("dataset").size().to_dict(),
                  "cadence_minutes": CADENCE_MINUTES,
                  "gap_counts": {dataset: int(group.timestamp.diff().gt(
                      pd.Timedelta(minutes=CADENCE_MINUTES[dataset])).sum())
                      for dataset, group in clean.groupby("dataset")},
                  "empty_events_valid": events.empty,
                  "artifacts_checked": len(entries),
              },
              "provenance_policy": "source_hash=immediate_input; raw lineage explicit; lag root unchanged"}
    atomic_write_json(report, audit_path)
    return report


def run_all_datasets(
    processed_dir: Path | str = DEFAULT_CLEAN_PATH.parent,
    out_dir: Path | str = DEFAULT_STL_PATH.parent,
    raw_dir: Path | str = ROOT / "data/raw",
    audit_path: Path | str = DEFAULT_SYNC_AUDIT_PATH,
    expected_rows: dict[str, int] | None = None,
) -> dict[str, str]:
    """ETL → features → statistics → audited raw lineage, no cross-station filling."""
    from scripts.preprocess_ett import run_multi_pipeline
    from src.data.feature_builder import save_grid_features

    set_seed()
    provenance = raw_provenance(raw_dir)
    clean = Path(processed_dir) / DEFAULT_CLEAN_PATH.name
    features = Path(processed_dir) / DEFAULT_FEATURE_PATH.name
    run_multi_pipeline(raw_dir, clean)
    clean_frame = pd.read_parquet(clean)
    if expected_rows is not None and clean_frame.groupby("dataset").size().to_dict() != expected_rows:
        raise ValueError("Unexpected raw row counts; refusing statistical engine run")
    save_grid_features(clean_frame, features,
                       source_hash=file_sha256(clean), source_path=clean)
    outputs = run_engine(features, out_dir)
    if raw_provenance(raw_dir) != provenance:
        raise ValueError("Raw changed during full pipeline")
    attach_raw_lineage([clean, features, *outputs.values()], provenance)
    # Updating clean/features metadata changes their byte identities. Preserve
    # immediate lineage after the final metadata refresh, atomically per file.
    for path in [features, *[Path(v) for v in outputs.values() if v.endswith('.parquet')]]:
        table = pq.read_table(path)
        metadata = dict(table.schema.metadata or {})
        metadata[b"source_hash"] = file_sha256(clean if path == features else features).encode()
        atomic_write_parquet(table.replace_schema_metadata(metadata), path)
    lag = Path(outputs["lag_correlation_matrix"])
    payload = json.loads(lag.read_text(encoding="utf-8"))
    payload["source_hash"] = file_sha256(features)
    atomic_write_json(payload, lag)
    audit_artifacts(clean, features, out_dir, raw_dir, audit_path, expected_rows)
    return {"clean_ett": str(clean), "grid_features": str(features),
            **outputs, "audit": str(audit_path)}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the offline statistical engine CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_HOURLY_QUANTILES_PATH.parent)
    parser.add_argument("--sync-all", action="store_true", help="Run full three-dataset ETL/features/engine/audit")
    parser.add_argument("--audit-only", action="store_true", help="Validate existing synchronized artifacts")
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_CLEAN_PATH.parent)
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--audit", type=Path, default=DEFAULT_SYNC_AUDIT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the engine; UI never performs these computations."""
    args = parse_args(argv)
    try:
        if args.sync_all and args.audit_only:
            raise ValueError("Choose --sync-all or --audit-only, not both")
        if args.sync_all:
            result = run_all_datasets(args.processed_dir, args.out, args.raw_dir,
                                      args.audit, EXPECTED_DATASET_ROWS)
        elif args.audit_only:
            report = audit_artifacts(args.processed_dir / DEFAULT_CLEAN_PATH.name,
                                     args.processed_dir / DEFAULT_FEATURE_PATH.name,
                                     args.out, args.raw_dir, args.audit, EXPECTED_DATASET_ROWS)
            result = {"status": report["status"], "audit": str(args.audit)}
        else:
            result = run_engine(args.input, args.out)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"Statistical engine failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
