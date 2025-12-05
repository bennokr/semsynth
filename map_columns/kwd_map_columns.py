#!/usr/bin/env python3
"""Keyword-driven Datasette lookup for dataset columns."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import defopt
import requests

from map_columns.codes_map_columns import (
    DEFAULT_JUSTIFICATION,
    DEFAULT_PREDICATE,
    CodeEntry,
    MatchResult,
    write_sssom,
)
from map_columns.shared import (
    DEFAULT_STOP_WORDS,
    ColumnInfo,
    DatasetMetadata,
    format_similarity_comment,
    load_columns,
    score_column_against_texts,
)

LOGGER = logging.getLogger(__name__)


STOP_WORDS = DEFAULT_STOP_WORDS


def query_codes(
    datasette_db_url: str,
    table: str,
    term: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """Query Datasette for candidate terminology rows."""

    base = datasette_db_url.rstrip("/")
    url = f"{base}/{table}.json"
    params = [
        ("_search", term),
        ("_size", str(limit)),
        ("_search_columns", "label"),
        ("_search_columns", "synonyms"),
    ]
    LOGGER.info("GET %s term=%r", url, term)
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    rows = data.get("rows", [])
    return rows


def _candidate_texts(label: str, synonyms: Iterable[str]) -> Tuple[str, ...]:
    texts: List[str] = []
    if label:
        texts.append(label)
    texts.extend(synonyms)
    return tuple(filter(None, texts))


def generate_matches(
    columns: Sequence[ColumnInfo],
    dataset_meta: DatasetMetadata,
    *,
    datasette_db_url: str,
    table: str = "codes",
    limit: int = 10,
    allowed_systems: Optional[Iterable[str]] = None,
    lexical_threshold: float = 0.35,
    top_k: int = 3,
) -> List[MatchResult]:
    """Generate Datasette-backed lexical matches for dataset columns."""

    allowed = {system.strip() for system in allowed_systems or [] if system.strip()}
    matches: List[MatchResult] = []

    for column in columns:
        name = column.name or column.column_id or "<unnamed column>"
        description = (column.description or column.about or "").strip()
        if not description:
            LOGGER.info("Column %s has no description; skipping keyword lookup", name)
            continue

        try:
            rows = query_codes(datasette_db_url, table, description, limit)
        except Exception as exc:  # pragma: no cover - network failures
            LOGGER.warning("Error querying Datasette for %s: %s", name, exc)
            continue

        scored: List[Tuple[float, MatchResult]] = []
        for row in rows:
            system = (row.get("system") or "").strip()
            if allowed and system not in allowed:
                continue
            code = (row.get("code") or "").strip()
            label = (row.get("label") or "").strip()
            if not system or not code or not label:
                continue
            synonyms = tuple(
                synonym.strip()
                for synonym in (row.get("synonyms") or "").split(";")
                if synonym.strip()
            )
            candidate_texts = _candidate_texts(label, synonyms)
            similarity = score_column_against_texts(
                column,
                candidate_texts,
                stop_words=STOP_WORDS,
            )
            score = similarity.score
            if score < lexical_threshold:
                continue
            comment = format_similarity_comment(similarity)
            code_entry = CodeEntry(
                system=system,
                code=code,
                label=label,
                synonyms=synonyms,
            )
            scored.append(
                (
                    score,
                    MatchResult(
                        column=column,
                        code=code_entry,
                        score=score,
                        predicate_id=DEFAULT_PREDICATE,
                        mapping_justification=DEFAULT_JUSTIFICATION,
                        comment=comment,
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        matches.extend(match for _, match in scored[:top_k])
        LOGGER.info("Column %s: kept %d keyword matches", name, min(len(scored), top_k))

    return matches


def main(
    dataset_json: Path,
    *,
    datasette_db_url: str = "http://127.0.0.1:8001/terminology",
    table: str = "codes",
    limit: int = 10,
    lexical_threshold: float = 0.35,
    top_k: int = 3,
    output: Optional[Path] = None,
    systems: Optional[Sequence[str]] = None,
    verbose: bool = False,
) -> None:
    """Suggest Datasette-backed terminology rows for each dataset column."""

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    columns, dataset_meta = load_columns(dataset_json)
    if not columns:
        LOGGER.warning("No columns found in %s", dataset_json)
        return

    matches = generate_matches(
        columns,
        dataset_meta,
        datasette_db_url=datasette_db_url,
        table=table,
        limit=limit,
        allowed_systems=systems,
        lexical_threshold=lexical_threshold,
        top_k=top_k,
    )

    if output is None:
        for match in matches:
            row = match.to_sssom_row()
            print(
                f"{row['subject_id']}\t{row['object_id']}\t"
                f"confidence={row['confidence']}\t{row['comment']}"
            )
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    write_sssom(matches, output, dataset_meta=dataset_meta)


if __name__ == "__main__":
    defopt.run(main)
