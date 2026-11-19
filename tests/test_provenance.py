"""The PROV-O of a run follows the makeprov 0.7 model, uses IRIs under one base, and carries scores as DQV measurements."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from semsynth.provenance import MEASURES, measurements

BASE = "https://bennokr.github.io/semsynth/output/"


def _graph(tmp_path: Path, **config: Any) -> tuple[dict[str, Any], Path]:
    pytest.importorskip("metasyn")
    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    rng = np.random.default_rng(0)
    age = rng.normal(55, 10, 400)
    frame = pd.DataFrame(
        {
            "age": age,
            "bmi": 22 + 0.1 * age + rng.normal(0, 2, 400),
            "sex": rng.choice(["f", "m"], 400),
        }
    )
    frame["dx"] = np.where(age > 55, "high", "low")
    spec = DatasetSpec("openml", name="Heart Disease (UCI)", target="dx", id=7)
    bundle = ModelConfigBundle(specs=[ModelSpec(name="Meta Syn", backend="metasyn", seed=3)])
    settings = {
        "generate_umap": False,
        "compute_privacy": True,
        "compute_joint": True,
        "bootstrap_reps": 100,
        **config,
    }
    process_dataset(
        spec,
        frame,
        frame["dx"],
        tmp_path,
        model_bundle=bundle,
        pipeline_config=PipelineConfig(**settings),
    )
    run = next((tmp_path / "heart-disease-uci" / "models").iterdir())
    return json.loads((run / "provenance.json").read_text()), run


def test_names_are_slugs_so_no_iri_has_a_space(tmp_path: Path) -> None:
    document, run = _graph(tmp_path)
    assert run.name == "meta-syn" and run.parent.parent.name == "heart-disease-uci"
    iris = [n["@id"] for n in document["@graph"]]
    assert not [i for i in iris if re.search(r"\s", i) or i.startswith("urn:")]
    assert f"{BASE}heart-disease-uci/models/meta-syn/#run" in iris


def test_a_run_is_a_plan_an_activity_and_hashed_entities(tmp_path: Path) -> None:
    document, run = _graph(tmp_path)
    nodes = {n["@id"]: n for n in document["@graph"]}
    activity = nodes[f"{BASE}heart-disease-uci/models/meta-syn/#run"]
    plan = nodes[activity["prov:qualifiedAssociation"]["prov:hadPlan"]["@id"]]
    assert "prov:Plan" in plan["@type"] and plan["schema:name"] == "semsynth"
    assert (
        nodes[activity["prov:qualifiedAssociation"]["prov:agent"]["@id"]]["schema:name"]
        == "CPython"
    )
    assert (
        activity["schema:duration"].startswith("PT")
        and activity["prov:startedAtTime"] < activity["prov:endedAtTime"]
    )
    properties = {
        p["schema:name"]: p["schema:value"] for p in activity["schema:additionalProperty"]
    }
    assert (
        properties["seed"] == 3
        and properties["test_size"] == 0.2
        and properties["train_rows"] > properties["test_rows"]
    )
    csv = nodes[f"{BASE}heart-disease-uci/models/meta-syn/synthetic.csv"]
    assert csv["schema:sha256"] == hashlib.sha256((run / "synthetic.csv").read_bytes()).hexdigest()
    assert csv["dct:identifier"] == f"sha256:{csv['schema:sha256']}" and csv[
        "prov:wasGeneratedBy"
    ] == {"@id": activity["@id"]}


def test_the_run_names_the_dataset_the_catalog_and_the_codebook_name(tmp_path: Path) -> None:
    document, run = _graph(tmp_path)
    nodes = {n["@id"]: n for n in document["@graph"]}
    source = f"{BASE}heart-disease-uci/"
    synthetic = nodes[f"{source}models/meta-syn/"]
    assert (
        synthetic["prov:wasDerivedFrom"] == {"@id": source}
        and nodes[source]["dct:identifier"] == "7"
    )
    used = {u["@id"] for u in nodes[f"{synthetic['@id']}#run"]["prov:used"]}
    assert source in used and f"{source}dataset.codebook.jsonld" in used
    codebook = json.loads((run.parent.parent / "dataset.codebook.jsonld").read_text())
    assert codebook["@id"] == source, "the codebook describes the same dataset IRI"


def test_bounds_are_measurements_of_derived_metrics_and_there_are_no_terms_of_ours(
    tmp_path: Path,
) -> None:
    document, _ = _graph(tmp_path)
    nodes = {n["@id"]: n for n in document["@graph"]}
    by_metric = {
        n["dqv:isMeasurementOf"]["@id"]: n
        for n in nodes.values()
        if n.get("@type") == "dqv:QualityMeasurement"
    }
    site = "https://bennokr.github.io/semsynth/"
    score = by_metric[f"{site}metric/privacy.dcr_below_holdout_p05"]
    low = by_metric[f"{site}metric/privacy.dcr_below_holdout_p05/lower95"]
    high = by_metric[f"{site}metric/privacy.dcr_below_holdout_p05/upper95"]
    assert low["dqv:value"] <= score["dqv:value"] <= high["dqv:value"]
    assert score["dqv:computedOn"] == {"@id": f"{BASE}heart-disease-uci/models/meta-syn/"}
    lower_metric = nodes[f"{site}metric/privacy.dcr_below_holdout_p05/lower95"]
    assert lower_metric["prov:wasDerivedFrom"] == {
        "@id": f"{site}metric/privacy.dcr_below_holdout_p05"
    }
    assert (
        lower_metric["dqv:inDimension"] == {"@id": f"{site}dimension/lower95"}
        and lower_metric["dct:hasVersion"]
    )
    assert nodes[f"{site}metric/privacy.dcr_below_holdout_p05"]["dqv:inDimension"] == {
        "@id": f"{site}dimension/privacy"
    }
    noise = by_metric[f"{site}metric/marginal.cont_ks_mean/noise-upper95"]["dqv:value"]
    assert noise >= by_metric[f"{site}metric/marginal.cont_ks_mean/noise-lower95"]["dqv:value"]
    assert 0 <= by_metric[f"{site}metric/joint.pairwise_tvd_mean/p-value"]["dqv:value"] <= 1
    text = json.dumps(document)
    assert "ss:" not in text and "urn:" not in text


def test_the_base_is_a_setting(tmp_path: Path) -> None:
    document, _ = _graph(tmp_path, iri_base="https://example.org/data")
    nodes = {n["@id"] for n in document["@graph"]}
    assert "https://example.org/data/heart-disease-uci/models/meta-syn/#run" in nodes


def test_only_present_scores_are_measured_and_nan_is_skipped() -> None:
    nodes = measurements(
        {"summary": {"disc_jsd_mean": 0.1, "cont_ks_mean": float("nan")}}, f"{BASE}d/models/m/"
    )
    kinds = [n["@type"] for n in nodes]
    assert kinds.count("dqv:QualityMeasurement") == 1 and "dqv:Metric" in kinds
    assert next(n for n in nodes if n["@type"] == "dqv:QualityMeasurement")["dqv:value"] == 0.1
    assert set(MEASURES) > {"marginal.disc_jsd_mean"}


def test_utility_and_cross_validation_are_measured_with_their_intervals() -> None:
    metrics = {
        "utility": {
            "scores": {"synthetic": 0.7, "real_sample": 0.8, "independent_marginals": 0.5},
            "recovered": 0.67,
            "intervals": {"synthetic": [0.6, 0.8], "recovered": [0.4, 0.9]},
        },
        "cv": {"scores": {"synthetic": {"disc_jsd_mean": {"mean": 0.1, "interval": [0.05, 0.15]}}}},
    }
    nodes = measurements(metrics, f"{BASE}d/models/m/")
    values = {n["@id"].rsplit("#measurement-", 1)[1]: n["dqv:value"] for n in nodes if n["@type"] == "dqv:QualityMeasurement"}
    assert values["utility-synthetic"] == 0.7 and values["utility-ceiling"] == 0.8 and values["utility-floor"] == 0.5
    assert values["utility-synthetic-lower95"] == 0.6 and values["utility-recovered-upper95"] == 0.9
    assert values["marginal-disc-jsd-mean-cv"] == 0.1 and values["marginal-disc-jsd-mean-cv-lower95"] == 0.05
    dimensions = {n["@id"].rsplit("/", 1)[1] for n in nodes if "dqv:Dimension" in n["@type"]}
    assert {"utility", "fidelity"} <= dimensions


def test_a_run_refers_to_the_command_that_started_it(tmp_path: Path) -> None:
    command = f"{BASE}__main__.py#mappings-job-7"
    document, _ = _graph(tmp_path, parent_activity=command)
    activity = next(n for n in document["@graph"] if n["@id"].endswith("/#run"))
    assert activity["prov:wasInfluencedBy"] == {"@id": command}
    other, _ = _graph(tmp_path / "other")
    assert "prov:wasInfluencedBy" not in next(n for n in other["@graph"] if n["@id"].endswith("/#run"))


def test_metrics_have_readable_labels_and_scores_have_six_digits() -> None:
    from semsynth.provenance import MEASURES, label

    assert label("marginal.disc_jsd_mean").startswith("Discrete columns")
    assert label("utility.synthetic_cv").endswith("mean over cross-validation folds")
    assert all(label(m) != m for m in MEASURES), "every metric has a label"
    nodes = measurements({"summary": {"disc_jsd_mean": 0.123456789012}}, f"{BASE}d/models/m/")
    assert next(n for n in nodes if n["@type"] == "dqv:QualityMeasurement")["dqv:value"] == 0.123457
