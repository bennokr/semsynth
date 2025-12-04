# ---------------------------
# OpenML
# ---------------------------

import json
import logging
import pathlib
import warnings
from typing import Dict, List, Optional

import pandas as pd
from pathlib import Path

from ..specs import DatasetSpec
from ._helpers import (
    CachePaths,
    DatasetPayload,
    clean_dataset_frame,
    load_cached_payload,
    store_cached_payload,
)


def get_default_openml(
    cache_dir: Path = Path("downloads-cache/openml/defaults"),
) -> List[DatasetSpec]:
    return [
        DatasetSpec("openml", "adult", target="class"),
        DatasetSpec("openml", "credit-g", target="class"),
        DatasetSpec("openml", "titanic", target="survived"),
        DatasetSpec("openml", "bank-marketing", target="y"),
    ]


def list_openml(
    name_substr: Optional[str] = None,
    cat_min: int = 1,
    num_min: int = 1,
    cache_dir: Path = Path("downloads-cache/openml/"),
) -> pd.DataFrame:
    import openml

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        logging.info("Requesting OpenML datasets")
        df = openml.datasets.list_datasets(output_format="dataframe", status="active")
        numcols = df.select_dtypes(include="float").columns
        df = df.astype({col: "Int64" for col in numcols})
    need = (df["NumberOfSymbolicFeatures"].fillna(0) >= cat_min) & (
        df["NumberOfNumericFeatures"].fillna(0) >= num_min
    )
    sets = df.loc[
        need,
        [
            "did",
            "name",
            "version",
            "NumberOfInstances",
            "NumberOfSymbolicFeatures",
            "NumberOfNumericFeatures",
        ],
    ]
    if name_substr:
        logging.info(f"Filtering OpenML datasets ({name_substr=})")
        mask = sets["name"].str.contains(name_substr, case=False, na=False)
        sets = sets.loc[mask]
    sets = sets.sort_values(["name", "version"]).drop_duplicates("name", keep="last")
    rename = {
        "did": "id",
        "NumberOfInstances": "n_instances",
        "NumberOfSymbolicFeatures": "n_categorical",
        "NumberOfNumericFeatures": "n_numeric",
    }
    sets = sets.rename(columns=rename)
    sets["min_cat_num"] = sets[["n_categorical", "n_numeric"]].min(axis=1)
    return sets.sort_values("min_cat_num", ascending=False).reset_index(drop=True)


def _openml_cache_paths(cache_root: Path, dataset_id: int) -> CachePaths:
    return CachePaths(
        data=cache_root / f"{dataset_id}.csv.gz",
        meta=cache_root / f"{dataset_id}.meta.json",
    )


def load_openml_by_name(name: str, cache_dir: pathlib.Path | Path) -> DatasetPayload:
    """Load an OpenML dataset by name, with local caching of the data payload.

    Caching layout:
      - downloads-cache/openml/by_name/{name}.json: pointer to dataset ID and metadata.
      - downloads-cache/openml/{did}.csv.gz: cached tabular data.
    """

    cache_root = Path(cache_dir)
    alias_dir = cache_root / "by_name"
    alias_dir.mkdir(parents=True, exist_ok=True)

    spec = DatasetSpec(provider="openml", name=name)
    alias_path = alias_dir / f"{name}.json"
    dataset_id: Optional[int] = None
    alias_info: Dict[str, object] = {}
    if alias_path.exists():
        alias_info = json.loads(alias_path.read_text(encoding="utf-8")) or {}
        dataset_id_raw = alias_info.get("did") or alias_info.get("dataset_id") or alias_info.get("id")
        if dataset_id_raw is not None:
            dataset_id = int(dataset_id_raw)

    if dataset_id is not None:
        cache_paths = _openml_cache_paths(cache_root, dataset_id)
        cached = load_cached_payload(cache_paths)
        if cached:
            df_cached, meta_cached = cached
            spec.id = dataset_id
            target_hint = alias_info.get("target") or meta_cached.get("target")
            if isinstance(target_hint, str) and target_hint:
                spec.target = target_hint
            else:
                spec.target = None
            df_clean, detected_target, color_series = clean_dataset_frame(
                df_cached, target=spec.target, metadata=meta_cached
            )
            spec.target = spec.target or detected_target
            spec.name = str(meta_cached.get("name") or name)
            spec.meta = meta_cached
            return DatasetPayload(
                spec=spec,
                frame=df_clean,
                color=color_series,
                metadata=meta_cached,
            )

    # 2) Fallback to OpenML API and cache results
    import openml

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        df = openml.datasets.list_datasets(
            output_format="dataframe", status="active", data_name=name
        )
    df = df[df["name"] == name]
    if df.empty:
        raise ValueError(f"No active OpenML dataset named {name!r}.")
    latest = df.sort_values("version", ascending=False).iloc[0]
    dataset_id = int(latest["did"])
    dataset = openml.datasets.get_dataset(dataset_id)
    spec.id = dataset_id
    spec.name = dataset.name or name

    Xy, _, _, _ = dataset.get_data(dataset_format="dataframe")
    df_all = Xy.copy()
    df_clean, detected_target, color_series = clean_dataset_frame(df_all)
    if detected_target:
        spec.target = detected_target

    metadata_payload: Dict[str, object] = {
        "id": dataset_id,
        "name": spec.name,
        "version": dataset.version,
        "target": spec.target,
        "url": dataset.url,
        "collection_date": getattr(dataset, "collection_date", None),
    }
    spec.meta = metadata_payload

    cache_paths = _openml_cache_paths(cache_root, dataset_id)
    store_cached_payload(cache_paths, df_clean, metadata_payload)
    alias_payload = {
        "id": dataset_id,
        "name": spec.name,
        "target": spec.target,
    }
    alias_path.write_text(json.dumps(alias_payload, indent=2), encoding="utf-8")

    return DatasetPayload(
        spec=spec,
        frame=df_clean,
        color=color_series,
        metadata=metadata_payload,
    )
