"""Tests for SPARQL query file generation in catalog workflow."""

from __future__ import annotations

from pathlib import Path

from semsynth.catalog import PathURLMapper, read_packaged_sparql_queries, write_sparql_query_files


def test_write_sparql_query_files_creates_distributions(tmp_path: Path) -> None:
    """Ensure SPARQL query templates are materialized and exposed as distributions."""

    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    mapper = PathURLMapper(root_dir=tmp_path)

    distributions = write_sparql_query_files(output_dir, mapper)

    assert len(distributions) == len(read_packaged_sparql_queries())
    query_dir = output_dir / "sparql"
    assert query_dir.exists()

    filenames = sorted(path.name for path in query_dir.glob("*.rq"))
    assert filenames == sorted(
        [
            "query-provenance-artifacts.rq",
            "query-semmap-and-provenance-artifacts.rq",
            "query-semmap-coverage.rq",
        ]
    )

    for distribution in distributions:
        assert distribution.media_type == "application/sparql-query"
        assert distribution.download_url
        assert distribution.download_url.endswith(".rq")
