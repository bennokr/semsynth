"""Every backend module has the same ``synthesize``."""

from __future__ import annotations

import importlib
import inspect
from types import ModuleType

import pytest


def ensure_synthesize_contract(module: ModuleType) -> None:
    """Validate that a backend module exposes ``synthesize(df, codebook, *, rows, seed, **options)``."""

    synthesize = getattr(module, "synthesize", None)
    assert callable(synthesize), f"{module.__name__} must define a callable 'synthesize'"
    params = list(inspect.signature(synthesize).parameters.values())
    positional = [p.name for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    assert positional[:2] == ["df", "codebook"], "synthesize takes the table and the codebook first"
    keyword_only = {p.name for p in params if p.kind is p.KEYWORD_ONLY}
    assert {"rows", "seed"} <= keyword_only, "synthesize takes rows and seed as keyword-only parameters"



@pytest.mark.parametrize("name", ["metasyn", "privbayes", "pybnesian", "synthcity"])
def test_synthesize_contract(name: str) -> None:
    """Every backend module imports without its engine and exposes ``synthesize``."""

    module = importlib.import_module(f"semsynth.backends.{name}")
    ensure_synthesize_contract(module)
