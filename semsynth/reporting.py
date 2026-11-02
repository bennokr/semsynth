"""Utilities for rendering dataset reports.

The reporting workflow produces a Markdown summary and a corresponding HTML
document for a dataset. The workflow follows three major steps:

1. Assemble an in-memory context describing the dataset, variable summaries and
   model runs.
2. Render Markdown content from a Jinja template using the assembled context.
3. Convert the Markdown output to HTML and embed it inside a static page
   template for distribution.

This module exposes :func:`write_report_md` as the high-level entry point and
contains helpers for computing summary tables, templating and distribution
formatting.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from .jsonld_to_rdfa import SCHEMA_ORG, render_rdfa
from .models import ModelRun
from .report_tables import (
    build_fidelity_table,
    build_metasyn_gmf_table,
    build_metric_table,
    build_missingness_table,
    build_overview_table,
    build_per_variable_table,
    build_privacy_table,
    build_variable_summary,
    downstream_metric_items,
    extract_codebook_labels,
    privacy_metric_items,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from jinja2 import Environment

_TEMPLATE_FILES = ("report.md.j2", "report_template.html", "report_style.css", "codebook_style.css")


def _load_template_sources() -> dict[str, str]:
    """Load packaged template text for Jinja and static CSS assets."""

    return {
        name: resources.files("semsynth.templates").joinpath(name).read_text(encoding="utf-8")
        for name in _TEMPLATE_FILES
    }


@dataclass
class _ModelLink:
    """Represents a hyperlink entry in a model's report row."""

    label: str
    href: str


@dataclass
class _ModelRow:
    """Pre-rendered data describing a model run section in the report."""

    name: str
    backend: str
    seed: Any
    rows: Any
    params_json: str | None
    umap_rel: str | None
    structure_rel: str | None
    links: Sequence[_ModelLink]
    missingness: dict[str, Any] | None = None
    per_variable_table: str | None = None
    downstream_table: str | None = None
    privacy_table: str | None = None
    structure_table: str | None = None


def _jinja_environment() -> Environment:
    """Return a configured Jinja environment for report templates."""

    from jinja2 import DictLoader, Environment, select_autoescape

    return Environment(
        loader=DictLoader(_load_template_sources()),
        autoescape=select_autoescape(("html", "xml"), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _resolve_codebook_context(data: dict[str, Any]) -> Any:
    if isinstance(data, dict) and data.get("@context"):
        return data["@context"]
    return SCHEMA_ORG


def _write_codebook_artifacts(
    output_dir: Path, dataset_name: str, codebook_jsonld: dict | None
) -> tuple[str | None, str | None]:
    """Persist the codebook artifacts and return filenames.

    Args:
        output_dir: Target directory for report files.
        dataset_name: Dataset label used for the HTML title.
        codebook_jsonld: JSON-LD payload representing semantic metadata.

    Returns:
        Tuple containing the JSON filename and the rendered HTML filename. Each
        entry can be ``None`` when the corresponding artifact could not be
        generated.
    """

    if not isinstance(codebook_jsonld, dict) or not codebook_jsonld:
        return None, None

    json_name = "dataset.codebook.jsonld"
    json_path = output_dir / json_name
    json_path.write_text(json.dumps(codebook_jsonld, indent=2), encoding="utf-8")

    html_name: str | None = None
    try:
        context = _resolve_codebook_context(codebook_jsonld)
        html_title = f"{dataset_name} — codebook"
        codebook_fragment = render_rdfa(codebook_jsonld, context, html_title)
        html_path = output_dir / "dataset.codebook.html"
        html_path.write_text(codebook_fragment, encoding="utf-8")
        html_name = html_path.name
        logging.info("Wrote codebook HTML: %s", html_path)
    except Exception:  # pragma: no cover - log and continue report generation
        logging.exception("Failed to render codebook HTML", exc_info=True)
    return json_name, html_name


def write_report_md(
    outdir: Path | str,
    dataset_name: str,
    dataset_provider: str | None,
    dataset_provider_id: int | None,
    df: pd.DataFrame,
    disc_cols: list[str],
    cont_cols: list[str],
    umap_png_real: str | None = None,
    declared_types: dict | None = None,
    inferred_types: dict | None = None,
    variable_descriptions: dict | None = None,
    codebook_jsonld: dict | None = None,
    dataset_metadata: Any | None = None,
    model_runs: list[ModelRun] | None = None,
    missingness_summary: dict[str, Any] | None = None,
) -> None:
    """Render Markdown and HTML reports for a dataset.

    Args:
        outdir: Directory where report files should be written.
        dataset_name: Human readable dataset title used in headings.
        dataset_provider: External provider identifier (e.g. ``"openml"``).
        dataset_provider_id: Provider specific identifier for linking back.
        df: Source dataframe containing the analysed dataset.
        disc_cols: Names of discrete variables used for summary statistics.
        cont_cols: Names of continuous variables used for numeric summaries.
        umap_png_real: Optional path to the real-data UMAP image.
        declared_types: Mapping of declared data types per variable.
        inferred_types: Mapping of inferred data types per variable.
        variable_descriptions: Optional free text descriptions for variables.
        codebook_jsonld: Semantic metadata to attach to the report.
        model_runs: Model execution metadata used to build model sections.
        missingness_summary: Optional description of fitted missingness rates used
            for contextual reporting.
    """

    output_dir = Path(outdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    codebook_json_name, codebook_html_name = _write_codebook_artifacts(output_dir, dataset_name, codebook_jsonld)
    properties = _dataset_properties(dataset_metadata, dataset_name)
    title = properties["title"]
    provider_link = _provider_link(dataset_provider, dataset_provider_id)
    counts = {
        "num_rows": df.shape[0],
        "num_cols": df.shape[1],
        "num_disc": len(disc_cols),
        "num_cont": len(cont_cols),
    }
    links = {
        "provider_link": provider_link,
        "codebook_json_name": codebook_json_name,
        "codebook_html_name": codebook_html_name,
    }
    tables = {
        "overview_table": build_overview_table(
            dataset_name=title, missingness_summary=missingness_summary, **links, **counts
        ),
        "variable_table": build_variable_summary(
            df=df,
            cont_cols=cont_cols,
            declared_types=declared_types,
            inferred_types=inferred_types,
            variable_descriptions=variable_descriptions,
            codebook_labels=extract_codebook_labels(dataset_metadata if dataset_metadata is not None else {}),
        ),
        "fidelity_table": build_fidelity_table(model_runs=model_runs),
        "privacy_table": build_privacy_table(model_runs=model_runs),
        "missingness_table": build_missingness_table(missingness_summary),
    }

    env = _jinja_environment()
    md_text = env.get_template("report.md.j2").render(
        dataset_name=title,
        model_rows=_prepare_model_rows(model_runs or [], output_dir),
        real_umap=os.path.basename(umap_png_real) if umap_png_real else None,
        missingness_summary=missingness_summary,
        dataset_description=properties["description"],
        dataset_purpose=properties["purpose"],
        dataset_table=properties["table"],
        dataset_citation=properties["citation"],
        **links,
        **counts,
        **tables,
    )
    md_path = output_dir / "report.md"
    md_path.write_text(md_text, encoding="utf-8")
    logging.info("Wrote report: %s", md_path)
    _write_html(env, md_text, output_dir / "index.html", f"Data Report — {title}")


def _dataset_properties(dataset_metadata: Any | None, dataset_name: str) -> dict[str, Any]:
    """Title, description, purpose, table of contents and citation of the dataset, from its metadata."""

    metadata: dict[str, Any] = {}
    if dataset_metadata is not None:
        if hasattr(dataset_metadata, "to_jsonld"):
            metadata = dataset_metadata.to_jsonld() or {}
        elif isinstance(dataset_metadata, dict):
            metadata = dataset_metadata
    return {
        "title": metadata.get("dcterms:title") or metadata.get("title") or dataset_name,
        "description": metadata.get("dcterms:description") or metadata.get("description"),
        "purpose": metadata.get("dcterms:purpose") or metadata.get("purpose"),
        "table": metadata.get("dcterms:tableOfContents") or metadata.get("tableOfContents"),
        "citation": metadata.get("schema:citation") or metadata.get("citation"),
    }


def _write_html(env: Environment, md_text: str, html_path: Path, title: str) -> None:
    """Convert the Markdown report to the HTML page."""

    import markdown
    from markupsafe import Markup

    html_body = markdown.markdown(md_text, extensions=["extra", "md_in_html"])
    html_out = _load_html_template(env).render(
        TITLE=title,
        CSS=Markup(_read_template_text("report_style.css")),
        BODY=Markup(textwrap.indent(html_body, "    ")),
    )
    html_path.write_text(html_out, encoding="utf-8")
    logging.info("Converted to HTML: %s", html_path)


def _prepare_model_rows(model_runs: Iterable[ModelRun], base_dir: Path) -> list[_ModelRow]:
    """Convert model runs into template-friendly rows."""

    prepared: list[_ModelRow] = []
    for run in sorted(model_runs, key=lambda r: (r.backend, r.name)):
        manifest = run.manifest or {}
        params = manifest.get("params") or {}
        params_json = json.dumps(params, sort_keys=True) if params else None

        links = []
        for label, target in (
            ("Synthetic CSV", run.synthetic_csv),
            ("Per-variable metrics", run.per_variable_csv),
            ("Metrics JSON", run.metrics_json or run.run_dir / "metrics.json"),
            ("Privacy metrics", run.privacy_json),
            ("Downstream metrics", run.downstream_json),
        ):
            rel = _relative_path(target, base_dir)
            if rel:
                links.append(_ModelLink(label=label, href=rel))

        per_variable_table = build_per_variable_table(run.per_variable_csv)
        downstream_table = build_metric_table(downstream_metric_items(run.downstream_metrics))
        privacy_table = build_metric_table(privacy_metric_items(run.privacy_metrics))
        structure_table = build_metasyn_gmf_table(run.run_dir) if run.backend == "metasyn" else None

        prepared.append(
            _ModelRow(
                name=run.name,
                backend=run.backend,
                seed=manifest.get("seed"),
                rows=manifest.get("rows"),
                params_json=params_json,
                umap_rel=_relative_path(run.umap_png, base_dir),
                structure_rel=_relative_path(run.run_dir / "structure.png", base_dir),
                links=tuple(links),
                missingness=manifest.get("missingness"),
                per_variable_table=per_variable_table,
                downstream_table=downstream_table,
                privacy_table=privacy_table,
                structure_table=structure_table,
            )
        )
    return prepared


def _relative_path(target: Path | None, base_dir: Path) -> str | None:
    """Return a relative path when the target exists."""

    if target is None:
        return None
    target_path = Path(target)
    if not target_path.exists():
        return None
    return os.path.relpath(target_path, start=base_dir)


def _provider_link(
    dataset_provider: str | None, dataset_provider_id: int | None
) -> dict[str, str] | None:
    """Build a provider hyperlink descriptor for the template."""

    if not dataset_provider or not dataset_provider_id:
        return None
    provider = dataset_provider.lower()
    if provider == "openml":
        url = f"https://www.openml.org/search?type=data&id={dataset_provider_id}"
        text = f"OpenML dataset {dataset_provider_id}"
    elif provider == "uciml":
        url = f"https://archive.ics.uci.edu/dataset/{dataset_provider_id}"
        text = f"UCI dataset {dataset_provider_id}"
    else:
        return None
    return {"url": url, "text": text}


def _read_template_text(template_name: str) -> str:
    """Load template text from disk and fail fast when missing."""

    return _load_template_sources()[template_name]


def _load_html_template(env: Environment):
    """Load the HTML template without silent fallbacks."""

    return env.get_template("report_template.html")












