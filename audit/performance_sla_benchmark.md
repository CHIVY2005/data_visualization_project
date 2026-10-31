# T0504 — Streamlit cache & SLA benchmark report

- **Generated:** 2026-10-31 08:33 +07:00 (local; raw JSON records UTC).
- **Branch:** `feat/T0504`; source baseline includes committed T0204/T0205/T0304.
- **Runtime:** Python 3.11.1 `.venv`, Streamlit 1.65.0, pandas 3.0.6.
- **Host:** Windows 10, Intel64 Family 6 Model 158 Stepping 9.
- **Benchmark:** `scripts/benchmark_cache_sla.py`.
- **Machine-readable results:** `audit/performance_sla_benchmark.json`.
- **Final regression:** 227 passed, 0 failed, 8 dependency deprecation warnings, 49.35s.

## Scope and measurement method

Measurements cover artifact reads, slicing/filter helpers, per-view Plotly figure
construction and Streamlit AppTest server-side render/interactions. They do not
include browser paint, network, concurrent users or other machines. Results are
local evidence, not an end-to-end production SLA guarantee. Cold six-artifact IO
clears caches first; AppTest cold/warm initial runs are separately reported.

The six cached inputs are grid features, STL/profile, quantile bands, lag JSON,
thermal events and LOESS. Paths, sizes and SHA-256 hashes are recorded in the JSON
evidence. No benchmark step writes or modifies these input artifacts.

## Cache loading and lightweight interactions

| Scenario | Runs | Mean | Median | Max |
|---|---:|---:|---:|---:|
| Cold load, six artifacts | 1 | 0.9394s | — | 0.9394s |
| Warm cached load, six artifacts | 1 | 0.0662s | — | 0.0662s |
| Switch/slice across three datasets | 10 | 0.0371s | 0.0330s | 0.0548s |
| Dataset + season/date helper filter | 10 | 0.0201s | 0.0200s | 0.0220s |

## Chart construction — ETTh1, five runs per view

| View | Mean | Median | Max |
|---|---:|---:|---:|
| Calendar Heatmap | 0.1297s | 0.0969s | 0.3528s |
| 100% Load Composition | 0.2736s | 0.2789s | 0.3041s |
| Lag Heatmap | 0.0861s | 0.0668s | 0.1773s |
| Quantile Fan | 0.0366s | 0.0344s | 0.0446s |
| STL Panels | 0.1821s | 0.1690s | 0.2793s |
| OT Threshold | 0.0627s | 0.0638s | 0.0707s |
| Event Barcode/Rug | 0.0087s | 0.0080s | 0.0104s |
| Synchronized Small Multiples | 0.0773s | 0.0739s | 0.0950s |
| Saved LOESS Scatter | 0.0437s | 0.0413s | 0.0519s |
| Thermal Regime Boxplots | 0.0729s | 0.0725s | 0.0836s |

## AppTest interactions and SLA assessment

| AppTest scenario | Result |
|---|---:|
| Initial render, new AppTest | 1.0082s |
| Warm initial render, second AppTest | 0.5036s |
| Dataset switches ETTh1 / ETTh2 / ETTm1 | 0.1810 / 0.1672 / 0.2101s |
| Role switch, three transitions | mean 0.2161s |
| Variable switch, two transitions | mean 0.2021s |
| Date-range filter | 0.1732s |
| View switch, nine transitions | mean 0.2475s; max 0.4362s |
| AppTest exceptions | 0 |

- Warm six-artifact loader mean **0.0662s < 1.5s** stretch target.
- Dataset and filter helper means **0.0371s / 0.0201s < 1.5s**.
- Cold and warm AppTest initial renders and measured switches were **<2s**.
- **Local server-side AppTest acceptance: PASS for this measured configuration.**
- **Browser/end-to-end SLA: NOT MEASURED.** No production-wide <2s claim is made.

## Cache design and guardrails

`src/visuals/cache_manager.py` centralizes Parquet and canonical lag JSON readers.
Cache keys include resolved `path` and `(mtime_ns, size)` `version`; no key parameter
starts with underscore. Cache capacity is bounded at 32 Parquet and 8 JSON entries.
Dataset switching slices the shared cached feature frame; role/view changes reuse
artifact cache. UI does not compute STL, lag correlation, LOWESS/LOESS or ETL.

Tests cover real cache hits (no second disk read), returned-frame mutation isolation,
path/dataset separation, file-version invalidation and warm-cache timing.
Processed/output artifacts, raw data, charter and references were not modified.
No commit or push was performed.

## Limitations and warnings

- AppTest uses Streamlit's in-memory test runtime, not a browser/deployed server.
- One local cold measurement is not a performance bound across machines.
- Existing Streamlit `use_container_width` deprecation warnings remain.
- Eight pytest warnings are Pandas/Seaborn/Matplotlib deprecations, not failures.
- See `audit/performance_sla_benchmark.json` for raw timings and artifact hashes.
