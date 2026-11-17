"""The PROV-O of a run follows the makeprov 0.7 model and carries the scores as DQV measurements."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semsynth.provenance import MEASURES, measurements


def _graph(tmp_path: Path) -> tuple[dict, Path]:
    pytest.importorskip("metasyn")
    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    rng = np.random.default_rng(0)
    age = rng.normal(55, 10, 400)
    frame = pd.DataFrame({"age": age, "bmi": 22 + 0.1 * age + rng.normal(0, 2, 400), "sex": rng.choice(["f", "m"], 400)})
    frame["dx"] = np.where(age > 55, "high", "low")
    spec = DatasetSpec("openml", name="prov", target="dx", id=7)
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=3)])
    config = PipelineConfig(generate_umap=False, compute_privacy=True, compute_joint=True, bootstrap_reps=100)
    process_dataset(spec, frame, frame["dx"], tmp_path, model_bundle=bundle, pipeline_config=config)
    run = next((tmp_path / "prov" / "models").iterdir())
    return json.loads((run / "provenance.json").read_text()), run


def test_a_run_is_a_plan_an_activity_and_hashed_entities(tmp_path: Path) -> None:
    document, run = _graph(tmp_path)
    nodes = {n["@id"]: n for n in document["@graph"]}
    activity = next(n for n in nodes.values() if n["@type"] == "prov:Activity")
    plan = nodes[activity["prov:qualifiedAssociation"]["prov:hadPlan"]["@id"]]
    assert "prov:Plan" in plan["@type"] and plan["schema:name"] == "semsynth"
    assert nodes[activity["prov:qualifiedAssociation"]["prov:agent"]["@id"]]["schema:name"] == "CPython"
    assert activity["schema:duration"].startswith("PT") and activity["prov:startedAtTime"] < activity["prov:endedAtTime"]
    properties = {p["schema:name"]: p["schema:value"] for p in activity["schema:additionalProperty"]}
    assert properties["seed"] == 3 and properties["test_size"] == 0.2 and properties["train_rows"] > properties["test_rows"]
    csv = next(n for n in nodes.values() if n.get("dcterms:title") == "synthetic.csv")
    assert csv["schema:sha256"] == hashlib.sha256((run / "synthetic.csv").read_bytes()).hexdigest()
    assert csv["dcterms:identifier"] == f"sha256:{csv['schema:sha256']}"
    dataset = next(n for n in nodes.values() if "schema:Dataset" in n.get("@type", []))
    assert dataset["dcterms:identifier"] == "7"


def test_scores_are_dqv_measurements_with_their_uncertainty(tmp_path: Path) -> None:
    document, _ = _graph(tmp_path)
    nodes = document["@graph"]
    measured = {n["dqv:isMeasurementOf"]["@id"].rsplit(":", 1)[-1]: n for n in nodes if n["@type"] == "dqv:QualityMeasurement"}
    assert {"marginal.cont_ks_mean", "privacy.dcr_below_holdout_p05", "joint.classifier_auc", "joint.pairwise_tvd_mean"} <= set(measured)
    privacy = measured["privacy.dcr_below_holdout_p05"]
    assert privacy["ss:lowerBound"] <= privacy["dqv:value"] <= privacy["ss:upperBound"]
    assert measured["marginal.cont_ks_mean"]["ss:noiseUpper"] >= measured["marginal.cont_ks_mean"]["ss:noiseLower"]
    assert all(n["dcterms:hasVersion"] for n in nodes if n["@type"] == "dqv:Metric")
    assert measured["joint.classifier_auc"]["dqv:computedOn"]["@id"].endswith(":synthetic.csv")


def test_only_present_scores_are_measured_and_nan_is_skipped() -> None:
    nodes = measurements({"summary": {"disc_jsd_mean": 0.1, "cont_ks_mean": float("nan")}}, "urn:x", "urn:run")
    assert [n["@type"] for n in nodes] == ["dqv:Metric", "dqv:QualityMeasurement"]
    assert nodes[1]["dqv:value"] == 0.1 and set(MEASURES) > {"marginal.disc_jsd_mean"}
