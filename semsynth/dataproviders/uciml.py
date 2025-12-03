# ---------------------------
# UCI Machine Learning Repository via ucimlrepo
# ---------------------------


from datetime import datetime
import json
import logging
import pathlib
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd
import requests
from makeprov import OutPath, rule

from ..specs import DatasetSpec
from ._helpers import (
    CachePaths,
    DatasetPayload,
    clean_dataset_frame,
    load_cached_payload,
    store_cached_payload,
)


EMPTY = (None, "", [], {},)


def _present(value: Any) -> bool:
    """Return True when a value is present and non-empty."""

    try:
        return pd.notna(value) and value not in EMPTY
    except Exception:
        return value not in EMPTY


def _put(target: Mapping[str, Any], key: str, value: Any) -> Mapping[str, Any]:
    """Set ``target[key]`` to ``value`` if present, enabling chained calls."""

    if _present(value):
        target[key] = value
    return target


def _add(target: Mapping[str, Any], key: str, value: Any) -> Mapping[str, Any]:
    """Append ``value`` to list ``target[key]`` when present."""

    if _present(value):
        target.setdefault(key, [])
        target[key].append(value)
    return target


def _prune(value: Any) -> Any:
    """Recursively drop empty fields from dictionaries and lists."""

    if isinstance(value, dict):
        return {k: _prune(v) for k, v in value.items() if _present(_prune(v))}
    if isinstance(value, list):
        pruned = [_prune(v) for v in value]
        return [v for v in pruned if _present(v)]
    return value


def _iso_date(date_string: str) -> str:
    """Convert strings like ``Mon Jan 01 2024`` to ISO-8601 when possible."""

    try:
        return datetime.strptime(date_string, "%a %b %d %Y").date().isoformat()
    except Exception:
        return date_string


def _statistical_datatype(term: str) -> str:
    """Map variable type to a DSV statistical data type class IRI."""

    lowered = (term or "").lower()
    if lowered == "categorical":
        return "dsv:CategoricalDataType"
    if lowered in {"integer", "real", "numeric", "number"}:
        return "dsv:NumericalDataType"
    return "dsv:StatisticalDataType"


def to_dcat_dsv(src: Mapping[str, Any]) -> Mapping[str, Any]:
    """Transform ucimlrepo-style metadata into DCAT + DSV JSON-LD."""

    ctx = {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dcterms": "http://purl.org/dc/terms/",
        "schema": "http://schema.org/",
        "dsv": "https://w3id.org/dsv-ontology#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }

    output: Mapping[str, Any] = {"@context": ctx, "@type": "dcat:Dataset"}

    _put(output, "dcterms:title", src.get("name"))
    _put(output, "dcterms:abstract", src.get("abstract"))
    _put(output, "dcterms:created", src.get("year_of_dataset_creation"))
    _put(output, "dcterms:modified", _iso_date(src.get("last_updated") or ""))
    _put(output, "dcat:landingPage", src.get("repository_url"))
    _put(output, "dcat:theme", src.get("area"))

    identifiers: Mapping[str, Any] = {"ids": []}
    _add(
        identifiers,
        "ids",
        {
            "@type": "schema:PropertyValue",
            "schema:propertyID": "uci",
            "schema:value": src.get("uci_id"),
        },
    )
    _add(
        identifiers,
        "ids",
        {
            "@type": "schema:PropertyValue",
            "schema:propertyID": "DOI",
            "schema:value": src.get("dataset_doi"),
        },
    )
    if identifiers.get("ids"):
        output["dcterms:identifier"] = identifiers["ids"]

    keywords = (src.get("demographics") or []) + (src.get("tasks") or []) + (
        src.get("characteristics") or []
    )
    if keywords:
        output["dcat:keyword"] = keywords

    _put(output, "schema:numberOfItems", src.get("num_instances"))
    if src.get("num_features") is not None:
        output["dcterms:extent"] = f"{src['num_features']} features"

    creators = [
        {"@type": "schema:Person", "schema:name": name}
        for name in (src.get("creators") or [])
        if _present(name)
    ]
    if creators:
        output["dcterms:creator"] = creators

    if _present(src.get("data_url")):
        output["dcat:distribution"] = [
            {
                "@type": "dcat:Distribution",
                "dcat:downloadURL": src["data_url"],
                "dcat:mediaType": "text/csv",
                "dcterms:format": "text/csv",
            }
        ]

    dataset_schema: Mapping[str, Any] = {"@type": "dsv:DatasetSchema"}
    columns: List[Mapping[str, Any]] = []

    for variable in src.get("variables") or []:
        column: Mapping[str, Any] = {"@type": "dsv:Column"}
        _put(column, "schema:name", variable.get("name"))
        _put(column, "dcterms:description", variable.get("description"))
        _put(column, "schema:unitText", variable.get("units"))
        _put(column, "prov:hadRole", variable.get("role"))
        _put(column, "schema:about", variable.get("demographic"))

        summary_stats: Mapping[str, Any] = {"@type": "dsv:SummaryStatistics"}
        _put(
            summary_stats,
            "dsv:statisticalDataType",
            _statistical_datatype(variable.get("type")),
        )
        if (variable.get("missing_values") or "").lower() == "yes":
            _put(
                summary_stats,
                "dsv:missingValueFormat",
                src.get("missing_values_symbol"),
            )
        if _present(summary_stats := _prune(summary_stats)):
            column["dsv:summaryStatistics"] = summary_stats

        columns.append(_prune(column))

    if columns:
        dataset_schema["dsv:column"] = columns
        output["dsv:datasetSchema"] = dataset_schema

    dataset_stats: Mapping[str, Any] = {"@type": "dsv:SummaryStatistics"}
    _put(dataset_stats, "dsv:numberOfRows", src.get("num_instances"))
    _put(dataset_stats, "dsv:numberOfColumns", src.get("num_features"))
    _put(dataset_stats, "dsv:missingValueFormat", src.get("missing_values_symbol"))
    if _present(dataset_stats := _prune(dataset_stats)):
        output["dsv:summaryStatistics"] = dataset_stats

    paper = src.get("intro_paper") or {}
    if paper:
        citation: Mapping[str, Any] = {
            "@type": "schema:ScholarlyArticle",
            "dcterms:title": paper.get("title"),
            "schema:author": [
                author.strip()
                for author in (paper.get("authors") or "").split(",")
                if author.strip()
            ],
            "schema:isPartOf": paper.get("venue") or paper.get("journal"),
            "schema:datePublished": paper.get("year"),
            "schema:url": paper.get("URL"),
        }
        identifiers_secondary: List[Mapping[str, Any]] = []
        if paper.get("DOI"):
            identifiers_secondary.append(
                {
                    "@type": "schema:PropertyValue",
                    "schema:propertyID": "DOI",
                    "schema:value": paper["DOI"],
                }
            )
        if paper.get("pmid"):
            identifiers_secondary.append(
                {
                    "@type": "schema:PropertyValue",
                    "schema:propertyID": "PMID",
                    "schema:value": paper["pmid"],
                }
            )
        if identifiers_secondary:
            citation["schema:identifier"] = identifiers_secondary
        output["schema:citation"] = _prune(citation)

    additional_info = src.get("additional_info") or {}
    _put(output, "dcterms:description", additional_info.get("summary"))
    _put(output, "dcterms:purpose", additional_info.get("purpose"))
    _put(output, "schema:funding", additional_info.get("funded_by"))
    _put(output, "schema:populationType", additional_info.get("instances_represent"))
    _put(output, "dcterms:tableOfContents", additional_info.get("variable_info"))
    if _present(additional_info.get("preprocessing_description")):
        output["prov:wasGeneratedBy"] = {
            "@type": "prov:Activity",
            "dcterms:description": additional_info["preprocessing_description"],
        }
    if additional_info.get("sensitive_data") is not None:
        output["dcterms:accessRights"] = additional_info.get("sensitive_data")

    return _prune(output)


def _uciml_metadata_to_dcat_dsv(
    metadata: Mapping[str, Any],
    variables: Optional[pd.DataFrame],
    dataset_id: int,
) -> Mapping[str, Any]:
    """Map ucimlrepo metadata into a DCAT/DSV JSON-LD skeleton."""

    enriched_metadata = dict(metadata)
    enriched_metadata.setdefault("uci_id", dataset_id)
    if variables is not None:
        enriched_metadata["variables"] = variables.to_dict(orient="records")

    return to_dcat_dsv(enriched_metadata)


@rule(phony=True)
def list_uciml(
    area: str = "Health and Medicine",
    name_substr: Optional[str] = None,
    cat_min: int = 1,
    num_min: int = 1,
    *,
    cachedir: pathlib.Path = pathlib.Path("uciml-cache"),
) -> pd.DataFrame:
    """Return (id, name, n_instances, n_categorical, n_numeric) for mixed datasets in area.

    It pulls the dataset list for the given area from the UCI API, then, for each
    dataset, fetches data via ucimlrepo and infers variable types to decide whether
    it is mixed (has at least one categorical and one numeric). Only mixed datasets
    are returned.
    """
    list_url = "https://archive.ics.uci.edu/api/datasets/list"
    logging.info(f"Requesting UCI ML datasets ({area=})")
    resp = requests.get(list_url, params={"area": area}, timeout=30)
    items = resp.json().get("data", []) if resp.ok else []
    pairs = [(int(d["id"]), d["name"]) for d in items]
    if name_substr:
        logging.info(f"Filtering UCI ML datasets ({name_substr=})")
        pairs = [(i, n) for i, n in pairs if name_substr.lower() in n.lower()]

    data_url = "https://archive.ics.uci.edu/api/dataset"
    cache_root = pathlib.Path(cachedir)
    cache_root.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, name in pairs:
        cache = cache_root / f"{i}.json"
        if not cache.exists():
            with cache.open("w") as fw:
                logging.info(f"Requesting UCI ML metadata {i} ({name})")
                r = requests.get(data_url, params={"id": i})
                if r.ok:
                    json.dump(r.json().get("data"), fw)
                else:
                    raise Exception(f"No content at {r}")
        metadata = json.load(cache.open())
        json.dump(metadata, cache.open('w'), indent=2)
        if any("type" in v for v in metadata["variables"]):
            vars = pd.DataFrame(metadata["variables"])
            row = {
                "id": i,
                "name": name,
                "has_data_url": bool(metadata["data_url"]),
                "n_instances": metadata["num_instances"],
                "n_categorical": vars["type"].isin(["Binary", "Categorical"]).sum(),
                "n_numeric": vars["type"].isin(["Integer", "Continuous"]).sum(),
            }
            if (row["n_categorical"] >= cat_min) and (row["n_numeric"] >= num_min):
                rows.append(row)

    return pd.DataFrame(rows)


@rule(phony=True)
def get_default_uciml(
    area: str = "Health and Medicine", *, cache_dir: pathlib.Path = pathlib.Path("uciml-cache")
) -> List[DatasetSpec]:
    df = list_uciml(area=area, cachedir=cache_dir)
    return [DatasetSpec("uciml", name=r.name, id=r.id) for r in df.itertuples()]


def _uciml_cache_paths(cache_dir: pathlib.Path | OutPath, dataset_id: int) -> CachePaths:
    cache_base = pathlib.Path(cache_dir)
    return CachePaths(
        data=cache_base / f"{dataset_id}.csv.gz",
        meta=cache_base / f"{dataset_id}.meta.json",
    )


@rule(phony=True)
def load_uciml_by_id(dataset_id: int, cache_dir: pathlib.Path | OutPath) -> DatasetPayload:
    """Load a UCI ML dataset by ID, with local caching of the data payload.

    Caching layout:
      - {cache_dir}/{id}.csv.gz: cached tabular data
      - {cache_dir}/{id}.meta.json: minimal metadata (name, color column)
    """
    cache_paths = _uciml_cache_paths(cache_dir, dataset_id)
    cache_paths.ensure()

    cached = load_cached_payload(cache_paths)
    spec = DatasetSpec(provider="uciml", id=dataset_id)
    if cached:
        df_cached, meta_cached = cached
        target_hint = meta_cached.get("target")
        if isinstance(target_hint, str) and target_hint:
            spec.target = target_hint
        df_clean, detected_target, color_series = clean_dataset_frame(
            df_cached, target=spec.target, metadata=meta_cached
        )
        spec.target = spec.target or detected_target
        spec.name = str(meta_cached.get("name") or f"UCI_{dataset_id}")
        spec.meta = meta_cached.get("dcat_dsv") or meta_cached
        return DatasetPayload(
            spec=spec,
            frame=df_clean,
            color=color_series,
            metadata=spec.meta,
        )

    from ucimlrepo import fetch_ucirepo

    logging.info("Downloading UCI ML dataset %s", dataset_id)
    dataset = fetch_ucirepo(id=dataset_id)

    X = dataset.data.features
    y = dataset.data.targets
    if y is None:
        df_all = X.copy()
        color_series = None
    else:
        df_all = pd.concat([X, y], axis=1)
        spec.target = (
            y.columns[0] if hasattr(y, "columns") and len(y.columns) else y.name
        )
        color_series = df_all[spec.target] if spec.target in df_all.columns else None

    df_clean, detected_target, color_series = clean_dataset_frame(
        df_all, target=spec.target
    )
    if detected_target:
        spec.target = detected_target

    raw_metadata: Mapping[str, Any] = dict(dataset.metadata)
    raw_metadata.setdefault("uci_id", dataset_id)
    dcat_dsv_meta = _uciml_metadata_to_dcat_dsv(raw_metadata, dataset.variables, dataset_id)
    spec.meta = dcat_dsv_meta
    spec.name = getattr(dataset.metadata, "name", f"UCI_{dataset_id}")

    meta_payload: Dict[str, Any] = {
        "id": dataset_id,
        "name": spec.name,
        "target": spec.target,
        "dcat_dsv": dcat_dsv_meta,
    }
    store_cached_payload(cache_paths, df_clean, meta_payload)

    return DatasetPayload(
        spec=spec,
        frame=df_clean,
        color=color_series,
        metadata=dcat_dsv_meta,
    )


if __name__ == "__main__":
    import sys

    import defopt

    def main(
        input_json: pathlib.Path,
        output_json: Optional[pathlib.Path] = None,
        indent: int = 2,
    ) -> None:
        """Transform UCI ML style metadata JSON to DCAT + DSV JSON-LD.

        Args:
            input_json: Path to the source UCI JSON metadata file.
            output_json: Optional path to write the converted JSON-LD. Defaults to
                stdout when not provided.
            indent: JSON indentation level.
        """

        src = json.loads(input_json.read_text(encoding="utf-8"))
        output = to_dcat_dsv(src)
        if output_json:
            output_json.write_text(
                json.dumps(output, indent=indent, ensure_ascii=False),
                encoding="utf-8",
            )
        else:
            json.dump(output, sys.stdout, indent=indent, ensure_ascii=False)
            sys.stdout.write("\n")

    defopt.run(main)
