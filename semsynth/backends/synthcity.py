from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

from ..result import SynthesisResult
from ..torch_compat import ensure_npsum_compat, ensure_torch_rmsnorm, ensure_trapz_compat
from ..utils import (
    coerce_continuous_to_float,
    coerce_discrete_to_category,
    rename_categorical_categories_to_str,
    split_columns,
)

LOGGER = logging.getLogger(__name__)


def canonical_generator_name(name: str) -> str:
    """Return the canonical synthcity plugin name for a user alias."""
    key = str(name).strip().lower()
    if not key:
        raise ValueError("Generator name must be non-empty")
    aliases = {
        "ctgan": "ctgan",
        "ads-gan": "adsgan",
        "adsgan": "adsgan",
        "pategan": "pategan",
        "dp-gan": "dpgan",
        "dpgan": "dpgan",
        "tvae": "tvae",
        "rtvae": "rtvae",
        "nflow": "nflow",
        "bn": "bayesian_network",
        "bayesiannetwork": "bayesian_network",
        "bayesian_network": "bayesian_network",
        "privbayes": "privbayes",
        "arf": "arf",
        "arfpy": "arf",
        "great": "great",
    }
    if key not in aliases:
        raise ValueError(f"Unknown generator alias: {name}")
    return aliases[key]


def _load_synthcity_plugins():
    try:
        from synthcity.plugins import Plugins
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "SynthCity backend requires 'synthcity'; install with pip install semsynth[synthcity]"
        ) from exc
    return Plugins


def _get_plugin(name: str, params: dict[str, Any]):
    ensure_trapz_compat()
    ensure_npsum_compat()
    ensure_torch_rmsnorm()
    Plugins = _load_synthcity_plugins()

    logging.info("Loading synthcity plugin: %s", name)
    return Plugins().get(name, **(params or {}))


def _normalize_plugin_params(
    plugin_name: str, params: dict[str, Any]
) -> dict[str, Any]:
    normalized = {k: v for k, v in (params or {}).items() if v is not None}
    iter_plugins = {
        "ctgan",
        "tvae",
        "pategan",
        "adsgan",
        "dpgan",
    }
    if (
        plugin_name in iter_plugins
        and "epochs" in normalized
        and "n_iter" not in normalized
    ):
        normalized["n_iter"] = normalized.pop("epochs")
    return normalized


def _ensure_dataframe(obj: Any) -> pd.DataFrame:
    import numpy as np
    import pandas as pd

    if isinstance(obj, pd.DataFrame):
        return obj
    if hasattr(obj, "dataframe"):
        df = obj.dataframe()
        if isinstance(df, pd.DataFrame):
            return df
    if hasattr(obj, "to_pandas"):
        df = obj.to_pandas()
        if isinstance(df, pd.DataFrame):
            return df
    if isinstance(obj, np.ndarray):
        return pd.DataFrame(obj)
    return pd.DataFrame(obj)


def _version() -> str:
    try:
        return importlib.metadata.version("synthcity")
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
    """Fit a SynthCity generator on ``df`` and draw ``rows`` rows.

    Args:
        df: The table to learn from.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its levels decide which columns are discrete.
        rows: Number of rows to draw; the rows of ``df`` when omitted.
        seed: Recorded with the run; SynthCity generators take their own ``random_state`` among the options.
        **options: ``type``, the generator (an alias such as ``ctgan``, ``tvae``, ``adsgan`` or ``bn``), and the
            settings of that generator; ``epochs`` is accepted for the generators that call it ``n_iter``.

    Returns:
        The synthetic table, with ``learned_model`` set to the fitted generator.

    Raises:
        ValueError: If ``type`` is missing or not a known generator.
    """

    settings = dict(options)
    model_type = settings.pop("type", None)
    if not model_type:
        raise ValueError("The synthcity backend needs a generator: pass type='ctgan', 'tvae', ...")
    disc_cols, cont_cols = split_columns(df, codebook)
    working = coerce_discrete_to_category(df.copy(), disc_cols)
    working = rename_categorical_categories_to_str(working, disc_cols)
    working = coerce_continuous_to_float(working, cont_cols).reset_index(drop=True)

    plugin_name = canonical_generator_name(model_type)
    plugin_params = _normalize_plugin_params(plugin_name, settings)
    plugin = _get_plugin(plugin_name, plugin_params)
    LOGGER.info("Fitting synthcity %s on %d rows", plugin_name, len(working))
    plugin.fit(working)
    count = int(rows or len(working))
    synthetic = _ensure_dataframe(plugin.generate(count=count)).reindex(columns=working.columns)
    for column in disc_cols:
        synthetic[column] = synthetic[column].astype("category")
    synthetic = rename_categorical_categories_to_str(synthetic, disc_cols)
    synthetic = coerce_continuous_to_float(synthetic, cont_cols)
    return SynthesisResult(
        synthetic_data=synthetic,
        backend="synthcity",
        parameters={"generator": plugin_name, "params": plugin_params, "rows": count, "seed": seed},
        provenance={"engine": "synthcity", "engine_version": _version()},
        learned_model=plugin,
    )
