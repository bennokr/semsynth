"""k-fold splits and the intervals of cross-validated scores."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth.crossval import corrected_interval, fold_record, fold_splits, summarize_folds


def test_the_test_folds_are_disjoint_and_cover_every_row() -> None:
    frame = pd.DataFrame({"a": range(103), "y": ["u"] * 80 + ["v"] * 23})
    splits = fold_splits(frame, 5, seed=1, stratify=frame["y"])
    tests = [set(test["a"]) for _, test in splits]
    assert set().union(*tests) == set(range(103)) and sum(map(len, tests)) == 103
    assert all(len(train) + len(test) == 103 for train, test in splits)
    assert all(abs(int((test["y"] == "v").sum()) - 23 / 5) <= 1 for _, test in splits), (
        "classes are spread over the folds"
    )


def test_a_class_with_fewer_rows_than_folds_falls_back_to_plain_folds() -> None:
    frame = pd.DataFrame({"a": range(40), "y": ["u"] * 38 + ["v"] * 2})
    assert len(fold_splits(frame, 5, seed=0, stratify=frame["y"])) == 5
    with pytest.raises(ValueError):
        fold_splits(frame, 1, seed=0)


def test_the_interval_is_wider_than_the_naive_one_and_widens_with_the_test_share() -> None:
    values = [0.50, 0.55, 0.45, 0.52, 0.48]
    corrected = corrected_interval(values, n_train=80, n_test=20)
    naive_half = 2.776 * np.std(values, ddof=1) / np.sqrt(5)
    half = (corrected["interval"][1] - corrected["interval"][0]) / 2
    assert half > naive_half
    wider = corrected_interval(values, n_train=40, n_test=40)
    assert (
        wider["interval"][1] - wider["interval"][0]
        > corrected["interval"][1] - corrected["interval"][0]
    )
    assert corrected["mean"] == pytest.approx(0.5)


def test_one_value_has_a_mean_and_no_interval_and_none_is_skipped() -> None:
    assert corrected_interval([0.3], 10, 5) == {"n": 1, "mean": 0.3}
    assert corrected_interval([None, float("nan")], 10, 5) == {"n": 0}


def test_folds_are_summarized_by_table_and_metric() -> None:
    references = {
        "scores": {
            "synthetic": {"disc_jsd_mean": 0.1, "status": "ok"},
            "real_sample": {"disc_jsd_mean": 0.05},
        }
    }
    utility = {
        "status": "ok",
        "scores": {"synthetic": 0.7, "real_sample": 0.8, "prior": 0.5},
        "recovered": 0.6,
    }
    record = fold_record(references, utility)
    assert record["synthetic"] == {"disc_jsd_mean": 0.1, "utility": 0.7}
    summary = summarize_folds(
        [record, fold_record({"scores": {"synthetic": {"disc_jsd_mean": 0.2}}}, None)], 80, 20
    )
    assert summary["folds"] == 2 and summary["scores"]["synthetic"]["disc_jsd_mean"][
        "mean"
    ] == pytest.approx(0.15)
    assert summary["scores"]["synthetic"]["utility"]["n"] == 1


def test_an_interval_stays_inside_the_range_of_the_score() -> None:
    values = [0.0, 0.0, 0.02, 0.0, 0.03]
    assert corrected_interval(values, 80, 20, bounds=(0.0, 1.0))["interval"][0] == 0.0
    assert corrected_interval([0.9, 1.0, 0.95, 1.0, 0.99], 80, 20, bounds=(0.0, 1.0))["interval"][1] == 1.0


def test_the_share_recovered_comes_from_the_mean_scores_and_has_no_interval() -> None:
    def fold(synthetic: float, ceiling: float, floor: float) -> dict:
        return fold_record({"scores": {}}, {"status": "ok", "scores": {"synthetic": synthetic, "real_sample": ceiling, "independent_marginals": floor}})

    summary = summarize_folds([fold(0.7, 0.9, 0.5), fold(0.8, 0.8, 0.8), fold(0.6, 0.9, 0.5)], 80, 20)
    recovered = summary["scores"]["synthetic"]["utility_recovered"]
    assert recovered["mean"] == pytest.approx((0.7 - 0.6) / (0.867 - 0.6), rel=0.01) and "interval" not in recovered
