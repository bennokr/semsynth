"""k-fold cross-validation of a generator, and intervals for the scores it gives.

One split gives one score, and a score from 20 held-out rows says little. With k folds, a generator is fitted k times,
each time on k - 1 folds, and scored on the fold it did not see. The k scores of a metric are summarized by their mean and
an interval.

The k scores are not independent, because any two training sets share most of their rows. The usual interval,
``mean ± t · sd / sqrt(k)``, is therefore too narrow. This module uses the corrected resampled t interval of
Nadeau and Bengio (2003, *Machine Learning* 52), whose variance is ``(1/k + n_test / n_train) · sd²``.
The interval says how much the score would change with other rows from the same population. It does not include the
randomness of the generator's seed: run one model with several seeds for that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

METHOD = "k-fold cross-validation; mean with the corrected resampled t interval of Nadeau and Bengio (2003)"
# The range that a score can take, so that an interval never leaves it (AUC and R-squared are at most 1).
BOUNDS: dict[str, tuple[float, float]] = {
    "disc_jsd_mean": (0.0, 1.0),
    "cont_ks_mean": (0.0, 1.0),
    "pairwise_tvd_mean": (0.0, 1.0),
    "classifier_auc": (0.0, 1.0),
    "exact_match_rate": (0.0, 1.0),
    "dcr_median": (0.0, 1.0),
    "dcr_below_holdout_p05": (0.0, 1.0),
    "utility": (float("-inf"), 1.0),
}
MIN_GAP = 0.02  # the smallest ceiling minus floor for which the share of the gain is reported


def fold_splits(
    frame: pd.DataFrame, k: int, seed: int, stratify: pd.Series | None = None
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """``k`` (train, test) pairs with disjoint test folds that cover every row.

    Args:
        frame: The rows to split.
        k: Number of folds, at least 2 and at most the number of rows.
        seed: Seed of the shuffle.
        stratify: A categorical column; if every class has at least ``k`` rows, the classes are spread over the folds.
    """
    from sklearn.model_selection import KFold, StratifiedKFold

    if not 2 <= k <= len(frame):
        raise ValueError(f"k must be between 2 and the number of rows ({len(frame)}), not {k}")
    labels = None if stratify is None else stratify.astype(str).to_numpy()
    if (
        labels is not None
        and min(len(frame), *(int((labels == c).sum()) for c in set(labels))) >= k
    ):
        pairs = StratifiedKFold(k, shuffle=True, random_state=seed).split(frame, labels)
    else:
        pairs = KFold(k, shuffle=True, random_state=seed).split(frame)
    return [
        (frame.iloc[a].reset_index(drop=True), frame.iloc[b].reset_index(drop=True))
        for a, b in pairs
    ]


def corrected_interval(
    values: Sequence[float],
    n_train: int,
    n_test: int,
    *,
    level: float = 0.95,
    bounds: tuple[float, float] = (float("-inf"), float("inf")),
) -> dict[str, Any]:
    """Mean, standard deviation and the corrected resampled t interval of the scores of the folds, kept within ``bounds``."""
    import numpy as np
    from scipy import stats

    array = np.asarray([v for v in values if v is not None], dtype=float)
    array = array[~np.isnan(array)]
    if len(array) == 0:
        return {"n": 0}
    out: dict[str, Any] = {"n": len(array), "mean": float(array.mean())}
    if len(array) < 2:
        return out
    sd = float(array.std(ddof=1))
    half = float(
        stats.t.ppf((1 + level) / 2, len(array) - 1)
        * np.sqrt((1 / len(array) + n_test / n_train) * sd**2)
    )
    return {**out, "sd": sd, "interval": [max(bounds[0], out["mean"] - half), min(bounds[1], out["mean"] + half)]}


def fold_record(
    references: Mapping[str, Any], utility: Mapping[str, Any] | None
) -> dict[str, dict[str, float]]:
    """The scalar scores of one fold, by table and metric: the reference scores and the utility."""
    record: dict[str, dict[str, float]] = {}
    for table, scores in (references.get("scores") or {}).items():
        record[table] = {
            k: v
            for k, v in scores.items()
            if isinstance(v, int | float) and not isinstance(v, bool)
        }
    if utility and utility.get("status") == "ok":
        for table, value in utility["scores"].items():
            record.setdefault(table, {})["utility"] = value
    return record


def _recovered(scores: Mapping[str, Mapping[str, Any]]) -> float | None:
    """The share of the prediction gain of real data over the floor that the synthetic table keeps, from the mean scores.

    The mean of the scores is used, not the mean of one share per fold: with a few folds the ceiling and the floor of one
    fold can be close, and their ratio is then unstable. No interval is given for the ratio.
    """
    try:
        synthetic, ceiling, floor = (scores[t]["utility"]["mean"] for t in ("synthetic", "real_sample", "independent_marginals"))
    except KeyError:
        return None
    return (synthetic - floor) / (ceiling - floor) if ceiling - floor >= MIN_GAP else None


def summarize_folds(
    records: Sequence[Mapping[str, Mapping[str, float]]], n_train: int, n_test: int
) -> dict[str, Any]:
    """The mean and interval of every score over the folds, by table and metric."""
    tables = sorted({t for record in records for t in record})
    scores: dict[str, dict[str, Any]] = {}
    for table in tables:
        metrics = sorted({m for record in records for m in record.get(table, {})})
        scores[table] = {
            m: corrected_interval(
                [record.get(table, {}).get(m) for record in records],  # type: ignore[misc]
                n_train,
                n_test,
                bounds=BOUNDS.get(m, (float("-inf"), float("inf"))),
            )
            for m in metrics
        }
    recovered = _recovered(scores)
    if recovered is not None:
        scores["synthetic"]["utility_recovered"] = {"n": len(records), "mean": recovered}
    return {
        "folds": len(records),
        "train_rows": n_train,
        "test_rows": n_test,
        "method": METHOD,
        "scores": scores,
    }
