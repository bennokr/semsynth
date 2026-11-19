"""IRIs, the catalog, the RDF files that the explorer loads and the packaged queries, checked as RDF (rdflib)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semsynth.iris import DEFAULT_BASE, SITE, Iris, slug

PAGES = Path(__file__).resolve().parents[1] / ".github/workflows/pages.yml"
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


def explorer_files(output: Path) -> list[Path]:
    """The files that the Pages workflow gives to the playground: the patterns of the ``data`` input of its step."""
    block = re.search(r"data: \|\n((?:[ ]+output/\S+\n)+)", PAGES.read_text())
    assert block, "the Pages step lists its data files in a block"
    patterns = block.group(1)
    found = [
        p
        for line in patterns.split()
        for p in sorted(output.parent.glob(line.replace("output/", f"{output.name}/", 1)))
    ]
    return sorted(set(found))


def explorer_graph(output: Path):  # type: ignore[no-untyped-def]
    """All the triples of the explorer's files: what the playground queries once it has merged its sources."""
    from rdflib import Graph

    graph = Graph()
    for path in explorer_files(output):
        graph.parse(path, format="json-ld")
    return graph


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

    def build(parent: str | None) -> None:
        config = PipelineConfig(
            generate_umap=False,
            compute_privacy=True,
            compute_joint=True,
            compute_utility=True,
            cv_folds=3,
            bootstrap_reps=20,
            structure_aware=True,
            parent_activity=parent,
        )
        for name, seed in (("Heart Disease", 1), ("Chronic Kidney Disease", 2)):
            spec = DatasetSpec("openml", name=name, id=seed, target="dx", meta=codebook.to_jsonld())
            bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
            frame = _table(400, seed)
            process_dataset(
                spec, frame, frame["dx"], out, model_bundle=bundle, pipeline_config=config
            )
        build_catalog(out)

    import makeprov

    if not hasattr(
        makeprov, "current_activity"
    ):  # makeprov before 0.8.2: the runs have no command to refer to
        build(None)
        return out
    session = makeprov.new_session()
    cfg = makeprov.ProvenanceConfig(
        prov_path=str(out / "provenance" / "command"),
        stream=True,
        context=True,
        base_iri=DEFAULT_BASE,
        run_id="test",
    )

    @makeprov.rule(config=cfg, session=session, phony=True)
    def command() -> None:
        build(makeprov.current_activity(session))

    command()
    return out


def test_the_folder_layout_is_the_iri_layout(output: Path) -> None:
    assert sorted(p.name for p in output.iterdir() if p.name != "provenance") == [
        "catalog.json",
        "chronic-kidney-disease",
        "heart-disease",
        "index.html",
    ]
    assert (output / "heart-disease" / "models" / "metasyn" / "provenance.json").exists()
    index = (output / "index.html").read_text()
    assert 'href="heart-disease/"' in index and "Heart Disease" in index and "../explore/" in index


def test_the_catalog_uses_dcat_terms_and_urls_that_are_iris(output: Path) -> None:
    graph = {n["@id"]: n for n in json.loads((output / "catalog.json").read_text())["@graph"]}
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


def test_the_explorer_loads_every_rdf_file_and_only_those(output: Path) -> None:
    from rdflib import Graph, URIRef

    files = explorer_files(output)
    assert {p.name for p in files} >= {"catalog.json", "provenance.json", "dataset.codebook.jsonld"}
    with_context = {
        p
        for p in output.rglob("*.json*")
        if p.suffix == ".jsonld"
        or (isinstance(json.loads(p.read_text()), dict) and "@context" in json.loads(p.read_text()))
    }
    assert set(files) == with_context, (
        "a JSON-LD file is missing from the data patterns, or one that is no RDF is listed"
    )
    graph = explorer_graph(output)
    assert len(graph) > 500
    iris = {t for triple in graph for t in triple if isinstance(t, URIRef)}
    assert not [i for i in iris if re.search(r"\s", str(i)) or str(i).startswith("urn:")]
    assert not [f.name for f in files if len(Graph().parse(f, format="json-ld")) == 0]


def test_the_declarations_of_the_codebook_are_in_the_rdf(output: Path) -> None:
    merged = explorer_graph(output)
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


def test_the_queries_run_on_the_explorer_files_and_join_across_the_three_views(
    output: Path,
) -> None:
    merged = explorer_graph(output)
    results = {q.name: list(merged.query(q.read_text())) for q in QUERIES}
    import makeprov

    # the runs refer to the command only if makeprov can say which activity runs (0.8.2 and later)
    waiting = set() if hasattr(makeprov, "current_activity") else {"runs-and-the-commands-that-made-them.rq"}
    assert all(rows for name, rows in results.items() if name not in waiting), {n: len(r) for n, r in results.items()}
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
    assert coverage["Heart Disease"][1:] == (1, 1)
    scores = [
        r
        for r in results["scores-with-uncertainty.rq"]
        if str(r.score) == "privacy.dcr_below_holdout_p05"
    ]
    assert scores and all(
        r.lower is not None and float(r.lower) <= float(r.value) <= float(r.upper) for r in scores
    )


def test_the_command_that_ran_the_pipeline_is_linked_to_its_runs(output: Path) -> None:
    import makeprov

    if not hasattr(makeprov, "current_activity"):
        pytest.skip("makeprov before 0.8.2 gives code that a rule calls no IRI of the rule")
    graph = explorer_graph(output)
    rows = list(
        graph.query((QUERIES[0].parent / "runs-and-the-commands-that-made-them.rq").read_text())
    )
    assert {str(r.title) for r in rows} == {
        "Heart Disease (synthetic, metasyn)",
        "Chronic Kidney Disease (synthetic, metasyn)",
    }
    assert all(str(r.command).endswith("#command-test") and r.started and r.ended for r in rows)
