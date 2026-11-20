"""The sequential generator keeps the columns, their types and the relations between them."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth.synthesis import synthesize


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 600
    x = rng.normal(size=n)
    group = rng.choice(["a", "b"], n)
    return pd.DataFrame({"group": group, "x": x, "y": 2 * x + rng.normal(scale=0.3, size=n), "flag": (x > 0).astype(int)})


@pytest.mark.parametrize("learner", ["cart", "hgb", "mlp"])
def test_the_chain_draws_a_table_of_the_same_shape_and_keeps_a_relation(table: pd.DataFrame, learner: str) -> None:
    result = synthesize(table, None, backend="chain", rows=400, seed=1, learner=learner)
    synthetic = result.synthetic_data
    assert list(synthetic.columns) == list(table.columns) and len(synthetic) == 400
    assert set(synthetic["group"]) <= {"a", "b"} and set(synthetic["flag"]) <= {0, 1}
    assert np.corrcoef(synthetic["x"], synthetic["y"])[0, 1] > 0.7, "y was predicted from x"
    assert result.parameters["learner"] == learner and result.backend == "chain"


def test_an_unknown_learner_is_an_error(table: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="learner"):
        synthesize(table, None, backend="chain", learner="svm")


def test_the_mostlyai_backend_names_its_extra_when_the_engine_is_missing(table: pd.DataFrame) -> None:
    try:
        import mostlyai.engine  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match="mostlyai"):
            synthesize(table, None, backend="mostlyai", rows=10)
    else:
        pytest.skip("mostlyai-engine is installed")


def test_numbers_back_turns_a_protected_value_into_a_missing_one() -> None:
    from semsynth.utils import numbers_back as _numbers_back

    assert _numbers_back(pd.Series(["1", "2", "2"]), "int64").tolist() == [1, 2, 2]
    protected = _numbers_back(pd.Series(["1", "_RARE_", "2"]), "int64")
    assert protected.isna().tolist() == [False, True, False]
    assert _numbers_back(pd.Series(["a", "_RARE_"]), "object").tolist() == ["a", "_RARE_"]


def test_cart_draws_real_values_and_keeps_the_distribution_of_a_column(table: pd.DataFrame) -> None:
    synthetic = synthesize(table, None, backend="chain", rows=2000, seed=3).synthetic_data
    assert set(synthetic["x"]) <= set(table["x"]), "every value is a real value"
    assert abs(synthetic["group"].eq("a").mean() - table["group"].eq("a").mean()) < 0.06
    assert abs(synthetic["x"].mean() - table["x"].mean()) < 0.15
