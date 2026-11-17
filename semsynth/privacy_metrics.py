"""Privacy facts about a synthetic table, independent of the generator that made it.

Two layers:

* The core (numpy, pandas, scikit-learn): exact matches and distance to the closest training record (DCR),
  each with a reference taken from real rows the generator never saw, plus rare quasi-identifier reproduction and
  t-closeness.
* The optional ``privacy`` extra (``sdmetrics``): attribute-inference risk with a random baseline, and two more DCR
  scores. They are recorded as ``skipped`` when the extra is missing.

None of these is a proof of privacy. They measure what a generic attacker with the training data could see, and
all of them are relative to a baseline: a score is only meaningful next to the holdout reference or the
random-data baseline stored beside it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

LOGGER = logging.getLogger(__name__)

MAX_QUERY_ROWS = 5000
MAX_LEVELS = 50
_RESERVED_ROLES = ("ignore", "id")


@dataclass
class PrivacySummary:
    """What :func:`summarize_privacy` measured. ``dcr`` is the distance to the closest training record (0 to 1)."""

    n_train: int
    n_holdout: int
    n_synth: int
    used_columns: list[str]
    qi_columns: list[str]
    sensitive_columns: list[str]
    exact_match_rate: float
    exact_match_rate_holdout: float | None
    dcr_synthetic: dict[str, float]
    dcr_holdout: dict[str, float] | None
    dcr_below_holdout_p05: float | None
    rare_qi_reproduction_rate: float | None
    t_closeness: dict[str, dict[str, float]]
    sdmetrics: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"


def _usable_columns(meta: pd.DataFrame, *frames: pd.DataFrame) -> pd.DataFrame:
    use = meta[~meta.role.isin(_RESERVED_ROLES)]
    columns = [c for c in use.variable if all(c in f.columns for f in frames)]
    if not columns:
        raise ValueError("No overlapping usable columns.")
    return use[use.variable.isin(columns)]


def _clean(frame: pd.DataFrame, meta: pd.DataFrame) -> pd.DataFrame:
    """Numeric columns as floats, everything else as strings; a missing value becomes its own category."""
    import pandas as pd

    kinds = dict(zip(meta.variable, meta.type, strict=False))
    out = pd.DataFrame(index=frame.index)
    for column in meta.variable:
        if kinds.get(column) == "numeric":
            out[column] = pd.to_numeric(frame[column], errors="coerce").astype(float)
        else:
            out[column] = frame[column].astype("string").fillna("<MISSING>").astype(object)
    return out


def _exact_match_rate(queries: pd.DataFrame, reference: pd.DataFrame) -> float:
    """Share of ``queries`` rows that equal some row of ``reference``, over all columns."""
    columns = list(reference.columns)
    keys = reference.drop_duplicates()
    flagged = queries.merge(keys.assign(_hit=True), on=columns, how="left")["_hit"]
    return float(flagged.notna().mean()) if len(queries) else float("nan")


class _Encoder:
    """Gower-style encoding: the L1 distance between two encoded rows is the sum of per-column distances.

    A numeric column contributes its absolute difference over the training range (clipped to 1) and a missing
    indicator; a categorical column contributes 1 when the values differ. Levels beyond ``MAX_LEVELS`` share one
    bucket, which makes rare categories look closer than they are.
    """

    def __init__(self, train: pd.DataFrame) -> None:
        import numpy as np

        self.numeric = [c for c in train.columns if train[c].dtype.kind == "f"]
        self.categorical = [c for c in train.columns if c not in self.numeric]
        self.lo = {c: float(np.nanmin(train[c])) if train[c].notna().any() else 0.0 for c in self.numeric}
        hi = {c: float(np.nanmax(train[c])) if train[c].notna().any() else 0.0 for c in self.numeric}
        self.span = {c: (hi[c] - self.lo[c]) or 1.0 for c in self.numeric}
        self.levels = {c: set(train[c].value_counts().index[:MAX_LEVELS]) for c in self.categorical}

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        import numpy as np

        parts: list[np.ndarray] = []
        for column in self.numeric:
            values = frame[column].to_numpy(float)
            missing = np.isnan(values)
            scaled = np.clip((values - self.lo[column]) / self.span[column], 0.0, 1.0)
            parts.append(np.where(missing, 0.0, scaled)[:, None])
            parts.append(missing.astype(float)[:, None])
        for column in self.categorical:
            codes = [*sorted(self.levels[column], key=str), "<OTHER>"]
            seen = frame[column].where(frame[column].isin(self.levels[column]), "<OTHER>")
            parts.append(np.stack([(seen == code).to_numpy(float) * 0.5 for code in codes], axis=1))
        return np.concatenate(parts, axis=1) / max(len(self.numeric) + len(self.categorical), 1)


def _dcr(queries: pd.DataFrame, reference: pd.DataFrame, seed: int) -> np.ndarray:
    """Distance from each query row to its closest reference row, in [0, 1]."""
    from sklearn.neighbors import NearestNeighbors

    if len(queries) > MAX_QUERY_ROWS:
        queries = queries.sample(MAX_QUERY_ROWS, random_state=seed)
    encoder = _Encoder(reference)
    index = NearestNeighbors(n_neighbors=1, metric="manhattan").fit(encoder.transform(reference))
    distances, _ = index.kneighbors(encoder.transform(queries))
    return distances[:, 0]  # type: ignore[no-any-return]


def _quantiles(values: np.ndarray) -> dict[str, float]:
    import numpy as np

    return {
        "min": float(values.min()),
        "p05": float(np.quantile(values, 0.05)),
        "median": float(np.median(values)),
        "mean": float(values.mean()),
    }


def _distance_block(
    train: pd.DataFrame, holdout: pd.DataFrame | None, synth: pd.DataFrame, seed: int
) -> tuple[dict[str, float], dict[str, float] | None, float | None]:
    """DCR summaries of the synthetic and holdout rows, and how often synthetic rows beat the holdout's 5th percentile.

    Both sets are measured against the same training rows, so their sizes need not match. A generator that
    memorizes puts many synthetic rows below the holdout's 5th percentile; a faithful one puts about 5% there.
    """
    import numpy as np

    synthetic = _dcr(synth, train, seed)
    if holdout is None or len(holdout) == 0:
        return _quantiles(synthetic), None, None
    reference = _dcr(holdout, train, seed)
    threshold = np.quantile(reference, 0.05)
    return _quantiles(synthetic), _quantiles(reference), float((synthetic < threshold).mean())


def _rare_qi_reproduction(train: pd.DataFrame, synth: pd.DataFrame, qi: list[str]) -> float | None:
    """Share of the rare real quasi-identifier combinations (at most 5 rows, or at most 1%) that the synthetic table repeats."""
    if not qi:
        return None
    counts = train.groupby(qi, dropna=False).size()
    rare = set(counts[(counts <= 5) | (counts / len(train) <= 0.01)].index)
    seen = set(synth.groupby(qi, dropna=False).size().index)
    return len(rare & seen) / len(rare) if rare else 0.0


def _total_variation(p: pd.Series, q: pd.Series) -> float:
    import numpy as np

    index = p.index.union(q.index)
    return 0.5 * float(np.abs(p.reindex(index, fill_value=0) - q.reindex(index, fill_value=0)).sum())


def _wasserstein(x: np.ndarray, y: np.ndarray) -> float:
    import numpy as np

    x, y = np.sort(x[~np.isnan(x)]), np.sort(y[~np.isnan(y)])
    if len(x) == 0 or len(y) == 0:
        return 0.0
    grid = (np.arange(max(len(x), len(y))) + 0.5) / max(len(x), len(y))
    return float(np.mean(np.abs(np.quantile(x, grid) - np.quantile(y, grid))))


def _t_closeness(
    train: pd.DataFrame, synth: pd.DataFrame, qi: list[str], sensitive: list[str], kinds: dict[str, str]
) -> dict[str, dict[str, float]]:
    """Per sensitive column: how far the sensitive values inside each synthetic QI group are from the real ones."""
    import numpy as np

    out: dict[str, dict[str, float]] = {}
    if not (qi and sensitive):
        return out
    groups = synth.groupby(qi, dropna=False)
    for column in sensitive:
        if kinds.get(column) == "numeric":
            reference = train[column].to_numpy(float)
            values = [_wasserstein(g[column].to_numpy(float), reference) for _, g in groups]
        else:
            reference_counts = train[column].value_counts(normalize=True, dropna=False)
            values = [_total_variation(g[column].value_counts(normalize=True, dropna=False), reference_counts) for _, g in groups]
        if values:
            array = np.array(values, float)
            out[column] = {"mean": float(array.mean()), "p95": float(np.quantile(array, 0.95)), "max": float(array.max())}
    return out


def _sdmetrics_block(
    train: pd.DataFrame,
    holdout: pd.DataFrame | None,
    synth: pd.DataFrame,
    meta: pd.DataFrame,
    qi: list[str],
    sensitive: list[str],
) -> dict[str, Any]:
    """The sdmetrics scores (1 is safest); one that cannot run is recorded with its reason, not left out."""
    try:
        from sdmetrics.single_table import (
            DCRBaselineProtection,
            DCROverfittingProtection,
            DisclosureProtection,
        )
    except ImportError as exc:
        return {"status": "skipped", "reason": f"install semsynth[privacy]: {exc}"}
    kinds = dict(zip(meta.variable, meta.type, strict=False))
    metadata = {
        "columns": {c: {"sdtype": "numerical" if kinds.get(c) == "numeric" else "categorical"} for c in train.columns}
    }
    numeric = [c for c in train.columns if kinds.get(c) == "numeric"]
    jobs: dict[str, Any] = {
        "dcr_baseline_protection": lambda: DCRBaselineProtection.compute_breakdown(train, synth, metadata, "table"),
    }
    if holdout is not None and len(holdout):
        jobs["dcr_overfitting_protection"] = lambda: DCROverfittingProtection.compute_breakdown(
            train, synth, holdout, metadata, "table"
        )
    if qi and sensitive:
        jobs["disclosure_protection"] = lambda: DisclosureProtection.compute_breakdown(
            train, synth, qi, sensitive, continuous_column_names=[c for c in numeric if c in qi + sensitive]
        )
    return {name: _run_sdmetrics(name, job) for name, job in jobs.items()}


def _run_sdmetrics(name: str, job: Any) -> dict[str, Any]:
    import numpy as np

    try:
        raw = job()
    except Exception as exc:
        LOGGER.warning("sdmetrics %s failed: %s", name, exc)
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
    return {"status": "ok", "score": float(np.asarray(raw["score"]).item()), **_numbers(raw)}


def _numbers(breakdown: dict[str, Any]) -> dict[str, Any]:
    """The breakdown without its ``score``, with numpy numbers turned into floats so that it serializes."""
    import numpy as np

    def convert(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): convert(v) for k, v in value.items()}
        if isinstance(value, np.generic):
            return value.item()
        return value

    return {k: convert(v) for k, v in breakdown.items() if k != "score"}


def summarize_privacy(
    train: pd.DataFrame,
    synth: pd.DataFrame,
    meta: pd.DataFrame,
    holdout: pd.DataFrame | None = None,
    *,
    seed: int = 0,
) -> PrivacySummary:
    """Compare a synthetic table with the real rows it was learned from.

    Args:
        train: The real rows the generator was fitted on.
        synth: The synthetic table.
        meta: ``variable``, ``role`` and ``type`` of each column (see
            :meth:`semsynth.codebook.Codebook.privacy_frame`). Columns with the role ``id`` or ``ignore`` are left out.
        holdout: Real rows the generator never saw. They give the reference for the exact-match and distance
            numbers; without them only the synthetic side is reported and nothing can be called "too close".
        seed: Seed for subsampling the query rows.

    Returns:
        A :class:`PrivacySummary`.

    Raises:
        ValueError: If no column is shared by the tables and usable.
    """
    frames = [train, synth] + ([holdout] if holdout is not None else [])
    use = _usable_columns(meta, *frames)
    qi = list(use.loc[use.role == "qi", "variable"])
    sensitive = list(use.loc[use.role == "sensitive", "variable"])
    kinds = dict(zip(use.variable, use.type, strict=False))
    real, fake = _clean(train, use), _clean(synth, use)
    held = _clean(holdout, use) if holdout is not None else None
    synthetic_dcr, holdout_dcr, below = _distance_block(real, held, fake, seed)
    return PrivacySummary(
        n_train=len(real),
        n_holdout=len(held) if held is not None else 0,
        n_synth=len(fake),
        used_columns=list(use.variable),
        qi_columns=qi,
        sensitive_columns=sensitive,
        exact_match_rate=_exact_match_rate(fake, real),
        exact_match_rate_holdout=_exact_match_rate(held, real) if held is not None else None,
        dcr_synthetic=synthetic_dcr,
        dcr_holdout=holdout_dcr,
        dcr_below_holdout_p05=below,
        rare_qi_reproduction_rate=_rare_qi_reproduction(real, fake, qi),
        t_closeness=_t_closeness(real, fake, qi, sensitive, kinds),
        sdmetrics=_sdmetrics_block(real, held, fake, use, qi, sensitive),
    )
