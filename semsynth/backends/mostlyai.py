"""MOSTLY AI TabularARGN backend (experimental).

A neural model for one table: every column is an autoregressive step over embeddings, trained with PyTorch on the CPU or a
GPU. It needs the extra ``mostlyai`` (PyTorch, several hundred MB on the CPU build) and does not run in Pyodide.
Rows with missing values should be removed first: the pipeline gives the complete rows to every backend.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

from ..result import SynthesisResult
from ..utils import coerce_continuous_to_float, split_columns

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)


def _version() -> str:
    try:
        return importlib.metadata.version("mostlyai-engine")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - not installed
        return "unknown"


def _encoding_types(disc_cols: list[str], cont_cols: list[str]) -> dict[str, str]:
    """TabularARGN column types: labels and codes are categorical, numbers are modelled as numbers."""
    return {**dict.fromkeys(disc_cols, "TABULAR_CATEGORICAL"), **dict.fromkeys(cont_cols, "TABULAR_NUMERIC_AUTO")}


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    rows: int | None = None,
    seed: int = 0,
    max_epochs: float = 100.0,
    max_training_time: float = 15.0,
    value_protection: bool = True,
    epsilon: float | None = None,
    device: str = "cpu",
    **options: Any,
) -> SynthesisResult:
    """Fit TabularARGN on ``df`` and draw ``rows`` rows.

    Args:
        df: The table to learn from; rows with missing values are not supported.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its levels decide which columns are categorical.
        rows: Number of rows to draw; the rows of ``df`` when omitted.
        seed: Random seed.
        max_epochs: Most training epochs; training also stops early when the validation loss stops improving.
        max_training_time: Most minutes of training.
        value_protection: Replace rare values (those that identify a few rows) by a placeholder when sampling.
        epsilon: If given, train with differential privacy and this budget (DP-SGD); ``None`` trains without it.
        device: ``cpu`` or ``cuda``.
        **options: Recorded as parameters of the run.

    Raises:
        ImportError: If ``mostlyai-engine`` is missing (extra ``mostlyai``).
    """
    try:
        from mostlyai.engine import TabularARGN
    except ImportError as exc:
        raise ImportError("The mostlyai backend needs 'mostlyai-engine'; install it with pip install 'semsynth[mostlyai]'.") from exc

    count = int(rows or len(df))
    disc_cols, cont_cols = split_columns(df, codebook)
    working = coerce_continuous_to_float(df.copy(), cont_cols)
    working[disc_cols] = working[disc_cols].astype(str)
    dp = {"max_epsilon": float(epsilon)} if epsilon else None
    LOGGER.info("Fitting TabularARGN on %d rows, %d columns", len(working), working.shape[1])
    model = TabularARGN(
        max_epochs=max_epochs,
        max_training_time=max_training_time,
        value_protection=value_protection,
        differential_privacy=dp,
        tgt_encoding_types=_encoding_types(disc_cols, cont_cols),
        device=device,
        random_state=seed,
    )
    model.fit(working)
    drawn = model.sample(n_samples=count).reindex(columns=df.columns)
    for column in disc_cols:  # back to the dtype of the real column where the labels are numbers
        if not str(df[column].dtype).startswith(("object", "string", "category")):
            drawn[column] = drawn[column].astype(float).round().astype(df[column].dtype)
    return SynthesisResult(
        synthetic_data=coerce_continuous_to_float(drawn, cont_cols),
        backend="mostlyai",
        parameters={"rows": count, "seed": seed, "max_epochs": max_epochs, "epsilon": epsilon, "params": dict(options)},
        provenance={"engine": "mostlyai-engine", "engine_version": _version()},
        learned_model=model,
    )
