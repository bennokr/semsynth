"""Entry points for a browser front end (Pyodide): text in, text out, no network, no files outside a temporary folder.

A page cannot call the command line or read the cache that the providers use. It holds a CSV (what the user loaded), a
codebook (JSON or JSON-LD, optional) and some settings, and wants the report and the metrics back as strings that it can
show or offer for download. Three functions cover that:

* :func:`capabilities` says what this runtime can do (which backends and metrics are installed, whether it is Pyodide),
  so that the page can disable what is missing instead of failing;
* :func:`inspect_table` checks a table against its codebook *before* anything is generated: how many cells hold declared
  missing codes, which skip rules the data breaks, whether the subgroup definitions refer to real columns and how big
  the groups are;
* :func:`run` runs the pipeline and returns every text file it wrote.

Nothing here is specific to Pyodide, so all of it is tested natively; the Pyodide smoke test (``scripts/pyodide_smoke.py``)
runs it in the real runtime.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .synthesis import CAPABILITIES

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from .codebook import Codebook

TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".jsonld", ".html", ".tsv"}
PYODIDE_ROW_LIMIT = 5000
"""Rows beyond which the pipeline subsamples in Pyodide; a few thousand rows take seconds, tens of thousands do not."""


def _available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def is_pyodide() -> bool:
    """Whether this runs inside Pyodide."""
    return sys.platform == "emscripten"


def capabilities() -> dict[str, Any]:
    """What this runtime can do; every value is a plain JSON type."""
    from . import get_version

    engines = {"chain": "sklearn", "metasyn": "metasyn", "privbayes": "DataSynthesizer", "pybnesian": "pybnesian", "synthcity": "synthcity"}
    return {
        "version": get_version(),
        "python": sys.version.split()[0],
        "pyodide": is_pyodide(),
        "backends": {name: _available(module) for name, module in engines.items()},
        "backend_capabilities": {name: asdict(caps) for name, caps in CAPABILITIES.items()},
        "metrics": {
            "sdmetrics": _available("sdmetrics"),
            "statsmodels": _available("statsmodels"),
            "umap": _available("umap"),
        },
        "row_limit": PYODIDE_ROW_LIMIT if is_pyodide() else None,
    }


def _table(csv_text: str) -> pd.DataFrame:
    import io

    import pandas as pd

    return pd.read_csv(io.StringIO(csv_text))


def _codebook(document: Mapping[str, Any] | str | None, frame: pd.DataFrame) -> Codebook:
    from .codebook import Codebook

    if document is None or document == "":
        return Codebook.from_frame(frame)
    return Codebook.read(json.loads(document) if isinstance(document, str) else dict(document))


def inspect_table(
    csv_text: str,
    codebook: Mapping[str, Any] | str | None = None,
    subgroups: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Check a table against its codebook, and subgroup definitions against the table, without generating anything.

    Returns:
        ``rows``, ``declared_missing`` (cells per column that hold a declared code), ``rule_problems`` (a skip rule that does not parse or refers
        to a field that is no column), ``structural`` (cells that the skip
        rules mark as not applicable and how many of them hold a value anyway), ``incomplete_rows`` (rows with a missing
        cell, after recoding) and ``subgroups`` (``problems`` such as a field that is no column, and the size of each
        group).
    """
    from .structure import (
        check_rules,
        check_subgroups,
        membership,
        recode_declared_missing,
        structural_violations,
        subgroups_from,
    )

    frame = _table(csv_text)
    book = _codebook(codebook, frame)
    recoded, declared = recode_declared_missing(frame, book)
    groups = subgroups_from(subgroups or [])
    problems = check_subgroups(groups, frame.columns)
    sizes = {} if problems else {g: int(n) for g, n in membership(recoded, groups).sum().items()}
    violations = structural_violations(recoded, book)
    return {
        "rows": len(frame),
        "declared_missing": declared,
        "rule_problems": check_rules(book, frame.columns),
        "structural": {"violation_rate": None if violations["rate"] != violations["rate"] else violations["rate"], "columns": violations["columns"]},
        "incomplete_rows": int(recoded.isna().any(axis=1).sum()),
        "subgroups": {"problems": problems, "sizes": sizes},
    }


def run(
    csv_text: str,
    *,
    config: Mapping[str, Any] | None = None,
    codebook: Mapping[str, Any] | str | None = None,
    target: str | None = None,
    name: str = "dataset",
) -> dict[str, Any]:
    """Run the report pipeline on a CSV and return the text files it wrote.

    Args:
        csv_text: The table.
        config: What :func:`semsynth.workflow.read_pipeline_config` reads from TOML, as a dictionary: ``pipeline`` (the
            settings of :class:`semsynth.config.PipelineConfig`) and ``models`` (a list of ``name``, ``backend``, ...).
            Without models only a report of the data is made.
        codebook: JSON or JSON-LD codebook, as text or dictionary; one is inferred when omitted.
        target: Name of the target column.
        name: Name of the dataset, used for the folder and the report.

    Returns:
        ``files`` (path relative to the dataset folder to text; binary files such as pictures and Parquet are left
        out), ``metrics`` (the parsed ``metrics*.json`` of each model, by model name) and ``capabilities``.
    """
    from .config import PipelineConfig
    from .iris import slug
    from .models import load_model_configs
    from .runner import process_dataset
    from .specs import DatasetSpec

    settings = dict(config or {})
    frame = _table(csv_text)
    book = _codebook(codebook, frame)
    cfg = PipelineConfig(generate_umap=False)
    cfg.apply_mapping(settings.get("pipeline", {}))
    if is_pyodide() and len(frame) > PYODIDE_ROW_LIMIT:
        cfg.fit_on_sample = min(cfg.fit_on_sample or PYODIDE_ROW_LIMIT, PYODIDE_ROW_LIMIT)
    bundle = load_model_configs(config_data=settings)
    spec = DatasetSpec("browser", name=name, target=target, meta=book.to_jsonld())
    with tempfile.TemporaryDirectory() as folder:
        process_dataset(spec, frame, frame[target] if target in frame.columns else None, folder, model_bundle=bundle, pipeline_config=cfg)
        root = Path(folder) / slug(name)  # the runner writes the folder under the slug of the name
        files = {
            str(p.relative_to(root)): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix in TEXT_SUFFIXES
        }
    metrics: dict[str, dict[str, Any]] = {}
    for path, text in files.items():
        parts = Path(path).parts
        if len(parts) == 3 and parts[0] == "models" and parts[2].startswith("metrics") and parts[2].endswith(".json"):
            metrics.setdefault(parts[1], {})[parts[2]] = json.loads(text)
    return {"files": files, "metrics": metrics, "capabilities": capabilities()}
