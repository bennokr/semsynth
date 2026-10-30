"""Unit tests for the distribution metrics."""

from __future__ import annotations

import pandas as pd

from semsynth.metrics import js_divergence_discrete, per_variable_distances


def test_discrete_codes_match_across_text_and_integers() -> None:
    """Text codes in the real data and integers read back from a CSV are the same categories."""

    real = pd.Series(["70", "80", "80", None], dtype="category")
    synth = pd.Series([70, 80, 80, pd.NA], dtype="Int64")
    assert js_divergence_discrete(real, synth) < 1e-3


def test_per_variable_distances_with_mixed_code_types() -> None:
    real = pd.DataFrame({"bp": pd.Series(["70", "90"], dtype="category"), "age": [1.0, 2.0]})
    synth = pd.DataFrame({"bp": pd.Series([70, 90], dtype="Int64"), "age": [1.5, 2.5]})
    distances = per_variable_distances(real, synth, ["bp"], ["age"])
    assert distances.set_index("variable").loc["bp", "JSD"] < 1e-3
