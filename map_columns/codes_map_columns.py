#!/usr/bin/env python3
"""Map dataset columns to terminology codes sourced from a TSV file.

This helper keeps the workflow offline by searching ``codes.tsv`` (as produced
by :mod:`map_columns.build_wikidata_medical_codes_table`) and emitting
SSSOM-style mappings for each dataset column. When automated matching does not
yield sufficiently precise results, a JSON file with manual overrides can be
provided to force specific mappings while still validating that the requested
codes exist in the TSV payload.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import defopt

from map_columns.shared import (
    ColumnInfo,
    DatasetMetadata,
    DEFAULT_STOP_WORDS,
    column_tokens,
    format_similarity_comment,
    load_columns,
    score_column_against_texts,
    tokenize,
)

LOGGER = logging.getLogger(__name__)

# Default justification used when a mapping is created through lexical matching.
DEFAULT_JUSTIFICATION = "semapv:LexicalMatching"
# Default predicate for fuzzy matches; manual overrides may supply alternatives.
DEFAULT_PREDICATE = "skos:closeMatch"

# Stop words removed from tokens before scoring. Keep short to avoid
# discarding medically relevant terms.
STOP_WORDS: Set[str] = set(DEFAULT_STOP_WORDS)


@dataclass(frozen=True)
class CodeEntry:
    """Representation of a single terminology code."""

    system: str
    code: str
    label: str
    synonyms: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def curie(self) -> str:
        """Return the CURIE-form of the code (e.g. ``WD_TEST:Q123``)."""

        return f"{self.system}:{self.code}"

class CodeIndex:
    """Simple token index for code synonyms."""

    def __init__(self, codes: Iterable[CodeEntry]):
        self._index: Dict[str, Set[CodeEntry]] = defaultdict(set)
        total_codes = 0
        for code in codes:
            total_codes += 1
            for synonym in code.synonyms:
                for token in tokenize(synonym, stop_words=STOP_WORDS):
                    self._index[token].add(code)
        LOGGER.debug(
            "Constructed code index for %d codes with %d unique tokens",
            total_codes,
            len(self._index),
        )

    def query(self, tokens: Iterable[str]) -> Set[CodeEntry]:
        """Return candidate codes matching any of the provided tokens."""

        candidates: Set[CodeEntry] = set()
        for token in tokens:
            candidates.update(self._index.get(token, set()))
        return candidates


@dataclass
class MatchResult:
    """Candidate mapping for a dataset column."""

    column: ColumnInfo
    code: CodeEntry
    score: float
    predicate_id: str = DEFAULT_PREDICATE
    mapping_justification: str = DEFAULT_JUSTIFICATION
    comment: str = ""

    @property
    def subject_id(self) -> str:
        """Return the canonical SemMap subject identifier for the column."""

        column_id = self.column.column_id or self.column.name or "unknown"
        return f"semmap:{column_id}"

    @property
    def subject_label(self) -> str:
        """Human-friendly label for the dataset column."""

        return (
            self.column.description
            or self.column.name
            or self.column.column_id
            or "unknown column"
        )

    @property
    def object_id(self) -> str:
        """Terminology CURIE for the candidate code."""

        return self.code.curie

    @property
    def object_label(self) -> str:
        """Preferred label for the terminology code."""

        return self.code.label

    @property
    def confidence(self) -> float:
        """Confidence score limited to the [0, 1] range."""

        return max(0.0, min(1.0, self.score))

    def to_sssom_row(self) -> Dict[str, str]:
        """Return a dictionary compatible with :mod:`map_columns.sssom_to_semmap`."""

        return {
            "subject_id": self.subject_id,
            "subject_label": self.subject_label,
            "predicate_id": self.predicate_id,
            "object_id": self.object_id,
            "object_label": self.object_label,
            "mapping_justification": self.mapping_justification,
            "confidence": f"{self.confidence:.3f}",
            "comment": self.comment,
        }


def load_codes(
    codes_tsv: Path,
    *,
    allowed_systems: Optional[Sequence[str]] = None,
) -> Dict[str, CodeEntry]:
    """Load terminology codes from a TSV file.

    Args:
        codes_tsv: Path to the TSV file.
        allowed_systems: Optional iterable restricting which vocabularies to
            load. When omitted all systems present in the TSV are considered.

    Returns:
        Dictionary keyed by ``SYSTEM:CODE`` strings.
    """

    allowed = {system.strip() for system in allowed_systems or [] if system.strip()}
    store: Dict[str, CodeEntry] = {}
    skipped_systems = set()
    with codes_tsv.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            system = row.get("system") or ""
            if allowed and system not in allowed:
                if system not in skipped_systems:
                    LOGGER.info("Skipped system %s (not in %s)", system, allowed)
                    skipped_systems.add(system)
                continue
            entry = CodeEntry(
                system=system,
                code=row.get("code") or "",
                label=row.get("label") or "",
                synonyms=tuple(
                    synonym.strip()
                    for synonym in (row.get("synonyms") or "").split(";")
                    if synonym.strip()
                ),
            )
            if not entry.code or not entry.label:
                continue
            store[entry.curie] = entry
    LOGGER.info("Loaded %d terminology codes from %s", len(store), codes_tsv)
    return store


def rank_codes_for_column(
    column: ColumnInfo,
    code_index: CodeIndex,
    *,
    min_score: float,
    top_k: int,
) -> List[MatchResult]:
    """Return the best ``top_k`` codes for ``column`` above ``min_score``."""

    tokens = column_tokens(column, stop_words=STOP_WORDS)
    if not tokens:
        LOGGER.info(
            "Skipping column %s due to missing descriptive text",
            column.name or column.column_id,
        )
        return []

    scored: List[Tuple[float, CodeEntry]] = []
    comments: Dict[str, str] = {}
    for code in code_index.query(tokens):
        similarity = score_column_against_texts(
            column,
            code.synonyms,
            stop_words=STOP_WORDS,
        )
        score = similarity.score
        if score >= min_score:
            scored.append((score, code))
            comm = format_similarity_comment(similarity)
            comments[code.curie] = comm
            LOGGER.debug("Matched %.2f %s", score, comm)
    scored.sort(key=lambda item: item[0], reverse=True)
    results = [
        MatchResult(
            column=column,
            code=code,
            score=score,
            comment=comments.get(code.curie, ""),
        )
        for score, code in scored[:top_k]
    ]
    LOGGER.info(
        "Found %d candidates for column %s",
        len(results),
        column.name or column.column_id,
    )
    return results


def load_manual_overrides(overrides_path: Optional[Path]) -> Dict[str, List[Dict[str, Any]]]:
    """Read manual override configuration keyed by column identifier.

    Args:
        overrides_path: Path to a JSON file where keys are column identifiers
            (name or SemMap identifier) and values are lists of SSSOM-style
            mapping dictionaries.

    Returns:
        Dictionary suitable for :func:`generate_matches`.
    """

    if overrides_path is None:
        return {}
    data = json.loads(overrides_path.read_text(encoding="utf-8"))
    overrides: Dict[str, List[Dict[str, Any]]] = {}
    for column_name, entries in data.items():
        if not isinstance(entries, list):
            raise ValueError(f"Overrides for {column_name!r} must be a list.")
        overrides[column_name] = entries
    return overrides


def build_manual_matches(
    column: ColumnInfo,
    overrides: Dict[str, List[Dict[str, Any]]],
    codes: Dict[str, CodeEntry],
    *,
    min_score: float,
) -> List[MatchResult]:
    """Create :class:`MatchResult` entries from manual overrides.

    Args:
        column: Column metadata to match.
        overrides: Manual override structure produced by
            :func:`load_manual_overrides`.
        codes: Loaded terminology dictionary keyed by CURIE.
        min_score: Minimum score enforced to keep confidence values >= threshold.

    Returns:
        List of manual :class:`MatchResult` objects for ``column``.
    """

    results: List[MatchResult] = []
    candidate_keys = [
        column.name or "",
        column.column_id or "",
    ]
    seen: Set[str] = set()
    for key in candidate_keys:
        if not key:
            continue
        for override in overrides.get(key, []):
            curie = override.get("object_id")
            if not isinstance(curie, str):
                raise ValueError(f"Manual override for {key} missing object_id")
            code = codes.get(curie)
            if code is None:
                raise ValueError(f"Manual override references unknown code {curie}")
            override_key = f"{key}:{curie}"
            if override_key in seen:
                continue
            seen.add(override_key)
            results.append(
                MatchResult(
                    column=column,
                    code=code,
                    score=max(float(override.get("confidence", 1.0)), min_score),
                    predicate_id=override.get("predicate_id", DEFAULT_PREDICATE),
                    mapping_justification=override.get(
                        "mapping_justification", DEFAULT_JUSTIFICATION
                    ),
                    comment=override.get("comment", ""),
                )
            )
    return results


def generate_matches(
    columns: Sequence[ColumnInfo],
    codes: Dict[str, CodeEntry],
    *,
    min_score: float,
    top_k: int,
    manual_overrides: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[MatchResult]:
    """Generate SSSOM-style matches for the provided columns.

    Args:
        columns: Iterable of column metadata entries.
        codes: Terminology dictionary keyed by CURIE.
        min_score: Minimum similarity score required for automatic candidates.
        top_k: Maximum number of automatic candidates retained per column.
        manual_overrides: Optional manual overrides keyed by column identifier.

    Returns:
        List of :class:`MatchResult` suitable for :func:`write_sssom`.
    """

    overrides = manual_overrides or {}
    code_index = CodeIndex(codes.values())
    matches: List[MatchResult] = []
    for column in columns:
        manual = build_manual_matches(column, overrides, codes, min_score=min_score)
        if manual:
            LOGGER.info("Applying manual overrides for column %s", column.name)
            matches.extend(manual)
            continue

        results = rank_codes_for_column(
            column, code_index, min_score=min_score, top_k=top_k
        )
        matches.extend(results)

    return matches


def write_sssom(
    matches: Iterable[MatchResult],
    output_path: Path,
    *,
    dataset_meta: DatasetMetadata,
    version_tag: str = "",
) -> None:
    """Persist matches in SSSOM TSV format."""

    header = [
        "# curie_map: semmap=https://w3id.org/semsynth/variable/",
        "# curie_map: skos=http://www.w3.org/2004/02/skos/core#",
        "# curie_map: semapv=http://purl.org/semapv/vocab/",
    ]
    if version_tag:
        header.append(f"# mapping_set_version: {version_tag}")
    if dataset_meta.title:
        header.append(f"# mapping_set_title: {dataset_meta.title}")
    header.append("# generated_by: map_columns.codes_map_columns")

    rows = [
        [
            "subject_id",
            "subject_label",
            "predicate_id",
            "object_id",
            "object_label",
            "mapping_justification",
            "confidence",
            "comment",
        ]
    ]
    for match in matches:
        row = match.to_sssom_row()
        rows.append(
            [
                row["subject_id"],
                row["subject_label"],
                row["predicate_id"],
                row["object_id"],
                row["object_label"],
                row["mapping_justification"],
                row["confidence"],
                row["comment"],
            ]
        )

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        for line in header:
            handle.write(f"{line}\n")
        writer = csv.writer(handle, delimiter="\t")
        writer.writerows(rows)
    LOGGER.info("Wrote %d mappings to %s", len(rows) - 1, output_path)


def main(
    dataset_json: Path,
    *,
    codes_tsv: Path,
    output_tsv: Path,
    systems: Sequence[str] = None,
    min_score: float = 0.45,
    top_k: int = 2,
    manual_overrides: Optional[Path] = None,
    verbose: bool = False,
) -> None:
    """Map dataset columns to terminology codes stored in a TSV file.

    Args:
        dataset_json: Path to the DCAT/DSV JSON (or SemMap JSON-LD) describing
            the dataset.
        codes_tsv: TSV file with ``system``, ``code``, ``label``, and
            ``synonyms`` columns.
        output_tsv: Destination path for the SSSOM result.
        systems: Terminology systems to consider when searching for matches.
        min_score: Minimum similarity score a candidate must achieve.
        top_k: Number of candidates to retain per column when no manual
            override is supplied.
        manual_overrides: Optional JSON file specifying manual mappings. The
            format is ``{column_name: [ {object_id, predicate_id, ...}, ...]}``.
        verbose: Enable info-level logging when ``True``.
    """

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    columns, dataset_meta = load_columns(dataset_json)
    codes = load_codes(Path(codes_tsv), allowed_systems=systems)

    overrides = load_manual_overrides(manual_overrides)
    matches = generate_matches(
        columns,
        codes,
        min_score=min_score,
        top_k=top_k,
        manual_overrides=overrides,
    )

    write_sssom(matches, Path(output_tsv), dataset_meta=dataset_meta)


if __name__ == "__main__":
    defopt.run(main)
