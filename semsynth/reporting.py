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

from dataclasses import dataclass
from pathlib import Path
from importlib import resources
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence
import json
import logging
import os
import textwrap
from numbers import Integral, Real

from jinja2 import Environment, DictLoader, select_autoescape
from markupsafe import Markup
import pandas as pd
from makeprov import OutPath, rule

from .jsonld_to_rdfa import SCHEMA_ORG, render_rdfa
from .models import ModelRun


_TEMPLATE_FILES = ("report.md.j2", "report_template.html", "report_style.css", "semmap_style.css")


def _load_template_sources() -> Dict[str, str]:
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
    params_json: Optional[str]
    umap_rel: Optional[str]
    structure_rel: Optional[str]
    links: Sequence[_ModelLink]
    missingness: Optional[Dict[str, Any]] = None
    per_variable_table: Optional[str] = None
    downstream_table: Optional[str] = None
    privacy_table: Optional[str] = None
    structure_table: Optional[str] = None


def _jinja_environment() -> Environment:
    """Return a configured Jinja environment for report templates."""

    return Environment(
        loader=DictLoader(_load_template_sources()),
        autoescape=select_autoescape(("html", "xml"), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _resolve_semmap_context(data: Dict[str, Any]) -> Any:
    if isinstance(data, dict) and data.get("@context"):
        return data["@context"]
    return SCHEMA_ORG


def _write_semmap_artifacts(
    output_dir: Path, dataset_name: str, semmap_jsonld: Optional[dict]
) -> tuple[Optional[str], Optional[str]]:
    """Persist SemMap metadata artifacts and return filenames.

    Args:
        output_dir: Target directory for report files.
        dataset_name: Dataset label used for the HTML title.
        semmap_jsonld: JSON-LD payload representing semantic metadata.

    Returns:
        Tuple containing the JSON filename and the rendered HTML filename. Each
        entry can be ``None`` when the corresponding artifact could not be
        generated.
    """

    if not isinstance(semmap_jsonld, dict) or not semmap_jsonld:
        return None, None

    json_name = "dataset.semmap.json"
    json_path = output_dir / json_name
    json_path.write_text(json.dumps(semmap_jsonld, indent=2), encoding="utf-8")

    html_name: Optional[str] = None
    try:
        context = _resolve_semmap_context(semmap_jsonld)
        html_title = f"{dataset_name} — SemMap metadata"
        semmap_fragment = render_rdfa(semmap_jsonld, context, html_title)
        html_path = output_dir / "dataset.semmap.html"
        html_path.write_text(semmap_fragment, encoding="utf-8")
        html_name = html_path.name
        logging.info("Wrote SemMap metadata HTML: %s", html_path)
    except Exception:  # pragma: no cover - log and continue report generation
        logging.exception("Failed to render SemMap metadata HTML", exc_info=True)
    return json_name, html_name


@rule(phony=True)
def write_report_md(
    outdir: OutPath,
    dataset_name: str,
    # metadata_file: str,
    # dataset_jsonld_file: Optional[str],
    dataset_provider: Optional[str],
    dataset_provider_id: Optional[int],
    df: "pd.DataFrame",
    disc_cols: List[str],
    cont_cols: List[str],
    umap_png_real: Optional[str] = None,
    declared_types: Optional[dict] = None,
    inferred_types: Optional[dict] = None,
    variable_descriptions: Optional[dict] = None,
    semmap_jsonld: Optional[dict] = None,
    dataset_metadata: Optional[Any] = None,
    model_runs: Optional[List[ModelRun]] = None,
    missingness_summary: Optional[Dict[str, Any]] = None,
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
        semmap_jsonld: Semantic metadata to attach to the report.
        model_runs: Model execution metadata used to build model sections.
        missingness_summary: Optional description of fitted missingness rates used
            for contextual reporting.
    """

    import markdown
    import pandas as pd

    output_dir = Path(outdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "report.md"
    dataset_title = dataset_name

    semmap_json_name, semmap_html_name = _write_semmap_artifacts(
        output_dir, dataset_title, semmap_jsonld
    )

    metadata_dict: Dict[str, Any] = {}
    if dataset_metadata is not None:
        if hasattr(dataset_metadata, "to_jsonld"):
            metadata_dict = dataset_metadata.to_jsonld() or {}
        elif isinstance(dataset_metadata, dict):
            metadata_dict = dataset_metadata
    codebook_labels = _extract_codebook_labels(metadata_dict)

    dataset_description = metadata_dict.get("dcterms:description") or metadata_dict.get("description")
    dataset_purpose = metadata_dict.get("dcterms:purpose") or metadata_dict.get("purpose")
    dataset_table = metadata_dict.get("dcterms:tableOfContents") or metadata_dict.get("tableOfContents")
    dataset_title = metadata_dict.get("dcterms:title") or metadata_dict.get("title") or dataset_title
    dataset_citation = metadata_dict.get("schema:citation") or metadata_dict.get("citation")

    num_rows, num_cols = df.shape
    provider_link = _provider_link(dataset_provider, dataset_provider_id)
    model_rows = _prepare_model_rows(model_runs or [], output_dir)
    variable_table = _build_variable_summary(
        df=df,
        cont_cols=cont_cols,
        declared_types=declared_types,
        inferred_types=inferred_types,
        variable_descriptions=variable_descriptions,
        codebook_labels=codebook_labels,
    )
    fidelity_table = _build_fidelity_table(model_runs=model_runs)
    privacy_table = _build_privacy_table(model_runs=model_runs)
    missingness_table = _build_missingness_table(missingness_summary)
    overview_table = _build_overview_table(
        dataset_name=dataset_title,
        provider_link=provider_link,
        semmap_json_name=semmap_json_name,
        semmap_html_name=semmap_html_name,
        num_rows=num_rows,
        num_cols=num_cols,
        num_disc=len(disc_cols),
        num_cont=len(cont_cols),
        missingness_summary=missingness_summary,
    )

    env = _jinja_environment()
    template = env.get_template("report.md.j2")
    md_text = template.render(
        dataset_name=dataset_title,
        provider_link=provider_link,
        semmap_json_name=semmap_json_name,
        semmap_html_name=semmap_html_name,
        num_rows=num_rows,
        num_cols=num_cols,
        num_disc=len(disc_cols),
        num_cont=len(cont_cols),
        overview_table=overview_table,
        variable_table=variable_table,
        fidelity_table=fidelity_table,
        privacy_table=privacy_table,
        model_rows=model_rows,
        real_umap=os.path.basename(umap_png_real) if umap_png_real else None,
        missingness_summary=missingness_summary,
        missingness_table=missingness_table,
        dataset_description=dataset_description,
        dataset_purpose=dataset_purpose,
        dataset_table=dataset_table,
        dataset_citation=dataset_citation,
    )
    md_path.write_text(md_text, encoding="utf-8")
    logging.info("Wrote report: %s", md_path)

    html_path = output_dir / "index.html"
    html_body = markdown.markdown(md_text, extensions=["extra", "md_in_html"])
    html_body = textwrap.indent(html_body, "    ")
    report_title = f"Data Report — {dataset_title}"
    css_text = _read_template_text("report_style.css")
    html_template = _load_html_template(env)
    html_out = html_template.render(
        TITLE=report_title,
        CSS=Markup(css_text),
        BODY=Markup(html_body),
    )
    html_path.write_text(html_out, encoding="utf-8")
    logging.info("Converted to HTML: %s", html_path)


def _format_dist(
    col: pd.Series,
    cont_cols: List[str],
    *,
    codebook: Optional[Dict[str, str]] = None,
    top_n: int = 10,
) -> str:
    """Return a concise distribution summary for a column."""

    s = col.dropna()
    if col.name in cont_cols:
        try:
            x = pd.to_numeric(s, errors="coerce")
            mean = float(x.mean())
            std = float(x.std())
            q25 = float(x.quantile(0.25))
            q50 = float(x.quantile(0.50))
            q75 = float(x.quantile(0.75))
            minv = float(x.min())
            maxv = float(x.max())

            def fmt(v: float) -> str:
                txt = f"{v:.4f}".rstrip("0").rstrip(".")
                return txt if txt else "0"

            quantiles = ", ".join([fmt(minv), fmt(q25), fmt(q50), fmt(q75), fmt(maxv)])
            return f"{mean:.4f} ± {std:.4f} [{quantiles}]"
        except Exception:
            return ""
    # Discrete
    if s.empty:
        return ""
    try:
        vc = s.value_counts(dropna=True)
        total = float(vc.sum()) if vc.sum() else 1.0
    except Exception:
        return ""
    entries: List[tuple[str, str, int]] = []
    for value, cnt in vc.items():
        key = _normalise_scalar(value)
        display = _format_codebook_value(key, codebook)
        entries.append((key, display, int(cnt)))
    if len(entries) == 2:
        keys = [key for key, _, _ in entries]
        pos_key = _select_positive_key(keys)
        counts = {key: cnt for key, _, cnt in entries}
        n_true = counts.get(pos_key, 0)
        pct = 100.0 * (n_true / total)
        display = _format_codebook_value(pos_key, codebook)
        return f"{display}: {n_true} ({pct:.2f}%)"
    parts = []
    for idx, (_, display, cnt) in enumerate(entries):
        pct = 100.0 * (cnt / total)
        if idx < top_n:
            parts.append(f"{display}: {cnt} ({pct:.2f}%)")
    if len(entries) > top_n:
        parts.append(f"… (+{len(entries) - top_n} more)")
    return "<br />".join(parts)


def _build_variable_summary(
    df: pd.DataFrame,
    cont_cols: Iterable[str],
    *,
    declared_types: Optional[dict],
    inferred_types: Optional[dict],
    variable_descriptions: Optional[dict],
    codebook_labels: Optional[Dict[str, Dict[str, str]]],
) -> str:
    """Create the Markdown table summarising variables."""

    cont_list = list(dict.fromkeys(cont_cols))
    var_rows = [
        {
            "variable": column,
            "dist": _format_dist(
                df[column],
                cont_list,
                codebook=(codebook_labels or {}).get(column),
            ),
        }
        for column in df.columns
    ]
    baseline = pd.DataFrame(var_rows).fillna("")

    merged = baseline
    for mapping, label in (
        (declared_types, "declared"),
        (inferred_types, "inferred"),
        (variable_descriptions, "description"),
    ):
        if isinstance(mapping, dict) and mapping:
            other = pd.DataFrame(
                [{"variable": key, label: value} for key, value in mapping.items()]
            )
            merged = other.merge(merged, on="variable", how="right").fillna("")

    return _dataframe_to_markdown(merged, index=False)


def _coerce_numeric(value: Any) -> Optional[float]:
    """Coerce a value to a finite float when possible."""

    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def _format_metric_cell(value: Any) -> str:
    """Render metric values with consistent rounding."""

    num = _coerce_numeric(value)
    if num is None:
        return ""
    if num.is_integer():
        return str(int(num))
    return f"{num:.4f}".rstrip("0").rstrip(".")


def _build_fidelity_table(*, model_runs: Optional[Sequence[ModelRun]]) -> Optional[str]:
    """Create the markdown representation of the fidelity table."""

    runs = sorted(model_runs or [], key=lambda run: (run.backend, run.name))
    if not runs:
        return None

    rows: List[Dict[str, Any]] = []
    for run in runs:
        summary = run.metrics.get("summary", {}) if isinstance(run.metrics, dict) else {}
        rows.append(
            {
                "model": run.name,
                "backend": run.backend,
                "disc_jsd_mean": _format_metric_cell(summary.get("disc_jsd_mean")),
                "disc_jsd_median": _format_metric_cell(summary.get("disc_jsd_median")),
                "cont_ks_mean": _format_metric_cell(summary.get("cont_ks_mean")),
                "cont_w1_mean": _format_metric_cell(summary.get("cont_w1_mean")),
                "downstream_sign_match": _format_metric_cell(_extract_downstream_sign_match(run)),
            }
        )

    if not rows:
        return None

    out = pd.DataFrame(rows)
    ordered_cols = [
        "model",
        "backend",
        "disc_jsd_mean",
        "disc_jsd_median",
        "cont_ks_mean",
        "cont_w1_mean",
        "downstream_sign_match",
    ]
    present_cols = [col for col in ordered_cols if col in out.columns]
    out = out[present_cols].fillna("")
    out.rename(columns=lambda col: col.replace("_", " "), inplace=True)
    return _dataframe_to_markdown(out, index=False)


def _privacy_metrics_summary(metrics: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick a consistent subset of privacy metrics for tabular reporting."""

    if not isinstance(metrics, dict) or not metrics:
        return {}
    nn_stats = metrics.get("nn_distance_stats", {})
    nn_mean = nn_stats.get("mean") if isinstance(nn_stats, dict) else None
    summary = {
        "n_real": _coerce_numeric(metrics.get("n_real")),
        "n_synth": _coerce_numeric(metrics.get("n_synth")),
        "exact_overlap_rate": _coerce_numeric(metrics.get("exact_overlap_rate")),
        "near_duplicate_rate_eps": _coerce_numeric(metrics.get("near_duplicate_rate_eps")),
        "nn_distance_mean": _coerce_numeric(nn_mean),
        "k_min": _coerce_numeric(metrics.get("k_min")),
        "k_pct_lt5": _coerce_numeric(metrics.get("k_pct_lt5")),
        "k_map": _coerce_numeric(metrics.get("k_map")),
        "rare_qi_reproduction_rate": _coerce_numeric(metrics.get("rare_qi_reproduction_rate")),
        "identifiability_score": _coerce_numeric(metrics.get("identifiability_score")),
        "delta_presence": _coerce_numeric(metrics.get("delta_presence")),
    }
    values = [val for key, val in summary.items() if key not in ("n_real", "n_synth")]
    if not any(val is not None for val in values):
        return {}
    return summary


def _build_privacy_table(*, model_runs: Optional[Sequence[ModelRun]]) -> Optional[str]:
    """Create the markdown representation of the dataset-level privacy table."""

    runs = sorted(model_runs or [], key=lambda run: (run.backend, run.name))
    rows: List[Dict[str, Any]] = []
    for run in runs:
        summary = _privacy_metrics_summary(run.privacy_metrics)
        if not summary:
            continue
        row = {"model": run.name, "backend": run.backend}
        row.update({key: _format_metric_cell(val) for key, val in summary.items()})
        rows.append(row)
    if not rows:
        return None
    out = pd.DataFrame(rows)
    ordered_cols = [
        "model",
        "backend",
        "n_real",
        "n_synth",
        "exact_overlap_rate",
        "near_duplicate_rate_eps",
        "nn_distance_mean",
        "k_min",
        "k_pct_lt5",
        "k_map",
        "rare_qi_reproduction_rate",
        "identifiability_score",
        "delta_presence",
    ]
    present_cols = [col for col in ordered_cols if col in out.columns]
    out = out[present_cols].fillna("")
    out.rename(columns=lambda col: col.replace("_", " "), inplace=True)
    return _dataframe_to_markdown(out, index=False)


def _extract_downstream_sign_match(run: ModelRun) -> Optional[float]:
    """Return the downstream sign match value using available sources."""

    for candidate in (
        getattr(run, "downstream_metrics", {}) or {},
        getattr(run, "metrics", {}) or {},
    ):
        value = None
        if isinstance(candidate, dict):
            value = candidate.get("sign_match_rate")
            if value is None:
                nested = candidate.get("downstream") if isinstance(candidate.get("downstream"), dict) else {}
                if nested:
                    value = nested.get("sign_match_rate")
        coerced = _coerce_numeric(value)
        if coerced is not None:
            return coerced
    return None


def _build_metric_table(items: List[tuple[str, Any]]) -> Optional[str]:
    """Convert a list of metric items into an HTML table."""

    if not items:
        return None
    rows: List[Dict[str, Any]] = []
    for label, value in items:
        formatted = _format_metric_cell(value)
        cell = formatted if formatted != "" else ("" if value is None else value)
        rows.append({"metric": label, "value": cell})
    df = pd.DataFrame(rows)
    df["value"] = df["value"].astype(str).replace({"nan": "", "None": ""})
    return df.to_html(index=False, escape=False, border=0)


def _downstream_metric_items(metrics: Optional[Dict[str, Any]]) -> List[tuple[str, Any]]:
    """Select downstream metric entries for display."""

    if not isinstance(metrics, dict) or not metrics:
        return []
    items: List[tuple[str, Any]] = []
    if "sign_match_rate" in metrics:
        items.append(("sign_match_rate", metrics.get("sign_match_rate")))
    for key, value in metrics.items():
        if key == "sign_match_rate":
            continue
        items.append((key, value))
    return items


def _privacy_metric_items(metrics: Optional[Dict[str, Any]]) -> List[tuple[str, Any]]:
    """Select a compact set of privacy metrics for per-model display."""

    summary = _privacy_metrics_summary(metrics)
    ordered = [
        ("n_real", summary.get("n_real")),
        ("n_synth", summary.get("n_synth")),
        ("exact_overlap_rate", summary.get("exact_overlap_rate")),
        ("near_duplicate_rate_eps", summary.get("near_duplicate_rate_eps")),
        ("nn_distance_mean", summary.get("nn_distance_mean")),
        ("k_min", summary.get("k_min")),
        ("k_pct_lt5", summary.get("k_pct_lt5")),
        ("k_map", summary.get("k_map")),
        ("rare_qi_reproduction_rate", summary.get("rare_qi_reproduction_rate")),
        ("identifiability_score", summary.get("identifiability_score")),
        ("delta_presence", summary.get("delta_presence")),
    ]
    return [(label, value) for label, value in ordered if value is not None]


def _build_per_variable_table(per_variable_path: Optional[Path]) -> Optional[str]:
    """Render a concise per-variable fidelity table."""

    if per_variable_path is None or not per_variable_path.exists():
        return None
    try:
        per_var = pd.read_csv(per_variable_path)
    except Exception:
        return None
    columns = [col for col in ("variable", "type", "KS", "W1", "JSD") if col in per_var.columns]
    if not columns:
        return None
    per_var = per_var[columns].head(10).copy()
    for col in ("KS", "W1", "JSD"):
        if col in per_var:
            per_var[col] = per_var[col].apply(_format_metric_cell)
    return per_var.fillna("").to_html(index=False, escape=False, border=0)


def _build_metasyn_gmf_table(run_dir: Path) -> Optional[str]:
    """Render a GMF summary table for MetaSyn models."""

    gmf_path = run_dir / "metasyn_gmf.json"
    if not gmf_path.exists():
        return None
    try:
        payload = json.loads(gmf_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    vars_block = payload.get("vars")
    if not isinstance(vars_block, list):
        return None
    rows: List[Dict[str, str]] = []
    for entry in vars_block:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        dist = entry.get("distribution") if isinstance(entry.get("distribution"), dict) else {}
        dist_label = dist.get("name") or dist.get("class_name")
        if name:
            rows.append({"variable": str(name), "distribution": str(dist_label or "")})
    if not rows:
        return None
    df = pd.DataFrame(rows)
    return df.to_html(index=False, escape=False, border=0)


def _build_missingness_table(summary: Optional[Dict[str, Any]]) -> Optional[str]:
    """Create a markdown table describing modeled missingness rates."""

    if not summary:
        return None

    rows = summary.get("rows") or []
    if not rows:
        return None

    out = pd.DataFrame(rows)
    if "missing_rate" not in out.columns or "column" not in out.columns:
        return None

    out = out.sort_values("missing_rate", ascending=False).reset_index(drop=True)
    out["missing_rate"] = out["missing_rate"].round(4)
    out["missing_pct"] = (out["missing_rate"] * 100).round(2)
    out.rename(
        columns={
            "column": "Column",
            "missing_rate": "Missing rate",
            "missing_pct": "Missing %",
        },
        inplace=True,
    )
    return _dataframe_to_markdown(out[["Column", "Missing rate", "Missing %"]], index=False)


def _prepare_model_rows(model_runs: Iterable[ModelRun], base_dir: Path) -> List[_ModelRow]:
    """Convert model runs into template-friendly rows."""

    prepared: List[_ModelRow] = []
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

        per_variable_table = _build_per_variable_table(run.per_variable_csv)
        downstream_table = _build_metric_table(_downstream_metric_items(run.downstream_metrics))
        privacy_table = _build_metric_table(_privacy_metric_items(run.privacy_metrics))
        structure_table = _build_metasyn_gmf_table(run.run_dir) if run.backend == "metasyn" else None

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


def _relative_path(target: Optional[Path], base_dir: Path) -> Optional[str]:
    """Return a relative path when the target exists."""

    if target is None:
        return None
    target_path = Path(target)
    if not target_path.exists():
        return None
    return os.path.relpath(target_path, start=base_dir)


def _provider_link(
    dataset_provider: Optional[str], dataset_provider_id: Optional[int]
) -> Optional[Dict[str, str]]:
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


def _dataframe_to_markdown(df: pd.DataFrame, *, index: bool) -> str:
    """Convert a dataframe to Markdown."""

    return df.to_markdown(index=index)


def _normalise_scalar(value: Any) -> str:
    """Convert scalar values into canonical string keys for lookups."""

    if isinstance(value, Integral):
        return str(int(value))
    if isinstance(value, Real) and not isinstance(value, bool):
        value_f = float(value)
        if value_f.is_integer():
            return str(int(value_f))
        text = f"{value_f}"
        stripped = text.rstrip("0").rstrip(".")
        return stripped or text
    text = str(value)
    if text.endswith(".0"):
        text = text.rstrip("0").rstrip(".")
    return text.strip()


def _format_codebook_value(value_key: str, codebook: Optional[Dict[str, str]]) -> str:
    """Return a user-friendly value label leveraging codebook metadata."""

    if not value_key:
        return "(missing)"
    if codebook:
        label = codebook.get(value_key)
        if label:
            return f"{label} [{value_key}]"
    return value_key


def _select_positive_key(keys: Sequence[str]) -> str:
    """Pick a representative positive key for binary distributions."""

    for key in keys:
        if key.strip().lower() in {"true", "1", "yes", "y", "t"}:
            return key
    numeric_candidates: List[tuple[float, str]] = []
    for key in keys:
        try:
            numeric_candidates.append((float(key), key))
        except Exception:
            continue
    if numeric_candidates:
        return max(numeric_candidates)[1]
    return keys[0] if keys else ""


def _iter_columns(metadata: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Yield column dictionaries from a SemMap-style metadata payload."""

    if not isinstance(metadata, dict):
        return []
    schema = (
        metadata.get("datasetSchema")
        or metadata.get("dsv:datasetSchema")
        or {}
    )
    columns = (
        schema.get("columns")
        or schema.get("dsv:column")
        or []
    )
    if isinstance(columns, list):
        return columns
    if columns:
        return [columns]
    return []


def _extract_codebook_labels(metadata: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Return per-column mappings from raw codes to human-readable labels."""

    codebooks: Dict[str, Dict[str, str]] = {}
    for column in _iter_columns(metadata):
        name = column.get("name") or column.get("schema:name")
        if not isinstance(name, str) or not name:
            continue
        column_prop = column.get("columnProperty") or column.get("dsv:columnProperty")
        if not isinstance(column_prop, dict):
            continue
        codebook = column_prop.get("hasCodeBook") or column_prop.get("dsv:hasCodeBook")
        if not isinstance(codebook, dict):
            continue
        concepts = codebook.get("hasTopConcept") or codebook.get("dsv:hasTopConcept")
        if not concepts:
            continue
        if not isinstance(concepts, list):
            concepts = [concepts]
        mapping: Dict[str, str] = {}
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            notation = concept.get("notation")
            label = (
                concept.get("prefLabel")
                or concept.get("label")
                or concept.get("titles")
            )
            if notation is None or label is None:
                continue
            key = _normalise_scalar(notation)
            if not key:
                continue
            mapping[key] = str(label).strip()
        if mapping:
            codebooks[name] = mapping
    return codebooks


def _build_overview_table(
    *,
    dataset_name: str,
    provider_link: Optional[Dict[str, str]],
    semmap_json_name: Optional[str],
    semmap_html_name: Optional[str],
    num_rows: int,
    num_cols: int,
    num_disc: int,
    num_cont: int,
    missingness_summary: Optional[Dict[str, Any]],
) -> str:
    """Construct a compact overview table for the report header."""

    rows: List[Dict[str, str]] = [
        {"Metric": "Dataset", "Value": dataset_name},
        {"Metric": "Rows", "Value": f"{num_rows:,}"},
        {"Metric": "Columns", "Value": f"{num_cols:,}"},
        {"Metric": "Discrete", "Value": f"{num_disc:,}"},
        {"Metric": "Continuous", "Value": f"{num_cont:,}"},
    ]

    if provider_link:
        rows.insert(
            1,
            {
                "Metric": "Source",
                "Value": f"[{provider_link['text']}]({provider_link['url']})",
            },
        )

    semmap_links: List[str] = []
    if semmap_json_name:
        semmap_links.append(f"[SemMap JSON-LD]({semmap_json_name})")
    if semmap_html_name:
        semmap_links.append(f"[SemMap HTML]({semmap_html_name})")
    if semmap_links:
        rows.append({"Metric": "SemMap", "Value": "<br />".join(semmap_links)})

    if missingness_summary:
        modeled = missingness_summary.get("nonzero_count", 0)
        total = missingness_summary.get("total_columns", num_cols)
        random_state = missingness_summary.get("random_state")
        label = f"modeled {modeled} of {total}"
        if random_state is not None:
            label = f"{label} (seed {random_state})"
        rows.append({"Metric": "Missingness", "Value": label})
    else:
        rows.append({"Metric": "Missingness", "Value": "Not modeled"})

    return _dataframe_to_markdown(pd.DataFrame(rows), index=False)
