"""Fidelity and privacy per subgroup: is the synthetic table as good, and as safe, for small groups as for everyone?

Aggregate scores can hide a subgroup for which the generator is poor or for which synthetic rows sit suspiciously
close to real people (outliers and minorities are the most exposed records). For each named subgroup
(:class:`semsynth.structure.Subgroup`) this module reports, next to the overall figure:

* the number of real training, holdout and synthetic rows in the group;
* marginal fidelity of the group's synthetic rows against the group's holdout rows;
* the exact-match rate and the share of synthetic rows closer to a training record than the 5th percentile of
  the group's holdout rows, with bootstrap intervals;
* the gap to the overall score, and the worst group.

A group with fewer holdout rows than ``min_size`` is listed with its sizes only: a score from a handful of rows is
noise, and showing it would invite reading it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from .structure import Subgroup

LOGGER = logging.getLogger(__name__)

DEFAULT_MIN_SIZE = 30
HEADLINES = ("exact_match_rate", "dcr_below_holdout_p05", "disc_jsd_mean", "cont_ks_mean")


def _scores(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    synth: pd.DataFrame,
    frame: pd.DataFrame,
    disc_cols: list[str],
    cont_cols: list[str],
    seed: int,
    reps: int,
    missing: str | Mapping[str, str],
) -> dict[str, Any]:
    from .evaluate import holdout_metrics
    from .privacy_metrics import summarize_privacy

    marginal = holdout_metrics(holdout, synth, disc_cols, cont_cols)["summary"]
    privacy = summarize_privacy(
        train, synth, frame, holdout, seed=seed, missing=missing, bootstrap_reps=reps, use_sdmetrics=False
    )
    return {
        "exact_match_rate": privacy.exact_match_rate,
        "dcr_below_holdout_p05": privacy.dcr_below_holdout_p05,
        "disc_jsd_mean": marginal.get("disc_jsd_mean"),
        "cont_ks_mean": marginal.get("cont_ks_mean"),
        "intervals": {k: v for k, v in privacy.intervals.items() if k in ("exact_match_rate", "dcr_below_holdout_p05")},
    }


def subgroup_scores(
    train: pd.DataFrame,
    holdout: pd.DataFrame,
    synth: pd.DataFrame,
    groups: Iterable[Subgroup],
    *,
    privacy_frame: pd.DataFrame,
    disc_cols: list[str],
    cont_cols: list[str],
    min_size: int = DEFAULT_MIN_SIZE,
    seed: int = 0,
    reps: int = 0,
    missing: str | Mapping[str, str] = "category",
) -> dict[str, Any]:
    """Scores per subgroup and overall, the gap of each group to the overall score, and the worst group.

    Args:
        train: Real rows the generator learned from.
        holdout: Real rows it never saw.
        synth: The synthetic table.
        groups: The subgroups to report; membership is evaluated on each table separately.
        privacy_frame: ``variable``, ``role`` and ``type`` of each column.
        disc_cols: Discrete columns, for the marginal fidelity.
        cont_cols: Continuous columns.
        min_size: Fewest holdout and synthetic rows for which a group gets scores.
        seed: Seed for subsampling and the bootstrap.
        reps: Bootstrap resamples for the intervals; 0 turns them off.
        missing: Missing-value policy of the distances (see :mod:`semsynth.distance`).

    Returns:
        ``overall``, ``groups`` (sizes, scores and ``gap``, or ``status: too_small``) and ``worst`` (for each headline
        score, the group furthest from the overall value in the unfavourable direction).
    """
    from .structure import membership

    groups = list(groups)
    args = (privacy_frame, disc_cols, cont_cols, seed, reps, missing)
    overall = _scores(train, holdout, synth, *args)
    masks = {name: membership(table, groups) for name, table in (("train", train), ("holdout", holdout), ("synth", synth))}
    out: dict[str, Any] = {}
    for group in groups:
        sizes = {name: int(m[group.name].sum()) for name, m in masks.items()}
        record: dict[str, Any] = {"label": group.label, "condition": group.condition, "rows": sizes}
        if min(sizes["holdout"], sizes["synth"]) < min_size:
            out[group.name] = {**record, "status": "too_small", "min_size": min_size}
            continue
        try:
            scores = _scores(
                train, holdout[masks["holdout"][group.name]], synth[masks["synth"][group.name]], *args
            )
        except Exception as exc:
            LOGGER.exception("Subgroup %s failed", group.name)
            out[group.name] = {**record, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"}
            continue
        gap = {k: _diff(scores[k], overall[k]) for k in HEADLINES}
        out[group.name] = {**record, "status": "ok", **scores, "gap": gap}
    return {"min_size": min_size, "overall": overall, "groups": out, "worst": _worst(out)}


def _diff(value: Any, reference: Any) -> float | None:
    if value is None or reference is None or value != value or reference != reference:
        return None
    return float(value) - float(reference)


def _worst(groups: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each headline score the group with the largest gap; higher is worse for every one of them."""
    worst: dict[str, dict[str, Any]] = {}
    for key in HEADLINES:
        gaps = {n: g["gap"][key] for n, g in groups.items() if g.get("status") == "ok" and g["gap"].get(key) is not None}
        if gaps:
            name = max(gaps, key=gaps.__getitem__)
            worst[key] = {"group": name, "gap": gaps[name]}
    return worst
