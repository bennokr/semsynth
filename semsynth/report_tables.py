"""Tables of the dataset report: variable summary, fidelity, privacy, downstream, missingness, overview.

Each function takes what it needs and returns Markdown (or ``None`` when there is nothing to show).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Sequence
from numbers import Integral, Real
from pathlib import Path
from typing import Any

import pandas as pd

from .codebook import Codebook
from .models import ModelRun


def format_dist(
    col: pd.Series,
    cont_cols: list[str],
    *,
    codebook: dict[str, str] | None = None,
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
    entries: list[tuple[str, str, int]] = []
    for value, cnt in vc.items():
        key = normalise_scalar(value)
        display = format_codebook_value(key, codebook)
        entries.append((key, display, int(cnt)))
    if len(entries) == 2:
        keys = [key for key, _, _ in entries]
        pos_key = select_positive_key(keys)
        counts = {key: cnt for key, _, cnt in entries}
        n_true = counts.get(pos_key, 0)
        pct = 100.0 * (n_true / total)
        display = format_codebook_value(pos_key, codebook)
        return f"{display}: {n_true} ({pct:.2f}%)"
    parts = []
    for idx, (_, display, cnt) in enumerate(entries):
        pct = 100.0 * (cnt / total)
        if idx < top_n:
            parts.append(f"{display}: {cnt} ({pct:.2f}%)")
    if len(entries) > top_n:
        parts.append(f"… (+{len(entries) - top_n} more)")
    return "<br />".join(parts)


def build_variable_summary(
    df: pd.DataFrame,
    cont_cols: Iterable[str],
    *,
    declared_types: dict | None,
    inferred_types: dict | None,
    variable_descriptions: dict | None,
    codebook_labels: dict[str, dict[str, str]] | None,
) -> str:
    """Create the Markdown table summarising variables."""

    cont_list = list(dict.fromkeys(cont_cols))
    var_rows = [
        {
            "variable": column,
            "dist": format_dist(
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

    return dataframe_to_markdown(merged, index=False)


def coerce_numeric(value: Any) -> float | None:
    """Coerce a value to a finite float when possible."""

    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def format_metric_cell(value: Any) -> str:
    """Render metric values with consistent rounding."""

    num = coerce_numeric(value)
    if num is None:
        return ""
    if num.is_integer():
        return str(int(num))
    return f"{num:.4f}".rstrip("0").rstrip(".")


def build_fidelity_table(*, model_runs: Sequence[ModelRun] | None) -> str | None:
    """Create the markdown representation of the fidelity table."""

    runs = sorted(model_runs or [], key=lambda run: (run.backend, run.name))
    if not runs:
        return None

    rows: list[dict[str, Any]] = []
    for run in runs:
        summary = run.metrics.get("summary", {}) if isinstance(run.metrics, dict) else {}
        rows.append(
            {
                "model": run.name,
                "backend": run.backend,
                "disc_jsd_mean": format_metric_cell(summary.get("disc_jsd_mean")),
                "disc_jsd_median": format_metric_cell(summary.get("disc_jsd_median")),
                "cont_ks_mean": format_metric_cell(summary.get("cont_ks_mean")),
                "cont_w1_mean": format_metric_cell(summary.get("cont_w1_mean")),
                "downstream_sign_match": format_metric_cell(extract_downstream_sign_match(run)),
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
    return dataframe_to_markdown(out, index=False)


def privacy_metrics_summary(metrics: dict[str, Any] | None) -> dict[str, Any]:
    """Pick a consistent subset of privacy metrics for tabular reporting."""

    if not isinstance(metrics, dict) or not metrics:
        return {}
    nn_stats = metrics.get("nn_distance_stats", {})
    nn_mean = nn_stats.get("mean") if isinstance(nn_stats, dict) else None
    summary = {
        "n_real": coerce_numeric(metrics.get("n_real")),
        "n_synth": coerce_numeric(metrics.get("n_synth")),
        "exact_overlap_rate": coerce_numeric(metrics.get("exact_overlap_rate")),
        "near_duplicate_rate_eps": coerce_numeric(metrics.get("near_duplicate_rate_eps")),
        "nn_distance_mean": coerce_numeric(nn_mean),
        "k_min": coerce_numeric(metrics.get("k_min")),
        "k_pct_lt5": coerce_numeric(metrics.get("k_pct_lt5")),
        "k_map": coerce_numeric(metrics.get("k_map")),
        "rare_qi_reproduction_rate": coerce_numeric(metrics.get("rare_qi_reproduction_rate")),
        "identifiability_score": coerce_numeric(metrics.get("identifiability_score")),
        "delta_presence": coerce_numeric(metrics.get("delta_presence")),
    }
    values = [val for key, val in summary.items() if key not in ("n_real", "n_synth")]
    if not any(val is not None for val in values):
        return {}
    return summary


def build_privacy_table(*, model_runs: Sequence[ModelRun] | None) -> str | None:
    """Create the markdown representation of the dataset-level privacy table."""

    runs = sorted(model_runs or [], key=lambda run: (run.backend, run.name))
    rows: list[dict[str, Any]] = []
    for run in runs:
        summary = privacy_metrics_summary(run.privacy_metrics)
        if not summary:
            continue
        row = {"model": run.name, "backend": run.backend}
        row.update({key: format_metric_cell(val) for key, val in summary.items()})
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
    return dataframe_to_markdown(out, index=False)


def extract_downstream_sign_match(run: ModelRun) -> float | None:
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
        coerced = coerce_numeric(value)
        if coerced is not None:
            return coerced
    return None


def build_metric_table(items: list[tuple[str, Any]]) -> str | None:
    """Convert a list of metric items into an HTML table."""

    if not items:
        return None
    rows: list[dict[str, Any]] = []
    for label, value in items:
        formatted = format_metric_cell(value)
        cell = formatted if formatted != "" else ("" if value is None else value)
        rows.append({"metric": label, "value": cell})
    df = pd.DataFrame(rows)
    df["value"] = df["value"].astype(str).replace({"nan": "", "None": ""})
    return df.to_html(index=False, escape=False, border=0)


def downstream_metric_items(metrics: dict[str, Any] | None) -> list[tuple[str, Any]]:
    """Select downstream metric entries for display."""

    if not isinstance(metrics, dict) or not metrics:
        return []
    items: list[tuple[str, Any]] = []
    if "sign_match_rate" in metrics:
        items.append(("sign_match_rate", metrics.get("sign_match_rate")))
    for key, value in metrics.items():
        if key == "sign_match_rate":
            continue
        items.append((key, value))
    return items


def privacy_metric_items(metrics: dict[str, Any] | None) -> list[tuple[str, Any]]:
    """Select a compact set of privacy metrics for per-model display."""

    summary = privacy_metrics_summary(metrics)
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


def build_per_variable_table(per_variable_path: Path | None) -> str | None:
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
            per_var[col] = per_var[col].apply(format_metric_cell)
    return per_var.fillna("").to_html(index=False, escape=False, border=0)


def build_metasyn_gmf_table(run_dir: Path) -> str | None:
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
    rows: list[dict[str, str]] = []
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


def build_missingness_table(summary: dict[str, Any] | None) -> str | None:
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
    return dataframe_to_markdown(out[["Column", "Missing rate", "Missing %"]], index=False)


def dataframe_to_markdown(df: pd.DataFrame, *, index: bool) -> str:
    """Convert a dataframe to Markdown."""

    return df.to_markdown(index=index)


def normalise_scalar(value: Any) -> str:
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


def format_codebook_value(value_key: str, codebook: dict[str, str] | None) -> str:
    """Return a user-friendly value label leveraging codebook metadata."""

    if not value_key:
        return "(missing)"
    if codebook:
        label = codebook.get(value_key)
        if label:
            return f"{label} [{value_key}]"
    return value_key


def select_positive_key(keys: Sequence[str]) -> str:
    """Pick a representative positive key for binary distributions."""

    for key in keys:
        if key.strip().lower() in {"true", "1", "yes", "y", "t"}:
            return key
    numeric_candidates: list[tuple[float, str]] = []
    for key in keys:
        try:
            numeric_candidates.append((float(key), key))
        except Exception:
            continue
    if numeric_candidates:
        return max(numeric_candidates)[1]
    return keys[0] if keys else ""


def extract_codebook_labels(metadata: Any) -> dict[str, dict[str, str]]:
    """Return per-column mappings from raw codes to human-readable labels."""

    codebooks: dict[str, dict[str, str]] = {}
    for column in Codebook.read(metadata).columns:
        mapping = {
            normalise_scalar(value["code"]): value["label"].strip()
            for value in column.get("values", [])
            if value.get("label") and normalise_scalar(value["code"])
        }
        if mapping:
            codebooks[column["name"]] = mapping
    return codebooks


def build_overview_table(
    *,
    dataset_name: str,
    provider_link: dict[str, str] | None,
    codebook_json_name: str | None,
    codebook_html_name: str | None,
    num_rows: int,
    num_cols: int,
    num_disc: int,
    num_cont: int,
    missingness_summary: dict[str, Any] | None,
) -> str:
    """Construct a compact overview table for the report header."""

    rows: list[dict[str, str]] = [
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

    codebook_links: list[str] = []
    if codebook_json_name:
        codebook_links.append(f"[Codebook JSON-LD]({codebook_json_name})")
    if codebook_html_name:
        codebook_links.append(f"[Codebook HTML]({codebook_html_name})")
    if codebook_links:
        rows.append({"Metric": "Codebook", "Value": "<br />".join(codebook_links)})

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

    return dataframe_to_markdown(pd.DataFrame(rows), index=False)
