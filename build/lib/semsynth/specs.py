"""Shared data structures for SemSynth dataset handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DatasetSpec:
    """Container describing how to locate and identify a dataset."""

    provider: str
    name: str | None = None
    id: int | None = None
    target: str | None = None
    meta: Any | None = None
