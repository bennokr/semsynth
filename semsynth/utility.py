"""Utility of a synthetic table for prediction: train on it, test on real rows.

A model that is trained on the synthetic rows and tested on held-out real rows (TSTR, "train on synthetic, test on
real") shows whether the synthetic table keeps the relations that a prediction needs. The number only means something
next to two references, computed the same way with tables of the same size:

``real_sample``
    A model trained on real training rows (TRTR). This is the ceiling: a perfect generator scores like fresh real data.
``independent_marginals``
    A model trained on a table that keeps every column's distribution and destroys every relation. This is the floor:
    whatever it scores is what the marginals alone give.

``prior`` is the trivial predictor (the class frequencies, or the mean) and needs no training.

The primary score is the area under the ROC curve for a categorical target (balanced accuracy where the held-out rows
do not have two classes) and R² for a numeric one. ``recovered`` is ``(synthetic - floor) / (ceiling - floor)``: the
share of what real data gains over the floor that the synthetic table keeps. It is left out when the ceiling and the
floor are less than :data:`MIN_GAP` apart, because the share is then meaningless.

The interval of a single split comes from resampling the held-out rows. It does not include the variation of the
training rows; the cross-validated scores of :mod:`semsynth.crossval` do.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

LOGGER = logging.getLogger(__name__)

MIN_TRAIN_ROWS = 10
MIN_TEST_ROWS = 5
MIN_GAP = 0.02
MIN_DRAWS = 20  # fewest usable resamples for an interval
TABLES = ("synthetic", "real_sample", "independent_marginals")


def _encode(
    frames: Mapping[str, pd.DataFrame], predictors: list[str], numeric: set[str]
) -> tuple[dict[str, np.ndarray], list[bool]]:
    """One matrix per table with the same encoding: numbers as they are, labels as codes (``NaN`` kept)."""
    import numpy as np
    import pandas as pd

    sizes = {name: len(frame) for name, frame in frames.items()}
    both = pd.concat([frame[predictors] for frame in frames.values()], ignore_index=True)
    columns, categorical = [], []
    for column in predictors:
        if column in numeric:
            columns.append(pd.to_numeric(both[column], errors="coerce").to_numpy(float))
            categorical.append(False)
        else:
            codes = pd.Categorical(both[column].astype("string")).codes.astype(float)
            columns.append(np.where(codes < 0, np.nan, codes))
            categorical.append(True)
    matrix = np.column_stack(columns)
    out, start = {}, 0
    for name, size in sizes.items():
        out[name] = matrix[start : start + size]
        start += size
    return out, categorical


def _fit_predict(
    task: str,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_test: np.ndarray,
    categorical: list[bool],
    classes: list[Any],
    seed: int,
) -> np.ndarray | None:
    """Predictions for the test rows: probabilities of ``classes`` (classification) or values (regression)."""
    import numpy as np
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

    options: dict[str, Any] = {
        "max_iter": 100,
        "min_samples_leaf": 5,
        "early_stopping": False,
        "random_state": seed,
    }
    if any(categorical):
        options["categorical_features"] = categorical
    if task == "regression":
        return np.asarray(
            HistGradientBoostingRegressor(**options).fit(x_train, y_train).predict(x_test)
        )
    if len(set(y_train)) < 2:
        return None
    model = HistGradientBoostingClassifier(**options).fit(x_train, y_train)
    proba = np.zeros((len(x_test), len(classes)))
    for column, label in enumerate(model.classes_):
        proba[:, classes.index(label)] = model.predict_proba(x_test)[:, column]
    return proba


def _score(
    task: str, y_true: np.ndarray, prediction: np.ndarray, classes: list[Any]
) -> tuple[str, float]:
    """The primary score of a prediction: ``("r2", value)``, ``("auc", value)`` or ``("balanced_accuracy", value)``."""
    import numpy as np
    from sklearn.metrics import balanced_accuracy_score, r2_score, roc_auc_score

    if task == "regression":
        return "r2", float(r2_score(y_true, prediction))
    present = sorted(set(y_true))
    if len(present) >= 2:
        if len(classes) == 2:
            return "auc", float(roc_auc_score(y_true == classes[1], prediction[:, 1]))
        if len(present) == len(classes):
            return "auc", float(
                roc_auc_score(y_true, prediction, multi_class="ovr", labels=classes)
            )
    chosen = np.asarray(classes)[prediction.argmax(axis=1)]
    return "balanced_accuracy", float(balanced_accuracy_score(y_true, chosen))


def _prior_prediction(task: str, y_train: np.ndarray, size: int, classes: list[Any]) -> np.ndarray:
    import numpy as np

    if task == "regression":
        return np.full(size, float(np.mean(y_train)))
    shares = np.array([np.mean(y_train == label) for label in classes])
    return np.tile(shares, (size, 1))


def _bootstrap(
    task: str,
    y_true: np.ndarray,
    predictions: Mapping[str, np.ndarray],
    classes: list[Any],
    metric: str,
    reps: int,
    seed: int,
) -> dict[str, list[float]]:
    """Percentile intervals of every score and of ``recovered``, from resampling the held-out rows (paired)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {name: [] for name in [*predictions, "recovered"]}
    for _ in range(reps):
        pick = rng.integers(0, len(y_true), len(y_true))
        try:
            found = {
                name: _score(task, y_true[pick], p[pick], classes)
                for name, p in predictions.items()
            }
        except ValueError:
            continue
        if any(kind != metric for kind, _ in found.values()):
            continue
        for name, (_, value) in found.items():
            draws[name].append(value)
        recovered = _recovered(
            found["synthetic"][1], found["real_sample"][1], found["independent_marginals"][1]
        )
        if recovered is not None:
            draws["recovered"].append(recovered)
    return {
        name: [float(x) for x in np.quantile(values, [0.025, 0.975])]
        for name, values in draws.items()
        if len(values) >= MIN_DRAWS
    }


def _as_target(task: str, values: pd.Series) -> np.ndarray:
    """The target as numbers for a regression and as text for a classification."""
    import pandas as pd

    if task == "regression":
        return pd.to_numeric(values, errors="coerce").to_numpy(float)
    return values.astype(str).to_numpy()


def _target(
    task: str, train: pd.DataFrame, holdout: pd.DataFrame, tables: Mapping[str, pd.DataFrame], target: str
) -> tuple[np.ndarray, np.ndarray, list[Any]]:
    """The held-out target, which of its rows have a value, and the classes of a classification (sorted)."""
    import numpy as np

    y = _as_target(task, holdout[target])
    keep = holdout[target].notna().to_numpy()
    if task == "regression":
        return y, keep & ~np.isnan(y), []
    seen = {str(v) for frame in (train, *tables.values()) for v in frame[target].dropna()}
    return y, keep, sorted(seen | {str(v) for v in holdout[target].dropna()})


def _recovered(synthetic: float, ceiling: float, floor: float) -> float | None:
    """The share of the gain of real data over the floor that the synthetic table keeps, if the gain is large enough."""
    return (synthetic - floor) / (ceiling - floor) if ceiling - floor >= MIN_GAP else None


def utility_tables(train: pd.DataFrame, synthetic: pd.DataFrame, seed: int) -> dict[str, pd.DataFrame]:
    """The three tables of :data:`TABLES`, all with the same number of rows, so that size does not decide the comparison.

    The size is the smaller of the synthetic table and the training rows (the real sample cannot be larger than those).
    """
    from .baselines import reference_tables

    size = min(len(synthetic), len(train))
    table = synthetic if len(synthetic) == size else synthetic.sample(size, random_state=seed).reset_index(drop=True)
    return {"synthetic": table, **reference_tables(train, size, seed)}


def tstr_utility(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    tables: Mapping[str, pd.DataFrame],
    target: str | None,
    kinds: Mapping[str, str],
    *,
    seed: int = 0,
    reps: int = 0,
) -> dict[str, Any]:
    """Score each of the :data:`TABLES` as training data for predicting ``target``, on the held-out real rows.

    Args:
        train: Real training rows. Their target gives the ``prior``.
        holdout: Real rows that no table was learned from; the test rows.
        tables: ``synthetic``, ``real_sample`` and ``independent_marginals``, with the same columns and the same size.
        target: The column to predict.
        kinds: Column name to ``numeric``, or another kind for a categorical column or one to leave out.
        seed: Seed of the models and of the resampling.
        reps: Resamples of the held-out rows for the intervals; 0 turns them off.

    Returns:
        ``status`` (``ok`` or ``not_applicable`` with a ``reason``), the ``task``, the ``metric``, the ``scores`` of
        the tables and of the ``prior``, ``recovered``, and ``intervals`` if ``reps`` is positive.
    """
    columns = [
        c
        for c in train.columns
        if c in holdout.columns and all(c in t.columns for t in tables.values())
    ]
    if not target or target not in columns:
        return {"status": "not_applicable", "reason": "no target column"}
    predictors = [c for c in columns if c != target and kinds.get(c) != "ignore"]
    task = "regression" if kinds.get(target) == "numeric" else "classification"
    if not predictors or len(train) < MIN_TRAIN_ROWS or len(holdout) < MIN_TEST_ROWS:
        return {"status": "not_applicable", "reason": "too few columns or rows"}
    frames = {**tables, "_holdout": holdout}
    numeric = {c for c in predictors if kinds.get(c) == "numeric"}
    matrices, categorical = _encode(frames, predictors, numeric)
    y_all, keep, classes = _target(task, train, holdout, tables, target)
    predictions: dict[str, np.ndarray] = {}
    for name, table in tables.items():
        usable = table[target].notna().to_numpy()
        y = _as_target(task, table[target][usable])
        prediction = _fit_predict(
            task, matrices[name][usable], y, matrices["_holdout"][keep], categorical, classes, seed
        )
        if prediction is None:
            return {"status": "not_applicable", "reason": f"the {name} table has one class"}
        predictions[name] = prediction
    predictions["prior"] = _prior_prediction(
        task, _as_target(task, train[target].dropna()), int(keep.sum()), classes
    )
    y_true = y_all[keep]
    found = {
        name: _score(task, y_true, prediction, classes) for name, prediction in predictions.items()
    }
    metric = found["synthetic"][0]
    if any(kind != metric for kind, _ in found.values()):
        return {"status": "not_applicable", "reason": "the held-out rows have a single class"}
    scores = {name: value for name, (_, value) in found.items()}
    out: dict[str, Any] = {
        "status": "ok",
        "target": target,
        "task": task,
        "metric": metric,
        "test_rows": int(keep.sum()),
        "scores": scores,
        "recovered": _recovered(
            scores["synthetic"], scores["real_sample"], scores["independent_marginals"]
        ),
    }
    if reps > 0:
        intervals = _bootstrap(task, y_true, predictions, classes, metric, reps, seed)
        if out["recovered"] is None:
            intervals.pop("recovered", None)
        out["intervals"] = intervals
    return out
