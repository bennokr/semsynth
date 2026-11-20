"""Sequential generator: each column is predicted from the columns before it.

The first column is drawn from its own values. Every later column is drawn from a model of that column given the columns
before it, fitted on the real rows and applied to the synthetic rows drawn so far.

The default learner, ``cart``, is the method of synthpop: a regression tree (:class:`sklearn.tree.DecisionTreeClassifier`
or ``DecisionTreeRegressor``) is fitted on the real rows, and each synthetic row takes the value of a real row drawn at
random from the leaf that the synthetic row falls in. The values of a column are therefore real values in proportion to
what the tree can tell apart, so the distribution of each column is kept, and nothing is assumed about its shape.

``mlp`` (a small neural network) and ``hgb`` (gradient boosting) predict instead:

* a categorical column is drawn from the class probabilities that the model predicts;
* a numeric column is the prediction plus a residual drawn at random from the residuals of the fit.

Both predicting learners fit the real rows closely, so their probabilities are over-confident and the distribution of a
column drifts from the real one; they are kept for comparison. Only scikit-learn and NumPy are used, which run in Pyodide,
so the backend works in a browser. The order of the columns is the order of the table.
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
LEARNERS = ("cart", "mlp", "hgb")


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


def _leaf_draw(leaf_real: np.ndarray, leaf_synth: np.ndarray, values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """For each synthetic row, the value of a real row drawn at random from the leaf of the synthetic row."""
    import numpy as np

    order = np.argsort(leaf_real, kind="stable")
    ordered = leaf_real[order]
    start = np.searchsorted(ordered, leaf_synth, side="left")
    size = np.searchsorted(ordered, leaf_synth, side="right") - start
    return values[order[start + (rng.random(len(leaf_synth)) * size).astype(int)]]


def _draw_cart(
    x_real: np.ndarray, x_synth: np.ndarray, target: np.ndarray, categorical: bool, seed: int, leaf: int, rng: np.random.Generator
) -> np.ndarray:
    from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

    tree = (DecisionTreeClassifier if categorical else DecisionTreeRegressor)(min_samples_leaf=leaf, random_state=seed)
    tree.fit(x_real, target)
    return _leaf_draw(tree.apply(x_real), tree.apply(x_synth), target, rng)


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
    learner: str = "cart",
    min_samples_leaf: int = 10,
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
        learner: ``cart`` (a tree per column, values drawn from the leaf), ``mlp`` (a small neural network) or ``hgb``
            (gradient boosting).
        min_samples_leaf: Fewest real rows in a leaf of the ``cart`` learner. A larger value smooths the draw and copies
            fewer real rows; a smaller one keeps more of the relations between columns.
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
            if learner == "cart":
                drawn = levels[_draw_cart(x_real, x_synth, codes, True, seed, min_samples_leaf, rng)]
            else:
                model = _learner(learner, True, seed, hidden, max_iter).fit(x_real, codes)
                drawn = levels[_draw_classes(model.predict_proba(x_synth), model.classes_, rng)]
            synthetic[column] = pd.Series(drawn).astype(real[column].dtype if real[column].dtype != "category" else "object")
        else:
            values = real[column].astype(float).to_numpy()
            if learner == "cart":
                synthetic[column] = _draw_cart(x_real, x_synth, values, False, seed, min_samples_leaf, rng)
            else:
                model = _learner(learner, False, seed, hidden, max_iter).fit(x_real, values)
                synthetic[column] = model.predict(x_synth) + rng.choice(values - model.predict(x_real), size=count)
    return SynthesisResult(
        synthetic_data=coerce_continuous_to_float(synthetic.reindex(columns=df.columns), cont_cols),
        backend="chain",
        parameters={"rows": count, "seed": seed, "learner": learner, "min_samples_leaf": min_samples_leaf, "hidden": list(hidden), "params": dict(options)},
        provenance={"engine": "semsynth chain", "engine_version": importlib.metadata.version("scikit-learn")},
    )
