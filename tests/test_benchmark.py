"""The injected-truth benchmark: the injection does what it says, and the pipeline's recovery is measured against it."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from semsynth.benchmark import Mechanism, inject, recovery_scores, run_injected_benchmark
from semsynth.structure import recode_declared_missing, structural_violations


def _complete(n: int = 1500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.normal(55, 12, n)
    smoker = rng.choice(["yes", "no"], n, p=[0.3, 0.7])
    return pd.DataFrame(
        {
            "age": age,
            "sex": rng.choice(["f", "m"], n),
            "bmi": 24 + 0.05 * (age - 55) + rng.normal(0, 3, n),
            "chol": 180 + 0.8 * age + rng.normal(0, 20, n),
            "sbp": 110 + 0.5 * age + rng.normal(0, 10, n),
            "smoker": smoker,
            "cigs": rng.poisson(12, n).astype(float),
        }
    )


MECHANISMS = [
    Mechanism("chol", "mar", 0.3, driver="age", strength=2.5),
    Mechanism("bmi", "mnar", 0.25, strength=2.5),
    Mechanism("cigs", "structural", rule="[smoker] == 'yes'"),
    Mechanism("sbp", "coded", 0.05),
]


def test_each_mechanism_hits_its_rate_and_depends_on_what_it_should() -> None:
    injection = inject(_complete(4000), MECHANISMS, seed=3)
    by_column = {t["column"]: t for t in injection.truth}
    assert by_column["chol"]["realized_rate"] == pytest.approx(0.3, abs=0.03)
    assert by_column["bmi"]["realized_rate"] == pytest.approx(0.25, abs=0.03)
    complete = injection.complete
    older = complete.age > complete.age.median()
    chol_missing = injection.cells["chol"]
    assert chol_missing[older].mean() > chol_missing[~older].mean() + 0.2  # MAR: more missing where age is high
    bmi_missing = injection.cells["bmi"]
    assert bmi_missing[complete.bmi > complete.bmi.median()].mean() > bmi_missing[complete.bmi <= complete.bmi.median()].mean() + 0.2
    structural = injection.frame["cigs"].isna()
    assert structural[injection.frame.smoker == "no"].all() and not structural[injection.frame.smoker == "yes"].any()


def test_the_codebook_declares_what_a_person_could_declare_and_the_codes_are_recoverable() -> None:
    injection = inject(_complete(), MECHANISMS, seed=1)
    assert injection.codebook.column("cigs")["applies_when"] == "[smoker] == 'yes'"
    assert injection.codebook.column("sbp")["missing_values"] == ["77", "99"]
    assert injection.frame["sbp"].isin([77.0, 99.0]).sum() == injection.cells["sbp"].sum() > 0
    recoded, counts = recode_declared_missing(injection.frame, injection.codebook)
    assert counts == {"sbp": int(injection.cells["sbp"].sum())}, "every injected code, and nothing else, is recovered"
    assert recoded["sbp"].isna().sum() == counts["sbp"]
    assert structural_violations(injection.frame, injection.codebook)["rate"] == 0.0


def test_censoring_substitutes_the_limit_and_flags_it() -> None:
    injection = inject(_complete(), [Mechanism("bmi", "censored", 0.2)], seed=1)
    item = injection.truth[0]
    flagged = injection.frame["bmi_below_lod"] == 1
    assert flagged.mean() == pytest.approx(0.2, abs=0.01)
    assert (injection.frame.loc[flagged, "bmi"] == item["limit"] / math.sqrt(2)).all()
    assert (injection.complete.loc[flagged, "bmi"] < item["limit"]).all()


def test_bad_input_is_refused() -> None:
    with pytest.raises(ValueError, match="not a column"):
        inject(_complete(), [Mechanism("nope", "mcar")])
    with pytest.raises(ValueError, match="unknown mechanism"):
        inject(_complete(), [Mechanism("age", "mnaar")])
    with pytest.raises(ValueError, match="needs a driver"):
        inject(_complete(), [Mechanism("age", "mar")])


def test_recovery_scores_a_perfect_copy_of_the_truth_and_a_blind_one() -> None:
    injection = inject(_complete(), MECHANISMS, seed=2)
    perfect = recovery_scores(injection, injection.complete, injection.frame)
    assert perfect["summary"]["rate_gap_mean"] == pytest.approx(0.0)
    assert perfect["summary"]["gradient_gap_mean"] == pytest.approx(0.0, abs=1e-9)
    blind = injection.frame.copy()
    rng = np.random.default_rng(0)
    for column in ("chol", "bmi"):  # same rates, no dependence on anything
        blind[column] = injection.complete[column].mask(rng.random(len(blind)) < injection.cells[column].mean())
    scores = recovery_scores(injection, injection.complete, blind)
    gaps = {m["column"]: m["gradient_gap"] for m in scores["mechanisms"] if "gradient_gap" in m}
    assert gaps["chol"] > 0.4 and gaps["bmi"] > 0.4 and scores["summary"]["rate_gap_mean"] < 0.05


def test_the_pipeline_recovers_mar_but_not_mnar_and_structure_aware_learning_keeps_the_rows() -> None:
    pytest.importorskip("metasyn")
    out = run_injected_benchmark(_complete(), MECHANISMS, seed=1)
    learned, aware = out["learned"], out["structure_aware"]
    assert list(out["recoded_codes"]) == ["sbp"]
    assert learned["status"] == aware["status"] == "ok"
    # complete-case learning keeps only smokers without a missing lab value; filling inapplicable cells keeps far more
    assert aware["complete_share"] > 2 * learned["complete_share"]
    assert aware["fidelity_to_truth"]["disc_jsd_mean"] < learned["fidelity_to_truth"]["disc_jsd_mean"] / 3
    assert aware["summary"]["structural_violation_rate"] == 0.0
    by_column = {m["column"]: m for m in aware["mechanisms"]}
    assert by_column["chol"]["gradient_gap"] < 0.15, "a MAR mechanism on an observed driver is recovered"
    # Known limit, not a goal: nothing observed gives the own-value dependence away, so this stays unrecovered.
    assert by_column["bmi"]["gradient_gap"] > 0.3
