# Workspace synchronization audit — 2026-10-29

## Git baseline and preservation

- Remote: origin; fetched with prune and tags, then pulled with `--ff-only`.
- Integration baseline: `b39cdd2`, `feat/T0501_T0502_T0503-integration-qa`.
- Working branch: `fix/T0501_T0502_T0503-integration-qa`.
- Created local tracking branch and fix branch without resetting any local branch.
- Protected paths have identical committed trees between the initial branch
  (`c7abaee`) and integration baseline. Switching did not change RED-zone files.
- Initial worktree changes were exclusively protected documentation: two tracked
  deletions and three untracked files, including an Excel lock file. They remain
  untouched and must not be included in this task's commit.
- No stash: stashing those files would modify RED-zone worktree state. Git could
  carry the existing changes safely; no user changes needed to be hidden.
- No reset, force-push, push, dependency installation, or raw regeneration.

## Canonical contracts

All five canonical files exist. Detailed observed Arrow schemas, metadata,
dataset counts and SHA-256 hashes are in `workspace_sync_runtime.json`.

| Artifact | Synchronization result |
|---|---|
| `data/processed/clean_ett.parquet` | Existing canonical clean producer/input preserved |
| `output/artifacts/load_profiles_stl.parquet` | Existing canonical producer/consumer preserved |
| `output/artifacts/quantile_bands.parquet` | Existing canonical producer/consumer preserved |
| `output/artifacts/lag_correlation_matrix.json` | Engine, standalone export and UI now use this envelope |
| `output/artifacts/thermal_breach_events.parquet` | Existing canonical producer/consumer preserved |

The UI's lag JSON adapter performs only validation and a small 6x13 reshape,
not correlations or model fitting. Null coefficients remain missing, not zero.
Regression cases reject invalid shape, NaN, counts, order and duplicate records.

The pre-existing tracked `lag_matrix.parquet` is preserved as legacy data, not a
canonical output or fallback. `save_lag_matrix` remains an explicitly requested
compatibility API with no default destination; the normal engine/CLI never
generates that duplicate. Its existing regression test remains intact.
`grid_features.parquet`, `loess_curves.parquet` and `event_load_zscores.parquet`
are existing supplementary artifacts, not replacements for the five contracts.
This audit verifies synchronization and records existing schemas; it is not
full certification of all historical metadata or every artifact value.

## Cache and business logic

- Initial regression: 187 passed, 1 failed. QA renamed public loaders and broke
  the pre-integration cache regression API.
- Restored public `artifact_version`, `load_parquet`, and `load_stl` functions;
  the UI uses the same implementations exercised by the regression suite.
- Parquet/STL/JSON cached arguments are `path` and `version`, with no leading
  underscores. Resolved path, nanosecond mtime and file size identify sources.
- Added JSON cache tests for path identity and version invalidation.
- LOWESS stays in `src/analysis/diagnostics.py`, outside the UI render path.
- Safety KPIs keep warning and critical Degree-Hours/duration separate; no
  overlapping cross-threshold total. Existing synthetic boundary tests pass.
- Manager load fractions exclude negative/invalid pairs, without clipping.
- Historical records have no observed breaches; empty events are legitimate.

## Validation evidence

- `.venv` activated; Python 3.11.1, interpreter under repository `.venv/Scripts`.
- `python -m pytest tests/ -v --tb=short`: **197 passed, 0 failed** (26.68s).
- `python -m compileall -q app.py src scripts tests`: passed.
- `git diff --check`: passed.
- Engine CLI and standalone lag CLI `--help`: passed.
- Engine regression uses 72 observed ETTh1 samples in a temporary directory,
  validates canonical export and confirms no legacy lag Parquet is generated.
- Streamlit AppTest: all 27 dataset/view combinations exception-free across
  ETTh1, ETTh2 and ETTm1, including both stories.
- Initial AppTest run: 1.2984s; maximum measured view rerun: 0.8491s.
- Measurements are a single server-side smoke run; browser paint/network,
  repeated cold-cache distributions and all filter combinations are not measured.
  End-to-end SLA remains a T0504 acceptance task, not certified here.
- Streamlit reports existing `use_container_width` deprecation warnings; no
  runtime failures. Version compatibility cleanup can accompany T0504.
- The existing environment contains Torch, but project runtime does not import
  it. CPU-only source is preserved; no environment packages were removed.

## Supplementary-task readiness (not implementation completion)

| Task | Ready surface | Remaining acceptance work |
|---|---|---|
| T0204 | Existing analysis, thermal risk and offline diagnostics modules | Agree multivariable LOESS artifact contract; implement/test offline producer and consumers |
| T0205 | Three clean/features datasets and all canonical artifacts exist | Formalize exhaustive per-dataset schema, provenance and quality checks |
| T0304 | Existing notebooks directory and handoff README | Author and execute the two planned notebooks; no fake placeholder notebooks |
| T0504 | Versioned caches plus reproducible AppTest audit command | Optimize as needed; measure browser/end-to-end and repeated cold/warm filter SLA |

The user-approved supplementary task IDs are recorded here; protected charter
and planning sources were not edited. Commit only task-specific source/tests,
notebooks handoff and audit files. Existing protected worktree changes are not
part of synchronization and intentionally leave Git status non-clean.