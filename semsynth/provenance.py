"""PROV-O of a synthesis run, in the shape makeprov 0.7+ uses, and its evaluation as W3C DQV measurements.

makeprov records the *commands* of the CLI (``semsynth.__main__``). This module records what a *run* did, and does it
without makeprov, because a browser has no git and no file system layout to hash: the library stays importable
there (see :mod:`semsynth.browser`). The two records use the same model, so they can be queried together:

``prov:Plan`` (semsynth at a version) and the runtime (CPython) are separate; the activity names both through
``prov:qualifiedAssociation`` / ``prov:hadPlan``; the activity ``prov:used`` the dataset, the engine and the codebook, and
carries its parameters as ``schema:additionalProperty``, a start, an end and a ``schema:duration``; every file it wrote
is a ``prov:Entity`` with a ``sha256``.

Scores become ``dqv:QualityMeasurement`` nodes of a ``dqv:Metric`` that has an id and a version. DQV has no property for
uncertainty, so the ``ss:`` terms (a placeholder namespace until one is registered) carry a bootstrap interval
(``ss:lowerBound``, ``ss:upperBound``) and a permutation noise floor (``ss:noiseLower``, ``ss:noiseUpper``, ``ss:pValue``).
"""

from __future__ import annotations

import hashlib
import platform
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .result import SynthesisResult

METRICS_VERSION = "1"
"""Bump when the definition of any metric changes (what it measures, not how it is called)."""

CONTEXT = {
    "prov": "http://www.w3.org/ns/prov#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "schema": "https://schema.org/",
    "dcterms": "http://purl.org/dc/terms/",
    "dqv": "http://www.w3.org/ns/dqv#",
    "ss": "https://w3id.org/semsynth/vocab#",
}

# metric id -> (path in the metrics, path of its bootstrap interval, path of its noise floor)
_Path = tuple[str, ...]
MEASURES: dict[str, tuple[_Path, _Path | None, _Path | None]] = {
    "marginal.disc_jsd_mean": (("summary", "disc_jsd_mean"), None, ("summary_null", "disc_jsd_mean")),
    "marginal.cont_ks_mean": (("summary", "cont_ks_mean"), None, ("summary_null", "cont_ks_mean")),
    "marginal.cont_w1_mean": (("summary", "cont_w1_mean"), None, ("summary_null", "cont_w1_mean")),
    "privacy.exact_match_rate": (("privacy", "exact_match_rate"), ("privacy", "intervals", "exact_match_rate"), None),
    "privacy.exact_match_rate_holdout": (("privacy", "exact_match_rate_holdout"), ("privacy", "intervals", "exact_match_rate_holdout"), None),
    "privacy.dcr_median": (("privacy", "dcr_synthetic", "median"), ("privacy", "intervals", "dcr_median"), None),
    "privacy.dcr_below_holdout_p05": (("privacy", "dcr_below_holdout_p05"), ("privacy", "intervals", "dcr_below_holdout_p05"), None),
    "joint.pairwise_tvd_mean": (("joint", "pairwise", "tvd_mean"), None, ("joint", "pairwise", "null")),
    "joint.classifier_auc": (("joint", "classifier", "auc"), ("joint", "classifier", "auc_interval"), None),
    "downstream.sign_match_rate": (("downstream", "sign_match_rate"), None, None),
}


def _dig(data: Mapping[str, Any], path: _Path) -> Any:
    for key in path:
        if not isinstance(data, Mapping) or key not in data:
            return None
        data = data[key]
    return data


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value else None


def measurements(metrics: Mapping[str, Any], subject: str, run: str) -> list[dict[str, Any]]:
    """``dqv:Metric`` and ``dqv:QualityMeasurement`` nodes for the scores that are present in ``metrics``."""
    nodes: list[dict[str, Any]] = []
    for metric_id, (value_path, interval_path, null_path) in MEASURES.items():
        value = _number(_dig(metrics, value_path))
        if value is None:
            continue
        metric = f"urn:semsynth:metric:{metric_id}"
        measurement: dict[str, Any] = {
            "@id": f"{run}:measurement:{metric_id}",
            "@type": "dqv:QualityMeasurement",
            "dqv:isMeasurementOf": {"@id": metric},
            "dqv:computedOn": {"@id": subject},
            "dqv:value": value,
        }
        interval = _dig(metrics, interval_path) if interval_path else None
        if isinstance(interval, list) and len(interval) == 2 and all(_number(x) is not None for x in interval):
            measurement |= {"ss:lowerBound": interval[0], "ss:upperBound": interval[1]}
        null = _dig(metrics, null_path) if null_path else None
        if isinstance(null, Mapping) and null.get("null_interval"):
            measurement |= {
                "ss:noiseLower": null["null_interval"][0],
                "ss:noiseUpper": null["null_interval"][1],
                "ss:pValue": null.get("p_value"),
            }
        nodes += [
            {"@id": metric, "@type": "dqv:Metric", "rdfs:label": metric_id, "dcterms:hasVersion": METRICS_VERSION},
            measurement,
        ]
    return nodes


def _property(name: str, value: Any) -> dict[str, Any]:
    return {"@type": "schema:PropertyValue", "schema:name": name, "schema:value": value}


def _duration(start: str | None, end: str | None) -> str | None:
    try:
        seconds = (datetime.fromisoformat(str(end)) - datetime.fromisoformat(str(start))).total_seconds()
    except (TypeError, ValueError):
        return None
    return f"PT{max(seconds, 0.0):.3f}S"


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def run_provenance(
    result: SynthesisResult,
    label: str,
    dataset: Mapping[str, Any],
    written: list[str],
    directory: Path,
) -> dict[str, Any]:
    """The PROV-O graph of one run: what ran, with which parameters, on what, and what it wrote and measured."""
    from . import get_version

    name = str(dataset.get("dataset_name") or "dataset")
    run = f"urn:semsynth:run:{name}:{label}"
    plan = f"urn:software:semsynth:{get_version()}"
    runtime = f"urn:software:python:{platform.python_version()}"
    engine = str(result.provenance.get("engine", result.backend))
    engine_iri = f"urn:engine:{engine}:{result.provenance.get('engine_version', 'unknown')}"
    dataset_iri = f"urn:dataset:{dataset.get('provider') or 'local'}:{name}"
    started = result.provenance.get("started_at")
    ended = result.provenance.get("ended_at") or datetime.now(UTC).isoformat()
    sizes = {k: result.metrics[k] for k in ("train_rows", "test_rows", "synth_rows") if k in result.metrics}
    properties = [_property(k, v) for k, v in {**result.parameters, **sizes}.items() if isinstance(v, (str, int, float, bool))]
    activity: dict[str, Any] = {
        "@id": run,
        "@type": "prov:Activity",
        "rdfs:label": f"{result.backend} synthesis {label}",
        "prov:wasAssociatedWith": {"@id": runtime},
        "prov:qualifiedAssociation": {"prov:agent": {"@id": runtime}, "prov:hadPlan": {"@id": plan}},
        "prov:used": [{"@id": dataset_iri}, {"@id": engine_iri}],
        "prov:endedAtTime": ended,
        "schema:additionalProperty": properties,
    }
    if started:
        activity |= {"prov:startedAtTime": started, "schema:duration": _duration(started, ended)}
    graph: list[dict[str, Any]] = [
        activity,
        {"@id": plan, "@type": ["prov:Plan", "schema:SoftwareApplication"], "schema:name": "semsynth", "schema:softwareVersion": get_version()},
        {"@id": runtime, "@type": ["prov:Agent", "prov:SoftwareAgent"], "schema:name": "CPython", "schema:softwareVersion": platform.python_version()},
        {"@id": engine_iri, "@type": ["prov:Entity", "schema:SoftwareApplication"], "schema:name": engine},
        {
            "@id": dataset_iri,
            "@type": ["prov:Entity", "schema:Dataset"],
            "dcterms:title": name,
            **({"dcterms:identifier": str(dataset["provider_id"])} if dataset.get("provider_id") is not None else {}),
        },
    ]
    for file_name in ["synthetic.csv", *written]:
        digest = _sha256(directory / file_name)
        graph.append(
            {
                "@id": f"{run}:{file_name}",
                "@type": "prov:Entity",
                "dcterms:title": file_name,
                "prov:wasGeneratedBy": {"@id": run},
                "prov:generatedAtTime": ended,
                **({"dcterms:identifier": f"sha256:{digest}", "schema:sha256": digest} if digest else {}),
            }
        )
    graph += measurements(result.metrics, f"{run}:synthetic.csv", run)
    return {"@context": CONTEXT, "@graph": graph}
