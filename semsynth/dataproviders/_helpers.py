"""Shared helpers for dataset provider modules."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..specs import DatasetSpec

PROVIDERS_HINT = "install the dataset providers with `pip install 'semsynth[providers]'`"


def import_provider(module: str) -> Any:
    """Import a library that only the dataset providers need; the error names the extra to install."""

    import importlib

    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ImportError(f"Loading datasets needs {module!r}; {PROVIDERS_HINT}.") from exc


@dataclass(slots=True)
class CachePaths:
    """Canonical cache locations for a dataset payload."""

    data: Path
    meta: Path

    def ensure(self) -> None:
        """Ensure parent directories exist before writing artifacts."""

        self.data.parent.mkdir(parents=True, exist_ok=True)
        self.meta.parent.mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class DatasetPayload:
    """Bundled dataset artefacts returned by provider loaders."""

    spec: DatasetSpec
    frame: pd.DataFrame
    color: pd.Series | None = None
    metadata: Mapping[str, Any] | None = None


def load_cached_payload(paths: CachePaths) -> tuple[pd.DataFrame, dict[str, Any]] | None:
    """Return cached dataframe and metadata when both files exist."""

    if not paths.data.exists():
        return None
    frame = pd.read_csv(paths.data).convert_dtypes()
    meta: dict[str, Any] = {}
    if paths.meta.exists():
        try:
            meta_text = paths.meta.read_text(encoding="utf-8")
            meta = json.loads(meta_text) if meta_text else {}
        except json.JSONDecodeError:
            meta = {}
    return frame, meta


def store_cached_payload(paths: CachePaths, frame: pd.DataFrame, meta: Mapping[str, Any]) -> None:
    """Persist dataframe and metadata to cache paths."""

    paths.ensure()
    frame.to_csv(paths.data, index=False, compression="infer")
    paths.meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def clean_dataset_frame(
    df: pd.DataFrame,
    *,
    target: str | None = None,
) -> tuple[pd.DataFrame, str | None, pd.Series | None]:
    """Return a cleaned dataframe, the target column if the table has it, and that column as the colour series.

    The helper removes trivial identifier columns (``id`` and ``index``).
    """

    clean_df = df.copy()
    for column in list(clean_df.columns):
        if str(column).lower() in {"id", "index"}:
            clean_df = clean_df.drop(columns=[column])
    if isinstance(target, str) and target in clean_df.columns:
        return clean_df, target, clean_df[target].copy()
    return clean_df, None, None


__all__ = [
    "CachePaths",
    "DatasetPayload",
    "clean_dataset_frame",
    "load_cached_payload",
    "store_cached_payload",
]
