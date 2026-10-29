"""Run WP02 offline statistical analytics and export UI-ready artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analysis.lag_correlation import save_lag_envelope
from src.analysis.load_profiling import save_hourly_quantiles, save_load_profiles_stl
from src.analysis.diagnostics import save_diagnostics
from src.analysis.common import file_sha256, load_feature_input, set_seed
from src.analysis.thermal_risk import save_thermal_breach_events, build_thermal_breach_events
from src.data.constants import (
    DEFAULT_FEATURE_PATH,
    DEFAULT_BREACH_EVENTS_PATH,
    DEFAULT_HOURLY_QUANTILES_PATH,
    DEFAULT_LAG_JSON_PATH,
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
    ))
    return {key: str(value) for key, value in outputs.items()}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the offline statistical engine CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_FEATURE_PATH)
    parser.add_argument("--out", type=Path, default=DEFAULT_HOURLY_QUANTILES_PATH.parent)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the engine; UI never performs these computations."""
    args = parse_args(argv)
    try:
        print(json.dumps(run_engine(args.input, args.out), ensure_ascii=False))
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"Statistical engine failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
