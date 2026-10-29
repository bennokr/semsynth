"""Tests for merging SSSOM mappings into SemMap metadata."""

from __future__ import annotations

import pytest

pytest.importorskip("linked_codebook")
pytest.importorskip("defopt")

from map_columns.sssom_to_semmap import integrate_sssom
from semsynth.semmap import Metadata

PAYLOAD = {
    "dsv:datasetSchema": {
        "dsv:column": [{"schema:name": "col_a"}, {"schema:name": "col_b"}, {"schema:name": "Col C"}]
    }
}


def _matches(metadata: Metadata) -> dict:
    return {
        column.name: {
            field: getattr(column.columnProperty, field)
            for field in ("exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch")
            if column.columnProperty is not None and getattr(column.columnProperty, field)
        }
        for column in metadata.datasetSchema.columns
    }


def test_rows_are_attached_to_their_columns_by_match_type() -> None:
    metadata = Metadata.from_dcat_dsv(PAYLOAD)
    rows = [
        {"subject_id": "semmap:col_a", "predicate_id": "skos:exactMatch", "object_id": "wd:Q1"},
        {"subject_id": "semmap:col_a", "predicate_id": "skos:exactMatch", "object_id": "wd:Q1"},
        {"subject_id": "https://w3id.org/semsynth/variable/col_b", "predicate_id": "skos:broadMatch", "object_id": "wd:Q2"},
    ]
    integrate_sssom(metadata, rows)
    assert _matches(metadata) == {
        "col_a": {"exactMatch": ["https://www.wikidata.org/entity/Q1"]},
        "col_b": {"broadMatch": ["https://www.wikidata.org/entity/Q2"]},
        "Col C": {},
    }


def test_unknown_subjects_and_predicates_are_skipped() -> None:
    metadata = Metadata.from_dcat_dsv(PAYLOAD)
    rows = [
        {"subject_id": "semmap:zzz", "predicate_id": "skos:exactMatch", "object_id": "wd:Q3"},
        {"subject_id": "semmap:col_b", "predicate_id": "owl:sameAs", "object_id": "wd:Q4"},
        {"subject_id": "", "predicate_id": "skos:exactMatch", "object_id": "wd:Q5"},
        {"subject_id": "semmap:col_b", "predicate_id": "skos:narrowMatch", "object_id": ""},
    ]
    integrate_sssom(metadata, rows)
    assert _matches(metadata) == {"col_a": {}, "col_b": {}, "Col C": {}}


def test_columns_are_found_by_the_end_of_the_subject_ignoring_case_and_separators() -> None:
    metadata = Metadata.from_dcat_dsv(PAYLOAD)
    rows = [{"subject_id": "semmap:Col_C", "predicate_id": "skos:closeMatch", "object_id": "http://example.org/c"}]
    integrate_sssom(metadata, rows)
    assert _matches(metadata)["Col C"] == {"closeMatch": ["http://example.org/c"]}
