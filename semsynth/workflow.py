"""The operations behind the command line and the Flask app: find datasets, run reports, collect mapping targets.

Nothing here parses a command line or knows about makeprov; ``__main__`` wraps these functions as commands.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from .config import PipelineConfig
    from .models import ModelConfigBundle

LOGGER = logging.getLogger(__name__)

__all__ = [
    "collect_mapping_targets",
    "read_pipeline_config",
    "run_reports",
    "run_reports_for_targets",
    "search_datasets",
]


def search_datasets(
    provider: str,
    *,
    name_substr: str | None = None,
    area: str = "Health and Medicine",
    cat_min: int = 1,
    num_min: int = 1,
) -> pd.DataFrame:
    """Mixed-type datasets of a provider, one row per dataset.

    Args:
        provider: ``"openml"`` or ``"uciml"``.
        name_substr: Keep datasets whose name contains this text (case-insensitive).
        area: Topic area for UCI ML datasets; ignored for OpenML.
        cat_min: Minimum number of categorical columns.
        num_min: Minimum number of numeric columns.

    Raises:
        ValueError: For an unknown provider.
        ImportError: If the ``providers`` extra is missing.
    """

    key = provider.lower()
    if key == "openml":
        from .dataproviders.openml import list_openml

        return list_openml(name_substr=name_substr, cat_min=cat_min, num_min=num_min)
    if key == "uciml":
        from .dataproviders.uciml import list_uciml

        return list_uciml(area=area, name_substr=name_substr, cat_min=cat_min, num_min=num_min)
    raise ValueError("provider must be 'openml' or 'uciml'")


def read_pipeline_config(pipeline_configs: str = "") -> tuple[ModelConfigBundle, PipelineConfig]:
    """The model bundle and pipeline settings of a TOML snippet or ``@file.toml``.

    Settings of the ``[pipeline]`` table (or the top level) override the defaults, and flags that the bundle sets
    override both.
    """

    from .config import PipelineConfig
    from .models import load_model_configs, parse_toml_config

    config_data = parse_toml_config(pipeline_configs.strip() or None)
    bundle = load_model_configs(config_data=config_data)
    cfg = PipelineConfig()
    section = config_data.get("pipeline") if isinstance(config_data.get("pipeline"), dict) else config_data
    cfg.apply_mapping(section)
    for field_def in fields(cfg):
        value = getattr(bundle, field_def.name, None)
        if value is not None:
            setattr(cfg, field_def.name, value)
    return bundle, cfg


def run_reports(
    provider: str,
    *,
    datasets: list[str] | None = None,
    outdir: str | Path = "output/",
    pipeline_configs: str = "",
    area: str = "Health and Medicine",
    on_dataset: Callable[[Path], None] | None = None,
) -> list[str]:
    """Run the report pipeline on datasets of a provider; a dataset that fails is skipped.

    Args:
        provider: ``"openml"`` or ``"uciml"``.
        datasets: OpenML names or UCI ML ids (as strings); the provider's defaults when omitted.
        outdir: Directory that gets one subdirectory per dataset.
        pipeline_configs: TOML snippet or ``@file.toml`` with the model bundle and pipeline settings.
        area: Topic area for the default UCI ML datasets.
        on_dataset: Called with the output directory of each dataset before it is processed.

    Returns:
        One message per dataset that failed; empty when all succeeded.
    """

    from .datasets import load_dataset, specs_from_input
    from .runner import process_dataset

    outdir_path = Path(outdir)
    outdir_path.mkdir(parents=True, exist_ok=True)
    bundle, cfg = read_pipeline_config(pipeline_configs)
    failures: list[str] = []
    for spec in specs_from_input(provider=provider, datasets=datasets, area=area):
        LOGGER.info("Loading dataset %s", spec)
        try:
            payload = load_dataset(spec)
            label = payload.spec.name or str(payload.spec.id)
            if on_dataset is not None:
                on_dataset(outdir_path / str(label).replace("/", "_"))
            process_dataset(
                payload.spec,
                payload.frame,
                payload.color,
                outdir_path,
                model_bundle=bundle,
                pipeline_config=cfg,
            )
        except Exception as exc:
            failures.append(f"{spec.provider}:{spec.name or spec.id}: {exc}")
            LOGGER.exception("Skipped %s:%s due to error", spec.provider, spec.name)
    return failures


def collect_mapping_targets(mapping_root: str | Path) -> dict[str, list[str]]:
    """Provider to dataset ids for the ``*.metadata.json`` files under a mapping directory."""

    provider_to_ids: dict[str, list[str]] = {}
    for path in sorted(Path(mapping_root).glob("*.metadata.json")):
        stem = path.stem
        if "-" not in stem:
            continue
        provider, dataset_id = stem.split("-", maxsplit=1)
        provider_to_ids.setdefault(provider, []).append(dataset_id.removesuffix(".metadata"))
    if not provider_to_ids:
        LOGGER.info("No mapping metadata files found under %s", mapping_root)
    return provider_to_ids


def run_reports_for_targets(
    provider_to_ids: dict[str, list[str]],
    *,
    outdir: str | Path,
    pipeline_configs: str,
    on_dataset: Callable[[Path], None] | None = None,
) -> tuple[int, list[str]]:
    """Run the report pipeline for each dataset of a provider-to-ids mapping.

    Returns:
        The number of datasets that succeeded, and one message per dataset that failed.
    """

    successes = 0
    failures: list[str] = []
    for provider, dataset_ids in provider_to_ids.items():
        for dataset_id in sorted(set(dataset_ids)):
            problems = run_reports(
                provider,
                datasets=[dataset_id],
                outdir=outdir,
                pipeline_configs=pipeline_configs,
                on_dataset=on_dataset,
            )
            if problems:
                failures.extend(problems)
            else:
                successes += 1
    return successes, failures
