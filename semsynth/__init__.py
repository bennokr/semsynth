"""Toolkit to profile, describe and synthesize tabular datasets.

- One call, ``synthesize(df, codebook, backend=...)``, for MetaSyn, PrivBayes, PyBNesian and SynthCity.
- Uniform outputs: each model writes artifacts under dataset/models/<model-name>/.
- Provider-aware metadata and UMAP visuals.
- Generate static HTML reports
"""

from __future__ import annotations

from importlib import metadata as importlib_metadata

from semsynth.result import SynthesisResult

__all__ = ["SynthesisResult", "__version__", "get_version", "synthesize"]


def __getattr__(name: str) -> object:
    """Expose ``synthesize`` without importing the synthesis machinery at ``import semsynth``."""

    if name == "synthesize":
        from semsynth.synthesis import synthesize

        return synthesize
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_version() -> str:
    """Return the installed SemSynth version string."""

    try:
        return importlib_metadata.version("semsynth")
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover - fallback for dev installs
        return "0.0.0"


__version__ = get_version()
