"""Evaluation of synthetic data as pure functions: tables in, dictionaries out. Nothing here writes files."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from .codebook import Codebook
from .metrics import heldout_loglik, per_variable_distances, summarize_distance_metrics

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

__all__ = [
    "build_downstream_meta",
    "build_privacy_metadata",
    "downstream_scores",
    "holdout_metrics",
    "privacy_frame",
    "privacy_scores",
    "split_train_test",
]


def split_train_test(df: pd.DataFrame, test_size: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shuffle and split a table into the rows a backend learns from and the rows kept back for evaluation."""

    from sklearn.model_selection import train_test_split

    train, test = train_test_split(df, test_size=test_size, random_state=seed, shuffle=True)
    return train.reset_index(drop=True), test.reset_index(drop=True)


def holdout_metrics(
    real: pd.DataFrame,
    synthetic: pd.DataFrame,
    disc_cols: list[str],
    cont_cols: list[str],
    *,
    model: Any = None,
    bootstrap_reps: int = 0,
    seed: int = 0,
) -> dict[str, Any]:
    """Per-variable distances between real and synthetic columns, and their summary.

    Args:
        real: Real rows that the backend did not learn from.
        synthetic: The synthetic table.
        disc_cols: Names of the discrete columns.
        cont_cols: Names of the continuous columns.
        model: The learned model; if it has a ``logl`` method (a PyBNesian network), the log-likelihood of the
            held-out rows is added as ``heldout_loglik``.
        bootstrap_reps: Random splits of the pooled rows for ``summary_null``, the range each summary value takes
            when the synthetic rows are exchangeable with real ones (see
            :func:`semsynth.uncertainty.permutation_null`); 0 skips it. Costs this many extra scorings.
        seed: Seed of the splits.

    Returns:
        ``summary`` (JSD for discrete, KS and Wasserstein for continuous columns), ``per_variable`` (one record
        per column) and the sizes of the tables.
    """

    distances = per_variable_distances(real, synthetic, disc_cols, cont_cols)
    summary = summarize_distance_metrics(distances)
    null = _summary_null(real, synthetic, disc_cols, cont_cols, summary, bootstrap_reps, seed) if bootstrap_reps else {}
    return {
        **({"summary_null": null} if null else {}),
        **({"heldout_loglik": heldout_loglik(model, real)} if hasattr(model, "logl") else {}),
        "summary": summary,
        "per_variable": distances.to_dict("records"),
        "test_rows": len(real),
        "synth_rows": len(synthetic),
        "discrete_cols": len(disc_cols),
        "continuous_cols": len(cont_cols),
    }


def _summary_null(
    real: pd.DataFrame,
    synthetic: pd.DataFrame,
    disc_cols: list[str],
    cont_cols: list[str],
    observed: dict[str, float],
    reps: int,
    seed: int,
) -> dict[str, Any]:
    """Noise floor of each marginal summary value: the real and synthetic rows are pooled and split at random."""
    import pandas as pd

    from .uncertainty import permutation_null

    pooled = pd.concat([real, synthetic], ignore_index=True)

    def split_summary(first: Any, second: Any) -> dict[str, float]:
        return summarize_distance_metrics(
            per_variable_distances(pooled.iloc[first], pooled.iloc[second], disc_cols, cont_cols)
        )

    names = {k: v for k, v in observed.items() if k in ("disc_jsd_mean", "cont_ks_mean", "cont_w1_mean")}
    return permutation_null(split_summary, len(real), len(synthetic), names, reps=reps, seed=seed)


def _type_name(inferred: Mapping[str, str], column: str) -> str:
    return "numeric" if inferred.get(column, "continuous") == "continuous" else "categorical"


def build_privacy_metadata(
    df: pd.DataFrame,
    inferred: Mapping[str, str],
    *,
    metadata: Any | None = None,
    role_overrides: Mapping[str, str] | None = None,
    target: str | None = None,
) -> pd.DataFrame:
    """The ``variable``, ``role`` and ``type`` of each column, as the privacy metrics expect them.

    The columns come from ``metadata`` (a codebook or a document that can be read as one) or, without it, from ``df``.
    The target has the role ``target``, a column named like an identifier ``id`` and every other column ``qi`` (a
    quasi-identifier). ``role_overrides`` (column name to ``qi``, ``sensitive``, ``id`` or ``ignore``) are applied last.
    """

    import pandas as pd

    frame: pd.DataFrame | None
    try:
        codebook = Codebook.read(metadata) if metadata is not None else Codebook.from_frame(df)
        frame = codebook.privacy_frame(inferred, target) if codebook.columns else None
    except Exception:
        LOGGER.exception("Failed to read the codebook for the privacy frame")
        frame = None
    if frame is None:
        frame = pd.DataFrame(
            [{"variable": c, "role": "qi", "type": _type_name(inferred, c)} for c in inferred]
        )
    for column, role in (role_overrides or {}).items():
        if column in frame.variable.values:
            frame.loc[frame.variable == column, "role"] = role
    if target:
        mask = frame.variable == target
        if mask.any():
            frame.loc[mask, "role"] = "target"
        elif target in df.columns:
            extra = pd.DataFrame([{"variable": target, "role": "target", "type": _type_name(inferred, target)}])
            frame = pd.concat([frame, extra])
    return frame


def privacy_frame(
    real_df: pd.DataFrame,
    inferred: Mapping[str, str],
    metadata: Any | None = None,
    *,
    role_overrides: Mapping[str, str] | None = None,
    target: str | None = None,
) -> pd.DataFrame:
    """The ``variable``, ``role`` and ``type`` of each column for the privacy and joint-fidelity metrics."""

    return build_privacy_metadata(real_df, inferred, metadata=metadata, role_overrides=role_overrides, target=target)


def privacy_scores(
    real_df: pd.DataFrame,
    synth_df: pd.DataFrame,
    inferred: Mapping[str, str],
    metadata: Any | None = None,
    *,
    holdout_df: pd.DataFrame | None = None,
    summarizer: Any | None = None,
    role_overrides: Mapping[str, str] | None = None,
    target: str | None = None,
    seed: int = 0,
    missing: str | Mapping[str, str] = "category",
    bootstrap_reps: int = 0,
) -> dict[str, Any]:
    """Privacy facts about a synthetic table: exact matches, distance to the closest record, attribute inference.

    Args:
        real_df: The real rows the generator was fitted on.
        synth_df: The synthetic table.
        inferred: Column names mapped to ``discrete`` or ``continuous``.
        metadata: A :class:`~semsynth.codebook.Codebook` or a document readable as one.
        holdout_df: Real rows the generator never saw, which give the reference for what "close" means.
        summarizer: Function ``(real, synthetic, metadata_frame, holdout)`` returning a dataclass or mapping;
            :func:`semsynth.privacy_metrics.summarize_privacy` when omitted.
        role_overrides: Privacy role by column name, applied over the metadata.
        target: Name of the target column, which gets the ``target`` role.
        seed: Seed for subsampling and the bootstrap.
        missing: How missing values enter the distances (``category``, ``observed``, ``asymmetric``, or a mapping by
            column); see :mod:`semsynth.distance`.
        bootstrap_reps: Resamples for the intervals.
    """

    if summarizer is None:
        from functools import partial

        from .privacy_metrics import summarize_privacy

        summarizer = partial(summarize_privacy, seed=seed, missing=missing, bootstrap_reps=bootstrap_reps)
    frame = privacy_frame(real_df, inferred, metadata, role_overrides=role_overrides, target=target)
    summary = summarizer(real_df, synth_df, frame, holdout_df)
    if is_dataclass(summary) and not isinstance(summary, type):
        return asdict(summary)
    return dict(summary)


def build_downstream_meta(df: pd.DataFrame, inferred: Mapping[str, str]) -> Codebook:
    """A codebook for downstream metrics when there is no metadata: the levels of the columns from ``inferred``."""

    columns: list[dict[str, Any]] = []
    for column in df.columns:
        if inferred.get(column, "continuous") == "continuous":
            columns.append({"name": str(column), "level": "numerical"})
            continue
        categories = [str(cat) for cat in df[column].astype("category").cat.categories]
        entry: dict[str, Any] = {"name": str(column), "level": "nominal"}
        if categories:
            entry["values"] = [{"code": cat} for cat in categories]
        columns.append(entry)
    return Codebook({"columns": columns})  # type: ignore[arg-type]


def downstream_scores(
    real_df: pd.DataFrame,
    synth_df: pd.DataFrame,
    inferred: Mapping[str, str],
    target: str | None,
    metadata: Codebook | None = None,
    *,
    compare: Any | None = None,
) -> dict[str, Any]:
    """How often a model fitted on the synthetic table has the same coefficient signs as one fitted on the real.

    Args:
        real_df: Real table.
        synth_df: Synthetic table.
        inferred: Column names mapped to ``discrete`` or ``continuous``.
        target: Name of the target column.
        metadata: Codebook with the levels; built from ``inferred`` when omitted.
        compare: Function ``(real, synthetic, codebook, target=...)`` returning ``formula`` and a ``compare`` table;
            :func:`semsynth.downstream_fidelity.compute_downstream` when omitted.

    Raises:
        ImportError: If the default comparison is used and the ``statsmodels`` extra is missing.
    """

    if compare is None:
        from .downstream_fidelity import compute_downstream as compare
    meta = metadata if isinstance(metadata, Codebook) else build_downstream_meta(real_df, inferred)
    results = compare(real_df, synth_df, meta, target=target)
    sign_match_rate = float("nan")
    table = results.get("compare")
    if hasattr(table, "__getitem__"):
        try:
            sign_match_rate = float(table["sign_match"].astype(float).mean())
        except Exception:
            sign_match_rate = float("nan")
    return {"formula": results.get("formula"), "sign_match_rate": sign_match_rate}
