"""Validate delivered Run-all notebooks and their read-only input provenance."""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", [
    "02_tqh04_statistical_analysis.ipynb",
    "03_tqh05_insights_visual_storytelling.ipynb",
])
def test_executed_notebook_contract(name: str) -> None:
    notebook = json.loads((ROOT / "notebooks" / name).read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    task = notebook["metadata"]["ett_task"]
    assert task["id"] == "T0304" and task["seed"] == 2026
    cells = [c for c in notebook["cells"] if c["cell_type"] == "code"]
    evidence = notebook["metadata"]["ett_execution"]
    assert evidence["errors"] == 0 and evidence["code_cells_executed"] == len(cells)
    assert len(cells) >= 7
    assert [c["execution_count"] for c in cells] == list(range(1, len(cells) + 1))
    outputs = [output for cell in cells for output in cell["outputs"]]
    assert not any(o["output_type"] == "error" for o in outputs)
    assert any("image/png" in o.get("data", {}) for o in outputs)
    assert any("text/html" in o.get("data", {}) for o in outputs)
    for path, digest in task["input_sha256"].items():
        # Use basename/location so evidence remains inspectable after relocation.
        name = Path(path).name
        source = ROOT / ("data/processed" if name in {
            "clean_ett.parquet", "grid_features.parquet",
        } else "output/artifacts") / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest


def test_notebook_execution_audit() -> None:
    audit = json.loads((ROOT / "audit/t0304_notebook_execution.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS" and audit["protected_unchanged"] is True
    assert audit["browser_sla"] == "NOT_MEASURED"
    assert len(audit["notebooks"]) == 2
    assert all(e["errors"] == 0 for e in audit["notebooks"].values())