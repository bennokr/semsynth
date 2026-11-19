"""Sequential generator: each column is predicted from the columns before it (experimental).

The first column is drawn from its own values. Every later column is drawn from a model of that column given the columns
before it, fitted on the real rows and applied to the synthetic rows drawn so far:

* a categorical column is drawn from the class probabilities that the model predicts;
* a numeric column is the prediction plus a residual drawn at random from the residuals of the fit, so that the spread is
  kept.

This is the idea of synthpop (CART per column), with a choice of learner. It uses only scikit-learn and NumPy, which run in
Pyodide, so it works in a browser. ``mlp`` is a small neural network (:class:`sklearn.neural_network.MLPClassifier` and
``MLPRegressor``); ``hgb`` is gradient boosting. The order of the columns is the order of the table.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

from ..result import SynthesisResult
from ..utils import coerce_continuous_to_float, split_columns

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

LOGGER = logging.getLogger(__name__)
LEARNERS = ("mlp", "hgb")


def _design(frame: pd.DataFrame, plan: dict[str, Any]) -> np.ndarray:
    """The inputs of a model: numbers standardized on the real rows, labels one-hot (a label never seen counts as none)."""
    import numpy as np

    parts = []
    for column in frame.columns:
        if column in plan["levels"]:
            codes = frame[column].astype(str).map({v: i for i, v in enumerate(plan["levels"][column])})
            hot = np.zeros((len(frame), len(plan["levels"][column])))
            known = codes.notna().to_numpy()
            hot[np.flatnonzero(known), codes[known].astype(int).to_numpy()] = 1.0
            parts.append(hot)
        else:
            mean, spread = plan["scale"][column]
            parts.append(((frame[column].astype(float) - mean) / spread).to_numpy()[:, None])
    return np.hstack(parts) if parts else np.zeros((len(frame), 0))


def _learner(kind: str, categorical: bool, seed: int, hidden: tuple[int, ...], max_iter: int) -> Any:
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
    from sklearn.neural_network import MLPClassifier, MLPRegressor

    if kind == "mlp":
        options: dict[str, Any] = {
            "hidden_layer_sizes": hidden,
            "max_iter": max_iter,
            "early_stopping": True,
            "random_state": seed,
        }
        return MLPClassifier(**options) if categorical else MLPRegressor(**options)
    options = {"max_iter": 100, "min_samples_leaf": 10, "random_state": seed}
    return HistGradientBoostingClassifier(**options) if categorical else HistGradientBoostingRegressor(**options)


def _draw_classes(probabilities: np.ndarray, classes: Any, rng: np.random.Generator) -> np.ndarray:
    import numpy as np

    cumulative = probabilities.cumsum(axis=1)
    pick = (rng.random((len(probabilities), 1)) > cumulative).sum(axis=1).clip(max=len(classes) - 1)
    return np.asarray(classes)[pick]


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    rows: int | None = None,
    seed: int = 0,
    learner: str = "mlp",
    hidden: tuple[int, ...] = (64, 32),
    max_iter: int = 200,
    **options: Any,
) -> SynthesisResult:
    """Fit the chain on ``df`` and draw ``rows`` rows.

    Args:
        df: The table to learn from; rows with missing values are not supported.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its levels decide which columns are categorical.
        rows: Number of rows to draw; the rows of ``df`` when omitted.
        seed: Random seed.
        learner: ``mlp`` (a small neural network) or ``hgb`` (gradient boosting).
        hidden: Sizes of the hidden layers of the ``mlp`` learner.
        max_iter: Most training iterations of one model (``mlp``).
        **options: Recorded as parameters of the run.
    """
    import numpy as np
    import pandas as pd

    if learner not in LEARNERS:
        raise ValueError(f"learner must be one of {LEARNERS}, not {learner!r}")
    count = int(rows or len(df))
    disc_cols, cont_cols = split_columns(df, codebook)
    real = coerce_continuous_to_float(df.copy(), cont_cols)
    rng = np.random.default_rng(seed)
    plan: dict[str, Any] = {
        "levels": {c: sorted(real[c].astype(str).unique()) for c in disc_cols},
        "scale": {c: (float(real[c].mean()), float(real[c].std() or 1.0)) for c in cont_cols},
    }
    columns = list(real.columns)
    synthetic = pd.DataFrame(index=range(count))
    first = columns[0]
    synthetic[first] = real[first].sample(count, replace=True, random_state=seed).to_numpy()
    for position, column in enumerate(columns[1:], start=1):
        before = columns[:position]
        x_real = _design(real[before], plan)
        x_synth = _design(synthetic[before], plan)
        if column in disc_cols:
            # Integer codes, not labels: scikit-learn 1.6 (the one in Pyodide) fails to score a MLPClassifier on text labels.
            levels = np.asarray(plan["levels"][column], dtype=object)
            codes = real[column].astype(str).map({v: i for i, v in enumerate(levels)}).to_numpy()
            model = _learner(learner, True, seed, hidden, max_iter).fit(x_real, codes)
            drawn = levels[_draw_classes(model.predict_proba(x_synth), model.classes_, rng)]
            synthetic[column] = pd.Series(drawn).astype(real[column].dtype if real[column].dtype != "category" else "object")
        else:
            model = _learner(learner, False, seed, hidden, max_iter).fit(x_real, real[column].astype(float))
            residuals = real[column].astype(float).to_numpy() - model.predict(x_real)
            synthetic[column] = model.predict(x_synth) + rng.choice(residuals, size=count)
    return SynthesisResult(
        synthetic_data=coerce_continuous_to_float(synthetic.reindex(columns=df.columns), cont_cols),
        backend="chain",
        parameters={"rows": count, "seed": seed, "learner": learner, "hidden": list(hidden), "params": dict(options)},
        provenance={"engine": "semsynth chain", "engine_version": importlib.metadata.version("scikit-learn")},
    )
