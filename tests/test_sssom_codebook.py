"""Tests for merging SSSOM mappings into a codebook."""

from __future__ import annotations

import pytest

pytest.importorskip("defopt")

from semsynth.codebook import Codebook
from semsynth.sssom_codebook import integrate_sssom

CODEBOOK = Codebook({"columns": [{"name": "col_a"}, {"name": "col_b"}, {"name": "Col C"}]})


def _matches(codebook: Codebook) -> dict:
    result: dict = {}
    for column in codebook.columns:
        found: dict = {}
        for mapping in column.get("mappings", []):
            found.setdefault(f"{mapping['match_type']}Match", []).append(mapping["object_id"])
        result[column["name"]] = found
    return result


def test_rows_are_attached_to_their_columns_by_match_type() -> None:
    rows = [
        {"subject_id": "variable:col_a", "predicate_id": "skos:exactMatch", "object_id": "wd:Q1"},
        {"subject_id": "variable:col_a", "predicate_id": "skos:exactMatch", "object_id": "wd:Q1"},
        {"subject_id": "https://w3id.org/semsynth/variable/col_b", "predicate_id": "skos:broadMatch", "object_id": "wd:Q2"},
    ]
    assert _matches(integrate_sssom(CODEBOOK, rows, reviewer="test")) == {
        "col_a": {"exactMatch": ["https://www.wikidata.org/entity/Q1"]},
        "col_b": {"broadMatch": ["https://www.wikidata.org/entity/Q2"]},
        "Col C": {},
    }


def test_unknown_subjects_and_predicates_are_skipped() -> None:
    rows = [
        {"subject_id": "variable:zzz", "predicate_id": "skos:exactMatch", "object_id": "wd:Q3"},
        {"subject_id": "variable:col_b", "predicate_id": "owl:sameAs", "object_id": "wd:Q4"},
        {"subject_id": "", "predicate_id": "skos:exactMatch", "object_id": "wd:Q5"},
        {"subject_id": "variable:col_b", "predicate_id": "skos:narrowMatch", "object_id": ""},
    ]
    assert _matches(integrate_sssom(CODEBOOK, rows, reviewer="test")) == {"col_a": {}, "col_b": {}, "Col C": {}}


def test_columns_are_found_by_the_end_of_the_subject_ignoring_case_and_separators() -> None:
    rows = [{"subject_id": "variable:Col_C", "predicate_id": "skos:closeMatch", "object_id": "http://example.org/c"}]
    assert _matches(integrate_sssom(CODEBOOK, rows, reviewer="test"))["Col C"] == {"closeMatch": ["http://example.org/c"]}
