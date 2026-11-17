"""Joint fidelity and the reference tables: the scores move the right way on the two extremes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semsynth.baselines import compact_scores, evaluate_references, reference_tables
from semsynth.joint_fidelity import (
    classifier_two_sample,
    joint_fidelity,
    missingness_fidelity,
    pairwise_dependence,
)

KINDS = {"age": "numeric", "bmi": "numeric", "sex": "categorical", "dx": "categorical"}
FRAME = pd.DataFrame(
    {
        "variable": list(KINDS),
        "role": ["qi", "qi", "qi", "sensitive"],
        "type": list(KINDS.values()),
    }
)


def _real(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.normal(50, 12, n)
    bmi = 22 + 0.1 * age + rng.normal(0, 2, n)
    sex = rng.choice(["f", "m"], n)
    dx = np.where(age + 3 * (sex == "m") + rng.normal(0, 4, n) > 54, "high", "low")
    return pd.DataFrame({"age": age, "bmi": bmi, "sex": sex, "dx": dx})


def _independent(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({c: rng.permutation(frame[c].to_numpy()) for c in frame.columns})


def test_independent_columns_break_the_pairwise_structure() -> None:
    train, holdout = _real(800, 1), _real(400, 2)
    fresh = pairwise_dependence(holdout, _real(400, 3), {"age", "bmi"})
    broken = pairwise_dependence(holdout, _independent(train, 4)[:400], {"age", "bmi"})
    assert fresh["status"] == broken["status"] == "ok"
    assert broken["tvd_mean"] > fresh["tvd_mean"] + 0.03
    assert broken["worst_pairs"][0]["tvd"] == broken["tvd_max"]


def test_the_classifier_tells_independent_columns_apart_but_not_fresh_draws() -> None:
    train, holdout = _real(800, 1), _real(400, 2)
    fresh = classifier_two_sample(holdout, _real(400, 3), {"age", "bmi"})
    broken = classifier_two_sample(holdout, _independent(train, 4)[:400], {"age", "bmi"}, reps=50)
    assert fresh["auc"] < 0.62 < broken["auc"]
    low, high = broken["auc_interval"]
    assert low <= broken["auc"] <= high


def test_missingness_is_a_level_of_the_pairwise_test() -> None:
    real = _real(500, 5)
    real.loc[real.sex == "m", "bmi"] = np.nan  # bmi is missing exactly for men
    faithful = real.sample(frac=1, random_state=1).reset_index(drop=True)
    blind = faithful.copy()
    blind["bmi"] = blind["bmi"].sample(frac=1, random_state=2).to_numpy()  # same missing rate, wrong dependence
    numeric = {"age", "bmi"}
    assert pairwise_dependence(real, blind, numeric)["tvd_mean"] > pairwise_dependence(real, faithful, numeric)["tvd_mean"]


def test_missingness_fidelity_compares_rates_and_patterns() -> None:
    real = _real(400, 6)
    real.loc[:99, "bmi"] = np.nan
    real.loc[:49, "age"] = np.nan
    same = missingness_fidelity(real, real.sample(frac=1, random_state=1))
    none = missingness_fidelity(real, real.fillna(0))
    assert same["rate_gap_max"] == 0 and same["pattern_tvd"] == 0
    assert none["rate_gap_max"] == pytest.approx(0.25) and none["pattern_tvd"] == pytest.approx(0.25)
    assert none["largest_gaps"]["bmi"] == pytest.approx(0.25)


def test_few_rows_are_reported_as_not_applicable() -> None:
    small = _real(10, 7)
    assert classifier_two_sample(small, small, {"age"})["status"] == "not_applicable"
    assert joint_fidelity(small.iloc[:0], small, KINDS)["pairwise"]["status"] == "not_applicable"


def test_reference_tables_have_the_scale_the_scores_need() -> None:
    train = _real(300, 8)
    tables = reference_tables(train, 200, 0)
    assert set(tables) == {"real_sample", "independent_marginals"}
    assert all(len(t) == 200 and list(t.columns) == list(train.columns) for t in tables.values())
    assert tables["real_sample"].merge(train).shape[0] == 200  # every row is a training row


def test_references_bracket_a_generator() -> None:
    train, holdout = _real(800, 9), _real(300, 10)
    synthetic = _real(300, 11)  # a perfect generator: fresh draws from the same process
    result = evaluate_references(
        train, holdout, synthetic, disc_cols=["sex", "dx"], cont_cols=["age", "bmi"], privacy_frame=FRAME, reps=20
    )
    scores = result["scores"]
    assert result["protocol"]["holdout_rows"] == 300
    # privacy: a copy of the training rows is the worst case, the perfect generator looks like fresh real data
    assert scores["real_sample"]["exact_match_rate"] == 1.0 and scores["synthetic"]["exact_match_rate"] < 0.05
    assert scores["real_sample"]["dcr_below_holdout_p05"] > 0.9 > scores["synthetic"]["dcr_below_holdout_p05"]
    # joint fidelity: independent columns are the floor, the generator is near the ceiling
    assert scores["independent_marginals"]["pairwise_tvd_mean"] > scores["synthetic"]["pairwise_tvd_mean"]
    assert scores["independent_marginals"]["classifier_auc"] > scores["synthetic"]["classifier_auc"]
    json.dumps(result)


def test_compact_scores_use_the_missing_value_policy() -> None:
    train, holdout = _real(300, 12), _real(150, 13)
    table = _real(150, 14)
    table.loc[:60, "bmi"] = np.nan
    kwargs = {"disc_cols": ["sex", "dx"], "cont_cols": ["age", "bmi"], "privacy_frame": FRAME}
    category = compact_scores(train, holdout, table, missing="category", **kwargs)
    observed = compact_scores(train, holdout, table, missing="observed", **kwargs)
    assert observed["dcr_median"] < category["dcr_median"]  # leaving the missing column out can only shrink it


def test_the_pipeline_writes_joint_and_baseline_files(tmp_path: Path) -> None:
    pytest.importorskip("metasyn")
    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    frame = _real(400, 15)
    frame.loc[::7, "bmi"] = np.nan
    spec = DatasetSpec("openml", name="joint", target="dx")
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
    config = PipelineConfig(
        generate_umap=False, compute_privacy=True, compute_joint=True, compute_baselines=True,
        enable_missingness_wrapping=True, bootstrap_reps=10,
    )
    process_dataset(spec, frame, frame["dx"], tmp_path, model_bundle=bundle, pipeline_config=config)
    run = next((tmp_path / "joint" / "models").iterdir())
    joint = json.loads((run / "metrics.joint.json").read_text())
    assert joint["pairwise"]["status"] == "ok" and joint["missingness"]["status"] == "ok"
    baselines = json.loads((run / "metrics.baselines.json").read_text())
    assert set(baselines["scores"]) == {"synthetic", "real_sample", "independent_marginals"}
    assert "disc_jsd_mean" in json.loads((run / "metrics.json").read_text())["summary_null"]
    privacy = json.loads((run / "metrics.privacy.json").read_text())
    assert privacy["intervals"]["dcr_below_holdout_p05"][0] <= privacy["dcr_below_holdout_p05"]


def test_the_noise_floor_contains_a_fresh_draw_and_excludes_independent_columns() -> None:
    train, holdout = _real(800, 21), _real(300, 22)
    fresh = pairwise_dependence(holdout, _real(300, 23), {"age", "bmi"}, reps=60, seed=1)
    broken = pairwise_dependence(holdout, _independent(train, 24)[:300], {"age", "bmi"}, reps=60, seed=1)
    low, high = fresh["null"]["null_interval"]
    assert low <= fresh["tvd_mean"] <= high and fresh["null"]["p_value"] > 0.05
    assert broken["tvd_mean"] > broken["null"]["null_interval"][1] and broken["null"]["p_value"] < 0.05


def test_marginal_summaries_come_with_a_noise_floor() -> None:
    from semsynth.evaluate import holdout_metrics

    metrics = holdout_metrics(_real(300, 31), _real(300, 32), ["sex", "dx"], ["age", "bmi"], bootstrap_reps=40)
    null = metrics["summary_null"]
    assert set(null) == {"disc_jsd_mean", "cont_ks_mean", "cont_w1_mean"}
    assert null["cont_ks_mean"]["null_interval"][0] <= metrics["summary"]["cont_ks_mean"]
    assert holdout_metrics(_real(50, 1), _real(50, 2), ["sex"], ["age"])["summary"].get("cont_ks_mean") is not None
