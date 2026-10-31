"""Shared helpers for parsing dataset column metadata and similarity scoring."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from semsynth.codebook import Codebook

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnInfo:
    """The parts of a codebook column that matchers use."""

    column_id: str | None
    name: str | None
    description: str | None = None
    unit: str | None = None
    role: str | None = None
    statistical_data_type: str | None = None


@dataclass(frozen=True)
class DatasetMetadata:
    """Dataset-level metadata extracted from a DCAT/DSV payload."""

    title: str | None
    description: str | None
    table_of_contents: str | None

    def as_dict(self) -> dict[str, str | None]:
        """Convert the dataset metadata into a plain mapping."""

        return {
            "title": self.title,
            "description": self.description,
            "table_of_contents": self.table_of_contents,
        }


@dataclass(frozen=True)
class SimilarityResult:
    """Similarity statistics between a column and candidate texts."""

    score: float = 0.0
    jaccard: float = 0.0
    ratio: float = 0.0
    overlap_terms: frozenset[str] = field(default_factory=frozenset)
    matched_pair: tuple[str, str] | None = None

    @property
    def has_overlap(self) -> bool:
        """Return whether term overlap is non-empty."""

        return bool(self.overlap_terms)


DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "in",
        "or",
        "for",
        "due",
        "to",
        "by",
        "no",
        "that",
        "with",
        "s",
        "is",
        "per",
        "presence",
        "type",
        "number",
        "value",
        "values",
        "results",
        "result",
        "measure",
        "measurement",
        "test",
        "level",
        "levels",
    }
)


def _coerce_optional_str(value: Any) -> str | None:
    """Convert ``value`` to a trimmed string when possible."""
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def parse_columns(data: Mapping[str, Any]) -> tuple[list[ColumnInfo], DatasetMetadata]:
    """Normalize raw metadata payload into column info and dataset summary.

    Args:
        data: DSV JSON-LD, or a linked-codebook profile.

    Returns:
        Tuple where the first item is a list of :class:`ColumnInfo` entries and
        the second item is the simplified dataset metadata.
    """

    codebook = Codebook.read(data)
    columns = [
        ColumnInfo(
            column_id=column["name"],
            name=column["name"],
            description=_coerce_optional_str(column.get("description")),
            unit=_coerce_optional_str(column.get("unit")),
            role=_coerce_optional_str(codebook.roles.get(column["name"])),
            statistical_data_type=_coerce_optional_str(column.get("level")),
        )
        for column in codebook.columns
        if column["name"]
    ]
    extras = codebook.extras
    dataset_meta = DatasetMetadata(
        title=_coerce_optional_str(codebook.profile.get("title")),
        description=_coerce_optional_str(codebook.profile.get("description")),
        table_of_contents=_coerce_optional_str(
            extras.get("dcterms:tableOfContents") or extras.get("dct:tableOfContents") or extras.get("tableOfContents")
        ),
    )
    logger.info("Parsed %d columns from metadata payload", len(columns))
    return columns, dataset_meta


def load_columns(path: Path) -> tuple[list[ColumnInfo], DatasetMetadata]:
    """Load dataset metadata and column definitions from JSON.

    Args:
        path: Location of the DCAT/DSV JSON/JSON-LD file.

    Returns:
        A tuple of ``(columns, metadata)`` where ``columns`` is a list
        of :class:`ColumnInfo` and ``metadata`` is a simplified dataset-level
        summary.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    columns, dataset_meta = parse_columns(data)
    logger.info("Loaded %d columns from %s", len(columns), path)
    return columns, dataset_meta


def tokenize(
    text: str | None,
    *,
    stop_words: Iterable[str] | None = None,
    min_token_length: int = 2,
) -> frozenset[str]:
    """Tokenize ``text`` removing punctuation and optional stop words.

    Args:
        text: Input text to tokenize.
        stop_words: Optional iterable of words to exclude after lowercasing.
        min_token_length: Minimum length of tokens to retain.

    Returns:
        ``frozenset`` of lowercase tokens that met the filtering criteria.
    """

    if not text:
        return frozenset()
    cleaned = re.sub(r"[^0-9A-Za-z]+", " ", text).lower()
    words = cleaned.split()
    stop_set = {word.lower() for word in stop_words or []}
    filtered = {
        token
        for token in words
        if token and len(token) >= min_token_length and token not in stop_set
    }
    return frozenset(filtered)


def column_tokens(
    column: ColumnInfo,
    *,
    stop_words: Iterable[str] | None = None,
) -> frozenset[str]:
    """Return the union of tokens derived from a column's name and description.

    Args:
        column: Column metadata to analyze.
        stop_words: Optional iterable of stop words to exclude.

    Returns:
        ``frozenset`` containing the aggregated tokens.
    """

    texts = [column.name, column.description]
    token_sets = [
        tokenize(text, stop_words=stop_words) for text in texts if text
    ]
    if not token_sets:
        return frozenset()
    return frozenset().union(*token_sets)


def format_similarity_comment(
    similarity: SimilarityResult,
    *,
    include_match_text: bool = True,
) -> str:
    """Return a human-readable description of lexical overlap.

    Args:
        similarity: Result produced by :func:`score_column_against_texts`.
        include_match_text: Whether to include the matching column/code text.

    Returns:
        Comment suitable for the SSSOM ``comment`` field.
    """

    if not similarity.has_overlap:
        base = "Lexical overlap terms: (none)"
    else:
        quoted = ", ".join(f'"{term}"' for term in sorted(similarity.overlap_terms))
        base = f"Lexical overlap terms: {quoted}"
    if include_match_text and similarity.matched_pair:
        lhs, rhs = similarity.matched_pair
        return f"{base}; match: {lhs!r} vs {rhs!r}"
    return base


def sequence_ratio(lhs: str | None, rhs: str | None) -> float:
    """Compute a Sørensen-Dice-like bigram similarity ratio in [0, 1].

    Args:
        lhs: Left-hand text input.
        rhs: Right-hand text input.

    Returns:
        Floating-point similarity ratio.
    """

    if not lhs or not rhs:
        return 0.0

    def _bigrams(value: str) -> frozenset[str]:
        cleaned = value.lower()
        return frozenset({cleaned[i : i + 2] for i in range(len(cleaned) - 1)})

    left = _bigrams(lhs)
    right = _bigrams(rhs)
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    return (2.0 * overlap) / (len(left) + len(right))


def score_column_against_texts(
    column: ColumnInfo,
    candidate_texts: Sequence[str],
    *,
    stop_words: Iterable[str] | None = None,
) -> SimilarityResult:
    """Score similarity between column metadata and candidate text snippets.

    Args:
        column: Column information containing name and description.
        candidate_texts: Iterable of labels/synonyms describing a code.
        stop_words: Optional iterable of stop words to exclude when tokenizing.

    Returns:
        :class:`SimilarityResult` aggregating the best overlap and ratio.
    """

    texts = tuple(text for text in candidate_texts if text)
    if not texts:
        return SimilarityResult()

    column_fields = tuple(filter(None, (column.name, column.description)))
    if not column_fields:
        return SimilarityResult()

    best_jaccard = 0.0
    best_overlap: frozenset[str] = frozenset()
    best_pair: tuple[str, str] | None = None

    for field_text in column_fields:
        field_tokens = tokenize(field_text, stop_words=stop_words)
        if not field_tokens:
            continue
        for candidate in texts:
            candidate_tokens = tokenize(candidate, stop_words=stop_words)
            if not candidate_tokens:
                continue
            overlap = field_tokens & candidate_tokens
            universe = field_tokens | candidate_tokens
            jaccard = len(overlap) / (len(universe) or 1)
            if jaccard > best_jaccard:
                best_jaccard = jaccard
                best_overlap = frozenset(overlap)
                best_pair = (field_text, candidate)

    if not best_pair:
        logger.debug(
            "No token overlap between column '%s' and candidates %s",
            column.name or column.column_id,
            texts,
        )

    ratios = [
        sequence_ratio(field_text, candidate)
        for field_text in column_fields
        for candidate in texts
    ]
    best_ratio = max(ratios) if ratios else 0.0
    score = (0.7 * best_jaccard) + (0.3 * best_ratio)
    return SimilarityResult(
        score=score,
        jaccard=best_jaccard,
        ratio=best_ratio,
        overlap_terms=best_overlap,
        matched_pair=best_pair,
    )
