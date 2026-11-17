"""Gower distance with the three missing-value policies, checked against values worked out by hand."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth.distance import GowerIndex, resolve_policies
from semsynth.uncertainty import bootstrap_interval, mean_and_interval

NAN = np.nan
REFERENCE = pd.DataFrame({"x": [0.0, 10.0, NAN], "c": ["a", "b", "a"]})


def _distances(query: tuple[float, object], policy: str | dict[str, str]) -> list[float]:
    queries = pd.DataFrame({"x": [query[0]], "c": [query[1]]})
    return [round(float(v), 6) for v in GowerIndex(REFERENCE, missing=policy).matrix(queries)[0]]


def test_complete_rows_are_plain_gower() -> None:
    # |5 - 0| / 10 = 0.5 on x, 0 on c; |5 - 10| / 10 = 0.5 and 1 on c.
    assert _distances((5.0, "a"), "category")[:2] == [0.25, 0.75]


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("category", [0.5, 1.0, 0.0]),  # x: missing vs 0 -> 1; missing vs missing -> 0
        ("observed", [0.0, 1.0, 0.0]),  # x is left out whenever either side is missing
        ("asymmetric", [0.5, 1.0, 0.0]),  # missing vs missing is left out of the count, not counted as agreement
    ],
)
def test_a_missing_number_by_policy(policy: str, expected: list[float]) -> None:
    got = _distances((NAN, "a"), policy)
    assert got[0] == expected[0]  # reference (0, "a")
    assert got[2] == expected[2]  # reference (missing, "a")


def test_shared_absence_agrees_only_under_category() -> None:
    # The category differs ("b" vs "a"); x is missing on both sides for the third reference row.
    assert _distances((NAN, "b"), "category")[2] == 0.5
    assert _distances((NAN, "b"), "asymmetric")[2] == 1.0
    assert _distances((NAN, "b"), "observed")[2] == 1.0


def test_one_sided_absence_is_a_difference_unless_observed_only() -> None:
    assert _distances((NAN, "a"), "category")[0] == 0.5
    assert _distances((NAN, "a"), "asymmetric")[0] == 0.5
    assert _distances((NAN, "a"), "observed")[0] == 0.0


def test_nothing_comparable_is_maximally_far() -> None:
    assert _distances((NAN, NAN), "observed") == [1.0, 1.0, 1.0]


def test_a_level_missing_from_the_reference_differs_from_everything() -> None:
    assert _distances((0.0, "never seen"), "category")[0] == 0.5


def test_policies_can_differ_by_column() -> None:
    mixed = {"*": "category", "x": "observed"}
    assert _distances((NAN, "a"), mixed)[0] == 0.0
    assert resolve_policies(["x", "c"], mixed) == {"x": "observed", "c": "category"}
    with pytest.raises(ValueError, match="Unknown missing-value policy"):
        resolve_policies(["x"], "nonsense")


def test_nearest_is_the_row_minimum_and_a_copy_is_at_zero() -> None:
    frame = pd.DataFrame({"x": np.random.default_rng(0).normal(size=50), "c": list("ab") * 25})
    index = GowerIndex(frame)
    assert np.allclose(index.nearest(frame), 0.0)
    shifted = frame.assign(x=frame.x + 5)
    assert (index.nearest(shifted) > 0).all()


def test_a_large_reference_is_subsampled_once() -> None:
    frame = pd.DataFrame({"x": np.arange(100.0)})
    index = GowerIndex(frame, max_reference=10)
    assert index.n_reference == 10


def test_bootstrap_interval_covers_the_statistic_and_is_empty_without_reps() -> None:
    values = np.random.default_rng(1).normal(5, 1, 400)
    low, high = bootstrap_interval(np.mean, values, reps=300, seed=2)
    assert low < values.mean() < high and high - low < 0.5
    assert np.isnan(bootstrap_interval(np.mean, values, reps=0)).all()


def test_mean_and_interval_over_seeds() -> None:
    result = mean_and_interval([0.1, 0.2, 0.3])
    assert result["n"] == 3 and result["lower"] < 0.2 < result["upper"]
    assert np.isnan(mean_and_interval([0.5])["lower"])
