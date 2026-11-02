"""Backend interface definitions for SemSynth.

Every backend module defines ``synthesize(df, codebook, *, rows, seed, **options) -> SynthesisResult``; that is the
contract that :func:`semsynth.synthesis.synthesize` dispatches to (see :func:`ensure_synthesize_contract`).

PyBNesian and SynthCity also keep their file-writing ``run_experiment`` (the second contract below, checked by
:func:`ensure_backend_contract`), because their ``synthesize`` is a wrapper around it and cannot be exercised
without the engines installed. MetaSyn keeps a thin ``run_experiment`` for compatibility. The second contract
can be retired once the two engines are called directly.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd
else:  # pragma: no cover - runtime does not require pandas
    pd = Any  # type: ignore


class Backend(Protocol):
    """Protocol describing the callable surface for backend implementations."""

    def run_experiment(
        self,
        df: pd.DataFrame,
        *,
        provider: str | None,
        dataset_name: str | None,
        provider_id: int | None,
        outdir: str,
        label: str,
        model_info: dict[str, Any] | None,
        rows: int | None,
        seed: int,
        test_size: float,
        codebook_jsonld: dict[str, Any] | None = None,
    ) -> Path:
        """Execute the backend for a dataset and return the run directory."""


class BackendModule(Protocol):
    """Protocol applied to backend modules."""

    def run_experiment(
        df: pd.DataFrame,
        *,
        provider: str | None,
        dataset_name: str | None,
        provider_id: int | None,
        outdir: str,
        label: str,
        model_info: dict[str, Any] | None,
        rows: int | None,
        seed: int,
        test_size: float,
        codebook_jsonld: dict[str, Any] | None = None,
    ) -> Path:
        """Execute the backend for a dataset and return the run directory."""


_REQUIRED_KEYWORD_PARAMS = (
    "provider",
    "dataset_name",
    "provider_id",
    "outdir",
    "label",
    "model_info",
    "rows",
    "seed",
    "test_size",
    "codebook_jsonld",
)


def ensure_backend_contract(module: ModuleType) -> None:
    """Validate that a backend module exposes a compliant ``run_experiment``."""

    run_experiment = getattr(module, "run_experiment", None)
    if not callable(run_experiment):
        raise RuntimeError(
            f"Backend module {module.__name__!r} must define a callable 'run_experiment'"
        )
    signature = inspect.signature(run_experiment)
    params = signature.parameters
    if not params:
        raise RuntimeError("run_experiment must accept a pandas DataFrame as the first argument")
    first = next(iter(params.values()))
    if first.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY):
        raise RuntimeError("run_experiment must accept the dataset as the first positional argument")
    for name in _REQUIRED_KEYWORD_PARAMS:
        if name not in params:
            raise RuntimeError(f"run_experiment missing required parameter '{name}'")
        if params[name].kind not in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise RuntimeError(f"Parameter '{name}' must be positional-or-keyword or keyword-only")


def ensure_synthesize_contract(module: ModuleType) -> None:
    """Validate that a backend module exposes ``synthesize(df, codebook, *, rows, seed, **options)``."""

    synthesize = getattr(module, "synthesize", None)
    if not callable(synthesize):
        raise RuntimeError(f"Backend module {module.__name__!r} must define a callable 'synthesize'")
    params = list(inspect.signature(synthesize).parameters.values())
    positional = [p.name for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    if positional[:2] != ["df", "codebook"]:
        raise RuntimeError("synthesize must take the table and the codebook as its first two parameters")
    keyword_only = {p.name for p in params if p.kind is p.KEYWORD_ONLY}
    missing = {"rows", "seed"} - keyword_only
    if missing:
        raise RuntimeError(f"synthesize is missing keyword-only parameters {sorted(missing)}")


__all__ = ["Backend", "BackendModule", "ensure_backend_contract", "ensure_synthesize_contract"]
