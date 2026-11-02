"""One entry point for synthetic data: :func:`synthesize`, and :func:`write_run` for the files.

``synthesize`` fits a backend on a table and returns a :class:`~semsynth.result.SynthesisResult` in memory. It
never touches the disk, so it can run in a browser. ``write_run`` is the only function here that writes files.
"""

from __future__ import annotations

import importlib
import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from .result import SynthesisResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

__all__ = ["BACKENDS", "EVALUATES_ITSELF", "load_backend", "synthesize", "write_run"]

BACKENDS = ("metasyn", "privbayes", "pybnesian", "synthcity")
"""The backend names; each is also the name of the extra that installs its engine."""

EVALUATES_ITSELF = frozenset({"pybnesian", "synthcity"})
"""Backends that hold rows out and report held-out metrics themselves; the runner gives them the whole sample."""

_PROV = "http://www.w3.org/ns/prov#"


def load_backend(name: str) -> ModuleType:
    """Import the module of a backend.

    Args:
        name: One of :data:`BACKENDS`.

    Raises:
        ValueError: For an unknown name.
        ImportError: If the backend cannot be imported; the message names the extra to install.
    """

    key = str(name).strip().lower()
    if key not in BACKENDS:
        raise ValueError(f"Unknown backend {name!r}; choose one of {', '.join(BACKENDS)}.")
    try:
        return importlib.import_module(f"semsynth.backends.{key}")
    except ImportError as exc:
        raise ImportError(
            f"The {key!r} backend could not be imported ({exc}); install it with `pip install 'semsynth[{key}]'`."
        ) from exc


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    backend: str = "metasyn",
    rows: int | None = None,
    seed: int = 0,
    **options: Any,
) -> SynthesisResult:
    """Fit ``backend`` on ``df`` and draw synthetic rows.

    Args:
        df: The real table.
        codebook: A :class:`~semsynth.codebook.Codebook` (or a document that it can read) that tells which
            columns are categorical and which are numeric; inferred from ``df`` when omitted.
        backend: One of :data:`BACKENDS`.
        rows: Number of synthetic rows; the number of rows of ``df`` when omitted.
        seed: Random seed.
        **options: Settings of the backend, such as ``epsilon`` for ``privbayes``.

    Returns:
        The synthetic table, the learned model and what is known about the run, all in memory.
    """

    module = load_backend(backend)
    count = len(df) if rows is None else int(rows)
    if count < 1:
        raise ValueError("rows must be at least 1.")
    if codebook is not None and not hasattr(codebook, "kind"):
        from .codebook import Codebook

        codebook = Codebook.read(codebook)
    result: SynthesisResult = module.synthesize(df, codebook, rows=count, seed=int(seed), **options)
    return result


def write_run(
    result: SynthesisResult,
    run_dir: str | Path,
    *,
    label: str | None = None,
    dataset: Mapping[str, Any] | None = None,
    codebook_jsonld: Mapping[str, Any] | None = None,
) -> Path:
    """Write a result as the files of a model run and return the directory.

    Writes ``synthetic.csv`` and, when the pieces exist, ``synthetic.parquet`` (with the codebook in its
    metadata), ``metrics.json``, ``per_variable_metrics.csv`` (``metrics["per_variable"]``),
    ``metrics.privacy.json`` (``metrics["privacy"]``), ``metrics.downstream.json`` (``metrics["downstream"]``),
    ``metasyn_gmf.json``, the result's ``artifacts``, ``manifest.json`` and a PROV-O ``provenance.json``.

    Args:
        result: What :func:`synthesize` returned, possibly with metrics added.
        run_dir: Directory of the run; created if missing.
        label: Name of the run; the backend name when omitted.
        dataset: ``provider``, ``dataset_name`` and ``provider_id`` of the real data, for the manifest.
        codebook_jsonld: DSV JSON-LD to store in the Parquet metadata.
    """

    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = label or result.backend
    result.synthetic_data.to_csv(directory / "synthetic.csv", index=False)
    if codebook_jsonld:
        _write_parquet(result.synthetic_data, directory / "synthetic.parquet", codebook_jsonld)
    written = _write_metrics(result, directory)
    written += _write_artifacts(result, directory)
    manifest = _manifest(result, name, dataset or {})
    _write_json(directory / "manifest.json", manifest)
    _write_json(directory / "provenance.json", _provenance(result, name, dataset or {}, written))
    LOGGER.info("Wrote run %s to %s", name, directory)
    return directory


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _write_parquet(frame: pd.DataFrame, path: Path, codebook_jsonld: Mapping[str, Any]) -> None:
    try:
        from .codebook import write_parquet

        write_parquet(frame, path, dict(codebook_jsonld))
    except Exception:
        LOGGER.exception("Failed to write Parquet with the codebook")


def _write_metrics(result: SynthesisResult, directory: Path) -> list[str]:
    import pandas as pd

    metrics = dict(result.metrics)
    per_variable = metrics.pop("per_variable", None)
    privacy = metrics.pop("privacy", None)
    downstream = metrics.pop("downstream", None)
    written = ["metrics.json"]
    _write_json(directory / "metrics.json", {"backend": result.backend, **metrics})
    if per_variable is not None:
        pd.DataFrame(per_variable).to_csv(directory / "per_variable_metrics.csv", index=False)
        written.append("per_variable_metrics.csv")
    if privacy is not None:
        _write_json(directory / "metrics.privacy.json", privacy)
        written.append("metrics.privacy.json")
    if downstream is not None:
        _write_json(directory / "metrics.downstream.json", downstream)
        written.append("metrics.downstream.json")
    return written


def _write_artifacts(result: SynthesisResult, directory: Path) -> list[str]:
    written: list[str] = []
    if result.backend == "metasyn" and hasattr(result.learned_model, "save"):
        try:
            result.learned_model.save(str(directory / "metasyn_gmf.json"))
            written.append("metasyn_gmf.json")
        except Exception:
            LOGGER.warning("Could not serialize the MetaSyn model", exc_info=True)
    for name, content in result.artifacts.items():
        target = directory / name
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        written.append(name)
    return written


def _manifest(result: SynthesisResult, label: str, dataset: Mapping[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "backend": result.backend,
        "name": label,
        "provider": dataset.get("provider"),
        "dataset_name": dataset.get("dataset_name"),
        "provider_id": dataset.get("provider_id"),
        **result.parameters,
    }
    if result.privacy_report is not None:
        manifest["privacy_report"] = dict(result.privacy_report)
    if result.warnings:
        manifest["warnings"] = list(result.warnings)
    return manifest


def _provenance(
    result: SynthesisResult, label: str, dataset: Mapping[str, Any], written: list[str]
) -> dict[str, Any]:
    """A small PROV-O description of the run: the dataset it used, the software, and the files it generated."""

    from . import get_version

    run = f"urn:semsynth:run:{dataset.get('dataset_name') or 'dataset'}:{label}"
    agent = f"urn:software:semsynth:{get_version()}"
    now = datetime.now(UTC).isoformat()
    engine = str(result.provenance.get("engine", result.backend))
    engine_iri = f"urn:engine:{engine}:{result.provenance.get('engine_version', 'unknown')}"
    dataset_iri = f"urn:dataset:{dataset.get('provider') or 'local'}:{dataset.get('dataset_name') or 'dataset'}"
    graph: list[dict[str, Any]] = [
        {
            "@id": run,
            "@type": "prov:Activity",
            "rdfs:label": f"{result.backend} synthesis {label}",
            "prov:wasAssociatedWith": {"@id": agent},
            "prov:used": [{"@id": dataset_iri}, {"@id": engine_iri}],
            "prov:startedAtTime": now,
            "dcterms:description": json.dumps(dict(result.parameters), default=str, sort_keys=True),
        },
        {
            "@id": agent,
            "@type": ["prov:Agent", "prov:SoftwareAgent"],
            "schema:name": "semsynth",
            "schema:softwareVersion": get_version(),
        },
        {"@id": engine_iri, "@type": ["prov:Entity", "schema:SoftwareApplication"], "schema:name": engine},
        {"@id": dataset_iri, "@type": "prov:Entity", "dcterms:title": str(dataset.get("dataset_name") or "dataset")},
    ]
    graph.extend(
        {
            "@id": f"{run}:{name}",
            "@type": "prov:Entity",
            "dcterms:title": name,
            "prov:wasGeneratedBy": {"@id": run},
            "prov:generatedAtTime": now,
        }
        for name in ["synthetic.csv", *written]
    )
    context = {
        "prov": _PROV,
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "schema": "https://schema.org/",
        "dcterms": "http://purl.org/dc/terms/",
    }
    return {"@context": context, "@graph": graph}
