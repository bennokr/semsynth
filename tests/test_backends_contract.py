"""Signature compliance tests for backend modules."""

from __future__ import annotations

import importlib

import pytest

from semsynth.backends.base import ensure_backend_contract, ensure_synthesize_contract

_BACKEND_DEPENDENCIES: dict[str, str] = {
    "semsynth.backends.pybnesian": "pybnesian",
    "semsynth.backends.synthcity": "synthcity",
    "semsynth.backends.metasyn": "metasyn",
}


@pytest.mark.parametrize("module_name", sorted(_BACKEND_DEPENDENCIES))
def test_backend_contract(module_name: str) -> None:
    """Ensure each backend exposes a compliant ``run_experiment`` signature."""

    dependency = _BACKEND_DEPENDENCIES[module_name]
    pytest.importorskip(dependency)

    module = importlib.import_module(module_name)
    ensure_backend_contract(module)


@pytest.mark.parametrize("name", ["metasyn", "privbayes", "pybnesian", "synthcity"])
def test_synthesize_contract(name: str) -> None:
    """Every backend module imports without its engine and exposes ``synthesize``."""

    module = importlib.import_module(f"semsynth.backends.{name}")
    ensure_synthesize_contract(module)
