"""A DCAT catalog of the output folder, as one JSON-LD file, and a plain index page.

The catalog says which datasets there are and where their files are; the codebook (DSV, written by linked-codebook)
says what is in a dataset's columns; the provenance of a run (:mod:`semsynth.provenance`) says how a synthetic dataset
came about. They are three views of the same IRIs (:mod:`semsynth.iris`), so SPARQL joins them without any string
handling:

* ``<dataset>/`` is a ``dcat:Dataset`` here and the dataset node of its codebook (``dsvo:datasetSchema``);
* ``<dataset>/models/<model>/`` is a ``dcat:Dataset`` that ``prov:wasDerivedFrom`` the dataset and
  ``prov:wasGeneratedBy`` the run, which ``prov:used`` the dataset;
* each ``dcat:Distribution`` has the URL of its file as ``dcat:downloadURL``, and that URL is the IRI of the
  ``prov:Entity`` in the provenance.

The query page is the playground at https://github.com/bennokr/data-catalog-sparql-playground, built from these files in
the Pages workflow; this module writes no HTML for it.
"""

from __future__ import annotations

import contextlib
import html
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .iris import CODEBOOK_FILE, DEFAULT_BASE, Iris

LOGGER = logging.getLogger(__name__)

CONTEXT = {
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
IANA = "https://www.iana.org/assignments/media-types/"
MEDIA_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".jsonld": "application/ld+json",
    ".parquet": "application/vnd.apache.parquet",
}
DATA_FILES = (
    "synthetic*.csv",
    "synthetic*.parquet",
    "provenance.json",
    "metrics*.json",
    "per_variable_metrics.csv",
)


def _iso(timestamp: float) -> dict[str, str]:
    return {"@value": datetime.fromtimestamp(timestamp, tz=UTC).isoformat(), "@type": "xsd:dateTime"}


def _title(folder: Path) -> str:
    """The title of the dataset: the one in its codebook, or its folder name."""
    try:
        title = json.loads((folder / CODEBOOK_FILE).read_text(encoding="utf-8")).get("title")
    except (OSError, ValueError):
        title = None
    return str(title) if title else folder.name


def _description(report: Path, title: str) -> str:
    """The first line of the report that is text."""
    try:
        lines = report.read_text(encoding="utf-8").splitlines()
    except OSError:
        return f"Synthetic data and the codebook of {title}."
    for line in lines:
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", line.strip()).replace("**", "")
        if text and not text.startswith("#"):
            return text
    return f"Synthetic data and the codebook of {title}."


def _distribution(iri: str, url: str, path: Path) -> dict[str, Any]:
    stat = path.stat()
    media = MEDIA_TYPES.get(
        ".jsonld" if path.name == "provenance.json" else path.suffix.lower()
    )  # JSON-LD with a plain extension
    return {
        "@id": iri,
        "@type": "dcat:Distribution",
        "dct:title": path.name,
        "dcat:downloadURL": {"@id": url},
        "dcat:accessURL": {"@id": url},
        **({"dcat:mediaType": {"@id": IANA + media}} if media else {}),
        "dcat:byteSize": {"@value": str(stat.st_size), "@type": "xsd:nonNegativeInteger"},
        "dct:modified": _iso(stat.st_mtime),
    }


def _model_dataset(iris: Iris, name: str, title: str, folder: Path) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    files = sorted({p for pattern in DATA_FILES for p in folder.glob(pattern) if p.is_file()})
    if not files:
        return None
    manifest: dict[str, Any] = {}
    with contextlib.suppress(OSError, ValueError):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    model = folder.name
    distributions = [_distribution(iris.distribution(name, model, f.name), iris.file(name, model, f.name), f) for f in files]
    dataset: dict[str, Any] = {
        "@id": iris.model(name, model),
        "@type": "dcat:Dataset",
        "dct:title": f"{title} (synthetic, {manifest.get('name') or model})",
        "dct:description": f"Synthetic version of {title} made by {manifest.get('backend') or 'a generator'}.",
        "prov:wasDerivedFrom": {"@id": iris.dataset(name)},
        "prov:wasGeneratedBy": {"@id": iris.run(name, model)},
        "dct:modified": _iso(max(f.stat().st_mtime for f in files)),
        "dcat:distribution": [{"@id": d["@id"]} for d in distributions],
    }
    return dataset, distributions


def _dataset_nodes(iris: Iris, folder: Path) -> list[dict[str, Any]]:
    name = folder.name
    title = _title(folder)
    own: list[dict[str, Any]] = []
    codebook = folder / CODEBOOK_FILE
    if codebook.exists():
        own.append(_distribution(f"{iris.dataset(name)}#distribution-codebook", iris.codebook(name), codebook))
    nodes: list[dict[str, Any]] = []
    for model_folder in sorted(p for p in (folder / "models").glob("*") if p.is_dir()):
        built = _model_dataset(iris, name, title, model_folder)
        if built:
            nodes += [built[0], *built[1]]
    if not nodes and not own:
        return []
    source: dict[str, Any] = {
        "@id": iris.dataset(name),
        "@type": "dcat:Dataset",
        "dct:title": title,
        "dct:description": _description(folder / "report.md", title),
        "dcat:landingPage": {"@id": iris.dataset(name)},
        "dcat:distribution": [{"@id": d["@id"]} for d in own],
    }
    return [source, *own, *nodes]


def build_catalog(
    base_dir: Path | str = "output",
    base_iri: str = DEFAULT_BASE,
    out_path: Path | str | None = None,
    index_path: Path | str | None = None,
) -> dict[str, Any]:
    """Write the DCAT catalog (``catalog.json``) and a plain index page of the datasets in ``base_dir``.

    Args:
        base_dir: Folder with one subfolder per dataset (a folder counts if it has a ``report.md``), served at ``base_iri``.
        base_iri: Base of every IRI (see :mod:`semsynth.iris`).
        out_path: Where to write the catalog; ``<base_dir>/catalog.json`` when omitted.
        index_path: Where to write the index page; ``<base_dir>/index.html`` when omitted.

    Returns:
        The catalog as JSON-LD.
    """
    base_dir = Path(base_dir)
    iris = Iris(base_iri)
    folders = [p for p in sorted(base_dir.iterdir()) if p.is_dir() and (p / "report.md").exists()]
    graph: list[dict[str, Any]] = []
    for folder in folders:
        graph += _dataset_nodes(iris, folder)
    datasets = [node["@id"] for node in graph if node["@type"] == "dcat:Dataset"]
    catalog: dict[str, Any] = {
        "@id": iris.catalog,
        "@type": "dcat:Catalog",
        "dct:title": "SemSynth synthetic data catalog",
        "dct:description": "Datasets, their codebooks and the synthetic datasets made from them.",
        "dct:modified": _iso(datetime.now(UTC).timestamp()),
        "dcat:dataset": [{"@id": iri} for iri in datasets],
    }
    document = {"@context": CONTEXT, "@graph": [catalog, *graph]}
    Path(out_path or base_dir / "catalog.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    write_index(Path(index_path or base_dir / "index.html"), [(f.name, _title(f)) for f in folders])
    LOGGER.info("Wrote the catalog of %d datasets", len(folders))
    return document


def write_index(path: Path, datasets: list[tuple[str, str]]) -> None:
    """A page that lists the datasets and points to the query page (``../explore/``)."""
    items = "\n".join(f'<li><a href="{quote(folder)}/">{html.escape(title)}</a></li>' for folder, title in datasets)
    path.write_text(
        f"""<!doctype html>
<meta charset="utf-8">
<title>SemSynth datasets</title>
<link rel="stylesheet" href="../templates/report_style.css">
<h1>SemSynth datasets</h1>
<ul>
{items}
</ul>
<p>Query the catalogs, codebooks and provenance with SPARQL: <a href="../explore/">explorer</a>
(<a href="catalog.json">catalog.json</a>).</p>
""",
        encoding="utf-8",
    )
