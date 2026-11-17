"""Uncertainty of scores: bootstrap intervals for row-level statistics, permutation nulls for distances."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

DEFAULT_REPS = 200


def bootstrap_interval(
    statistic: Callable[..., float],
    *samples: np.ndarray,
    reps: int = DEFAULT_REPS,
    level: float = 0.95,
    seed: int = 0,
) -> list[float]:
    """Percentile interval of ``statistic(*samples)`` when every sample is resampled with replacement.

    The samples are resampled independently, which suits statistics that compare two sets of rows (synthetic and
    held-out). They are per-row values (a distance, a 0/1 match), so resampling is cheap. The interval reflects
    the sampling noise of the rows only: not the generator's randomness (use several seeds for that), and not
    the noise of the model fitting.

    Returns:
        ``[lower, upper]``; ``[nan, nan]`` when ``reps`` is 0 or a sample is empty.
    """
    import numpy as np

    nan = float("nan")
    if reps <= 0 or any(len(s) == 0 for s in samples):
        return [nan, nan]
    rng = np.random.default_rng(seed)
    draws = np.array(
        [statistic(*[s[rng.integers(0, len(s), len(s))] for s in samples]) for _ in range(reps)], dtype=float
    )
    lower, upper = np.nanquantile(draws, [(1 - level) / 2, 1 - (1 - level) / 2])
    return [float(lower), float(upper)]


def permutation_null(
    statistic: Callable[[np.ndarray, np.ndarray], Mapping[str, float]],
    n_first: int,
    n_second: int,
    observed: Mapping[str, float],
    *,
    reps: int = DEFAULT_REPS,
    level: float = 0.95,
    seed: int = 0,
) -> dict[str, dict[str, Any]]:
    """The range of distances between two samples when they are exchangeable, and where the observed values fall.

    A distance between two empirical distributions is above 0 even when both samples come from one population, and a
    bootstrap interval of it is biased upwards, so it is not shown as a confidence interval. Instead the pooled rows
    are split at random into samples of the original sizes ``reps`` times and the statistic is recomputed on each
    split: that is the noise floor of the score at this sample size.

    Args:
        statistic: Called with two arrays of row indices into the pooled rows (the first ``n_first`` rows come from
            the first sample, for example the real holdout) and returning named distances.
        n_first: Rows of the first sample.
        n_second: Rows of the second sample (the synthetic table).
        observed: The named distances of the actual samples; only these names are reported.
        reps: Number of random splits; 0 returns an empty result.
        level: Coverage of the null interval.
        seed: Seed of the splits.

    Returns:
        For each name: ``null_interval`` (lower and upper quantile of the null) and ``p_value`` (share of splits at
        least as far apart as the observed value, the observed split counted once). A score inside the interval cannot
        be told from a fresh real sample at this size; above it, the synthetic rows differ from one.
    """
    import numpy as np

    if reps <= 0 or n_first == 0 or n_second == 0:
        return {}
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {name: [] for name in observed}
    for _ in range(reps):
        order = rng.permutation(n_first + n_second)
        values = statistic(order[:n_first], order[n_first : n_first + n_second])
        for name in draws:
            draws[name].append(float(values[name]))
    out: dict[str, dict[str, Any]] = {}
    for name, values_ in draws.items():
        null = np.asarray(values_, dtype=float)
        if np.isnan(null).all() or np.isnan(observed[name]):
            continue
        lower, upper = np.nanquantile(null, [(1 - level) / 2, 1 - (1 - level) / 2])
        out[name] = {
            "null_interval": [float(lower), float(upper)],
            "p_value": float((1 + np.nansum(null >= observed[name])) / (1 + len(null))),
        }
    return out


def mean_and_interval(
    values: Sequence[float], *, level: float = 0.95
) -> dict[str, float]:
    """Mean of values from repeated runs (seeds) with a t-based interval; for 1 value the interval is NaN."""
    import numpy as np
    from scipy import stats

    array = np.asarray(values, dtype=float)
    array = array[~np.isnan(array)]
    if len(array) == 0:
        return {"mean": float("nan"), "lower": float("nan"), "upper": float("nan"), "n": 0}
    mean = float(array.mean())
    if len(array) < 2:
        return {"mean": mean, "lower": float("nan"), "upper": float("nan"), "n": 1}
    half = float(stats.t.ppf((1 + level) / 2, len(array) - 1) * array.std(ddof=1) / np.sqrt(len(array)))
    return {"mean": mean, "lower": mean - half, "upper": mean + half, "n": len(array)}
