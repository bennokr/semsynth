"""Joint fidelity: does the synthetic table keep the relations between columns, not only each column?

Three views, all of them computed on the same columns and rows as the marginal metrics and none needing an extra:

``pairwise``
    Total variation distance between the real and synthetic contingency tables of every column pair (numbers are
    cut at the quantiles of the real column; a missing value is a level of its own, so a pair also tests whether the
    missingness of one column depends on the other the same way). 0 is identical, 1 disjoint.
``missingness``
    Per-column missing rates and the distribution of whole missingness patterns, compared with the real table.
    Needs real rows with missing values, which are not the rows the generators learn from (they learn from complete
    rows), so the runner calls it only where it has them.
``classifier``
    A classifier two-sample test: how well can gradient boosting tell real rows from synthetic ones (cross-validated
    AUC, 0.5 is "cannot")? Missing values go to the classifier as they are.

All of them are noisy for few rows, and none is meaningful without its baseline: see :mod:`semsynth.baselines`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from .uncertainty import permutation_null

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

LOGGER = logging.getLogger(__name__)

MAX_COLUMNS = 60
MIN_CLASSIFIER_ROWS = 30
N_BINS = 5
WORST_PAIRS = 5


def _codes(real: pd.Series, synth: pd.Series, numeric: bool) -> tuple[np.ndarray, np.ndarray, int]:
    """Integer codes of a column in both tables on the same scale; 0 is missing. Returns the number of levels."""
    import numpy as np
    import pandas as pd

    if numeric:
        a, b = pd.to_numeric(real, errors="coerce").to_numpy(float), pd.to_numeric(synth, errors="coerce").to_numpy(float)
        seen = a[~np.isnan(a)]
        edges = np.unique(np.quantile(seen, np.linspace(0, 1, N_BINS + 1)[1:-1])) if len(seen) else np.array([])
        out = [np.where(np.isnan(v), 0, np.searchsorted(edges, v) + 1) for v in (a, b)]
        return out[0], out[1], len(edges) + 2
    labels = pd.concat([real, synth]).dropna().astype(str).unique().tolist()
    lookup = {label: i + 1 for i, label in enumerate(sorted(labels))}
    out = [
        s.astype("string").map(lookup).fillna(0).to_numpy(int) if len(s) else np.zeros(0, int) for s in (real, synth)
    ]
    return out[0], out[1], len(lookup) + 1


def _pair_tvd(a_real: np.ndarray, b_real: np.ndarray, a_syn: np.ndarray, b_syn: np.ndarray, width: int) -> float:
    import numpy as np

    size = width * width
    p = np.bincount(a_real * width + b_real, minlength=size) / max(len(a_real), 1)
    q = np.bincount(a_syn * width + b_syn, minlength=size) / max(len(a_syn), 1)
    return 0.5 * float(np.abs(p - q).sum())


def _prepare(
    real: pd.DataFrame, synth: pd.DataFrame, columns: list[str], numeric: set[str]
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, int]]:
    real_codes, synth_codes, levels = {}, {}, {}
    for column in columns:
        real_codes[column], synth_codes[column], levels[column] = _codes(real[column], synth[column], column in numeric)
    return real_codes, synth_codes, levels


def _all_pairs(
    columns: list[str], real_codes: dict[str, np.ndarray], synth_codes: dict[str, np.ndarray], levels: dict[str, int],
    rows_real: np.ndarray | None = None, rows_synth: np.ndarray | None = None,
) -> dict[tuple[str, str], float]:
    """TVD of every column pair, optionally on resampled rows."""
    out: dict[tuple[str, str], float] = {}
    for i, a in enumerate(columns):
        for b in columns[i + 1 :]:
            ra, rb, sa, sb = real_codes[a], real_codes[b], synth_codes[a], synth_codes[b]
            if rows_real is not None and rows_synth is not None:
                ra, rb, sa, sb = ra[rows_real], rb[rows_real], sa[rows_synth], sb[rows_synth]
            out[(a, b)] = _pair_tvd(ra, rb, sa, sb, max(levels[a], levels[b]))
    return out


def pairwise_dependence(
    real: pd.DataFrame,
    synth: pd.DataFrame,
    numeric: set[str],
    *,
    reps: int = 0,
    seed: int = 0,
) -> dict[str, Any]:
    """Mean and maximum contingency-table TVD over column pairs, the worst pairs, and the noise floor of the mean.

    ``null`` holds the range of the mean TVD when real and synthetic rows are exchangeable and the p-value of the
    observed mean (:func:`semsynth.uncertainty.permutation_null`); for many columns keep ``reps`` small.
    """
    import numpy as np

    columns = [c for c in real.columns if c in synth.columns][:MAX_COLUMNS]
    if len(columns) < 2 or len(real) == 0 or len(synth) == 0:
        return {"status": "not_applicable", "n_pairs": 0}
    codes = _prepare(real, synth, columns, numeric)
    tvd = _all_pairs(columns, *codes)
    values = np.array(list(tvd.values()))
    worst = sorted(tvd.items(), key=lambda item: -item[1])[:WORST_PAIRS]
    out: dict[str, Any] = {
        "status": "ok",
        "n_columns": len(columns),
        "n_pairs": len(tvd),
        "tvd_mean": float(values.mean()),
        "tvd_max": float(values.max()),
        "worst_pairs": [{"columns": list(pair), "tvd": float(v)} for pair, v in worst],
    }
    if reps > 0:
        pooled = {c: np.concatenate([codes[0][c], codes[1][c]]) for c in columns}
        n_real = len(real)

        def split_tvd(first: np.ndarray, second: np.ndarray) -> dict[str, float]:
            split = _all_pairs(
                columns,
                {c: v[first] for c, v in pooled.items()},
                {c: v[second] for c, v in pooled.items()},
                codes[2],
            )
            return {"tvd_mean": float(np.mean(list(split.values())))}

        out["null"] = permutation_null(
            split_tvd, n_real, len(synth), {"tvd_mean": out["tvd_mean"]}, reps=reps, seed=seed
        ).get("tvd_mean", {})
    return out


def _pattern_shares(mask: pd.DataFrame) -> pd.Series:
    """Share of rows for each whole-row missingness pattern (a string of 0 and 1)."""
    return mask.astype(int).astype(str).agg("".join, axis=1).value_counts(normalize=True)


def missingness_fidelity(real: pd.DataFrame, synth: pd.DataFrame) -> dict[str, Any]:
    """Compare missing rates per column and the distribution of missingness patterns.

    Args:
        real: Real rows *with* their missing values.
        synth: The synthetic table, with the missingness the generator or the missingness model produced.

    Returns:
        ``rate_gap_mean`` and ``rate_gap_max`` (absolute difference of the per-column missing share), ``pattern_tvd``
        (total variation over whole-row patterns, which also catches columns that go missing together) and the
        columns with the largest gap.
    """
    import numpy as np

    columns = [c for c in real.columns if c in synth.columns]
    if not columns or len(real) == 0 or len(synth) == 0:
        return {"status": "not_applicable"}
    miss_real, miss_synth = real[columns].isna(), synth[columns].isna()
    gap = (miss_real.mean() - miss_synth.mean()).abs()
    p, q = _pattern_shares(miss_real), _pattern_shares(miss_synth)
    index = p.index.union(q.index)
    return {
        "status": "ok",
        "real_incomplete_rows": float(miss_real.any(axis=1).mean()),
        "synthetic_incomplete_rows": float(miss_synth.any(axis=1).mean()),
        "rate_gap_mean": float(gap.mean()),
        "rate_gap_max": float(gap.max()),
        "pattern_tvd": 0.5 * float(np.abs(p.reindex(index, fill_value=0) - q.reindex(index, fill_value=0)).sum()),
        "largest_gaps": {str(c): float(v) for c, v in gap.sort_values(ascending=False).head(WORST_PAIRS).items() if v > 0},
    }


def _features(real: pd.DataFrame, synth: pd.DataFrame, columns: list[str], numeric: set[str]) -> tuple[np.ndarray, list[bool]]:
    """One matrix for both tables: numbers as they are (``NaN`` kept), labels as integer codes (``NaN`` kept)."""
    import numpy as np
    import pandas as pd

    both = pd.concat([real[columns], synth[columns]], ignore_index=True)
    parts, categorical = [], []
    for column in columns:
        if column in numeric:
            parts.append(pd.to_numeric(both[column], errors="coerce").to_numpy(float))
            categorical.append(False)
        else:
            codes = pd.Categorical(both[column].astype("string")).codes.astype(float)
            parts.append(np.where(codes < 0, np.nan, codes))
            categorical.append(True)
    return np.column_stack(parts), categorical


def classifier_two_sample(
    real: pd.DataFrame, synth: pd.DataFrame, numeric: set[str], *, seed: int = 0, reps: int = 0
) -> dict[str, Any]:
    """Cross-validated AUC of a gradient-boosting classifier that tells real from synthetic rows.

    The tables are cut to the same size (random rows) first. ``pmse`` is the mean squared distance of the predicted
    probability from 0.5 (Snoke et al.): 0 when the classes cannot be told apart.
    """
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict

    columns = [c for c in real.columns if c in synth.columns]
    n = min(len(real), len(synth))
    if n < MIN_CLASSIFIER_ROWS or not columns:
        return {"status": "not_applicable", "reason": f"fewer than {MIN_CLASSIFIER_ROWS} rows per class"}
    a, b = real.sample(n, random_state=seed), synth.sample(n, random_state=seed)
    matrix, categorical = _features(a, b, columns, numeric)
    labels = np.r_[np.zeros(n), np.ones(n)]
    model = HistGradientBoostingClassifier(
        max_iter=100, categorical_features=categorical if any(categorical) else None, random_state=seed
    )
    folds = StratifiedKFold(5, shuffle=True, random_state=seed)
    prob = cross_val_predict(model, matrix, labels, cv=folds, method="predict_proba")[:, 1]
    out: dict[str, Any] = {
        "status": "ok",
        "rows_per_class": n,
        "auc": float(roc_auc_score(labels, prob)),
        "pmse": float(np.mean((prob - 0.5) ** 2)),
    }
    if reps > 0:
        rng = np.random.default_rng(seed)
        draws = []
        for _ in range(reps):
            pick = rng.integers(0, 2 * n, 2 * n)
            if 0 < labels[pick].sum() < 2 * n:
                draws.append(roc_auc_score(labels[pick], prob[pick]))
        out["auc_interval"] = [float(x) for x in np.quantile(draws, [0.025, 0.975])] if draws else [float("nan")] * 2
    return out


def joint_fidelity(
    real: pd.DataFrame,
    synth: pd.DataFrame,
    kinds: Mapping[str, str],
    *,
    seed: int = 0,
    reps: int = 0,
) -> dict[str, Any]:
    """Pairwise dependence and the classifier two-sample test, with the same row set for both.

    Args:
        real: Real rows the generator did not learn from.
        synth: The synthetic table.
        kinds: Column name to ``numeric`` or anything else (categorical).
        seed: Seed for subsampling and the bootstrap.
        reps: Bootstrap resamples for the intervals; 0 turns them off.
    """
    columns = [c for c in real.columns if c in synth.columns and kinds.get(c) != "ignore"]
    numeric = {c for c in columns if kinds.get(c) == "numeric"}
    real, synth = real[columns], synth[columns]
    return {
        "n_real": len(real),
        "n_synth": len(synth),
        "pairwise": pairwise_dependence(real, synth, numeric, reps=reps, seed=seed),
        "classifier": classifier_two_sample(real, synth, numeric, seed=seed, reps=reps),
    }
