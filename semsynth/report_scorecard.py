"""The scorecard of a dataset report, and the smaller pieces of the report that read the evaluation files.

The scorecard puts the scores of every model in one table, between the two reference tables that give them a scale: on the
left the floor (columns drawn independently, so no relation survives) and on the right the ceiling (rows of the real
training data). With a cross-validation each cell is the mean over the folds with its interval; otherwise it is the score of
the one split with its bootstrap interval or noise range.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .models import ModelRun

# Each entry is the score, its label and what is better.
SCORES = (
    ("disc_jsd_mean", "Discrete columns: Jensen-Shannon distance", "lower"),
    ("cont_ks_mean", "Numeric columns: Kolmogorov-Smirnov distance", "lower"),
    ("pairwise_tvd_mean", "Relations between column pairs: distance", "lower"),
    ("classifier_auc", "Can a classifier tell real from synthetic rows? (AUC)", "0.5 means it cannot"),
    ("utility", "Prediction of the target: model trained on these rows, tested on real rows", "higher"),
    ("utility_recovered", "Share of the real data's prediction gain that is kept", "higher, 1 is the real data"),
    ("exact_match_rate", "Rows that copy a real row", "lower"),
    ("dcr_median", "Median distance to the closest real row", "higher"),
    ("dcr_below_holdout_p05", "Rows closer to a real row than 95% of unseen real rows are", "lower"),
)
FLOOR, CEILING = "independent_marginals", "real_sample"


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value) else None


def _format(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


def _cell(value: Any, interval: Any = None, noise: Any = None) -> str:
    """A score with its interval in brackets, or with its noise range in parentheses (a distance between samples)."""
    number = _number(value)
    if number is None:
        return ""
    pair = interval if isinstance(interval, list) and len(interval) == 2 else None
    if pair and all(_number(x) is not None for x in pair):
        return f"{_format(number)} [{_format(pair[0])}, {_format(pair[1])}]"
    pair = noise.get("null_interval") if isinstance(noise, Mapping) else None
    if isinstance(pair, list) and len(pair) == 2 and all(_number(x) is not None for x in pair):
        return f"{_format(number)} (noise {_format(pair[0])} to {_format(pair[1])})"
    return _format(number)


def _from_folds(cv: Mapping[str, Any], table: str, score: str) -> str:
    entry = ((cv.get("scores") or {}).get(table) or {}).get(score)
    return _cell(entry.get("mean"), entry.get("interval")) if isinstance(entry, Mapping) else ""


def _from_split(run: ModelRun, table: str, score: str) -> str:
    """The score of the one split: the utility record for the utility scores, the reference comparison for the others."""
    utility = run.metrics.get("utility") or {}
    if score in ("utility", "utility_recovered"):
        if utility.get("status") != "ok":
            return ""
        if score == "utility_recovered":
            return _cell(utility.get("recovered"), (utility.get("intervals") or {}).get("recovered")) if table == "synthetic" else ""
        return _cell((utility.get("scores") or {}).get(table), (utility.get("intervals") or {}).get(table))
    record = ((run.baselines_metrics or {}).get("scores") or {}).get(table) or {}
    return _cell(record.get(score), (record.get("intervals") or {}).get(score), (record.get("null") or {}).get(score))


def _value(run: ModelRun, table: str, score: str) -> str:
    cv = run.metrics.get("cv")
    return _from_folds(cv, table, score) if isinstance(cv, Mapping) and cv.get("scores") else _from_split(run, table, score)


def scorecard_rows(model_runs: Sequence[ModelRun]) -> list[dict[str, str]]:
    """One row per score that any model has: the floor, each model, and the ceiling. Rows without a value are left out."""
    runs = sorted(model_runs, key=lambda r: (r.backend, r.name))
    rows = []
    for score, label, better in SCORES:
        row = {"Score": label, "Better": better, "Floor": _first(runs, FLOOR, score)}
        row.update({run.name: _value(run, "synthetic", score) for run in runs})
        row["Ceiling"] = _first(runs, CEILING, score)
        if any(row[run.name] for run in runs):
            rows.append(row)
    return rows


def _first(runs: Sequence[ModelRun], table: str, score: str) -> str:
    """The reference score of the first model that has one: the references do not depend on the model."""
    return next((v for v in (_value(run, table, score) for run in runs) if v), "")


def scorecard_note(model_runs: Sequence[ModelRun]) -> str | None:
    """One sentence on how the scores were made: the folds and their sizes, or the single split."""
    for run in model_runs:
        cv = run.metrics.get("cv")
        if isinstance(cv, Mapping) and cv.get("folds"):
            return (
                f"Each cell is the mean over {cv['folds']} folds, with the interval in brackets "
                f"({cv.get('train_rows')} rows to train and {cv.get('test_rows')} unseen rows to test in each fold)."
            )
    return None


def build_scorecard(model_runs: Sequence[ModelRun] | None) -> str | None:
    """Markdown table of the scores of all models between the floor and the ceiling, or ``None`` if there are none."""
    import pandas as pd

    rows = scorecard_rows(model_runs or [])
    if not rows:
        return None
    frame = pd.DataFrame(rows).rename(columns={"Floor": "Floor (independent columns)", "Ceiling": "Ceiling (real rows)"})
    return frame.to_markdown(index=False)


def joint_items(joint: Mapping[str, Any] | None) -> list[tuple[str, Any]]:
    """The facts of the joint fidelity of one model, for a two-column table."""
    if not isinstance(joint, Mapping) or not joint:
        return []
    pairwise, classifier = joint.get("pairwise") or {}, joint.get("classifier") or {}
    items: list[tuple[str, Any]] = []
    if pairwise.get("status") == "ok":
        items += [
            ("Column pairs compared", pairwise.get("n_pairs")),
            ("Mean distance between pair tables", _cell(pairwise.get("tvd_mean"), None, pairwise.get("null"))),
            ("Largest distance", pairwise.get("tvd_max")),
        ]
        worst = pairwise.get("worst_pairs") or []
        items += [(f"Pair {' and '.join(p['columns'])}", p["tvd"]) for p in worst[:3] if isinstance(p, Mapping) and p.get("columns")]
    if classifier.get("status") == "ok":
        items.append(("Real-vs-synthetic classifier AUC", _cell(classifier.get("auc"), classifier.get("auc_interval"))))
    elif classifier.get("reason"):
        items.append(("Real-vs-synthetic classifier", classifier["reason"]))
    return items


def structure_summary(run_dir: Path) -> str | None:
    """What the model learned about the dependencies between columns, from ``structure.graphml``, as a sentence or list."""
    path = run_dir / "structure.graphml"
    if not path.exists():
        return None
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8"))
    except (ET.ParseError, OSError):
        return None
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    names = {n.get("id"): n.get("id") for n in root.iter(f"{ns}node")}
    edges = [(e.get("source"), e.get("target")) for e in root.iter(f"{ns}edge")]
    if not names:
        return None
    if not edges:
        return "The model learned no dependencies between the columns: every column is drawn on its own."
    listed = "\n".join(f"- {names.get(a, a)} → {names.get(b, b)}" for a, b in edges)
    return f"The model learned {len(edges)} dependencies between {len(names)} columns:\n\n{listed}"


def citation_text(value: Any) -> str | None:
    """A citation as text. A string stays as it is; a schema.org article becomes ``Authors (year). Title. Venue. URL``."""
    if not value:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "; ".join(t for t in (citation_text(v) for v in value) if t) or None
    if not isinstance(value, Mapping):
        return str(value)
    authors = value.get("schema:author") or value.get("author")
    authors = ", ".join(map(str, authors)) if isinstance(authors, list) else authors
    year = value.get("schema:datePublished") or value.get("datePublished")
    venue = value.get("schema:isPartOf") or value.get("isPartOf")
    parts = [
        f"{authors} ({year})." if authors and year else (f"{authors}." if authors else None),
        f"{value['title']}." if value.get("title") else None,
        f"{venue}." if isinstance(venue, str) else None,
        value.get("url") or value.get("@id"),
    ]
    return " ".join(str(p) for p in parts if p) or None


def documentation_items(text: Any) -> list[str]:
    """The lines of a source's own documentation of its variables, one item each (empty lines dropped)."""
    if not isinstance(text, str):
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]
