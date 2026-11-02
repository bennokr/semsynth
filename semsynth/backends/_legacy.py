"""Adapter from a file-writing ``run_experiment`` to the in-memory :func:`synthesize` contract.

PyBNesian and SynthCity still implement ``run_experiment``, which splits the table, writes its files and returns
the run directory. :func:`synthesize_via_run_experiment` runs it in a temporary directory and reads the outcome
back into a :class:`~semsynth.result.SynthesisResult`.

Limitations: the data comes back through ``synthetic.csv``, so categories become plain strings and numbers; the
engine holds out ``test_size`` of the rows it is given for its own metrics (kept in ``result.metrics``), which are
not the metrics of the held-out rows that the pipeline computes itself.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from ..result import SynthesisResult

# Files that semsynth.synthesis.write_run writes itself; everything else a backend wrote is an artifact.
_REGENERATED = frozenset(
    {
        "synthetic.csv",
        "synthetic.parquet",
        "metrics.json",
        "manifest.json",
        "per_variable_metrics.csv",
        "provenance.json",
    }
)
_BOOKKEEPING = frozenset({"backend", "name", "provider", "dataset_name", "provider_id"})


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def synthesize_via_run_experiment(
    run_experiment: Callable[..., Path | str],
    backend: str,
    df: Any,
    *,
    rows: int | None,
    seed: int,
    options: Mapping[str, Any],
) -> SynthesisResult:
    """Run ``run_experiment`` on ``df`` in a temporary directory and return what it produced.

    Args:
        run_experiment: The backend's file-based entry point.
        backend: Name of the backend.
        df: The table to learn from.
        rows: Number of synthetic rows.
        seed: Random seed.
        options: The settings that the backend takes as ``model_info``; ``test_size`` (default 0.2) and
            ``dataset_name`` are taken out and passed on separately.
    """

    import pandas as pd

    model_info = dict(options)
    test_size = float(model_info.pop("test_size", 0.2))
    dataset_name = model_info.pop("dataset_name", None)
    with tempfile.TemporaryDirectory(prefix=f"semsynth-{backend}-") as temp_dir:
        run_dir = Path(
            run_experiment(
                df=df,
                provider=None,
                dataset_name=dataset_name,
                provider_id=None,
                outdir=temp_dir,
                label="run",
                model_info=model_info,
                rows=rows,
                seed=seed,
                test_size=test_size,
                codebook_jsonld=None,
            )
        )
        synthetic = pd.read_csv(run_dir / "synthetic.csv")
        metrics = _read_json(run_dir / "metrics.json")
        manifest = _read_json(run_dir / "manifest.json")
        artifacts = {
            path.name: path.read_bytes()
            for path in sorted(run_dir.iterdir())
            if path.is_file() and path.name not in _REGENERATED
        }
    metrics.pop("backend", None)
    parameters = {key: value for key, value in manifest.items() if key not in _BOOKKEEPING}
    return SynthesisResult(
        synthetic_data=synthetic,
        backend=backend,
        parameters=parameters,
        metrics=metrics,
        provenance={"engine": backend, "via": "run_experiment"},
        artifacts=artifacts,
    )
