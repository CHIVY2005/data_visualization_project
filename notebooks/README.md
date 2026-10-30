# Executed research notebooks — T0304

The two T0304 deliverables have been created and executed independently:

- `02_tqh04_statistical_analysis.ipynb` — TQH-04 statistical analysis.
- `03_tqh05_insights_visual_storytelling.ipynb` — TQH-05 visual storytelling.

Both notebooks include saved tables/figures, seed 2026, input hash checks against
the T0205 audit, and actual execution metadata. Existing notebooks are preserved.

At the repository root, activate `.venv`, then run
`python scripts/build_t0304_notebooks.py` to rebuild and Run-all both notebooks.
This launches the active interpreter as a fresh kernel for each notebook; it
does not install packages, modify source artifacts or run the statistical engine.
Execution evidence is saved in `audit/t0304_notebook_execution.json`.

Use the repository `.venv` kernel. Read clean/features data and precomputed
artifacts, preserving dataset keys and the separate 1h/15-minute cadences.
Do not write into raw data or protected documentation. Use project conventions
85/95°C, original OT units, historical empirical bands, and non-causal wording.

Keep heavy statistical computation in offline analysis modules/scripts. Notebook
experiments must not introduce computation into the Streamlit rendering path.
T0204 provides six independent load–OT LOWESS relations with a seven-column
artifact. This is not a simultaneous six-input causal model. Notebook 03 reads
saved coordinates, never fits LOWESS during storytelling/rendering.

Charts are static research outputs, not evidence of dashboard interaction or
browser SLA. Seasonal bins are project month groups, not verified local climate.