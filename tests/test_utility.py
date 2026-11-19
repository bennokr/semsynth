"""Train-on-synthetic, test-on-real utility: it must separate a good table from the floor and report what it cannot do."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth.baselines import reference_tables
from semsynth.utility import tstr_utility

KINDS = {"x": "numeric", "z": "categorical", "noise": "numeric", "y": "categorical", "t": "numeric"}


def _draw(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x, z = rng.normal(size=n), rng.integers(0, 3, n)
    y = ((x + 0.5 * (z == 1) + rng.normal(scale=0.7, size=n)) > 0).astype(int).astype(str)
    return pd.DataFrame(
        {
            "x": x,
            "z": z.astype(str),
            "noise": rng.normal(size=n),
            "y": y,
            "t": 2 * x + rng.normal(size=n),
        }
    )


@pytest.fixture(scope="module")
def tables() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    train, holdout = _draw(500, 1), _draw(300, 2)
    return train, holdout, {"synthetic": _draw(300, 3), **reference_tables(train, 300, 1)}


def test_a_good_table_recovers_most_of_the_gain_over_the_floor(tables) -> None:
    train, holdout, refs = tables
    result = tstr_utility(train, holdout, refs, "y", KINDS, seed=0, reps=100)
    scores = result["scores"]
    assert (
        result["status"] == "ok"
        and result["metric"] == "auc"
        and result["task"] == "classification"
    )
    assert scores["independent_marginals"] < 0.65 < 0.75 < scores["synthetic"]
    assert scores["prior"] == 0.5
    assert result["recovered"] > 0.8
    low, high = result["intervals"]["synthetic"]
    assert low <= scores["synthetic"] <= high


def test_the_floor_is_below_the_ceiling_for_a_numeric_target(tables) -> None:
    train, holdout, refs = tables
    result = tstr_utility(train, holdout, refs, "t", KINDS, seed=0)
    assert result["metric"] == "r2"
    assert result["scores"]["independent_marginals"] < 0.2 < 0.5 < result["scores"]["real_sample"]
    assert result["scores"]["prior"] < 0.05


def test_the_share_recovered_is_left_out_when_there_is_nothing_to_recover() -> None:
    from semsynth.utility import _recovered

    assert _recovered(0.8, 0.9, 0.5) == pytest.approx(0.75)
    assert _recovered(0.55, 0.51, 0.50) is None


def test_no_target_or_too_few_rows_is_recorded_not_guessed(tables) -> None:
    train, holdout, refs = tables
    assert tstr_utility(train, holdout, refs, None, KINDS)["status"] == "not_applicable"
    assert tstr_utility(train.head(5), holdout, refs, "y", KINDS)["status"] == "not_applicable"
    one_class = {name: frame.assign(y="0") for name, frame in refs.items()}
    assert tstr_utility(train, holdout, one_class, "y", KINDS)["status"] == "not_applicable"


def test_the_tables_have_the_same_size(tables) -> None:
    from semsynth.utility import utility_tables

    train, _, refs = tables
    sized = utility_tables(train.head(120), refs["synthetic"], seed=0)
    assert {len(t) for t in sized.values()} == {120}
    assert set(sized) == {"synthetic", "real_sample", "independent_marginals"}
