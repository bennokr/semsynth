"""Command-line entry points for SemSynth.

Each command is a thin wrapper over a function of the library (``semsynth.workflow``, ``semsynth.mappings``,
``semsynth.catalog``, ``semsynth.app``, ``semsynth.downstream_fidelity``); makeprov records the provenance of the
command here, not inside the library. Heavy modules are imported when a command runs, so ``--help`` stays fast.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from makeprov import InPath, OutPath, main, rule
from makeprov.config import ProvenanceConfig

__all__ = [
    "build_catalog",
    "create_mapping",
    "main",
    "mappings",
    "recompute_downstream",
    "refresh_mapping_reports",
    "report",
    "run_app",
    "search",
]


def _set_prov_dir(dataset_outdir: Path) -> None:
    """Write the provenance of a dataset's commands next to its reports."""

    ProvenanceConfig.get().prov_dir = str(dataset_outdir / "prov")


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
    from .workflow import search_datasets

    if verbose:
        logging.root.setLevel(logging.INFO)
    try:
        table = search_datasets(
            provider, name_substr=name_substr, area=area, cat_min=cat_min, num_min=num_min
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output_text = table.to_csv(sep="\t", index=None)
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
    from .workflow import run_reports

    if verbose:
        logging.root.setLevel(logging.INFO)
    failures = run_reports(
        provider,
        datasets=datasets,
        outdir=Path(outdir),
        pipeline_configs=pipeline_configs,
        area=area,
        on_dataset=_set_prov_dir,
    )
    if failures:
        raise SystemExit("; ".join(failures))


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
    from .mappings import create_mappings

    if verbose:
        logging.root.setLevel(logging.INFO)
    try:
        create_mappings(
            provider,
            datasets=datasets,
            codes_tsv=codes_tsv,
            manual_overrides_dir=manual_overrides_dir,
            outdir=Path(outdir),
            indent=indent,
            version_tag=version_tag,
            method=method,
            systems=systems,
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
            min_score=min_score,
            top_k=top_k,
        )
    except (ImportError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def _reports_for_mappings(
    mapping_root: str,
    *,
    outdir: str,
    pipeline_configs: str,
    verbose: bool,
    base_url: str | None,
) -> None:
    """Run reports for the curated mappings and, if a ``base_url`` is given, rebuild the catalog."""

    from .workflow import collect_mapping_targets, run_reports_for_targets

    if verbose:
        logging.root.setLevel(logging.INFO)
    targets = collect_mapping_targets(mapping_root)
    if not targets:
        return
    successes, failures = run_reports_for_targets(
        targets, outdir=outdir, pipeline_configs=pipeline_configs, on_dataset=_set_prov_dir
    )
    if successes and base_url:
        from .catalog import build_catalog as write_catalog

        ProvenanceConfig.get().prov_dir = str(Path(outdir))
        write_catalog(
            base_dir=Path(outdir),
            base_url=base_url,
            out_path=Path(outdir) / "catalog.json",
            index_path=Path(outdir) / "index.html",
        )
    if failures:
        logging.warning("Completed with skipped datasets: %s", "; ".join(failures))
        if successes == 0:
            raise SystemExit("; ".join(failures))


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
    _reports_for_mappings(
        "mappings", outdir=outdir, pipeline_configs=pipeline_configs, verbose=verbose, base_url=base_url
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
    _reports_for_mappings(
        mapping_root, outdir=outdir, pipeline_configs=pipeline_configs, verbose=verbose, base_url=None
    )


@rule(merge=True)
def recompute_downstream(
    metrics: OutPath = OutPath("{metrics}"),
    *,
    real: InPath | None = None,
    synth: InPath | None = None,
    meta: InPath | None = None,
    target: str | None = None,
    verbose: bool = False,
) -> None:
    """Recompute downstream metrics from existing real/synthetic CSVs."""
    from .downstream_fidelity import recompute_downstream as recompute

    recompute(metrics, real=real, synth=synth, meta=meta, target=target, verbose=verbose)


@rule()
def build_catalog(
    base_dir: InPath = InPath("output"),
    base_url: str = "https://w3id.org/semsynth/demo#",
    out_path: OutPath = OutPath("output/catalog.json"),
    index_path: OutPath = OutPath("output/index.html"),
) -> None:
    """Construct the DCAT catalog.

    Args:
        base_dir: The base directory that holds all SemSynth reports.
        base_url: Base URL for creating IRIs.
        out_path: Output path for the catalog JSON-LD.
        index_path: Output path for the HTML index file.
    """
    from . import catalog

    ProvenanceConfig.get().prov_dir = out_path.parent
    catalog.build_catalog(base_dir, base_url, out_path, index_path)


@rule(phony=True)
def run_app(*, host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Create and run the Flask development server.

    Args:
        host: Host interface for the server.
        port: Port to bind the server to.
        debug: Whether to enable Flask debug mode.
    """
    from .app import run_app as serve

    serve(host=host, port=port, debug=debug)


if __name__ == "__main__":
    from . import get_version

    main(argparse_kwargs={"prog": "python -m semsynth", "description": __doc__}, version=get_version())
