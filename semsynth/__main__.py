"""Command-line entry points for SemSynth."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import fields
from pathlib import Path
from typing import TYPE_CHECKING

from makeprov import OutPath, main, rule
from makeprov.config import ProvenanceConfig

from . import downstream_fidelity  # noqa: F401 - register build rules
from .app import run_app
from .catalog import build_catalog

__all__ = [
    "build_catalog",
    "create_mapping",
    "main",
    "mappings",
    "report",
    "run_app",
    "search",
]

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from .models import ModelConfigBundle
    from .specs import DatasetSpec



@rule(merge=True)
def search(
    provider: str,
    *,
    name_substr: str | None = None,
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
    datasets: list[str] | None = None,
    outdir: OutPath = OutPath("output/"),
    pipeline_configs: str = "",
    area: str = "Health and Medicine",
    verbose: bool = False,
) -> None:
    """Run the report pipeline on a collection of datasets.

    Args:
        provider: Either ``"openml"`` or ``"uciml"``.
        datasets: Dataset identifiers. For OpenML, these are names; for UCI ML, they are
            numeric identifiers as strings. Defaults are used when omitted.
        outdir: Output directory for per-dataset reports.
        pipeline_configs: Path to a TOML file (or inline TOML snippet) defining model and pipeline configurations.
        area: Default topic area for UCI datasets.
        verbose: Whether to enable informational logging during execution.
    """
    from .datasets import load_dataset, specs_from_input
    from .models import load_model_configs, parse_toml_config
    from .pipeline import PipelineConfig, process_dataset
    from .utils import ensure_dir

    if verbose:
        logging.root.setLevel(logging.INFO)

    outdir_path = Path(outdir)
    ensure_dir(str(outdir_path))

    dataset_specs: list[DatasetSpec]
    dataset_specs = specs_from_input(provider=provider, datasets=datasets, area=area)

    config_text = pipeline_configs.strip()
    config_data = parse_toml_config(config_text or None)
    bundle: ModelConfigBundle = load_model_configs(config_data=config_data)

    cfg = PipelineConfig()
    if isinstance(config_data, dict):
        section = config_data.get("pipeline") if isinstance(config_data.get("pipeline"), dict) else config_data
        if isinstance(section, dict):
            cfg.apply_mapping(section)
    for field_def in fields(cfg):
        if hasattr(bundle, field_def.name):
            value = getattr(bundle, field_def.name)
            if value is not None:
                setattr(cfg, field_def.name, value)

    failures: list[str] = []
    for dataset_spec in dataset_specs:
        logging.info("Loading dataset %s", dataset_spec)
        try:
            payload = load_dataset(dataset_spec)
            resolved_spec = payload.spec
            dataset_label = resolved_spec.name or str(resolved_spec.id)
            dataset_outdir = outdir_path / str(dataset_label).replace("/", "_")
            ProvenanceConfig.get().prov_dir = str(dataset_outdir / "prov")
            process_dataset(
                resolved_spec,
                payload.frame,
                payload.color,
                str(outdir_path),
                model_bundle=bundle,
                pipeline_config=cfg,
            )
        except Exception as exc:  # pragma: no cover - surfaced to CLI
            failures.append(f"{dataset_spec.provider}:{dataset_spec.name or dataset_spec.id}: {exc}")
            logging.exception(
                "Skipped %s:%s due to error", dataset_spec.provider, dataset_spec.name
            )
    if failures:
        raise SystemExit("; ".join(failures))


def _dataset_slug(spec: DatasetSpec, label: str) -> str:
    """The file stem of a dataset's mappings: provider and id, or provider and the slugged name."""

    tail = str(spec.id) if spec.id is not None else re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return "-".join(part for part in (spec.provider, tail) if part)


def _override_file(directory: Path | None, spec: DatasetSpec, slug: str) -> Path | None:
    """The manual override file of a dataset in ``directory``, if there is one."""

    if directory is None:
        return None
    names = [f"{slug}.json"]
    if spec.id is not None:
        names.append(f"{spec.provider}-{spec.id}.json")
    return next((path for name in names if (path := directory / name).exists()), None)


@rule(merge=True, phony=True)
def create_mapping(
    provider: str,
    *,
    datasets: list[str] | None = None,
    codes_tsv: str = "map_columns/codes.tsv",
    manual_overrides_dir: str | None = None,
    systems: Sequence[str] = ("WD",),
    method: str = "lexical",
    datasette_url: str = "http://127.0.0.1:8001/terminology",
    datasette_table: str = "codes",
    datasette_limit: int = 15,
    lexical_threshold: float = 0.35,
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    candidate_pool_multiplier: int = 5,
    cosine_threshold: float = 0.0,
    llm_model: str = "gpt-4.1-mini",
    llm_extra_prompt: str = "",
    llm_subject_prefix: str = "dataset",
    confidence_threshold: float = 0.0,
    min_score: float = 0.45,
    top_k: int = 2,
    outdir: OutPath = OutPath("mappings/"),
    indent: int = 2,
    version_tag: str = "",
    verbose: bool = False,
) -> None:
    """Create SSSOM mappings for one or more datasets and merge them into their codebooks.

    Args:
        provider: Dataset provider key (``"uciml"`` or ``"openml"``).
        datasets: Optional list of dataset identifiers; falls back to default
            provider catalog when omitted.
        codes_tsv: Path to the terminology TSV produced by
            `entailmap.match.build_wikidata_medical_codes_table`.
        manual_overrides_dir: Directory holding optional ``*.json`` overrides.
        systems: Terminology systems to consider during matching.
        method: Mapping strategy to use. Supported values are ``"lexical"``
            (offline TSV scoring), ``"keyword"`` (Datasette keyword search),
            ``"embed"`` (sentence-transformer re-ranking), and ``"llm"`` (tool
            augmented LLM).
        datasette_url: Base URL for Datasette-backed strategies (keyword and
            LLM).
        datasette_table: Table name used by Datasette strategies.
        datasette_limit: Number of rows fetched per column for keyword lookup.
        lexical_threshold: Minimum lexical similarity required by Datasette and
            embedding strategies.
        embed_model: Sentence-transformer model identifier.
        candidate_pool_multiplier: Pool size factor before lexical re-scoring
            in the embedding strategy.
        cosine_threshold: Minimum cosine similarity for embedding candidates.
        llm_model: Identifier of the LLM registered with ``llm``.
        llm_extra_prompt: Optional extra instructions appended to the LLM
            system prompt.
        llm_subject_prefix: Prefix applied to ``subject_id`` when using LLMs.
        confidence_threshold: Minimum confidence required for LLM results.
        min_score: Minimum similarity score applied to automatic matches
            produced by the lexical strategy.
        top_k: Maximum number of automatic matches per column.
        outdir: Output directory for SSSOM and the merged codebooks.
        indent: JSON indentation for the saved codebooks.
        version_tag: Optional version string recorded in the SSSOM header.
        verbose: Switch logging level to ``INFO`` when ``True``.
    """

    try:
        from entailmap.match.api import run_match
        from entailmap.match.codes_map_columns import load_manual_overrides, write_sssom
        from entailmap.match.shared import parse_columns
    except ImportError as exc:
        raise SystemExit(
            "create_mapping needs entailmap.match: pip install 'semsynth[mapping]'."
        ) from exc

    from .codebook import Codebook
    from .datasets import load_dataset, specs_from_input
    from .sssom_codebook import integrate_sssom
    from .utils import ensure_dir

    if verbose:
        logging.root.setLevel(logging.INFO)

    specs = specs_from_input(provider=provider, datasets=datasets)
    overrides_dir = Path(manual_overrides_dir) if manual_overrides_dir else None
    outdir_path = Path(outdir)
    ensure_dir(str(outdir_path))

    for spec in specs:
        payload = load_dataset(spec)
        slug = _dataset_slug(spec, payload.spec.name or str(payload.spec.id))

        metadata_payload = payload.metadata or payload.spec.meta
        if isinstance(metadata_payload, Codebook):
            metadata_payload = metadata_payload.to_jsonld()
        if not isinstance(metadata_payload, dict):
            raise RuntimeError(f"No metadata found for dataset {slug}")

        columns, dataset_meta = parse_columns(metadata_payload)
        try:
            matches = run_match(
                columns,
                dataset_meta,
                method=method,
                codes_tsv=codes_tsv,
                systems=systems,
                overrides=load_manual_overrides(_override_file(overrides_dir, spec, slug)),
                min_score=min_score,
                top_k=top_k,
                datasette_url=datasette_url,
                datasette_table=datasette_table,
                datasette_limit=datasette_limit,
                lexical_threshold=lexical_threshold,
                embed_model=embed_model,
                candidate_pool_multiplier=candidate_pool_multiplier,
                cosine_threshold=cosine_threshold,
                llm_model=llm_model,
                llm_extra_prompt=llm_extra_prompt,
                llm_subject_prefix=llm_subject_prefix,
                confidence_threshold=confidence_threshold,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc

        sssom_path = outdir_path / f"{slug}.sssom.tsv"
        write_sssom(matches, sssom_path, dataset_meta=dataset_meta, version_tag=version_tag)

        updated = integrate_sssom(
            Codebook.read(metadata_payload),
            [match.to_sssom_row() for match in matches],
            reviewer=f"semsynth map-columns ({method.lower()})",
        )
        metadata_path = outdir_path / f"{slug}.metadata.json"
        metadata_path.write_text(
            json.dumps(updated.to_jsonld(), indent=indent, ensure_ascii=False),
            encoding="utf-8",
        )

        logging.info("Wrote mappings for %s -> %s", slug, sssom_path)


@rule(phony=True)
def mappings(
    *,
    pipeline_configs: str = "",
    outdir: str = "output/",
    base_url: str = "https://w3id.org/semsynth/demo#",
    verbose: bool = False,
) -> None:
    """Generate reports for all curated mapping JSON files and rebuild the catalog.

    Args:
        pipeline_configs: Optional model configuration bundle (TOML); leave empty for metadata-only runs.
        outdir: Directory for report outputs.
        base_url: Base IRI used when rebuilding the catalog and HTML index.
        verbose: Whether to enable informational logging.
    """
    provider_to_ids = _collect_mapping_targets(Path("mappings"))
    _run_reports_for_targets(
        provider_to_ids,
        outdir=outdir,
        pipeline_configs=pipeline_configs,
        verbose=verbose,
        rebuild_catalog=True,
        base_url=base_url,
    )


@rule(phony=True)
def refresh_mapping_reports(
    *,
    pipeline_configs: str = "[pipeline]\ngenerate_umap=false\ncompute_privacy=false\ncompute_downstream=false\noverwrite_umap=false\n",
    outdir: str = "output/",
    mapping_root: str = "mappings",
    verbose: bool = False,
) -> None:
    """Regenerate reports for curated mapping metadata without re-running mappings.

    Args:
        pipeline_configs: Optional TOML snippet or file path passed to the ``report``
            subcommand. Leave empty for metadata-only reports or pass a pipeline block
            to disable heavy steps (e.g. ``{pipeline={generate_umap=false,compute_privacy=false,compute_downstream=false,overwrite_umap=false}}``).
        outdir: Output directory where dataset report folders live.
        mapping_root: Directory containing ``*.metadata.json`` mapping files.
        verbose: Whether to enable informational logging.
    """

    provider_to_ids = _collect_mapping_targets(Path(mapping_root))
    _run_reports_for_targets(
        provider_to_ids,
        outdir=outdir,
        pipeline_configs=pipeline_configs,
        verbose=verbose,
        rebuild_catalog=False,
        base_url=None,
    )


def _collect_mapping_targets(mapping_root: Path) -> dict[str, list[str]]:
    """Return provider→dataset_id mappings discovered under a mapping directory."""

    provider_to_ids: dict[str, list[str]] = {}
    for path in sorted(mapping_root.glob("*.metadata.json")):
        stem = path.stem
        if "-" not in stem:
            continue
        provider, dataset_id = stem.split("-", maxsplit=1)
        dataset_id = dataset_id.removesuffix(".metadata")
        provider_to_ids.setdefault(provider, []).append(dataset_id)
    if not provider_to_ids:
        logging.info("No mapping metadata files found under %s", mapping_root)
    return provider_to_ids


def _run_reports_for_targets(
    provider_to_ids: dict[str, list[str]],
    *,
    outdir: str,
    pipeline_configs: str,
    verbose: bool,
    rebuild_catalog: bool,
    base_url: str | None,
) -> None:
    """Invoke the report pipeline for a provider→dataset mapping."""

    if not provider_to_ids:
        return

    failures: list[str] = []
    successes = 0
    for provider, dataset_ids in provider_to_ids.items():
        for dataset_id in sorted(set(dataset_ids)):
            try:
                report(
                    provider=provider,
                    datasets=[dataset_id],
                    outdir=outdir,
                    pipeline_configs=pipeline_configs,
                    verbose=verbose,
                )
                successes += 1
            except SystemExit as exc:
                failures.append(f"{provider}:{dataset_id} ({exc})")

    if successes and rebuild_catalog and base_url:
        build_catalog(
            base_dir=Path(outdir),
            base_url=base_url,
            out_path=Path(outdir) / "catalog.json",
            index_path=Path(outdir) / "index.html",
        )

    if failures:
        logging.warning("Completed with skipped datasets: %s", "; ".join(failures))
        if successes == 0:
            raise SystemExit("; ".join(failures))


if __name__ == "__main__":
    main(argparse_kwargs = {
        "prog": 'python -m semsynth',
        "description": __doc__}, version=True)
