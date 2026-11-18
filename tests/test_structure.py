"""Declared missing codes, skip rules and subgroups applied to tables, including pandas NaN."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth.codebook import Codebook
from semsynth.structure import (
    Subgroup,
    applicability,
    check_rules,
    check_subgroups,
    enforce_applicability,
    membership,
    recode_declared_missing,
    structural_violations,
    subgroups_from,
)

CODEBOOK = Codebook(
    {
        "columns": [
            {"name": "age", "datatype": "integer"},
            {
                "name": "smoker",
                "datatype": "string",
                "values": [{"code": "yes"}, {"code": "no"}, {"code": "refused", "missing": True}],
            },
            {
                "name": "cigs",
                "datatype": "integer",
                "applies_when": "[smoker] == 'yes'",
                "missing_values": ["77", "99"],
            },
            {"name": "egfr", "datatype": "number", "missing_range": {"low": 9000, "high": 9999}},
        ]
    }
)
FRAME = pd.DataFrame(
    {
        "age": [30, 55, 82, 90, 41],
        "smoker": ["yes", "no", "yes", "refused", None],
        "cigs": [
            10.0,
            5.0,
            77.0,
            3.0,
            np.nan,
        ],  # 5.0 and 3.0 are answers to a question that does not apply
        "egfr": [88.0, 9999.0, 45.0, 9001.0, 70.0],
    }
)


def test_declared_codes_become_missing_whatever_their_type() -> None:
    recoded, counts = recode_declared_missing(FRAME, CODEBOOK)
    assert counts == {
        "smoker": 1,
        "cigs": 1,
        "egfr": 2,
    }  # 77.0 matches "77"; 9999 and 9001 are in the range
    assert recoded["cigs"].isna().sum() == 2 and recoded["egfr"].isna().sum() == 2
    assert FRAME["cigs"].iloc[2] == 77.0, "the input is not changed"


def test_a_refused_answer_does_not_decide_a_skip_rule() -> None:
    state = applicability(FRAME, CODEBOOK)
    # row 3 smoker "refused" -> blank in the rule -> unknown; row 4 is blank -> unknown
    assert list(state["cigs"]) == [True, False, True, pd.NA, pd.NA]


def test_violations_count_answers_where_the_question_does_not_apply() -> None:
    report = structural_violations(FRAME, CODEBOOK)
    assert report["columns"]["cigs"] == {"not_applicable": 1, "answered": 1}
    assert report["rate"] == 1.0
    fixed = enforce_applicability(FRAME, CODEBOOK)
    assert structural_violations(fixed, CODEBOOK)["columns"]["cigs"]["answered"] == 0
    assert fixed["cigs"].iloc[1] != fixed["cigs"].iloc[1]  # NaN


def test_subgroups_come_from_settings_and_nan_is_not_a_member() -> None:
    groups = subgroups_from(
        [
            {"name": "elderly", "condition": "[age] >= 80", "label": "Age 80+"},
            {"name": "low_egfr", "condition": "[egfr] < 60"},
        ]
    )
    assert groups == [
        Subgroup("elderly", "[age] >= 80", "Age 80+"),
        Subgroup("low_egfr", "[egfr] < 60"),
    ]
    recoded, _ = recode_declared_missing(FRAME, CODEBOOK)
    members = membership(recoded, groups)
    assert list(members["elderly"]) == [False, False, True, True, False]
    assert list(members["low_egfr"]) == [
        False,
        False,
        True,
        False,
        False,
    ]  # NaN egfr is unknown, not "< 60"


def test_a_misspelt_field_is_reported_not_silently_empty() -> None:
    problems = check_subgroups(
        [Subgroup("a", "[agee] >= 80"), Subgroup("b", "[age] >="), Subgroup("a", "[age] > 1")],
        ["age"],
    )
    assert problems == [
        "a: [agee] is not a column",
        "b: expected a field or a value, found 'the end'",
        "a: defined twice",
    ]
    assert not membership(FRAME, [Subgroup("a", "[agee] >= 80")])["a"].any()
    with pytest.raises(KeyError):
        subgroups_from([{"condition": "[age] > 1"}])


def test_the_pipeline_learns_across_skip_rules_and_enforces_them(tmp_path) -> None:  # type: ignore[no-untyped-def]
    pytest.importorskip("metasyn")
    import json

    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    rng = np.random.default_rng(0)
    n = 600
    smoker = rng.choice(["yes", "no"], n, p=[0.3, 0.7])
    frame = pd.DataFrame(
        {
            "age": rng.normal(55, 10, n),
            "smoker": smoker,
            "cigs": np.where(smoker == "yes", rng.poisson(12, n), np.nan),
        }
    )
    codebook = Codebook(
        {
            "columns": [
                {"name": "age"},
                {"name": "smoker"},
                {"name": "cigs", "applies_when": "[smoker] == 'yes'"},
            ]
        }
    )
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
    shares = {}
    for aware in (False, True):
        spec = DatasetSpec(
            "openml", name=f"aware{aware}", target="smoker", meta=codebook.to_jsonld()
        )
        config = PipelineConfig(
            generate_umap=False,
            structure_aware=aware,
            enable_missingness_wrapping=True,
            fit_on_sample=600,
        )
        process_dataset(
            spec, frame, frame["smoker"], tmp_path, model_bundle=bundle, pipeline_config=config
        )
        run = next((tmp_path / spec.name.lower() / "models").iterdir())
        synthetic = pd.read_csv(run / "synthetic.csv")
        shares[aware] = (synthetic["smoker"] == "yes").mean()
        if aware:
            assert synthetic.loc[synthetic.smoker != "yes", "cigs"].isna().all()
            structure = json.loads((run / "metrics.json").read_text())["structure"]
            assert structure["columns"]["cigs"]["not_applicable"] > 0
    assert shares[False] > 0.9 and abs(shares[True] - 0.3) < 0.1, (
        "complete-case learning sees only smokers"
    )


def test_a_skip_rule_with_a_misspelt_field_is_reported() -> None:
    book = Codebook(
        {
            "columns": [
                {"name": "smoker"},
                {"name": "cigs", "applies_when": "[smokr] == 'yes'"},
                {"name": "x", "applies_when": "[smoker] =="},
            ]
        }
    )
    assert check_rules(book, ["smoker", "cigs", "x"]) == [
        "cigs: [smokr] is not a column",
        "x: expected a field or a value, found 'the end'",
    ]
    assert check_rules(CODEBOOK, FRAME.columns) == []
