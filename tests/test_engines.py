"""The two engines that need their own packages: skipped when the engine is not installed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth import synthesize


def _table(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    age = rng.normal(55, 10, n).round()
    sex = rng.choice(["f", "m"], n)
    chol = 150 + 1.1 * age + (sex == "m") * 10 + rng.normal(0, 15, n)
    return pd.DataFrame({"age": age, "sex": sex, "chol": chol, "smoker": rng.choice(["no", "yes"], n)})


def test_pybnesian_draws_a_table_like_the_real_one_and_keeps_the_network() -> None:
    pytest.importorskip("pybnesian")

    result = synthesize(_table(), backend="pybnesian", rows=40, seed=1, type="clg")

    synthetic = result.synthetic_data
    assert list(synthetic.columns) == ["age", "sex", "chol", "smoker"]
    assert len(synthetic) == 40
    assert set(synthetic["sex"].astype(str)) <= {"f", "m"}
    assert synthetic["age"].dtype == "float64"
    assert hasattr(result.learned_model, "logl")
    assert {"model.pickle", "structure.graphml"} <= set(result.artifacts)
    assert result.parameters["type"] == "clg"
    assert result.provenance["engine"] == "pybnesian"


def test_pybnesian_roots_have_no_parents() -> None:
    pytest.importorskip("pybnesian")

    result = synthesize(_table(), backend="pybnesian", rows=10, seed=1, type="clg", roots=["age"])

    assert all(target != "age" for _source, target in result.learned_model.arcs())


def test_synthcity_draws_a_table_with_a_fast_generator() -> None:
    pytest.importorskip("synthcity")

    result = synthesize(_table(), backend="synthcity", rows=30, seed=1, type="bn")

    assert list(result.synthetic_data.columns) == ["age", "sex", "chol", "smoker"]
    assert len(result.synthetic_data) == 30
    assert result.parameters["generator"] == "bayesian_network"


def test_synthcity_needs_a_generator() -> None:
    pytest.importorskip("synthcity")

    with pytest.raises(ValueError, match="needs a generator"):
        synthesize(_table(), backend="synthcity")


def test_synthcity_neural_generator_takes_epochs_as_iterations() -> None:
    pytest.importorskip("synthcity")

    result = synthesize(_table(), backend="synthcity", rows=20, seed=1, type="ctgan", epochs=2, batch_size=40)

    assert len(result.synthetic_data) == 20
    assert result.parameters["params"]["n_iter"] == 2
    assert "epochs" not in result.parameters["params"]
