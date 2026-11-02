"""Evaluation functions: tables in, dictionaries out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from semsynth.codebook import Codebook
from semsynth.evaluate import (
    build_downstream_meta,
    downstream_scores,
    holdout_metrics,
    privacy_scores,
    split_train_test,
)


def test_split_is_deterministic_and_disjoint() -> None:
    frame = pd.DataFrame({"x": range(20)})

    train, test = split_train_test(frame, 0.25, 3)
    again, _ = split_train_test(frame, 0.25, 3)

    assert len(train) == 15 and len(test) == 5
    assert train.equals(again)
    assert set(train["x"]).isdisjoint(test["x"])
    assert list(train.index) == list(range(15))


def test_holdout_metrics_summarizes_each_column() -> None:
    rng = np.random.default_rng(0)
    real = pd.DataFrame({"g": rng.choice(["a", "b"], 200), "v": rng.normal(0, 1, 200)})
    synthetic = pd.DataFrame({"g": rng.choice(["a", "b"], 200), "v": rng.normal(0, 1, 200)})

    metrics = holdout_metrics(real, synthetic, ["g"], ["v"])

    assert {record["variable"] for record in metrics["per_variable"]} == {"g", "v"}
    assert metrics["summary"]["disc_jsd_mean"] < 0.2
    assert metrics["test_rows"] == 200 and metrics["discrete_cols"] == 1 and metrics["continuous_cols"] == 1


def test_privacy_scores_turns_a_dataclass_into_a_dict() -> None:
    real = pd.DataFrame({"value": [1.0, 2.0]})

    @dataclass
    class Summary:
        score: float

    seen: dict[str, Any] = {}

    def summarizer(_real: pd.DataFrame, _synth: pd.DataFrame, meta: pd.DataFrame) -> Summary:
        seen["meta"] = meta
        return Summary(score=0.5)

    scores = privacy_scores(real, real, {"value": "continuous"}, summarizer=summarizer, target="value")

    assert scores == {"score": 0.5}
    assert seen["meta"].set_index("variable").loc["value", "role"] == "target"


def test_downstream_scores_reports_the_sign_match_rate() -> None:
    real = pd.DataFrame({"value": [1.0, 2.0]})

    def compare(_real: pd.DataFrame, _synth: pd.DataFrame, metadata: Codebook) -> dict[str, Any]:
        assert metadata.kind("value") == "numeric"
        return {"formula": "y ~ x", "compare": pd.DataFrame({"sign_match": [True, False]})}

    scores = downstream_scores(real, real, {"value": "continuous"}, None, compare=compare)

    assert scores == {"formula": "y ~ x", "sign_match_rate": 0.5}


def test_build_downstream_meta_is_a_codebook() -> None:
    df = pd.DataFrame({"feature": ["a", "b", "a"], "target": [0, 1, 1]})
    target_series = df["target"].copy()
    target_series.attrs["prov:hadRole"] = "target"

    meta = build_downstream_meta(df, {"feature": "discrete", "target": "discrete"}, target_series)

    assert meta.roles == {"feature": "predictor", "target": "target"}
    assert meta.column("target")["level"] == "nominal"
    assert meta.codes("target") == ["0", "1"]
