from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

from makeprov import OutDir

from ..metrics import per_variable_distances, summarize_distance_metrics
from ..models import model_run_root, write_manifest
from ..torch_compat import ensure_npsum_compat, ensure_torch_rmsnorm, ensure_trapz_compat
from ..utils import (
    coerce_continuous_to_float,
    coerce_discrete_to_category,
    ensure_dir,
    infer_types,
    rename_categorical_categories_to_str,
)


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
        "tabularflow": "tabularflow",
        "bn": "bayesiannetwork",
        "bayesiannetwork": "bayesiannetwork",
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
        raise RuntimeError(
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
    import pandas as pd
    from sklearn.model_selection import train_test_split

    logging.info("Starting synthcity run: %s", label)
    working = df.copy()
    disc_cols, cont_cols = infer_types(working)
    working = coerce_discrete_to_category(working, disc_cols)
    working = rename_categorical_categories_to_str(working, disc_cols)
    working = coerce_continuous_to_float(working, cont_cols)
    train_df, test_df = train_test_split(
        working, test_size=test_size, random_state=seed, shuffle=True
    )
    train_df = train_df.reset_index(drop=True)
    test_df = test_df.reset_index(drop=True)

    for col in cont_cols:
        if col in train_df.columns:
            train_df[col] = pd.to_numeric(train_df[col], errors="coerce").astype(
                "float64"
            )
        if col in test_df.columns:
            test_df[col] = pd.to_numeric(test_df[col], errors="coerce").astype(
                "float64"
            )

    model_type = model_info.pop("type")
    plugin_name = canonical_generator_name(model_type)
    plugin_params = _normalize_plugin_params(plugin_name, model_info)
    plugin = _get_plugin(plugin_name, plugin_params)
    plugin.fit(train_df)
    n_rows = int(rows) if rows else len(train_df)
    generated = plugin.generate(count=n_rows)
    synth_df = _ensure_dataframe(generated)
    synth_df = synth_df.reindex(columns=train_df.columns)
    for col in disc_cols:
        if col in synth_df.columns:
            synth_df[col] = synth_df[col].astype("category")
    synth_df = rename_categorical_categories_to_str(synth_df, disc_cols)
    synth_df = coerce_continuous_to_float(synth_df, cont_cols)

    run_root = model_run_root(Path(outdir))
    run_dir = OutDir(run_root / label)
    ensure_dir(str(run_dir))
    synth_csv = run_dir.file("synthetic.csv")
    synth_df.to_csv(synth_csv, index=False)
    logging.info("Wrote synthetic CSV: %s", synth_csv)
    if codebook_jsonld:
        try:
            from semsynth.codebook import write_parquet

            write_parquet(synth_df, run_dir.file("synthetic.parquet"), codebook_jsonld)
        except Exception as e:
            logging.warning("Parquet with codebook failed: %s", e)

    # Per-variable distances and summary
    dist_df = per_variable_distances(test_df, synth_df, disc_cols, cont_cols)
    dist_df.to_csv(run_dir.file("per_variable_metrics.csv"), index=False)
    metrics = {
        "backend": "synthcity",
        "summary": summarize_distance_metrics(dist_df),
        "train_rows": len(train_df),
        "test_rows": len(test_df),
        "synth_rows": len(synth_df),
        "discrete_cols": len(disc_cols),
        "continuous_cols": len(cont_cols),
        "umap_png": None,
    }
    run_dir.file("metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "backend": "synthcity",
        "name": label,
        "provider": provider,
        "dataset_name": dataset_name,
        "provider_id": provider_id,
        "generator": plugin_name,
        "params": plugin_params,
        "seed": seed,
        "rows": n_rows,
        "test_size": test_size,
    }
    write_manifest(run_dir, manifest)
    logging.info("Finished synthcity run: %s", label)
    return run_dir
