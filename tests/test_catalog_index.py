"""Tests for catalog index rendering."""

from __future__ import annotations

from pathlib import Path

from semsynth.catalog import SPARQL_ENDPOINT_ID, write_index


def test_write_index_includes_sparql_section(tmp_path: Path) -> None:
    """Ensure the generated demo index includes SPARQL endpoint guidance."""

    dataset_a = tmp_path / "Dataset A"
    dataset_b = tmp_path / "Dataset B"
    dataset_a.mkdir()
    dataset_b.mkdir()

    index_path = tmp_path / "output" / "index.html"
    index_path.parent.mkdir(parents=True, exist_ok=True)

    write_index(index_path, [dataset_a, dataset_b])
    html = index_path.read_text(encoding="utf-8")

    assert "Static SPARQL endpoint playground" in html
    assert SPARQL_ENDPOINT_ID in html
    assert "Datasets with SemMap metadata" in html
    assert 'href="Dataset A"' in html
    assert 'href="Dataset B"' in html

    assert "mediaType: \"application/ld+json\"" in html
    assert "new URL(\"catalog.jsonld\", location.href)" in html
