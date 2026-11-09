from __future__ import annotations

import pathlib
from collections.abc import Iterable
from typing import Any

from .dataproviders._helpers import DatasetPayload
from .specs import DatasetSpec

__all__ = [
    "DatasetPayload",
    "DatasetSpec",
    "load_dataset",
    "specs_from_input",
]

def __getattr__(name: str) -> Any:
    """``list_openml`` and ``list_uciml`` stay importable from here; the providers load on first use."""

    if name == "list_openml":
        from .dataproviders.openml import list_openml

        return list_openml
    if name == "list_uciml":
        from .dataproviders.uciml import list_uciml

        return list_uciml
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Local cache directories for dataset payloads (separate from uciml metadata cache)
_DATA_CACHE_ROOT = pathlib.Path(".") / "downloads-cache"
_OPENML_CACHE_DIR = _DATA_CACHE_ROOT / "openml"
_UCIML_CACHE_DIR = _DATA_CACHE_ROOT / "uciml"


def _ensure_cache_dirs(openml_cache_dir: pathlib.Path, uciml_cache_dir: pathlib.Path) -> None:
    """Create cache directories lazily when dataset APIs are invoked."""

    openml_cache_dir.mkdir(parents=True, exist_ok=True)
    uciml_cache_dir.mkdir(parents=True, exist_ok=True)


def _as_path(path_like: pathlib.Path | str) -> pathlib.Path:
    """Coerce a string into a :class:`~pathlib.Path`."""
    return pathlib.Path(path_like)


def _default_specs(provider: str, area: str) -> list[DatasetSpec]:
    """The datasets that a provider offers when none are named."""

    if provider == "openml":
        from .dataproviders.openml import get_default_openml

        return get_default_openml()
    from .dataproviders.uciml import get_default_uciml

    return get_default_uciml(area=area)


def specs_from_input(
    provider: str,
    datasets: Iterable[str] | None = None,
    area: str = "Health and Medicine",
    *,
    openml_cache_dir: pathlib.Path = _OPENML_CACHE_DIR,
    uciml_cache_dir: pathlib.Path = _UCIML_CACHE_DIR,
) -> list[DatasetSpec]:
    """Dataset specifications for the names (OpenML) or numeric ids (UCI ML) given, or the provider's defaults."""

    _ensure_cache_dirs(_as_path(openml_cache_dir), _as_path(uciml_cache_dir))
    provider = provider.lower()
    if provider not in {"openml", "uciml"}:
        raise ValueError("provider must be 'openml' or 'uciml'")
    if not datasets:
        return _default_specs(provider, area)
    if provider == "openml":
        return [DatasetSpec("openml", name=d) for d in datasets]
    try:
        return [DatasetSpec("uciml", name=None, id=int(d)) for d in datasets]
    except ValueError as exc:
        raise ValueError("For uciml provider, datasets must be numeric IDs (as strings).") from exc


def load_dataset(
    spec: DatasetSpec,
    *,
    openml_cache_dir: pathlib.Path = pathlib.Path(str(_OPENML_CACHE_DIR)),
    uciml_cache_dir: pathlib.Path = pathlib.Path(str(_UCIML_CACHE_DIR)),
) -> DatasetPayload:
    openml_cache = _as_path(openml_cache_dir)
    uciml_cache = _as_path(uciml_cache_dir)
    _ensure_cache_dirs(openml_cache, uciml_cache)

    if spec.provider == "openml":
        if not spec.name:
            raise ValueError("OpenML dataset requires a name.")
        from .dataproviders.openml import load_openml_by_name

        return load_openml_by_name(spec.name, openml_cache)
    if spec.provider == "uciml":
        if spec.id is None:
            raise ValueError("uciml dataset requires an 'id'")
        from .dataproviders.uciml import load_uciml_by_id

        return load_uciml_by_id(spec.id, uciml_cache)
    raise ValueError(f"Unknown provider: {spec.provider}")
