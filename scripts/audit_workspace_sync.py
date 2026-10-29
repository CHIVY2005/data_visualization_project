"""Read-only artifact inspection and timed Streamlit integration smoke audit."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyarrow.parquet as pq
from streamlit.testing.v1 import AppTest

from src.analysis.common import atomic_write_json, file_sha256, utc_now_iso
from src.data.constants import ARTIFACTS_DIR, DEFAULT_CLEAN_PATH, ROOT
from src.visuals.lag_artifact import lag_envelope_frame


def main() -> None:
    """Record observed contracts and server-side reruns, not browser paint SLA."""
    report: dict[str, object] = {
        "generated_at": utc_now_iso(), "python": sys.version,
        "platform": platform.platform(), "interpreter": sys.executable,
        "scope": "AppTest server-side load/filter/render; excludes browser paint",
        "artifacts": {}, "smoke": [],
    }
    artifacts = report["artifacts"]
    paths = [DEFAULT_CLEAN_PATH, *[
        ARTIFACTS_DIR / name for name in (
            "load_profiles_stl.parquet", "quantile_bands.parquet",
            "thermal_breach_events.parquet",
        )
    ]]
    for path in paths:
        table = pq.read_table(path)
        metadata = {
            key.decode(): value.decode()
            for key, value in (table.schema.metadata or {}).items()
            if key != b"pandas"
        }
        frame = table.to_pandas()
        artifacts[path.name] = {
            "path": str(path), "sha256": file_sha256(path),
            "rows": len(frame), "columns": table.schema.names,
            "dtypes": {field.name: str(field.type) for field in table.schema},
            "dataset_rows": frame.groupby("dataset").size().to_dict(),
            "metadata": metadata,
        }
    path = ARTIFACTS_DIR / "lag_correlation_matrix.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    lag = lag_envelope_frame(payload)
    artifacts[path.name] = {
        "path": str(path), "sha256": file_sha256(path),
        "records": len(payload["records"]),
        "dataset_rows": lag.groupby("dataset").size().to_dict(),
        "metadata": {key: value for key, value in payload.items() if key != "records"},
    }
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    started = perf_counter()
    app.run()
    report["initial_run_seconds"] = perf_counter() - started
    if app.exception:
        raise RuntimeError(str(app.exception))
    datasets = list(app.sidebar.selectbox[0].options)
    for dataset in datasets:
        app.sidebar.selectbox[0].select(dataset).run()
        for story in app.sidebar.radio[0].options:
            app.sidebar.radio[0].set_value(story).run()
            # Dataset, Season, View, Variable are the four sidebar selectboxes.
            for view in list(app.sidebar.selectbox[2].options):
                started = perf_counter()
                app.sidebar.selectbox[2].select(view).run()
                elapsed = perf_counter() - started
                errors = [str(item.value) for item in app.exception]
                report["smoke"].append({
                    "dataset": dataset, "story": story, "view": view,
                    "seconds": elapsed, "exceptions": errors,
                })
    report["all_views_exception_free"] = all(
        not item["exceptions"] for item in report["smoke"]
    )
    report["server_reruns_under_2s"] = all(
        item["seconds"] < 2 for item in report["smoke"]
    )
    output = atomic_write_json(report, ROOT / "audit" / "workspace_sync_runtime.json")
    print(json.dumps({
        "report": str(output), "views": len(report["smoke"]),
        "exception_free": report["all_views_exception_free"],
        "initial_run_seconds": report["initial_run_seconds"],
        "server_reruns_under_2s": report["server_reruns_under_2s"],
        "max_rerun_seconds": max(item["seconds"] for item in report["smoke"]),
    }))
    if not report["all_views_exception_free"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()