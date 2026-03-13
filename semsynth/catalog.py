"""Build DCAT catalogs for SemSynth reports and datasets."""

from __future__ import annotations

import json
import logging
import mimetypes
import re
from importlib import resources
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from makeprov import GLOBAL_CONFIG, InPath, RDFMixin, OutPath, main, rule

from .mappings import normalize_jsonld_payload

LOGGER = logging.getLogger(__name__)


SPARQL_ENDPOINT_ID = "browser://semsynth-static-catalog"


@dataclass(frozen=True)
class SparqlQueryDefinition:
    """Metadata for a packaged SPARQL example query.

    Attributes:
        name: Human-readable label shown in the playground.
        filename: Query filename written under output/sparql.
        description: Short explanation shown in query cards.
    """

    name: str
    filename: str
    description: str


SPARQL_QUERY_DEFINITIONS: Tuple[SparqlQueryDefinition, ...] = (
    SparqlQueryDefinition(
        name="SemMap coverage per dataset",
        filename="query-semmap-coverage.rq",
        description="Counts SemMap distributions across datasets to confirm semantic metadata coverage.",
    ),
    SparqlQueryDefinition(
        name="Provenance sources driving synthetic artifacts",
        filename="query-provenance-artifacts.rq",
        description="Aggregates provenance sources linked to multiple synthetic artifact distributions.",
    ),
    SparqlQueryDefinition(
        name="Datasets with SemMap + provenance synthetic outputs",
        filename="query-semmap-and-provenance-artifacts.rq",
        description="Joins SemMap and provenance-linked synthetic distributions per dataset.",
    ),
)


@dataclass
class PathURLMapper:
    """Map repository paths to catalog-friendly URLs."""

    root_dir: Path
    base_url: Optional[str] = None

    def for_path(self, path: Path) -> str:
        """Return a URL for a filesystem path."""

        resolved_root = self.root_dir.resolve()
        resolved_path = path.resolve()
        try:
            relative = resolved_path.relative_to(resolved_root)
            relative_text = relative.as_posix()
        except ValueError:
            # Fall back to a normalized absolute path without a file scheme.
            relative_text = resolved_path.as_posix().lstrip("/")

        if self.base_url:
            return f"{self.base_url.rstrip('/')}/{relative_text}"
        return relative_text


DCAT_CONTEXT: Dict[str, object] = {
    "id": "@id",
    "type": "@type",
    "dcat": "http://www.w3.org/ns/dcat#",
    "dct": "http://purl.org/dc/terms/",
    "prov": "http://www.w3.org/ns/prov#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "title": "dct:title",
    "description": "dct:description",
    "identifier": "dct:identifier",
    "keywords": "dcat:keyword",
    "modified": {"@id": "dct:modified", "@type": "xsd:dateTime"},
    "issued": {"@id": "dct:issued", "@type": "xsd:dateTime"},
    "landing_page": {"@id": "dcat:landingPage", "@type": "@id"},
    "datasets": {"@id": "dcat:dataset"},
    "distributions": {"@id": "dcat:distribution"},
    "access_url": {"@id": "dcat:accessURL", "@type": "@id"},
    "download_url": {"@id": "dcat:downloadURL", "@type": "@id"},
    "media_type": "dcat:mediaType",
    "format": "dct:format",
    "byte_size": {"@id": "dcat:byteSize", "@type": "xsd:integer"},
    "wasGeneratedBy": {"@id": "prov:wasGeneratedBy", "@type": "@id"},
    "wasDerivedFrom": {"@id": "prov:wasDerivedFrom", "@type": "@id"},
}


@dataclass
class CatalogDistribution(RDFMixin):
    """DCAT Distribution entry for catalog output."""

    __context__ = DCAT_CONTEXT

    id: str
    title: str
    type: List[str] = field(default_factory=lambda: ["dcat:Distribution"])
    access_url: Optional[str] = None
    download_url: Optional[str] = None
    media_type: Optional[str] = None
    format: Optional[str] = None
    byte_size: Optional[int] = None
    modified: Optional[str] = None
    issued: Optional[str] = None


@dataclass
class CatalogDataset(RDFMixin):
    """DCAT Dataset entry representing a SemSynth report."""

    __context__ = DCAT_CONTEXT

    id: str
    identifier: str
    title: str
    description: str
    type: List[str] = field(default_factory=lambda: ["dcat:Dataset"])
    keywords: List[str] = field(default_factory=list)
    landing_page: Optional[str] = None
    modified: Optional[str] = None
    issued: Optional[str] = None
    wasDerivedFrom: Optional[List[Dict[str, str]]] = None
    distributions: List[CatalogDistribution] = field(default_factory=list)


@dataclass
class DataCatalog(RDFMixin):
    """DCAT Catalog container for SemSynth outputs."""

    __context__ = DCAT_CONTEXT

    id: str
    title: str
    description: str
    type: List[str] = field(default_factory=lambda: ["dcat:Catalog"])
    modified: Optional[str] = None
    datasets: List[CatalogDataset] = field(default_factory=list)
    distributions: List[CatalogDistribution] = field(default_factory=list)
    wasGeneratedBy: Optional[Dict[str, str]] = None


def slugify(value: str) -> str:
    """Convert a dataset name to a slug for identifiers."""

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return slug.strip("-")


def to_iso(dt: datetime) -> str:
    """Return an ISO 8601 timestamp with timezone information."""

    return dt.astimezone(timezone.utc).isoformat()


def read_lines(path: Path) -> Sequence[str]:
    """Read a text file safely and return its lines."""

    try:
        return path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []


def build_description(name: str, report_path: Path) -> str:
    """Generate a short dataset description."""

    lines = read_lines(report_path)
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
        text = text.replace("**", "")
        if text:
            return f"{text} — synthetic assets curated by SemSynth."
    return f"Synthetic datasets and semantic mappings for {name} generated by SemSynth."


def infer_model_name(path: Path, dataset_dir: Path) -> str:
    """Best-effort extraction of model name from a synthetic artifact path."""

    try:
        parts = path.relative_to(dataset_dir).parts
    except ValueError:
        parts = path.parts
    if "models" in parts:
        idx = parts.index("models")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    match = re.search(r"(metasyn|ctgan|tvae|semi|clg)[^./]*", path.name, re.IGNORECASE)
    if match:
        return match.group(1)
    return path.stem


def distribution_title(dataset_name: str, dataset_dir: Path, path: Path) -> str:
    """Create a human readable title for a distribution."""

    if path.name == "dataset.semmap.json":
        return f"{dataset_name} SemMap JSON-LD"
    model = infer_model_name(path, dataset_dir)
    suffix = path.suffix.lstrip(".")
    return f"{dataset_name} synthetic data ({model}, {suffix})"


def mimetype_for(path: Path) -> Optional[str]:
    """Look up the MIME type for a path."""

    mime, _ = mimetypes.guess_type(path.name)
    return mime


def sha256_digest(path: Path) -> str:
    """Compute a SHA-256 digest for a file."""

    hsh = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hsh.update(chunk)
    return hsh.hexdigest()


def collect_distributions(
    dataset_name: str, dataset_dir: InPath, mapper: PathURLMapper
) -> Tuple[List[CatalogDistribution], Set[Path]]:
    """Collect SemMap and synthetic distributions for a dataset."""

    distributions: List[CatalogDistribution] = []
    inputs: Set[Path] = set()

    semmap = dataset_dir / "dataset.semmap.json"
    if semmap.exists():
        url = mapper.for_path(semmap)
        distributions.append(
            CatalogDistribution(
                id=f"urn:distribution:{slugify(dataset_name)}:semmap-json",
                title=distribution_title(dataset_name, dataset_dir, semmap),
                access_url=url,
                download_url=url,
                media_type="application/ld+json",
                format="JSON-LD",
                byte_size=semmap.stat().st_size,
                modified=to_iso(datetime.fromtimestamp(semmap.stat().st_mtime, tz=timezone.utc)),
                issued=to_iso(datetime.fromtimestamp(semmap.stat().st_ctime, tz=timezone.utc)),
            )
        )
        inputs.add(semmap)

    seen: Set[Path] = set()
    for pattern in ("synthetic*.csv", "synthetic*.parquet", "synthetic*.json"):
        for path in dataset_dir.rglob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            mime = mimetype_for(path)
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                created = datetime.fromtimestamp(path.stat().st_ctime, tz=timezone.utc)
                size = path.stat().st_size
            except OSError:
                continue
            try:
                relative_id = path.relative_to(dataset_dir.parent)
            except ValueError:
                relative_id = path.name
            dist_id = slugify(f"{dataset_name}-{relative_id}")
            url = mapper.for_path(path)
            distributions.append(
                CatalogDistribution(
                    id=f"urn:distribution:{dist_id}",
                    title=distribution_title(dataset_name, dataset_dir, path),
                    access_url=url,
                    download_url=url,
                    media_type=mime,
                    format=path.suffix.upper().lstrip("."),
                    byte_size=size,
                    modified=to_iso(modified),
                    issued=to_iso(created),
                )
            )
            inputs.add(path)

    return distributions, inputs


def collect_datasets(
    base_dir: Path, dataset_dirs: Sequence[Path], mapper: PathURLMapper
) -> Tuple[List[CatalogDataset], Set[Path]]:
    """Build catalog dataset entries and gather provenance inputs."""

    datasets: List[CatalogDataset] = []
    inputs: Set[Path] = set()

    for dataset_dir in dataset_dirs:
        dataset_name = dataset_dir.name
        distributions, dist_inputs = collect_distributions(dataset_name, dataset_dir, mapper)
        if not distributions:
            LOGGER.info("Skipping %s – no distributions detected", dataset_name)
            continue

        inputs.update(dist_inputs)

        slug = slugify(dataset_name)
        landing = dataset_dir / "index.html"
        latest_modified = max(
            (datetime.fromisoformat(dist.modified) for dist in distributions if dist.modified),
            default=datetime.now(timezone.utc),
        )
        dataset = CatalogDataset(
            id=f"urn:dataset:{slug}",
            identifier=slug,
            title=dataset_name,
            description=build_description(dataset_name, dataset_dir / "report.md"),
            keywords=[dataset_name, "synthetic data", "SemMap", "SemSynth"],
            landing_page=mapper.for_path(landing) if landing.exists() else None,
            modified=to_iso(latest_modified),
            issued=distributions[0].issued,
            wasDerivedFrom=[{"id": mapper.for_path(path)} for path in sorted(dist_inputs)],
            distributions=distributions,
        )
        datasets.append(dataset)

    return datasets, inputs


def read_packaged_sparql_queries() -> List[Dict[str, str]]:
    """Load packaged SPARQL query templates.

    Returns:
        Query descriptors with name, description, filename, and query text.
    """

    templates_dir = resources.files("semsynth.templates")
    queries: List[Dict[str, str]] = []
    for definition in SPARQL_QUERY_DEFINITIONS:
        query_text = (templates_dir / definition.filename).read_text(encoding="utf-8").strip()
        queries.append(
            {
                "name": definition.name,
                "description": definition.description,
                "filename": definition.filename,
                "query": query_text,
            }
        )
    return queries


def write_sparql_query_files(base_dir: Path, mapper: PathURLMapper) -> List[CatalogDistribution]:
    """Write packaged SPARQL query files under output/sparql and return distributions.

    Args:
        base_dir: Catalog output root (typically ``output``).
        mapper: URL mapper for converting files to catalog URLs.

    Returns:
        Catalog distributions for generated SPARQL query files.
    """

    query_dir = base_dir / "sparql"
    query_dir.mkdir(parents=True, exist_ok=True)

    distributions: List[CatalogDistribution] = []
    now_iso = to_iso(datetime.now(timezone.utc))
    for query in read_packaged_sparql_queries():
        query_path = query_dir / query["filename"]
        query_path.write_text(query["query"] + "\n", encoding="utf-8")
        file_slug = slugify(query["filename"].replace(".rq", ""))
        query_url = mapper.for_path(query_path)
        distributions.append(
            CatalogDistribution(
                id=f"urn:distribution:sparql:{file_slug}",
                title=f"SPARQL example: {query['name']}",
                access_url=query_url,
                download_url=query_url,
                media_type="application/sparql-query",
                format="RQ",
                byte_size=query_path.stat().st_size,
                modified=now_iso,
                issued=now_iso,
            )
        )

    return distributions


def write_index(
    index_path: Path,
    dataset_dirs: Sequence[Path],
    query_examples: Sequence[Dict[str, str]],
) -> None:
    """Rewrite output/index.html with dataset links and a static SPARQL UI.

    Args:
        index_path: Destination HTML file.
        dataset_dirs: Dataset directories to expose in the report index.
        query_examples: Query metadata used for cards and YASGUI tabs.
    """

    css_href = "../templates/report_style.css"
    dataset_items = "\n".join(
        f'<li><a href="{directory.name}">{directory.name}</a></li>'
        for directory in dataset_dirs
    )

    query_json = json.dumps(
        [
            {
                "name": query["name"],
                "filename": query["filename"],
                "description": query["description"],
            }
            for query in query_examples
        ]
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SemSynth demo reports</title>
  <link rel="stylesheet" href="{css_href}" />
  <link rel="stylesheet" href="../templates/yasgui.min.css" />
  <style>
    .endpoint-pill {{ display: inline-block; font-family: monospace; background: #f4f4f4; padding: 0.35rem 0.55rem; border-radius: 0.35rem; }}
    #sparql-app {{ height: 70vh; min-height: 520px; border: 1px solid #ddd; border-radius: 0.5rem; overflow: hidden; }}
    .semsynth-query-result {{ margin: 0.75rem; padding: 0.75rem; max-height: 16rem; overflow: auto; border-radius: 0.35rem; background: #fafafa; border: 1px solid #ddd; font-family: monospace; white-space: pre-wrap; }}
  </style>
</head>
<body>
<main class="report-container">
  <h1>Data Reports</h1>
  <ul>
{dataset_items}
  </ul>

  <section>
    <h2>Static SPARQL endpoint playground</h2>
    <p>
      Endpoint identifier: <span class="endpoint-pill">{SPARQL_ENDPOINT_ID}</span>.
      This page embeds YASGUI + the browser Comunica SPARQL engine (no server-side SPARQL service).
    </p>
    <p>
      The engine queries <code>output/catalog.jsonld</code> and loads query tabs from <code>output/sparql/*.rq</code> files.
      Use the tabs below to select and run each example query.
    </p>
    <div id="sparql-app"></div>
  </section>
</main>

<script src="../templates/comunica-browser.js"></script>
<script src="../templates/yasgui.min.js"></script>
<script>
  const endpointId = {json.dumps(SPARQL_ENDPOINT_ID)};
  const exampleQueries = {query_json};

  function streamToString(stream) {{
    return new Promise((resolve, reject) => {{
      const chunks = [];
      stream.on("data", (chunk) => chunks.push(typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk)));
      stream.on("end", () => resolve(chunks.join("")));
      stream.on("error", reject);
    }});
  }}

  async function initStaticSparql() {{
    const yasgui = new Yasgui(document.getElementById("sparql-app"), {{
      requestConfig: {{ endpoint: endpointId }},
      copyEndpointOnNewTab: false,
    }});

    const engine = new Comunica.QueryEngine();
    const catalogUrl = new URL("catalog.jsonld", location.href).toString();
    const catalogText = await fetch(catalogUrl).then(r => r.text());
    const sources = [{{
      type: "string",
      value: catalogText,
      mediaType: "application/ld+json",
      baseIRI: catalogUrl,
    }}];

    const renderPayload = (yasr, payload, mediaType) => {{
      const host = yasr.rootEl.parentElement;
      let pre = host.querySelector(".semsynth-query-result");
      if (!pre) {{
        pre = document.createElement("pre");
        pre.className = "semsynth-query-result";
        host.appendChild(pre);
      }}
      pre.dataset.mediaType = mediaType;
      pre.textContent = payload;
    }};

    const runWithComunica = async (tab) => {{
      tab.show();
      const yasqe = tab.getYasqe();
      const yasr = tab.getYasr();
      const queryText = yasqe.getValue();
      try {{
        const result = await engine.query(queryText, {{ sources }});
        const media = result.resultType === "bindings"
          ? "application/sparql-results+json"
          : (result.resultType === "boolean" ? "application/sparql-results+json" : "application/trig");
        const serialized = await engine.resultToString(result, media);
        const payload = await streamToString(serialized.data);
        renderPayload(yasr, payload, media);
      }} catch (error) {{
        renderPayload(yasr, JSON.stringify({{ error: String(error) }}, null, 2), "application/json");
      }}
    }};

    const wireTab = (tab) => {{
      const yasqe = tab.getYasqe();
      yasqe.query = () => runWithComunica(tab);
      const keys = yasqe.getOption("extraKeys") || {{}};
      yasqe.setOption("extraKeys", Object.assign({{}}, keys, {{
        "Cmd-Enter": () => {{ runWithComunica(tab); return false; }},
        "Ctrl-Enter": () => {{ runWithComunica(tab); return false; }},
      }}));
    }};

    const loadQueryText = async (queryInfo) => {{
      const queryUrl = new URL(`sparql/${{queryInfo.filename}}`, location.href).toString();
      const response = await fetch(queryUrl);
      if (!response.ok) {{
        throw new Error(`Unable to load query file ${{queryInfo.filename}} (${{response.status}})`);
      }}
      return response.text();
    }};

    const firstTab = yasgui.getTab();
    wireTab(firstTab);

    if (exampleQueries.length) {{
      const firstQuery = exampleQueries[0];
      firstTab.setName(firstQuery.name);
      firstTab.getYasqe().setValue(await loadQueryText(firstQuery));
      for (const queryInfo of exampleQueries.slice(1)) {{
        const tab = yasgui.addTab(true);
        tab.setName(queryInfo.name);
        tab.show();
        tab.getYasqe().setValue(await loadQueryText(queryInfo));
        wireTab(tab);
      }}
      firstTab.show();
    }}
  }}

  initStaticSparql().catch((error) => {{
    const container = document.getElementById("sparql-app");
    container.innerHTML = `<pre>Failed to initialize static SPARQL UI: ${{String(error)}}</pre>`;
  }});
</script>
</body>
</html>
"""

    index_path.write_text(html + "\n", encoding="utf-8")
    LOGGER.info("Updated %s", index_path)


@rule()
def build_catalog(
    base_dir: InPath = InPath("output"),
    base_url: str = "https://w3id.org/semsynth/demo#",
    out_path: OutPath = OutPath("output/catalog.json"),
    index_path: OutPath = OutPath("output/index.html"),
):
    """Construct the DCAT catalog.

    Args:
        base_dir: The base directory that holds all SemSynth reports.
        base_url: Base URL for creating IRIs.
        out_path: Output path for the catalog JSON-LD.
        index_path: Output path for the HTML index file.
    """

    GLOBAL_CONFIG.prov_dir = out_path.parent

    mapper = PathURLMapper(root_dir=base_dir.parent, base_url=base_url)

    dataset_dirs = []
    for path in sorted(base_dir.iterdir()):
        if not path.is_dir():
            continue
        if path.name.startswith(".") or path.name.lower() == "semsynth":
            continue
        if (path / "report.md").exists():
            dataset_dirs.append(path)

    datasets, _inputs = collect_datasets(base_dir, dataset_dirs, mapper)
    query_examples = read_packaged_sparql_queries()
    sparql_distributions = write_sparql_query_files(base_dir, mapper)

    now = datetime.now(timezone.utc)
    catalog = DataCatalog(
        id="urn:catalog:semsynth-demo",
        title="SemSynth Synthetic Data Catalog",
        description="DCAT catalog of SemSynth reports and synthetic datasets.",
        modified=to_iso(now),
        datasets=datasets,
        distributions=sparql_distributions,
    )
    write_index(index_path, dataset_dirs, query_examples)
    catalog_payload = normalize_jsonld_payload(catalog.to_jsonld())
    catalog_json = json.dumps(catalog_payload, indent=2)
    out_path.write_text(catalog_json)

    jsonld_path = out_path.with_suffix(".jsonld")
    jsonld_path.write_text(catalog_json)
    LOGGER.info("Updated %s", jsonld_path)


if __name__ == "__main__":  # pragma: no cover - CLI bridge
    main()
