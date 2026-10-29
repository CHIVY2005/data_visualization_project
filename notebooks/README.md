# Supplementary notebook handoff — T0304

This existing directory is ready for the two planned deliverables:

- `02_tqh04_statistical_analysis.ipynb` — TQH-04 statistical analysis.
- `03_tqh05_insights_visual_storytelling.ipynb` — TQH-05 visual storytelling.

These filenames are **planned outputs, not implemented notebooks**. Existing
notebooks are preserved; empty placeholder notebooks are intentionally not added.

Use the repository `.venv` kernel. Read clean/features data and precomputed
artifacts, preserving dataset keys and the separate 1h/15-minute cadences.
Do not write into raw data or protected documentation. Use project conventions
85/95°C, original OT units, historical empirical bands, and non-causal wording.

Keep heavy statistical computation in offline analysis modules/scripts. Notebook
experiments must not introduce computation into the Streamlit rendering path.
T0204 should extend the existing offline diagnostics with an agreed additional
artifact contract; the existing single-branch LOWESS curves are not evidence
that multivariable LOESS has been implemented.