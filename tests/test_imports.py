"""Tests ensuring the package keeps imports lightweight."""

from __future__ import annotations

import builtins

import pytest


_HEAVY_ROOT_MODULES = frozenset(
    {
        "pandas",
        "umap",
        "synthcity",
        "metasyn",
        "pybnesian",
    }
)


@pytest.fixture()
def isolated_semsynth_import():
    """Provide a stable import context for lightweight import checks."""

    yield



def test_import_is_lightweight(monkeypatch, isolated_semsynth_import):
    """Ensure importing :mod:`semsynth` does not import heavy optional deps."""

    original_import = builtins.__import__
    attempted_heavy: list[str] = []

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root in _HEAVY_ROOT_MODULES:
            attempted_heavy.append(name)
            raise AssertionError(
                f"Attempted to import heavy module '{name}' during package import"
            )
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)

    import semsynth  # noqa: F401  # pylint: disable=import-outside-toplevel

    assert attempted_heavy == []
