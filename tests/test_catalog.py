"""IRIs, the catalog, the merged RDF and the packaged queries, checked as RDF (rdflib) and not only as JSON."""

from __future__ import annotations

import json
import re
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semsynth.iris import DEFAULT_BASE, SITE, Iris, slug

LC11 = tuple(int(n) for n in version("linked-codebook").split(".")[:2]) >= (0, 11)
needs_lc11 = pytest.mark.skipif(
    not LC11, reason="linked-codebook 0.11 writes the skip rules and limits into the RDF"
)
QUERIES = sorted((Path(__file__).resolve().parents[1] / "queries").glob("*.rq"))
STRING_FUNCTIONS = re.compile(
    r"\b(STRBEFORE|STRAFTER|SUBSTR|REPLACE|CONTAINS|REGEX|LCASE|UCASE|STRSTARTS|STRENDS|STR)\s*\(",
    re.I,
)


def test_slugs_and_iris() -> None:
    assert (
        slug("Heart Disease (UCI)") == "heart-disease-uci"
        and slug("Éé  ñ") == "ee-n"
        and slug("///") == "dataset"
    )
    iris = Iris("https://example.org/x")
    assert iris.dataset("Heart Disease") == "https://example.org/x/heart-disease/"
    assert (
        iris.run("Heart Disease", "My Model")
        == "https://example.org/x/heart-disease/models/my-model/#run"
    )
    assert iris.file("a", "b", "synthetic.csv") == "https://example.org/x/a/models/b/synthetic.csv"
    assert iris.metric("privacy.dcr_median/lower95") == f"{SITE}metric/privacy.dcr_median/lower95"
    assert (
        Iris().base == DEFAULT_BASE
        and DEFAULT_BASE.startswith(SITE)
        and Iris().catalog == DEFAULT_BASE + "#catalog"
    )


def test_the_packaged_queries_use_no_string_functions() -> None:
    assert len(QUERIES) >= 5
    for query in QUERIES:
        text = "\n".join(
            line for line in query.read_text().splitlines() if not line.lstrip().startswith("#")
        )
        assert not STRING_FUNCTIONS.search(text), f"{query.name} slices strings"


def _table(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.normal(55, 10, n)
    smoker = rng.choice(["yes", "no"], n, p=[0.3, 0.7])
    frame = pd.DataFrame(
        {
            "age": age,
            "sex": rng.choice(["f", "m"], n),
            "smoker": smoker,
            "cigs": np.where(smoker == "yes", rng.poisson(12, n), 77),
        }
    )
    frame["dx"] = np.where(age > 55, "high", "low")
    return frame


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> Path:
    pytest.importorskip("metasyn")
    pytest.importorskip("rdflib")
    from semsynth.catalog import build_catalog
    from semsynth.codebook import Codebook
    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    out = tmp_path_factory.mktemp("output")
    codebook = Codebook(
        {
            "columns": [
                {"name": "age", "datatype": "number", "minimum": 18, "maximum": 100},
                {"name": "smoker", "datatype": "string"},
                {
                    "name": "cigs",
                    "datatype": "integer",
                    "applies_when": "[smoker] == 'yes'",
                    "missing_values": ["77"],
                    "missing_range": {"low": 9000, "high": 9999},
                },
            ]
        }
    )
    config = PipelineConfig(
        generate_umap=False,
        compute_privacy=True,
        compute_joint=True,
        bootstrap_reps=20,
        structure_aware=True,
    )
    for name, seed in (("Heart Disease", 1), ("Chronic Kidney Disease", 2)):
        spec = DatasetSpec("openml", name=name, id=seed, target="dx", meta=codebook.to_jsonld())
        bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
        frame = _table(400, seed)
        process_dataset(spec, frame, frame["dx"], out, model_bundle=bundle, pipeline_config=config)
    build_catalog(out, merge=True)
    return out


def test_the_folder_layout_is_the_iri_layout(output: Path) -> None:
    assert sorted(p.name for p in output.iterdir()) == [
        "catalog.jsonld",
        "chronic-kidney-disease",
        "heart-disease",
        "index.html",
        "semsynth.ttl",
    ]
    assert (output / "heart-disease" / "models" / "metasyn" / "provenance.jsonld").exists()
    index = (output / "index.html").read_text()
    assert 'href="heart-disease/"' in index and "Heart Disease" in index and "../explore/" in index


def test_the_catalog_uses_dcat_terms_and_urls_that_are_iris(output: Path) -> None:
    graph = {n["@id"]: n for n in json.loads((output / "catalog.jsonld").read_text())["@graph"]}
    dataset = graph[f"{DEFAULT_BASE}heart-disease/"]
    assert dataset["@type"] == "dcat:Dataset" and dataset["dct:title"] == "Heart Disease"
    csv = graph[f"{DEFAULT_BASE}heart-disease/models/metasyn/#distribution-synthetic-csv"]
    assert csv["dcat:downloadURL"] == {
        "@id": f"{DEFAULT_BASE}heart-disease/models/metasyn/synthetic.csv"
    }
    assert csv["dcat:mediaType"] == {"@id": "https://www.iana.org/assignments/media-types/text/csv"}
    assert not [k for node in graph.values() for k in node if "_" in k], (
        "no snake_case keys: every key is a CURIE"
    )


def test_every_iri_in_the_rdf_is_clean_and_the_merge_loses_nothing(output: Path) -> None:
    from rdflib import Graph, URIRef

    parts = Graph()
    files = sorted(output.rglob("*.jsonld"))
    for path in files:
        parts.parse(path, format="json-ld")
    merged = Graph().parse(output / "semsynth.ttl", format="turtle")
    assert len(merged) == len(parts) > 500
    iris = {t for triple in merged for t in triple if isinstance(t, URIRef)}
    assert not [i for i in iris if re.search(r"\s", str(i)) or str(i).startswith("urn:")]
    lost = [f.name for f in files if len(Graph().parse(f, format="json-ld")) == 0]
    assert not lost


@needs_lc11
def test_the_declarations_of_the_codebook_are_in_the_rdf(output: Path) -> None:
    from rdflib import Graph

    merged = Graph().parse(output / "semsynth.ttl", format="turtle")
    rows = list(
        merged.query(
            (
                Path(__file__).resolve().parents[1] / "queries" / "skip-rules-and-missing-codes.rq"
            ).read_text()
        )
    )
    assert {
        (str(r.title), str(r.column), str(r.appliesWhen), str(r.missingCodes)) for r in rows
    } >= {("Heart Disease", "cigs", "[smoker] == 'yes'", "77")}
    limits = merged.query(
        "SELECT ?lo ?hi WHERE { ?c <http://www.w3.org/ns/csvw#minInclusive> ?lo ; <http://www.w3.org/ns/csvw#maxInclusive> ?hi . FILTER(?lo = 18) }"
    )
    assert list(limits)


def test_the_queries_run_on_the_merged_file_and_join_across_the_three_views(output: Path) -> None:
    from rdflib import Graph

    merged = Graph().parse(output / "semsynth.ttl", format="turtle")
    results = {q.name: list(merged.query(q.read_text())) for q in QUERIES}
    skipped = {"skip-rules-and-missing-codes.rq"} if not LC11 else set()
    assert all(rows for name, rows in results.items() if name not in skipped), {
        n: len(r) for n, r in results.items()
    }
    versions = results["datasets-and-synthetic-versions.rq"]
    assert {(str(r.title), str(r.generator)) for r in versions} == {
        ("Heart Disease", "metasyn"),
        ("Chronic Kidney Disease", "metasyn"),
    }
    assert all(int(r.files) >= 5 for r in versions), "data, provenance and metrics files"
    coverage = {
        str(r.title): (int(r.columns), int(r.withSkipRule), int(r.withMissingCodes))
        for r in results["codebook-coverage.rq"]
    }
    assert coverage["Heart Disease"][1:] == ((1, 1) if LC11 else (0, 1))
    scores = [
        r
        for r in results["scores-with-uncertainty.rq"]
        if str(r.score) == "privacy.dcr_below_holdout_p05"
    ]
    assert scores and all(
        r.lower is not None and float(r.lower) <= float(r.value) <= float(r.upper) for r in scores
    )
