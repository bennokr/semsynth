"""Command-line entry points for SemSynth."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

from makeprov import GLOBAL_CONFIG, OutPath, main, rule

from .app import run_app
from .catalog import build_catalog


__all__ = ["search", "report", "run_app", "build_catalog", "main"]

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from .models import ModelConfigBundle, ModelSpec
    from .specs import DatasetSpec



@rule(merge=True)
def search(
    provider: str,
    *,
    name_substr: Optional[str] = None,
    area: str = "Health and Medicine",
    cat_min: int = 1,
    num_min: int = 1,
    verbose: bool = False,
    output: OutPath = OutPath("output/search.tsv"),
) -> None:
    """Search mixed-type datasets on OpenML or the UCI ML Repository.

    Args:
        provider: Either ``"openml"`` or ``"uciml"``.
        name_substr: Optional substring to filter dataset names (case-insensitive).
        area: Topic area for UCI ML datasets. Ignored for OpenML.
        cat_min: Minimum number of categorical columns.
        num_min: Minimum number of numeric columns.
        verbose: Whether to enable informational logging during execution.
    """
    from .datasets import list_openml, list_uciml  # defer heavy imports

    if verbose:
        logging.root.setLevel(logging.INFO)

    provider_key = provider.lower()
    if provider_key == "openml":
        df = list_openml(name_substr=name_substr, cat_min=cat_min, num_min=num_min)
    elif provider_key == "uciml":
        df = list_uciml(
            area=area,
            name_substr=name_substr,
            cat_min=cat_min,
            num_min=num_min,
        )
    else:
        raise SystemExit("provider must be 'openml' or 'uciml'")
    output_text = df.to_csv(sep="\t", index=None)
    print(output_text)
    with output.open("w", encoding="utf-8") as handle:
        handle.write(output_text)


@rule(merge=True, phony=True)
def report(
    provider: str = "openml",
    *,
    datasets: List[str] | None = None,
    outdir: OutPath = OutPath("output/"),
    configs_yaml: str = "",
    area: str = "Health and Medicine",
    verbose: bool = False,
    generate_umap: bool = False,
    overwrite_umap: bool = False,
    compute_privacy: bool = False,
    compute_downstream: bool = False,
) -> None:
    """Run the report pipeline on a collection of datasets.

    Args:
        provider: Either ``"openml"`` or ``"uciml"``.
        datasets: Dataset identifiers. For OpenML, these are names; for UCI ML, they are
            numeric identifiers as strings. Defaults are used when omitted.
        outdir: Output directory for per-dataset reports.
        configs_yaml: Path to a YAML file defining synthetic data model configurations.
        area: Default topic area for UCI datasets.
        verbose: Whether to enable informational logging during execution.
        generate_umap: Whether to generate UMAP projections for datasets.
        overwrite_umap: Whether to regenerate synthetic UMAP plots when files exist.
        compute_privacy: Whether to compute privacy metrics for each model run.
        compute_downstream: Whether to compute downstream fidelity metrics.
    """
    from .datasets import DatasetSpec, load_dataset, specs_from_input
    from .models import ModelConfigBundle, load_model_configs
    from .pipeline import PipelineConfig, process_dataset
    from .utils import ensure_dir

    if verbose:
        logging.root.setLevel(logging.INFO)

    outdir_path = Path(outdir)
    ensure_dir(str(outdir_path))

    dataset_specs: List[DatasetSpec]
    dataset_specs = specs_from_input(provider=provider, datasets=datasets, area=area)

    bundle: ModelConfigBundle 
    bundle = load_model_configs(configs_yaml.strip() or None)

    cfg = PipelineConfig()
    cfg.generate_umap = generate_umap
    cfg.compute_privacy = compute_privacy
    cfg.compute_downstream = compute_downstream
    cfg.overwrite_umap = overwrite_umap

    for dataset_spec in dataset_specs:
        logging.info("Loading dataset %s", dataset_spec)
        try:
            payload = load_dataset(dataset_spec)
            resolved_spec = payload.spec
            dataset_label = resolved_spec.name or str(resolved_spec.id)
            dataset_outdir = outdir_path / str(dataset_label).replace("/", "_")
            GLOBAL_CONFIG.prov_dir = str(dataset_outdir / "prov")
            process_dataset(
                resolved_spec,
                payload.frame,
                payload.color,
                str(outdir_path),
                model_bundle=bundle,
                pipeline_config=cfg,
            )
        except Exception as exc:  # pragma: no cover - surfaced to CLI
            logging.exception(
                "Skipped %s:%s due to error", dataset_spec.provider, dataset_spec.name
            )
            raise SystemExit(str(exc))

if __name__ == "__main__":
    main(argparse_kwargs = dict(
        prog='python -m semsynth',
        description=__doc__), version=True)
