"""Tests for the codebook: a linked-codebook profile and the role of each column."""

from pathlib import Path

import pandas as pd

from semsynth.codebook import Codebook, read_parquet, write_parquet

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_curated_file_is_read_with_roles_and_survives_json_ld() -> None:
    codebook = Codebook.read(FIXTURES / "heart.metadata.json")
    names = [column["name"] for column in codebook.columns]
    assert "chol" in names
    codebook.roles["chol"] = "target"
    again = Codebook.read(codebook.to_jsonld())
    assert again.profile == codebook.profile
    assert again.roles == codebook.roles


def test_parquet_carries_the_codebook(tmp_path: Path) -> None:
    df = pd.read_csv(FIXTURES / "heart.csv")
    codebook = Codebook.read(FIXTURES / "heart.metadata.json")
    path = tmp_path / "heart.parquet"
    write_parquet(df, path, codebook.to_jsonld())
    df2, read = read_parquet(path)
    pd.testing.assert_frame_equal(df, df2)
    assert read is not None and read.profile == codebook.profile and read.roles == codebook.roles


def test_privacy_frame_normalizes_roles_and_types() -> None:
    codebook = Codebook(
        {
            "columns": [
                {"name": "age", "level": "interval"},
                {"name": "disease", "values": [{"code": "yes", "label": "Yes"}, {"code": "no", "label": "No"}]},
                {"name": "id_col"},
                {"name": "notes"},
            ]
        },
        {"age": "predictor", "disease": "Sensitive", "id_col": "identifier"},
    )
    inferred = {"age": "continuous", "disease": "discrete", "id_col": "discrete", "notes": "continuous"}
    privacy_df = codebook.privacy_frame(inferred)
    assert dict(zip(privacy_df.variable, privacy_df.role, strict=True)) == {
        "age": "qi",
        "disease": "sensitive",
        "id_col": "id",
        "notes": "qi",
    }
    types = dict(zip(privacy_df.variable, privacy_df.type, strict=True))
    assert types == {"age": "numeric", "disease": "categorical", "id_col": "categorical", "notes": "numeric"}


def test_declared_metadata_wins_over_inference() -> None:
    df = pd.DataFrame({"code": [1, 2, 1, 2, 1, 2], "x": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]})
    declared = Codebook({"columns": [{"name": "code", "level": "ordinal", "closed": True, "values": [{"code": "1"}, {"code": "2"}]}]})
    codebook = Codebook.from_frame(df, declared)
    code = codebook.column("code")
    assert code is not None and code["level"] == "ordinal"
    assert code["observed"] == [{"code": "1", "count": 3}, {"code": "2", "count": 3}]
    assert codebook.kind("x") == "numeric"


def test_flat_graph_of_nodes_is_read() -> None:
    """Modlet writes the dataset, schema, columns and properties as separate nodes."""
    payload = {
        "@context": {
            "dsv": "https://w3id.org/dsv-ontology#",
            "csvw": "http://www.w3.org/ns/csvw#",
            "qudt": "http://qudt.org/schema/qudt/",
            "datasetSchema": {"@id": "dsv:datasetSchema", "@type": "@id"},
            "column": {"@id": "dsv:column", "@type": "@id"},
            "columnProperty": {"@id": "dsv:columnProperty", "@type": "@id"},
            "hasVariable": {"@id": "dsv:hasVariable", "@type": "@id"},
            "unit": {"@id": "qudt:hasUnit", "@type": "@id"},
            "name": "csvw:name",
        },
        "@graph": [
            {"@id": "ex:d", "@type": ["dsv:Dataset"], "datasetSchema": {"@id": "ex:s"}},
            {"@id": "ex:s", "@type": "dsv:DatasetSchema", "column": [{"@id": "ex:c1"}, {"@id": "ex:c2"}]},
            {"@id": "ex:c1", "@type": "dsv:Column", "name": "age", "columnProperty": {"@id": "ex:p1"}},
            {"@id": "ex:p1", "@type": "dsv:ColumnProperty", "hasVariable": {"@id": "ex:v1"}, "unit": {"@id": "http://qudt.org/vocab/unit/YR"}},
            {"@id": "ex:c2", "@type": "dsv:Column", "name": "time"},
        ],
    }
    codebook = Codebook.read(payload)
    assert [column["name"] for column in codebook.columns] == ["age", "time"]
    assert codebook.columns[0]["unit_iri"] == "http://qudt.org/vocab/unit/YR"
