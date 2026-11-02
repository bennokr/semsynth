"""MetaSyn backend: a metadata-only generative model per column.

MetaSyn learns one distribution per column and draws columns independently, so it is the backend to use for
dummy data that has the right types, ranges and missingness but no relations between columns.
"""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..result import SynthesisResult
from ..utils import coerce_continuous_to_float, split_columns

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)


def _load_metasyn() -> Any:
    try:
        from metasyn.metaframe import MetaFrame
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "The MetaSyn backend needs 'metasyn'; install it with `pip install 'semsynth[metasyn]'`."
        ) from exc
    return MetaFrame


def _to_pandas(drawn: Any) -> pd.DataFrame:
    import pandas as pd

    return drawn.to_pandas() if hasattr(drawn, "to_pandas") else pd.DataFrame(drawn)


def _restore_dtypes(
    synthetic: pd.DataFrame, real: pd.DataFrame, disc_cols: list[str], cont_cols: list[str]
) -> pd.DataFrame:
    """Give the synthetic columns the column order and categorical levels of the real table."""

    import pandas as pd

    synthetic = synthetic.reindex(columns=real.columns)
    for column in disc_cols:
        synthetic[column] = synthetic[column].astype("category")
        if isinstance(real[column].dtype, pd.CategoricalDtype):
            synthetic[column] = synthetic[column].cat.set_categories(real[column].cat.categories)
    return coerce_continuous_to_float(synthetic, cont_cols)


def _version() -> str:
    try:
        return importlib.metadata.version("metasyn")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - vendored copy
        return "unknown"


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    rows: int | None = None,
    seed: int = 0,
    **options: Any,
) -> SynthesisResult:
    """Fit MetaSyn on ``df`` and draw ``rows`` rows.

    Args:
        df: The table to learn from.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its levels decide which columns are discrete.
        rows: Number of rows to draw; the rows of ``df`` when omitted.
        seed: Random seed handed to MetaSyn.
        **options: Recorded as parameters of the run; MetaSyn has no settings that are used here.

    Returns:
        The synthetic table, with ``learned_model`` set to the fitted MetaFrame.
    """

    MetaFrame = _load_metasyn()
    count = int(rows or len(df))
    disc_cols, cont_cols = split_columns(df, codebook)
    working = coerce_continuous_to_float(df.copy(), cont_cols)

    LOGGER.info("Fitting MetaSyn on %d rows", len(working))
    frame = MetaFrame.fit_dataframe(working, progress_bar=False)
    drawn = frame.synthesize(n=count, seed=seed, progress_bar=False)
    synthetic = _restore_dtypes(_to_pandas(drawn), df, disc_cols, cont_cols)

    return SynthesisResult(
        synthetic_data=synthetic,
        backend="metasyn",
        parameters={"rows": count, "seed": seed, "params": dict(options)},
        provenance={"engine": "metasyn", "engine_version": _version()},
        learned_model=frame,
    )


def run_experiment(
    df: pd.DataFrame,
    *,
    provider: str | None,
    dataset_name: str | None,
    provider_id: int | None,
    outdir: str,
    label: str,
    model_info: dict[str, Any] | None,
    rows: int | None,
    seed: int,
    test_size: float,
    codebook_jsonld: dict[str, Any] | None = None,
) -> Path:
    """Fit on a training split, evaluate on the held-out rows and write the run's files.

    This is the file-based entry point that the other backends still implement; the pipeline calls
    :func:`synthesize` and :func:`semsynth.synthesis.write_run` itself.
    """

    from ..evaluate import holdout_metrics, split_train_test
    from ..synthesis import write_run

    disc_cols, cont_cols = split_columns(df)
    train, test = split_train_test(df, test_size, seed)
    result = synthesize(train, rows=rows or len(df), seed=seed, **dict(model_info or {}))
    metrics = holdout_metrics(test, result.synthetic_data, disc_cols, cont_cols)
    result = replace(
        result,
        metrics={**metrics, "train_rows": len(train)},
        parameters={**result.parameters, "test_size": test_size},
    )
    dataset = {"provider": provider, "dataset_name": dataset_name, "provider_id": provider_id}
    return write_run(
        result,
        Path(outdir) / "models" / label,
        label=label,
        dataset=dataset,
        codebook_jsonld=codebook_jsonld,
    )
