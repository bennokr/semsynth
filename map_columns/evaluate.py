#!/usr/bin/env python3
"""Evaluate SSSOM mappings against a gold standard."""

from __future__ import annotations

import csv
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import defopt

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MappingRow:
    """Minimal SSSOM row representation for evaluation."""

    subject_id: str
    object_id: str
    confidence: float = 1.0


@dataclass
class MetricResults:
    """Container for aggregate evaluation metrics."""

    micro_precision: float
    micro_recall: float
    micro_f1: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    mean_average_precision: float
    ndcg: float

    def as_dict(self) -> Dict[str, float]:
        """Convert the metrics to a plain dictionary."""

        return {
            "micro_precision": self.micro_precision,
            "micro_recall": self.micro_recall,
            "micro_f1": self.micro_f1,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "map": self.mean_average_precision,
            "ndcg": self.ndcg,
        }


def _read_sssom_rows(path: Path) -> List[MappingRow]:
    rows: List[MappingRow] = []
    with path.open("r", encoding="utf-8") as handle:
        filtered = [line for line in handle if not line.lstrip().startswith("#")]
    if not filtered:
        return rows
    reader = csv.DictReader(filtered, delimiter="\t")
    for raw in reader:
        subject_id = (raw.get("subject_id") or "").strip()
        object_id = (raw.get("object_id") or "").strip()
        if not subject_id or not object_id:
            continue
        confidence_raw = raw.get("confidence", "")
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 1.0
        rows.append(MappingRow(subject_id=subject_id, object_id=object_id, confidence=confidence))
    return rows


def _group_by_subject(rows: Iterable[MappingRow]) -> Dict[str, List[MappingRow]]:
    grouped: Dict[str, List[MappingRow]] = {}
    for row in rows:
        grouped.setdefault(row.subject_id, []).append(row)
    for values in grouped.values():
        values.sort(key=lambda item: item.confidence, reverse=True)
    return grouped


def _set_by_subject(rows: Iterable[MappingRow]) -> Dict[str, set[str]]:
    grouped: Dict[str, set[str]] = {}
    for row in rows:
        grouped.setdefault(row.subject_id, set()).add(row.object_id)
    return grouped


def _safe_div(num: float, denom: float) -> float:
    return num / denom if denom else 0.0


def _average_precision(preds: List[MappingRow], gold: set[str]) -> float:
    if not gold:
        return 0.0
    hits = 0
    precision_sum = 0.0
    seen: set[str] = set()
    for idx, row in enumerate(preds, start=1):
        if row.object_id in gold and row.object_id not in seen:
            hits += 1
            precision_sum += hits / idx
            seen.add(row.object_id)
    return precision_sum / len(gold)


def _ndcg(preds: List[MappingRow], gold: set[str]) -> float:
    if not gold:
        return 0.0
    dcg = 0.0
    for idx, row in enumerate(preds, start=1):
        if row.object_id in gold:
            dcg += 1.0 / math.log2(idx + 1)
    ideal_len = len(gold)
    idcg = sum(1.0 / math.log2(idx + 1) for idx in range(1, ideal_len + 1))
    return _safe_div(dcg, idcg)


def compute_metrics(gold_rows: List[MappingRow], pred_rows: List[MappingRow]) -> MetricResults:
    gold_by_subject = _set_by_subject(gold_rows)
    pred_by_subject = _group_by_subject(pred_rows)
    all_subjects = sorted(set(gold_by_subject.keys()) | set(pred_by_subject.keys()))

    micro_tp = micro_fp = micro_fn = 0
    macro_precisions: List[float] = []
    macro_recalls: List[float] = []
    macro_f1s: List[float] = []

    ap_values: List[float] = []
    ndcg_values: List[float] = []

    for subject in all_subjects:
        gold_set = gold_by_subject.get(subject, set())
        preds = pred_by_subject.get(subject, [])
        pred_objects = [row.object_id for row in preds]

        tp = len([obj for obj in pred_objects if obj in gold_set])
        fp = len(pred_objects) - tp
        fn = len(gold_set - set(pred_objects))

        micro_tp += tp
        micro_fp += fp
        micro_fn += fn

        precision_s = _safe_div(tp, len(pred_objects))
        recall_s = _safe_div(tp, len(gold_set))
        f1_s = (
            2 * precision_s * recall_s / (precision_s + recall_s)
            if precision_s and recall_s
            else 0.0
        )
        macro_precisions.append(precision_s)
        macro_recalls.append(recall_s)
        macro_f1s.append(f1_s)

        if gold_set:
            ap_values.append(_average_precision(preds, gold_set))
            ndcg_values.append(_ndcg(preds, gold_set))

    micro_precision = _safe_div(micro_tp, micro_tp + micro_fp)
    micro_recall = _safe_div(micro_tp, micro_tp + micro_fn)
    micro_f1 = (
        2 * micro_precision * micro_recall / (micro_precision + micro_recall)
        if micro_precision and micro_recall
        else 0.0
    )

    macro_precision = sum(macro_precisions) / len(macro_precisions) if macro_precisions else 0.0
    macro_recall = sum(macro_recalls) / len(macro_recalls) if macro_recalls else 0.0
    macro_f1 = sum(macro_f1s) / len(macro_f1s) if macro_f1s else 0.0

    map_score = sum(ap_values) / len(ap_values) if ap_values else 0.0
    ndcg_score = sum(ndcg_values) / len(ndcg_values) if ndcg_values else 0.0

    return MetricResults(
        micro_precision=micro_precision,
        micro_recall=micro_recall,
        micro_f1=micro_f1,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        mean_average_precision=map_score,
        ndcg=ndcg_score,
    )


def _format_metrics(metrics: MetricResults) -> str:
    return (
        f"micro P/R/F1={metrics.micro_precision:.4f}/"
        f"{metrics.micro_recall:.4f}/{metrics.micro_f1:.4f}, "
        f"macro P/R/F1={metrics.macro_precision:.4f}/{metrics.macro_recall:.4f}/"
        f"{metrics.macro_f1:.4f}, MAP={metrics.mean_average_precision:.4f}, "
        f"nDCG={metrics.ndcg:.4f}"
    )


def main(
    gold_tsv: Path,
    predictions: Sequence[Path],
    *,
    output: Optional[Path] = None,
    verbose: bool = False,
) -> None:
    """Compare one or more SSSOM files against a gold standard.

    Args:
        gold_tsv: Path to the gold-standard SSSOM TSV file.
        predictions: One or more SSSOM TSV files to evaluate.
        output: Optional JSON path where metrics will be written.
        verbose: When ``True`` enable INFO-level logging.
    """

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    if not predictions:
        raise SystemExit("At least one prediction file must be provided.")

    gold_rows = _read_sssom_rows(gold_tsv)
    if not gold_rows:
        raise SystemExit(f"No gold mappings found in {gold_tsv}")

    summary: Dict[str, Dict[str, float]] = {}

    for pred_path in predictions:
        pred_rows = _read_sssom_rows(pred_path)
        metrics = compute_metrics(gold_rows, pred_rows)
        summary[pred_path.name] = metrics.as_dict()
        print(f"{pred_path.name}: {_format_metrics(metrics)}")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        LOGGER.info("Wrote metrics to %s", output)


if __name__ == "__main__":
    defopt.run(main)
