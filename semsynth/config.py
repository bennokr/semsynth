"""Configuration of the report pipeline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any

from makeprov.config import Config

__all__ = ["PipelineConfig", "UmapConfig"]


@dataclass
class UmapConfig(Config):
    """UMAP geometry parameters."""

    n_neighbors: int = 30
    min_dist: float = 0.1
    n_components: int = 2


@dataclass
class PipelineConfig(Config):
    """Configuration values controlling the reporting pipeline."""

    random_state: int = 42
    max_umap_sample: int = 1000
    fit_on_sample: int | None = 1000
    synthetic_sample: int = 1000
    test_size: float = 0.2
    umap: UmapConfig = field(default_factory=UmapConfig)
    generate_umap: bool = True
    compute_privacy: bool = False
    compute_downstream: bool = False
    overwrite_umap: bool = False
    enable_missingness_wrapping: bool = False
    missingness_random_state: int | None = None

    def apply_mapping(self, params: Mapping[str, Any]) -> PipelineConfig:
        """Apply a mapping of overrides onto this config, recursing into nested dataclasses."""

        if not isinstance(params, Mapping):
            return self

        def set_conf(dc: Any, mapping: Mapping[str, Any]) -> None:
            field_names = {f.name for f in fields(dc)}
            for key, value in mapping.items():
                if key not in field_names:
                    continue
                current = getattr(dc, key)
                if is_dataclass(current) and isinstance(value, Mapping):
                    set_conf(current, value)
                else:
                    setattr(dc, key, value)

        set_conf(self, params)
        return self
