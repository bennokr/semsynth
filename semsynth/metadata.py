from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional


from makeprov import JSONLDMixin

JSONLD_CONTEXT = {
    "@context": {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dct": "http://purl.org/dc/terms/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "identifier": "dct:identifier",
        "title": "dct:title",
        "description": "dct:description",
        "publisher": "dct:publisher",
        "keywords": "dcat:keyword",
        "issued": {"@id": "dct:issued", "@type": "xsd:date"},
        "modified": {"@id": "dct:modified", "@type": "xsd:date"},
        "language": "dct:language",
        "distributions": {"@id": "dcat:distribution", "@type": "@id"},
        "Distribution": "dcat:Distribution",
        "access_url": "dcat:accessURL",
        "download_url": "dcat:downloadURL",
        "media_type": "dcat:mediaType",
    }
}


@dataclass
class DCATDistribution(JSONLDMixin):
    __context__ = JSONLD_CONTEXT
    title: str
    access_url: Optional[str] = None
    download_url: Optional[str] = None
    media_type: Optional[str] = None


@dataclass
class DCATDataset(JSONLDMixin):
    __context__ = JSONLD_CONTEXT
    identifier: str
    title: str
    description: str
    publisher: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    issued: Optional[str] = None
    modified: Optional[str] = None
    language: Optional[str] = None
    distributions: List[DCATDistribution] = field(default_factory=list)


def get_uciml_variable_descriptions(dataset_id: int) -> Dict[str, str]:
    """Best-effort retrieval of UCI ML variable descriptions.

    The lookup first checks for a cached UCI ML payload under
    ``uciml-cache/{dataset_id}.json``. If no cached metadata is found or the
    payload does not contain variable descriptions, it falls back to the
    ``ucimlrepo`` metadata API.

    Args:
        dataset_id: UCI ML dataset identifier used for cache lookup and API
            fallback.

    Returns:
        Mapping of column name to free-text description. Missing or empty
        descriptions are filtered out.
    """

    def _read_cached_variables(cache_path: Path) -> List[Any]:
        try:
            payload = json.loads(cache_path.read_text())
        except Exception:
            logging.exception("Failed to read UCI ML cache file: %s", cache_path)
            return []

        if isinstance(payload, dict) and "data" in payload:
            payload = payload.get("data") or {}

        variables = payload.get("variables") if isinstance(payload, dict) else None
        return variables if isinstance(variables, list) else []

    cache_path = Path("uciml-cache") / f"{int(dataset_id)}.json"
    variables: List[Any] = []
    if cache_path.exists():
        variables = _read_cached_variables(cache_path)

    if not variables:
        try:
            import ssl
            from ucimlrepo import fetch_ucirepo

            try:
                dataset = fetch_ucirepo(id=dataset_id)
            except ConnectionError as exc:  # pragma: no cover - network dependent
                logging.warning(
                    "Retrying ucimlrepo fetch for %s with relaxed SSL: %s",
                    dataset_id,
                    exc,
                )
                default_https_context = ssl._create_default_https_context
                default_context_factory = ssl.create_default_context

                def insecure_context(*args, **kwargs):
                    context = default_context_factory(*args, **kwargs)
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    return context

                try:
                    ssl._create_default_https_context = (
                        ssl._create_unverified_context
                    )
                    ssl.create_default_context = insecure_context
                    dataset = fetch_ucirepo(id=dataset_id)
                finally:
                    ssl._create_default_https_context = default_https_context
                    ssl.create_default_context = default_context_factory

            metadata = getattr(dataset, "metadata", None)
            variables = getattr(metadata, "variables", None) or []
        except Exception:
            logging.exception(
                "Failed to fetch UCI ML metadata for variable descriptions (%s)",
                dataset_id,
            )
            variables = []

    desc_map: Dict[str, str] = {}
    for var in variables:
        name: Optional[str] = None
        description: Optional[str] = None
        if isinstance(var, dict):
            name = var.get("name") or var.get("column")
            description = var.get("description")
        else:
            name = getattr(var, "name", None) or getattr(var, "column", None)
            description = getattr(var, "description", None)

        if name and description:
            desc_map[str(name)] = str(description)

    return desc_map
