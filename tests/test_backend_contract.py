"""What every backend must do, and the plugin hook.

Every backend that is installed is fitted on a small table with categories, integers and decimals, and has to return the
same columns, the requested number of rows, and values of the right kind. The capabilities that a backend declares have to be
true. A backend whose engine is not installed is skipped, so this runs everywhere and covers what is there.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from semsynth import synthesis
from semsynth.result import SynthesisResult
from semsynth.synthesis import (
    BACKENDS,
    CAPABILITIES,
    Capabilities,
    available_backends,
    capabilities,
    load_backend,
    synthesize,
)

# The smallest settings that still fit; the contract is about the shape of the output, not its quality.
FAST: dict[str, dict[str, Any]] = {
    "chain": {},
    "dp_cgans": {"epochs": 2, "batch_size": 20},
    "metasyn": {},
    "mostlyai": {"max_epochs": 1, "max_training_time": 1, "value_protection": False},
    "privbayes": {"epsilon": 0, "k": 1},
    "pybnesian": {"type": "clg"},
    "synthcity": {"type": "ctgan", "n_iter": 2, "batch_size": 40},
}


@pytest.fixture(scope="module")
def table() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 120
    age = rng.integers(20, 70, n)
    return pd.DataFrame(
        {
            "group": rng.choice(["a", "b", "c"], n),
            "age": age,
            "score": 0.05 * age + rng.normal(0, 1, n),
            "flag": (age > 45).astype(int),
            "city": rng.choice(["Delft", "Utrecht", "Maastricht", "Leiden", "Breda"], n),
        }
    )


def _fit(name: str, frame: pd.DataFrame, rows: int = 60) -> SynthesisResult:
    try:
        return synthesize(frame, None, backend=name, rows=rows, seed=1, **FAST[name])
    except ImportError as exc:
        pytest.skip(f"the {name!r} backend is not installed: {exc}")


def test_every_builtin_backend_declares_capabilities_and_a_fast_setting() -> None:
    assert set(CAPABILITIES) == set(BACKENDS) == set(FAST)
    assert all(isinstance(value, Capabilities) for value in CAPABILITIES.values())
    assert set(BACKENDS) <= set(available_backends())


@pytest.mark.parametrize("name", BACKENDS)
def test_a_backend_returns_the_columns_rows_and_kinds_of_the_table(name: str, table: pd.DataFrame) -> None:
    result = _fit(name, table)
    synthetic = result.synthetic_data
    assert isinstance(result, SynthesisResult) and result.backend
    assert list(synthetic.columns) == list(table.columns) and len(synthetic) == 60
    assert "started_at" in result.provenance and "ended_at" in result.provenance
    for column in ("age", "score"):
        assert pd.api.types.is_numeric_dtype(synthetic[column]), column
    for column in ("group", "city"):
        assert set(synthetic[column].dropna().astype(str)) <= set(table[column]), "a category that the real table has"
    assert set(pd.to_numeric(synthetic["flag"], errors="coerce").dropna()) <= {0, 1}


@pytest.mark.parametrize("name", [name for name in BACKENDS if CAPABILITIES[name].nulls])
def test_a_backend_that_declares_nulls_learns_from_a_table_with_blanks(name: str, table: pd.DataFrame) -> None:
    blank = table.copy()
    blank.loc[blank.index[::9], "score"] = np.nan
    blank.loc[blank.index[::7], "group"] = None
    result = _fit(name, blank)
    assert list(result.synthetic_data.columns) == list(blank.columns) and len(result.synthetic_data) == 60


class _EntryPoint:
    """The part of an ``importlib.metadata.EntryPoint`` that the hook uses."""

    def __init__(self, name: str, target: Any) -> None:
        self.name, self.value, self._target = name, "tests:fake", target

    def load(self) -> Any:
        return self._target


def _fake_backend(**declared: Any) -> SimpleNamespace:
    def synthesize_(df: pd.DataFrame, codebook: Any = None, *, rows: int, seed: int, **options: Any) -> SynthesisResult:
        return SynthesisResult(synthetic_data=df.sample(rows, replace=True, random_state=seed).reset_index(drop=True), backend="fake")

    return SimpleNamespace(synthesize=synthesize_, **({"CAPABILITIES": declared} if declared else {}))


def test_a_plugin_is_found_by_its_entry_point_and_runs_through_synthesize(monkeypatch: pytest.MonkeyPatch, table: pd.DataFrame) -> None:
    monkeypatch.setattr(synthesis, "_plugins", lambda: {"fakegan": _EntryPoint("fakegan", _fake_backend(dp=True, nulls=True))})
    assert "fakegan" in available_backends()
    assert capabilities("fakegan") == Capabilities(nulls=True, dp=True)
    result = synthesize(table, None, backend="fakegan", rows=10, seed=2)
    assert len(result.synthetic_data) == 10 and "started_at" in result.provenance


def test_a_plugin_that_declares_nothing_is_assumed_to_do_nothing_in_particular(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(synthesis, "_plugins", lambda: {"plain": _EntryPoint("plain", _fake_backend())})
    assert capabilities("plain") == Capabilities()


def test_a_plugin_without_synthesize_and_an_unknown_name_are_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(synthesis, "_plugins", lambda: {"broken": _EntryPoint("broken", SimpleNamespace())})
    with pytest.raises(ValueError, match="no function 'synthesize'"):
        load_backend("broken")
    with pytest.raises(ValueError, match=r"Unknown backend 'nope'.*broken"):
        load_backend("nope")


def test_a_builtin_cannot_be_shadowed_by_a_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(synthesis, "_plugins", lambda: {"chain": _EntryPoint("chain", _fake_backend())})
    assert load_backend("chain").__name__ == "semsynth.backends.chain"


def test_a_name_with_a_hyphen_is_the_name_with_an_underscore() -> None:
    assert capabilities("dp-cgans") == CAPABILITIES["dp_cgans"]


def test_the_privacy_budget_of_dp_cgans_is_read_from_its_log() -> None:
    from semsynth.backends.dp_cgans import _budget

    assert _budget("x\ndifferential privacy with eps = 5.92 and delta = 2e-06.\n") == {
        "epsilon": 5.92,
        "delta": 2e-06,
        "mechanism": "DP-SGD, Renyi accounting (dp_cgans)",
    }
    assert _budget("no budget here") is None
