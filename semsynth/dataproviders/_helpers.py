"""Shared helpers for dataset provider modules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import pandas as pd

from ..specs import DatasetSpec


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
    color: Optional[pd.Series] = None
    metadata: Optional[Mapping[str, Any]] = None


def load_cached_payload(paths: CachePaths) -> Optional[Tuple[pd.DataFrame, Dict[str, Any]]]:
    """Return cached dataframe and metadata when both files exist."""

    if not paths.data.exists():
        return None
    frame = pd.read_csv(paths.data).convert_dtypes()
    meta: Dict[str, Any] = {}
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
    target: Optional[str] = None,
    metadata: Optional[Mapping[str, object]] = None,
) -> Tuple[pd.DataFrame, Optional[str], Optional[pd.Series]]:
    """Return a cleaned dataframe plus detected target column and colour series.

    The helper removes trivial identifier columns, then inspects the provided
    ``target`` hint and metadata for SemMap-style ``prov:hadRole`` annotations to
    identify the target column. When a target column is found, the returned
    series is annotated with ``prov:hadRole = "target"`` for downstream
    consumers.
    """

    clean_df = df.copy()
    for column in list(clean_df.columns):
        if str(column).lower() in {"id", "index"}:
            clean_df = clean_df.drop(columns=[column])

    candidates = []

    def _append_candidate(name: Optional[str]) -> None:
        if isinstance(name, str) and name and name not in candidates:
            candidates.append(name)

    def _normalise_role(role: object) -> Optional[str]:
        if isinstance(role, str) and role:
            role_lower = role.strip().lower()
            if role_lower == "target":
                return role_lower
        return None

    def _extract_named_role(node: object) -> None:
        if isinstance(node, Mapping):
            role_value = node.get("prov:hadRole")
            role_items: Iterable[str]
            if isinstance(role_value, str):
                role_items = [role_value]
            elif isinstance(role_value, Iterable) and not isinstance(
                role_value, (str, bytes)
            ):
                role_items = [str(item) for item in role_value if isinstance(item, str)]
            else:
                role_items = []

            if any(_normalise_role(r) for r in role_items):
                possible_names = [
                    node.get("schema:name"),
                    node.get("name"),
                    node.get("column"),
                    node.get("column_name"),
                    node.get("field"),
                ]
                for possible in possible_names:
                    if isinstance(possible, str) and possible:
                        _append_candidate(possible)
                        break

            for value in node.values():
                _extract_named_role(value)
        elif isinstance(node, Iterable) and not isinstance(node, (str, bytes)):
            for value in node:
                _extract_named_role(value)

    _append_candidate(target)
    if metadata and isinstance(metadata, Mapping):
        _extract_named_role(metadata)

    detected_target: Optional[str] = None
    color_series: Optional[pd.Series] = None
    for candidate in candidates:
        if candidate in clean_df.columns:
            detected_target = candidate
            color_series = clean_df[candidate].copy()
            color_series.attrs["prov:hadRole"] = "target"
            clean_df[detected_target] = color_series
            break

    return clean_df, detected_target, color_series


__all__ = [
    "CachePaths",
    "DatasetPayload",
    "clean_dataset_frame",
    "load_cached_payload",
    "store_cached_payload",
]
