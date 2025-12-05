"""Command-line entry points for SemSynth."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

from makeprov import GLOBAL_CONFIG, OutPath, main, rule

from .app import run_app
from .catalog import build_catalog


__all__ = ["search", "report", "create_mapping", "run_app", "build_catalog", "main"]

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


@rule(merge=True, phony=True)
def create_mapping(
    provider: str,
    *,
    datasets: Optional[List[str]] = None,
    codes_tsv: str = "map_columns/codes.tsv",
    manual_overrides_dir: Optional[str] = "map_columns/manual",
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
    """Create SemMap-aware SSSOM mappings for one or more datasets.

    Args:
        provider: Dataset provider key (``"uciml"`` or ``"openml"``).
        datasets: Optional list of dataset identifiers; falls back to default
            provider catalog when omitted.
        codes_tsv: Path to the terminology TSV produced by
            :mod:`map_columns.build_wikidata_medical_codes_table`.
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
        outdir: Output directory for SSSOM and merged SemMap metadata.
        indent: JSON indentation for saved SemMap metadata.
        version_tag: Optional version string recorded in the SSSOM header.
        verbose: Switch logging level to ``INFO`` when ``True``.
    """

    from .datasets import load_dataset, specs_from_input
    from .semmap import Metadata
    from .utils import ensure_dir
    from map_columns.codes_map_columns import (
        build_manual_matches,
        load_manual_overrides,
        write_sssom,
    )
    from map_columns.shared import parse_columns
    from map_columns.sssom_to_semmap import integrate_sssom

    if verbose:
        logging.root.setLevel(logging.INFO)

    specs = specs_from_input(provider=provider, datasets=datasets)
    overrides_dir = Path(manual_overrides_dir) if manual_overrides_dir else None
    allowed_systems = tuple(system for system in systems if system)

    codes_cache: Optional[Dict[str, Any]] = None
    if method.lower() in {"lexical", "embed"} or overrides_dir:
        from map_columns.codes_map_columns import load_codes

        codes_cache = load_codes(
            Path(codes_tsv), allowed_systems=allowed_systems or None
        )

    outdir_path = Path(outdir)
    ensure_dir(str(outdir_path))

    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    method_key = method.lower()

    for spec in specs:
        payload = load_dataset(spec)
        dataset_label = payload.spec.name or str(payload.spec.id)
        slug_parts = [spec.provider]
        if spec.id is not None:
            slug_parts.append(str(spec.id))
        elif dataset_label:
            slug_parts.append(_slug(dataset_label))
        slug = "-".join(slug_parts)

        metadata_payload = payload.metadata or payload.spec.meta
        if isinstance(metadata_payload, Metadata):
            metadata_payload = metadata_payload.to_jsonld()
        if not isinstance(metadata_payload, dict):
            raise RuntimeError(f"No metadata found for dataset {slug}")

        columns, dataset_meta = parse_columns(metadata_payload)

        manual_overrides_path: Optional[Path] = None
        if overrides_dir:
            candidate_names = [
                f"{slug}.json",
                f"{spec.provider}-{spec.id}.json" if spec.id is not None else "",
            ]
            for name in candidate_names:
                if not name:
                    continue
                candidate = overrides_dir / name
                if candidate.exists():
                    manual_overrides_path = candidate
                    break
        overrides = load_manual_overrides(manual_overrides_path)

        if method_key == "lexical":
            from map_columns.codes_map_columns import generate_matches as lexical_generate_matches

            matches = lexical_generate_matches(
                columns,
                codes_cache or {},
                min_score=min_score,
                top_k=top_k,
                manual_overrides=overrides,
            )
        elif method_key == "keyword":
            from map_columns.kwd_map_columns import generate_matches as keyword_generate_matches

            matches = keyword_generate_matches(
                columns,
                dataset_meta,
                datasette_db_url=datasette_url,
                table=datasette_table,
                limit=datasette_limit,
                allowed_systems=allowed_systems,
                lexical_threshold=lexical_threshold,
                top_k=top_k,
            )
        elif method_key == "embed":
            from map_columns.embed_map_columns import generate_matches as embed_generate_matches

            if not codes_cache:
                raise SystemExit(
                    "Embedding-based mapping requires a terminology codes TSV."
                )
            matches = embed_generate_matches(
                columns,
                dataset_meta,
                list(codes_cache.values()),
                model_name=embed_model,
                top_k=top_k,
                candidate_pool_multiplier=candidate_pool_multiplier,
                cosine_threshold=cosine_threshold,
                lexical_threshold=lexical_threshold,
            )
        elif method_key == "llm":
            from map_columns.llm_map_columns import generate_matches as llm_generate_matches

            matches = llm_generate_matches(
                columns,
                dataset_meta,
                datasette_url=datasette_url,
                model=llm_model,
                extra_prompt=llm_extra_prompt,
                subject_prefix=llm_subject_prefix,
                allowed_systems=allowed_systems,
                top_k=top_k,
                confidence_threshold=confidence_threshold,
            )
        else:
            raise SystemExit(
                f"Unknown mapping method '{method}'. Expected lexical, keyword, embed, or llm."
            )

        if overrides and method_key != "lexical":
            if codes_cache is None:
                from map_columns.codes_map_columns import load_codes

                codes_cache = load_codes(
                    Path(codes_tsv), allowed_systems=allowed_systems or None
                )
            manual_matches = []
            overridden = set()
            for column in columns:
                manual = build_manual_matches(
                    column, overrides, codes_cache, min_score=min_score
                )
                if manual:
                    manual_matches.extend(manual)
                    overridden.add(column)
            if manual_matches:
                matches = manual_matches + [
                    match for match in matches if match.column not in overridden
                ]

        sssom_path = outdir_path / f"{slug}.sssom.tsv"
        write_sssom(
            matches,
            sssom_path,
            dataset_meta=dataset_meta,
            version_tag=version_tag,
        )

        metadata = Metadata.from_dcat_dsv(metadata_payload)
        mapping_rows = [match.to_sssom_row() for match in matches]
        updated = integrate_sssom(metadata, mapping_rows)
        metadata_path = outdir_path / f"{slug}.metadata.json"
        metadata_path.write_text(
            json.dumps(updated.to_jsonld(), indent=indent, ensure_ascii=False),
            encoding="utf-8",
        )

        logging.info("Wrote mappings for %s -> %s", slug, sssom_path)

if __name__ == "__main__":
    main(argparse_kwargs = dict(
        prog='python -m semsynth',
        description=__doc__), version=True)
