"""Per-subgroup scores: a leak confined to one group shows in that group, and small groups are not scored."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semsynth.structure import Subgroup
from semsynth.subgroups import subgroup_scores

FRAME = pd.DataFrame(
    {"variable": ["age", "bmi", "sex"], "role": ["qi", "qi", "qi"], "type": ["numeric", "numeric", "categorical"]}
)


def _real(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.uniform(20, 95, n)
    return pd.DataFrame({"age": age, "bmi": 22 + 0.05 * age + rng.normal(0, 2, n), "sex": rng.choice(["f", "m"], n)})


def test_a_leak_confined_to_one_group_shows_in_that_group() -> None:
    train, holdout, synth = _real(1500, 1), _real(500, 2), _real(1000, 3)
    old = train[train.age >= 80].sample(60, random_state=0)  # copies of real people over 80
    synth = pd.concat([synth[synth.age < 80], old], ignore_index=True)
    groups = [Subgroup("elderly", "[age] >= 80"), Subgroup("female", "[sex] == 'f'"), Subgroup("tiny", "[age] >= 94.9")]
    result = subgroup_scores(
        train, holdout, synth, groups, privacy_frame=FRAME, disc_cols=["sex"], cont_cols=["age", "bmi"], reps=20
    )
    elderly, female = result["groups"]["elderly"], result["groups"]["female"]
    assert elderly["status"] == "ok" and elderly["exact_match_rate"] > 0.5 > female["exact_match_rate"]
    assert elderly["gap"]["exact_match_rate"] > 0.4 and abs(female["gap"]["exact_match_rate"]) < 0.1
    assert result["worst"]["exact_match_rate"]["group"] == "elderly"
    assert result["groups"]["tiny"]["status"] == "too_small" and "exact_match_rate" not in result["groups"]["tiny"]
    assert result["groups"]["elderly"]["rows"]["holdout"] >= 30
    json.dumps(result)


def test_the_pipeline_scores_subgroups_from_the_codebook_and_the_settings(tmp_path: Path) -> None:
    pytest.importorskip("metasyn")
    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    frame = _real(600, 4)
    frame["dx"] = np.where(frame.age > 60, "high", "low")
    spec = DatasetSpec("openml", name="sg", target="dx")
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
    config = PipelineConfig(
        generate_umap=False,
        compute_subgroups=True,
        subgroups=[{"name": "older", "condition": "[age] >= 65", "label": "65+"}, {"name": "typo", "condition": "[agee] > 1"}],
        subgroup_min_size=20,
        bootstrap_reps=10,
    )
    process_dataset(spec, frame, frame["dx"], tmp_path, model_bundle=bundle, pipeline_config=config)
    run = next((tmp_path / "sg" / "models").iterdir())
    failed = json.loads((run / "metrics.subgroups.json").read_text())
    assert failed["status"] == "failed" and "[agee] is not a column" in failed["reason"]

    config.subgroups = config.subgroups[:1]
    process_dataset(spec, frame, frame["dx"], tmp_path, model_bundle=bundle, pipeline_config=config)
    scores = json.loads((run / "metrics.subgroups.json").read_text())
    assert scores["groups"]["older"]["status"] == "ok" and scores["groups"]["older"]["label"] == "65+"
