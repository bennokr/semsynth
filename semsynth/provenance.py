"""PROV-O of a synthesis run, in the shape makeprov 0.7+ uses, and its evaluation as W3C DQV measurements.

makeprov records the *commands* of the CLI (``semsynth.__main__``). This module records what a *run* did, and does it
without makeprov, because a browser has no git and no folder layout to hash: the library stays importable there (see
:mod:`semsynth.browser`). The two records use the same model, so they can be queried together.

* ``prov:Plan`` (semsynth at a version) and the runtime (CPython) are separate; the activity names both through
  ``prov:qualifiedAssociation`` / ``prov:hadPlan``. The activity ``prov:used`` the source dataset, the codebook and the
  engine, carries its parameters as ``schema:additionalProperty``, a start, an end and a ``schema:duration``.
* Every file it wrote is a ``prov:Entity`` named by its URL, with a ``sha256``, and the files are the synthetic dataset
  (:mod:`semsynth.catalog` describes the same IRI as a ``dcat:Dataset``): ``prov:wasDerivedFrom`` the source dataset.
* Scores are ``dqv:QualityMeasurement`` nodes of a ``dqv:Metric``. DQV has no property for uncertainty or for the
  version of a metric, and no term of ours is used for them: a bound of an interval, a noise floor and a p-value are
  measurements of their own metrics, each ``prov:wasDerivedFrom`` the metric of the score, and the version is
  ``dct:hasVersion``.
* Every IRI is under :mod:`semsynth.iris`; there are no ``urn:`` IRIs and no blank nodes that a query would need.
"""

from __future__ import annotations

import hashlib
import platform
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .iris import DEFAULT_BASE, SITE, Iris, slug

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .result import SynthesisResult

METRICS_VERSION = "1"
"""Bump when the definition of any metric changes (what it measures, not how it is called)."""

CONTEXT = {
    "prov": "http://www.w3.org/ns/prov#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "schema": "https://schema.org/",
    "dct": "http://purl.org/dc/terms/",
    "dqv": "http://www.w3.org/ns/dqv#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}

REPOSITORY = "https://github.com/bennokr/semsynth"
PYPI = {"chain": "scikit-learn", "metasyn": "metasyn", "privbayes": "DataSynthesizer", "datasynthesizer": "DataSynthesizer", "pybnesian": "pybnesian", "synthcity": "synthcity"}

_Path = tuple[str, ...]
# metric id -> where its score is in the metrics of a run
MEASURES: dict[str, _Path] = {
    "marginal.disc_jsd_mean": ("summary", "disc_jsd_mean"),
    "marginal.cont_ks_mean": ("summary", "cont_ks_mean"),
    "marginal.cont_w1_mean": ("summary", "cont_w1_mean"),
    "privacy.exact_match_rate": ("privacy", "exact_match_rate"),
    "privacy.exact_match_rate_holdout": ("privacy", "exact_match_rate_holdout"),
    "privacy.dcr_median": ("privacy", "dcr_synthetic", "median"),
    "privacy.dcr_below_holdout_p05": ("privacy", "dcr_below_holdout_p05"),
    "joint.pairwise_tvd_mean": ("joint", "pairwise", "tvd_mean"),
    "joint.classifier_auc": ("joint", "classifier", "auc"),
    "downstream.sign_match_rate": ("downstream", "sign_match_rate"),
    # train on the synthetic table, test on real rows (the ceiling is a model trained on real rows, the floor one trained
    # on independent marginals), and the same scores averaged over the folds of a cross-validation
    "utility.synthetic": ("utility", "scores", "synthetic"),
    "utility.ceiling": ("utility", "scores", "real_sample"),
    "utility.floor": ("utility", "scores", "independent_marginals"),
    "utility.recovered": ("utility", "recovered"),
    "marginal.disc_jsd_mean_cv": ("cv", "scores", "synthetic", "disc_jsd_mean", "mean"),
    "joint.pairwise_tvd_mean_cv": ("cv", "scores", "synthetic", "pairwise_tvd_mean", "mean"),
    "joint.classifier_auc_cv": ("cv", "scores", "synthetic", "classifier_auc", "mean"),
    "utility.synthetic_cv": ("cv", "scores", "synthetic", "utility", "mean"),
    "utility.recovered_cv": ("cv", "scores", "synthetic", "utility_recovered", "mean"),
}
# where the bootstrap interval of a score is, and where the noise floor of a distance is
LABELS = {
    "marginal.disc_jsd_mean": "Discrete columns: Jensen-Shannon distance",
    "marginal.cont_ks_mean": "Numeric columns: Kolmogorov-Smirnov distance",
    "marginal.cont_w1_mean": "Numeric columns: Wasserstein distance",
    "privacy.exact_match_rate": "Synthetic rows that copy a real training row",
    "privacy.exact_match_rate_holdout": "Unseen real rows that copy a training row",
    "privacy.dcr_median": "Median distance to the closest real row",
    "privacy.dcr_below_holdout_p05": "Synthetic rows closer to a real row than 95% of unseen real rows are",
    "joint.pairwise_tvd_mean": "Relations between column pairs: distance",
    "joint.classifier_auc": "Can a classifier tell real from synthetic rows (AUC)",
    "downstream.sign_match_rate": "Regression coefficients with the same sign as on real data",
    "utility.synthetic": "Prediction of the target, model trained on the synthetic rows (AUC or R-squared)",
    "utility.ceiling": "Prediction of the target, model trained on real rows (ceiling)",
    "utility.floor": "Prediction of the target, model trained on independent columns (floor)",
    "utility.recovered": "Share of the real data's prediction gain that the synthetic rows keep",
}
_INTERVALS = {
    "privacy.exact_match_rate": ("privacy", "intervals", "exact_match_rate"),
    "privacy.exact_match_rate_holdout": ("privacy", "intervals", "exact_match_rate_holdout"),
    "privacy.dcr_median": ("privacy", "intervals", "dcr_median"),
    "privacy.dcr_below_holdout_p05": ("privacy", "intervals", "dcr_below_holdout_p05"),
    "joint.classifier_auc": ("joint", "classifier", "auc_interval"),
    "utility.synthetic": ("utility", "intervals", "synthetic"),
    "utility.ceiling": ("utility", "intervals", "real_sample"),
    "utility.floor": ("utility", "intervals", "independent_marginals"),
    "utility.recovered": ("utility", "intervals", "recovered"),
    "marginal.disc_jsd_mean_cv": ("cv", "scores", "synthetic", "disc_jsd_mean", "interval"),
    "joint.pairwise_tvd_mean_cv": ("cv", "scores", "synthetic", "pairwise_tvd_mean", "interval"),
    "joint.classifier_auc_cv": ("cv", "scores", "synthetic", "classifier_auc", "interval"),
    "utility.synthetic_cv": ("cv", "scores", "synthetic", "utility", "interval"),
    "utility.recovered_cv": ("cv", "scores", "synthetic", "utility_recovered", "interval"),
}

def label(metric_id: str) -> str:
    """A readable name of a metric; a score averaged over cross-validation folds says so."""
    base, folds = (metric_id[:-3], True) if metric_id.endswith("_cv") else (metric_id, False)
    name = LABELS.get(base, base)
    return f"{name}, mean over cross-validation folds" if folds else name


_NULLS = {
    "marginal.disc_jsd_mean": ("summary_null", "disc_jsd_mean"),
    "marginal.cont_ks_mean": ("summary_null", "cont_ks_mean"),
    "marginal.cont_w1_mean": ("summary_null", "cont_w1_mean"),
    "joint.pairwise_tvd_mean": ("joint", "pairwise", "null"),
}
_DERIVED = {
    "lower95": "lower bound of the 95% bootstrap interval",
    "upper95": "upper bound of the 95% bootstrap interval",
    "noise-lower95": "lower end of the 95% range of this score when the synthetic rows are exchangeable with real ones",
    "noise-upper95": "upper end of the 95% range of this score when the synthetic rows are exchangeable with real ones",
    "p-value": "share of random splits of the pooled rows at least as far apart as the observed ones",
}


_KINDS = {"marginal": "fidelity", "joint": "fidelity", "privacy": "privacy", "downstream": "utility", "utility": "utility"}
_DIMENSIONS = {
    "fidelity": "how closely the synthetic rows resemble real ones",
    "privacy": "how close the synthetic rows are to the real rows they were learned from",
    "utility": "how well conclusions drawn from the synthetic rows hold for the real ones",
    **_DERIVED,
}


def dimension(name: str) -> str:
    """IRI of a dimension of the quality of a synthetic dataset, or of a statistic about a score."""
    return f"{SITE}dimension/{name}"


def _dig(data: Mapping[str, Any], path: _Path) -> Any:
    for key in path:
        if not isinstance(data, Mapping) or key not in data:
            return None
        data = data[key]
    return data


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value else None


def _significant(value: float) -> float:
    """Six significant digits: a score is not known more precisely, and long numbers are hard to read in a table."""
    return float(f"{value:.6g}")


def _pair(value: Any) -> list[float] | None:
    ok = isinstance(value, list) and len(value) == 2 and all(_number(x) is not None for x in value)
    return [float(x) for x in value] if ok else None


def _values(metrics: Mapping[str, Any]) -> dict[str, float]:
    """Every score present in ``metrics``, and its intervals, noise floors and p-values, by metric id."""
    found: dict[str, float] = {}
    for metric_id, path in MEASURES.items():
        value = _number(_dig(metrics, path))
        if value is None:
            continue
        found[metric_id] = _significant(value)
        bounds = _pair(_dig(metrics, _INTERVALS[metric_id])) if metric_id in _INTERVALS else None
        null = _dig(metrics, _NULLS[metric_id]) if metric_id in _NULLS else None
        noise = _pair(null.get("null_interval")) if isinstance(null, Mapping) else None
        for suffix, number in zip(("lower95", "upper95"), bounds or [], strict=False):
            found[f"{metric_id}/{suffix}"] = _significant(number)
        for suffix, number in zip(("noise-lower95", "noise-upper95"), noise or [], strict=False):
            found[f"{metric_id}/{suffix}"] = _significant(number)
        if isinstance(null, Mapping) and _number(null.get("p_value")) is not None:
            found[f"{metric_id}/p-value"] = _significant(float(null["p_value"]))
    return found


def measurements(metrics: Mapping[str, Any], subject: str) -> list[dict[str, Any]]:
    """``dqv:Metric`` and ``dqv:QualityMeasurement`` nodes for the scores that are present in ``metrics``.

    Args:
        metrics: The metrics of a run (see :func:`semsynth.synthesis.write_run`).
        subject: IRI of the thing measured, the synthetic dataset; the IRIs of the measurements are fragments of it.
    """
    nodes: list[dict[str, Any]] = []
    defined: set[str] = set()

    def metric(metric_id: str) -> str:
        root, _, suffix = metric_id.partition("/")
        iri = Iris.metric(metric_id)
        if iri not in defined:
            defined.add(iri)
            node: dict[str, Any] = {
                "@id": iri,
                "@type": "dqv:Metric",
                "rdfs:label": _DERIVED[suffix] if suffix else label(metric_id),
                "dct:hasVersion": METRICS_VERSION,
            }
            node["dqv:inDimension"] = {"@id": dimension(suffix or _KINDS[root.split(".")[0]])}
            if suffix:
                node["prov:wasDerivedFrom"] = {"@id": metric(root)}
            nodes.append(node)
        return iri

    for metric_id, value in _values(metrics).items():
        nodes.append(
            {
                "@id": f"{subject}#measurement-{slug(metric_id)}",
                "@type": "dqv:QualityMeasurement",
                "dqv:isMeasurementOf": {"@id": metric(metric_id)},
                "dqv:computedOn": {"@id": subject},
                "dqv:value": value,
            }
        )
    used = sorted({n["dqv:inDimension"]["@id"].rsplit("/", 1)[1] for n in nodes if n["@type"] == "dqv:Metric"})
    nodes.extend(
        {
            "@id": dimension(name),
            "@type": ["dqv:Dimension", "skos:Concept"],
            "skos:prefLabel": name,
            "skos:definition": _DIMENSIONS[name],
        }
        for name in used
    )
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


def _software(result: SynthesisResult, version: str) -> tuple[str, str, str]:
    """IRIs of the plan (semsynth at a version), the runtime and the engine."""
    python = platform.python_version()
    runtime = f"https://www.python.org/downloads/release/python-{python.replace('.', '')}/"
    engine = str(result.provenance.get("engine", result.backend))
    engine_version = result.provenance.get("engine_version")
    dist = PYPI.get(engine.lower())
    engine_iri = f"https://pypi.org/project/{dist}/{engine_version}/" if dist and engine_version else f"{REPOSITORY}#{quote(engine)}"
    return f"{REPOSITORY}#{version}", runtime, engine_iri


def run_provenance(
    result: SynthesisResult,
    label: str,
    dataset: Mapping[str, Any],
    written: list[str],
    directory: Path,
    *,
    base_iri: str = DEFAULT_BASE,
    codebook: bool = False,
    parent_activity: str | None = None,
) -> dict[str, Any]:
    """The PROV-O graph of one run: what ran, with which parameters, on what, and what it wrote and measured.

    ``parent_activity`` is the IRI of the command that started the run (an activity in the makeprov record of the
    command). The run refers to it with ``prov:wasInfluencedBy``, as makeprov does for a rule that another rule calls.
    """
    from . import get_version

    iris = Iris(base_iri)
    name = dataset.get("dataset_name") or dataset.get("provider_id") or "dataset"
    source, synthetic, run = iris.dataset(name), iris.model(name, label), iris.run(name, label)
    plan, runtime, engine_iri = _software(result, get_version())
    started = result.provenance.get("started_at")
    ended = result.provenance.get("ended_at") or datetime.now(UTC).isoformat()
    sizes = {k: result.metrics[k] for k in ("train_rows", "test_rows", "synth_rows") if k in result.metrics}
    properties = [_property(k, v) for k, v in {**result.parameters, **sizes}.items() if isinstance(v, (str, int, float, bool))]
    used = [{"@id": source}, {"@id": engine_iri}] + ([{"@id": iris.codebook(name)}] if codebook else [])
    activity: dict[str, Any] = {
        "@id": run,
        "@type": "prov:Activity",
        "rdfs:label": f"{label} ({result.backend})",
        "prov:wasAssociatedWith": {"@id": runtime},
        "prov:qualifiedAssociation": {"prov:agent": {"@id": runtime}, "prov:hadPlan": {"@id": plan}},
        "prov:used": used,
        "prov:endedAtTime": ended,
        "schema:additionalProperty": properties,
        **({"prov:wasInfluencedBy": {"@id": parent_activity}} if parent_activity else {}),
    }
    if started:
        activity |= {"prov:startedAtTime": started, "schema:duration": _duration(started, ended)}
    graph: list[dict[str, Any]] = [
        activity,
        {"@id": plan, "@type": ["prov:Plan", "schema:SoftwareApplication"], "schema:name": "semsynth", "schema:softwareVersion": get_version()},
        {"@id": runtime, "@type": ["prov:Agent", "prov:SoftwareAgent"], "schema:name": "CPython", "schema:softwareVersion": platform.python_version()},
        {
            "@id": engine_iri,
            "@type": ["prov:Entity", "schema:SoftwareApplication"],
            "schema:name": str(result.provenance.get("engine", result.backend)),
            **({"schema:softwareVersion": str(result.provenance["engine_version"])} if result.provenance.get("engine_version") else {}),
        },
        {"@id": source, "@type": "prov:Entity", **({"dct:identifier": str(dataset["provider_id"])} if dataset.get("provider_id") is not None else {})},
        {"@id": synthetic, "@type": "prov:Entity", "prov:wasGeneratedBy": {"@id": run}, "prov:wasDerivedFrom": {"@id": source}},
    ]
    for file_name in ["synthetic.csv", *written]:
        digest = _sha256(directory / file_name)
        graph.append(
            {
                "@id": iris.file(name, label, file_name),
                "@type": "prov:Entity",
                "dct:title": file_name,
                "prov:wasGeneratedBy": {"@id": run},
                "prov:generatedAtTime": ended,
                **({"dct:identifier": f"sha256:{digest}", "schema:sha256": digest} if digest else {}),
            }
        )
    graph += measurements(result.metrics, synthetic)
    return {"@context": CONTEXT, "@graph": graph}
