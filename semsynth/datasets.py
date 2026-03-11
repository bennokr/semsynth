from __future__ import annotations

from typing import Iterable, List, Optional

import pathlib

from makeprov import InPath, OutPath, rule

from .dataproviders._helpers import DatasetPayload
from .dataproviders.openml import get_default_openml, list_openml, load_openml_by_name
from .dataproviders.uciml import get_default_uciml, list_uciml, load_uciml_by_id
from .specs import DatasetSpec

__all__ = [
    "DatasetSpec",
    "DatasetPayload",
    "specs_from_input",
    "load_dataset",
    "list_openml",
    "list_uciml",
]

# Local cache directories for dataset payloads (separate from uciml metadata cache)
_DATA_CACHE_ROOT = pathlib.Path(".") / "downloads-cache"
_OPENML_CACHE_DIR = _DATA_CACHE_ROOT / "openml"
_UCIML_CACHE_DIR = _DATA_CACHE_ROOT / "uciml"


def _ensure_cache_dirs(openml_cache_dir: pathlib.Path, uciml_cache_dir: pathlib.Path) -> None:
    """Create cache directories lazily when dataset APIs are invoked."""

    openml_cache_dir.mkdir(parents=True, exist_ok=True)
    uciml_cache_dir.mkdir(parents=True, exist_ok=True)


def _as_path(path_like: pathlib.Path | InPath | OutPath | str) -> pathlib.Path:
    """Coerce ``makeprov`` markers or strings into a :class:`~pathlib.Path`."""
    return pathlib.Path(path_like)


@rule(merge=True, phony=True)
def specs_from_input(
    provider: str,
    datasets: Optional[Iterable[str]] = None,
    area: str = "Health and Medicine",
    *,
    openml_cache_dir: OutPath = OutPath(str(_OPENML_CACHE_DIR)),
    uciml_cache_dir: OutPath = OutPath(str(_UCIML_CACHE_DIR)),
) -> List[DatasetSpec]:
    openml_cache = _as_path(openml_cache_dir)
    uciml_cache = _as_path(uciml_cache_dir)
    _ensure_cache_dirs(openml_cache, uciml_cache)
    provider = provider.lower()
    if provider not in {"openml", "uciml"}:
        raise ValueError("provider must be 'openml' or 'uciml'")
    if datasets:
        if provider == "openml":
            return [DatasetSpec("openml", name=d) for d in datasets]
        else:
            ids: List[DatasetSpec] = []
            for d in datasets:
                try:
                    ids.append(DatasetSpec("uciml", name=None, id=int(d)))
                except ValueError:
                    raise ValueError(
                        "For uciml provider, datasets must be numeric IDs (as strings)."
                    )
            return ids
    else:
        if provider == "openml":
            return get_default_openml()
        else:
            return get_default_uciml(area=area)


@rule(merge=True, phony=True)
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
        return load_openml_by_name(spec.name, openml_cache)
    elif spec.provider == "uciml":
        if spec.id is None:
            raise ValueError("uciml dataset requires an 'id'")
        return load_uciml_by_id(spec.id, uciml_cache)
    else:
        raise ValueError(f"Unknown provider: {spec.provider}")
