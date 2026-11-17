"""Reference tables that give the evaluation scores their scale.

A score alone does not say whether it is good. Every score of a synthetic table is therefore computed again for two
stand-in tables, with the same functions, rows and holdout:

``real_sample``
    Rows drawn from the training data. For fidelity and utility this is the ceiling: a perfect generator scores like
    a fresh real sample, and the gap that remains is sampling noise. For privacy it is the worst case, a leak of the
    whole table.
``independent_marginals``
    Each column drawn independently from its training values. It keeps every column's distribution and destroys
    every relation (and every co-missingness), so it is the floor for joint fidelity and for utility. Its marginal
    fidelity is a ceiling for what "same marginals" can claim.

The holdout rows play the role of "other real people": their distance to the training rows is the reference for the
privacy scores (see :mod:`semsynth.privacy_metrics`).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

REFERENCES = ("real_sample", "independent_marginals")


def reference_tables(train: pd.DataFrame, rows: int, seed: int) -> dict[str, pd.DataFrame]:
    """The stand-in tables of :data:`REFERENCES`, each with ``rows`` rows (at most ``len(train)`` for the sample)."""
    import pandas as pd

    sample = train.sample(min(rows, len(train)), random_state=seed).reset_index(drop=True)
    independent = pd.DataFrame(
        {
            column: train[column].sample(rows, replace=True, random_state=seed + 1 + i).to_numpy()
            for i, column in enumerate(train.columns)
        }
    )
    return {"real_sample": sample, "independent_marginals": independent}


def compact_scores(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    table: pd.DataFrame,
    *,
    disc_cols: list[str],
    cont_cols: list[str],
    privacy_frame: pd.DataFrame,
    seed: int = 0,
    reps: int = 0,
    missing: str | Mapping[str, str] = "category",
) -> dict[str, Any]:
    """The headline numbers of fidelity, joint fidelity and privacy for one table, in one flat record.

    The same function scores the synthetic table and the references, so their numbers are comparable.
    Each part that cannot be computed is left out (and logged), not guessed.
    """
    from .evaluate import holdout_metrics
    from .joint_fidelity import joint_fidelity
    from .privacy_metrics import summarize_privacy

    out: dict[str, Any] = {}
    intervals: dict[str, list[float]] = {}
    nulls: dict[str, Any] = {}
    marginal = holdout_metrics(holdout, table, disc_cols, cont_cols, bootstrap_reps=min(reps, 50), seed=seed)
    out.update({k: marginal["summary"].get(k) for k in ("disc_jsd_mean", "cont_ks_mean", "cont_w1_mean")})
    nulls.update(marginal.get("summary_null", {}))
    kinds = dict(zip(privacy_frame.variable, privacy_frame.type, strict=False))
    joint = joint_fidelity(holdout, table, kinds, seed=seed, reps=min(reps, 50))
    out["pairwise_tvd_mean"] = joint["pairwise"].get("tvd_mean")
    out["classifier_auc"] = joint["classifier"].get("auc")
    nulls["pairwise_tvd_mean"] = joint["pairwise"].get("null", {})
    intervals["classifier_auc"] = joint["classifier"].get("auc_interval", [])
    privacy = summarize_privacy(
        train, table, privacy_frame, holdout, seed=seed, missing=missing, bootstrap_reps=reps, use_sdmetrics=False
    )
    out["exact_match_rate"] = privacy.exact_match_rate
    out["dcr_median"] = privacy.dcr_synthetic["median"]
    out["dcr_below_holdout_p05"] = privacy.dcr_below_holdout_p05
    intervals["dcr_below_holdout_p05"] = privacy.intervals.get("dcr_below_holdout_p05", [])
    out["intervals"] = {k: v for k, v in intervals.items() if v and v == v}
    out["null"] = {k: v for k, v in nulls.items() if v}
    return out


def evaluate_references(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    synthetic: pd.DataFrame,
    *,
    disc_cols: list[str],
    cont_cols: list[str],
    privacy_frame: pd.DataFrame,
    seed: int = 0,
    reps: int = 0,
    missing: str | Mapping[str, str] = "category",
) -> dict[str, Any]:
    """Score the synthetic table and the reference tables with :func:`compact_scores`, and record the protocol."""
    tables = {"synthetic": synthetic, **reference_tables(train, len(synthetic), seed)}
    scores: dict[str, Any] = {}
    for name, table in tables.items():
        try:
            scores[name] = compact_scores(
                train, holdout, table, disc_cols=disc_cols, cont_cols=cont_cols, privacy_frame=privacy_frame,
                seed=seed, reps=reps, missing=missing,
            )
        except Exception as exc:
            LOGGER.exception("Failed to score %s", name)
            scores[name] = {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "protocol": {
            "train_rows": len(train),
            "holdout_rows": len(holdout),
            "table_rows": len(synthetic),
            "seed": seed,
            "bootstrap_reps": reps,
            "references": list(REFERENCES),
            "note": "synthetic, real_sample and independent_marginals are scored with the same functions on the same "
            "holdout; real_sample is the fidelity ceiling and the privacy worst case.",
        },
        "scores": scores,
    }
