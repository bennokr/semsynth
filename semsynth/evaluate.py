"""Evaluation of synthetic data as pure functions: tables in, dictionaries out. Nothing here writes files."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from .codebook import Codebook, privacy_role
from .metrics import per_variable_distances, summarize_distance_metrics

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

__all__ = [
    "build_downstream_meta",
    "build_privacy_metadata",
    "downstream_scores",
    "holdout_metrics",
    "privacy_scores",
    "split_train_test",
]


def split_train_test(df: pd.DataFrame, test_size: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shuffle and split a table into the rows a backend learns from and the rows kept back for evaluation."""

    from sklearn.model_selection import train_test_split

    train, test = train_test_split(df, test_size=test_size, random_state=seed, shuffle=True)
    return train.reset_index(drop=True), test.reset_index(drop=True)


def holdout_metrics(
    real: pd.DataFrame, synthetic: pd.DataFrame, disc_cols: list[str], cont_cols: list[str]
) -> dict[str, Any]:
    """Per-variable distances between real and synthetic columns, and their summary.

    Args:
        real: Real rows that the backend did not learn from.
        synthetic: The synthetic table.
        disc_cols: Names of the discrete columns.
        cont_cols: Names of the continuous columns.

    Returns:
        ``summary`` (JSD for discrete, KS and Wasserstein for continuous columns), ``per_variable`` (one record
        per column) and the sizes of the tables.
    """

    distances = per_variable_distances(real, synthetic, disc_cols, cont_cols)
    return {
        "summary": summarize_distance_metrics(distances),
        "per_variable": distances.to_dict("records"),
        "test_rows": len(real),
        "synth_rows": len(synthetic),
        "discrete_cols": len(disc_cols),
        "continuous_cols": len(cont_cols),
    }


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

    Roles come from ``metadata`` (a codebook or a document that can be read as one); columns without any
    metadata are quasi-identifiers. ``role_overrides`` and ``target`` are applied last.
    """

    import pandas as pd

    frame: pd.DataFrame | None
    try:
        codebook = Codebook.read(metadata) if metadata is not None else Codebook.from_frame(df)
        frame = codebook.privacy_frame(inferred) if codebook.columns else None
    except Exception:
        LOGGER.exception("Failed to read metadata for privacy roles")
        frame = None
    if frame is None:
        frame = pd.DataFrame(
            [{"variable": c, "role": "qi", "type": _type_name(inferred, c)} for c in inferred]
        )
    for column, raw_role in (role_overrides or {}).items():
        if column in frame.variable.values:
            frame.loc[frame.variable == column, "role"] = privacy_role(raw_role)
    if target:
        mask = frame.variable == target
        if mask.any():
            frame.loc[mask, "role"] = "target"
        elif target in df.columns:
            extra = pd.DataFrame([{"variable": target, "role": "target", "type": _type_name(inferred, target)}])
            frame = pd.concat([frame, extra])
    return frame


def privacy_scores(
    real_df: pd.DataFrame,
    synth_df: pd.DataFrame,
    inferred: Mapping[str, str],
    metadata: Any | None = None,
    *,
    summarizer: Any | None = None,
    role_overrides: Mapping[str, str] | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """Privacy facts about a synthetic table (overlap, nearest neighbours, k-map, t-closeness).

    Args:
        real_df: Real table without missing values.
        synth_df: Synthetic table.
        inferred: Column names mapped to ``discrete`` or ``continuous``.
        metadata: A :class:`~semsynth.codebook.Codebook` or a document readable as one.
        summarizer: Function ``(real, synthetic, metadata_frame)`` returning a dataclass or mapping; the
            SynthCity-based :func:`semsynth.privacy_metrics.summarize_privacy_synthcity` when omitted.
        role_overrides: Privacy role by column name, applied over the metadata.
        target: Name of the target column, which gets the ``target`` role.

    Raises:
        ImportError: If the default summarizer is used and the ``synthcity`` extra is missing.
    """

    if summarizer is None:
        from .privacy_metrics import summarize_privacy_synthcity as summarizer
    if isinstance(metadata, Codebook):
        frame = metadata.privacy_frame(inferred)
    else:
        frame = build_privacy_metadata(
            real_df, inferred, metadata=metadata, role_overrides=role_overrides, target=target
        )
    if target and target in frame.variable.values:
        frame.loc[frame.variable == target, "role"] = "target"
    summary = summarizer(real_df, synth_df, frame)
    if is_dataclass(summary) and not isinstance(summary, type):
        return asdict(summary)
    return dict(summary)


def build_downstream_meta(
    df: pd.DataFrame,
    inferred: Mapping[str, str],
    target_series: pd.Series | None,
    *,
    target: str | None = None,
) -> Codebook:
    """A codebook for downstream metrics when there is no metadata: levels from ``inferred`` and the target role."""

    import pandas as pd

    target_name: str | None = None
    if isinstance(target_series, pd.Series) and target_series.attrs.get("prov:hadRole") == "target":
        target_name = target_series.name if target_series.name in df.columns else None
    if target_name is None and target and target in df.columns:
        target_name = target

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
    roles = {str(name): "target" if name == target_name else "predictor" for name in df.columns}
    return Codebook({"columns": columns}, roles)  # type: ignore[arg-type]


def downstream_scores(
    real_df: pd.DataFrame,
    synth_df: pd.DataFrame,
    inferred: Mapping[str, str],
    target_series: pd.Series | None,
    metadata: Codebook | None = None,
    *,
    compare: Any | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    """How often a model fitted on the synthetic table has the same coefficient signs as one fitted on the real.

    Args:
        real_df: Real table.
        synth_df: Synthetic table.
        inferred: Column names mapped to ``discrete`` or ``continuous``.
        target_series: The target column, annotated with ``prov:hadRole``.
        metadata: Codebook with the levels and roles; built from ``inferred`` when omitted.
        compare: Function ``(real, synthetic, codebook)`` returning ``formula`` and a ``compare`` table;
            :func:`semsynth.downstream_fidelity.compute_downstream` when omitted.
        target: Name of the target column.

    Raises:
        ImportError: If the default comparison is used and the ``statsmodels`` extra is missing.
    """

    if compare is None:
        from .downstream_fidelity import compute_downstream as compare
    meta = metadata if isinstance(metadata, Codebook) else build_downstream_meta(
        real_df, inferred, target_series, target=target
    )
    results = compare(real_df, synth_df, meta)
    sign_match_rate = float("nan")
    table = results.get("compare")
    if hasattr(table, "__getitem__"):
        try:
            sign_match_rate = float(table["sign_match"].astype(float).mean())
        except Exception:
            sign_match_rate = float("nan")
    return {"formula": results.get("formula"), "sign_match_rate": sign_match_rate}
