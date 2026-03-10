"""Shared helpers for parsing dataset column metadata and similarity scoring."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from semsynth.semmap import Column, Metadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnInfo:
    """Flattened representation of a ``dsv:column`` entry."""

    column_id: Optional[str]
    name: Optional[str]
    description: Optional[str] = None
    about: Optional[str] = None
    unit: Optional[str] = None
    role: Optional[str] = None
    statistical_data_type: Optional[str] = None
    summary_statistics: Optional[Dict[str, Any]] = None
    source: Optional[str] = None


@dataclass(frozen=True)
class DatasetMetadata:
    """Dataset-level metadata extracted from a DCAT/DSV payload."""

    title: Optional[str]
    description: Optional[str]
    table_of_contents: Optional[str]

    def as_dict(self) -> Dict[str, Optional[str]]:
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
    overlap_terms: FrozenSet[str] = field(default_factory=frozenset)
    matched_pair: Optional[Tuple[str, str]] = None

    @property
    def has_overlap(self) -> bool:
        """Return whether term overlap is non-empty."""

        return bool(self.overlap_terms)


DEFAULT_STOP_WORDS: FrozenSet[str] = frozenset(
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


def _coerce_optional_str(value: Any) -> Optional[str]:
    """Convert ``value`` to a trimmed string when possible."""
    if value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None


def _column_to_info(col: Column) -> ColumnInfo:
    summary_stats: Optional[Dict[str, Any]] = None
    statistical_data_type: Optional[str] = None
    if col.summaryStatistics:
        summary_stats = col.summaryStatistics.to_jsonld()
        data_type = getattr(col.summaryStatistics, "statisticalDataType", None)
        if hasattr(data_type, "value"):
            statistical_data_type = data_type.value
        elif isinstance(data_type, str):
            statistical_data_type = data_type
        elif isinstance(summary_stats, dict):
            statistical_data_type = summary_stats.get("dsv:statisticalDataType") or summary_stats.get(
                "statisticalDataType"
            )
    return ColumnInfo(
        column_id=_coerce_optional_str(col.identifier) or _coerce_optional_str(col.name),
        name=_coerce_optional_str(col.name),
        description=_coerce_optional_str(col.description),
        about=_coerce_optional_str(col.about),
        unit=_coerce_optional_str(getattr(col.columnProperty, "unitText", None)),
        role=_coerce_optional_str(col.hadRole),
        statistical_data_type=statistical_data_type,
        summary_statistics=summary_stats,
        source=_coerce_optional_str(getattr(col.columnProperty, "source", None)),
    )




def _parse_columns_direct(data: Mapping[str, Any]) -> Tuple[List[ColumnInfo], DatasetMetadata]:
    """Parse column metadata directly from JSON-LD mapping.

    Args:
        data: Raw DCAT/DSV mapping.

    Returns:
        Parsed columns and dataset metadata.
    """

    schema = data.get("dsv:datasetSchema") or data.get("datasetSchema") or {}
    raw_columns = []
    if isinstance(schema, Mapping):
        raw = schema.get("dsv:column") or schema.get("columns") or []
        if isinstance(raw, Mapping):
            raw_columns = [raw]
        elif isinstance(raw, list):
            raw_columns = [item for item in raw if isinstance(item, Mapping)]

    columns: List[ColumnInfo] = []
    for raw_col in raw_columns:
        summary_stats = raw_col.get("dsv:summaryStatistics") or raw_col.get("summaryStatistics")
        if not isinstance(summary_stats, dict):
            summary_stats = None
        statistical_data_type = None
        if isinstance(summary_stats, dict):
            statistical_data_type = _coerce_optional_str(
                summary_stats.get("dsv:statisticalDataType")
                or summary_stats.get("statisticalDataType")
            )
        columns.append(
            ColumnInfo(
                column_id=_coerce_optional_str(raw_col.get("schema:identifier") or raw_col.get("identifier") or raw_col.get("schema:name") or raw_col.get("name") or raw_col.get("dcterms:title")),
                name=_coerce_optional_str(raw_col.get("schema:name") or raw_col.get("name") or raw_col.get("dcterms:title") or raw_col.get("schema:identifier") or raw_col.get("identifier")),
                description=_coerce_optional_str(raw_col.get("dcterms:description") or raw_col.get("description")),
                about=_coerce_optional_str(raw_col.get("schema:about") or raw_col.get("about")),
                unit=_coerce_optional_str(raw_col.get("schema:unitText") or raw_col.get("unitText")),
                role=_coerce_optional_str(raw_col.get("prov:hadRole") or raw_col.get("hadRole")),
                statistical_data_type=statistical_data_type,
                summary_statistics=summary_stats,
                source=_coerce_optional_str(raw_col.get("dct:source") or raw_col.get("source")),
            )
        )

    dataset_meta = DatasetMetadata(
        title=_coerce_optional_str(data.get("dcterms:title") or data.get("title")),
        description=_coerce_optional_str(data.get("dcterms:description") or data.get("description")),
        table_of_contents=_coerce_optional_str(
            data.get("dcterms:tableOfContents") or data.get("tableOfContents")
        ),
    )
    return columns, dataset_meta


def parse_columns(data: Mapping[str, Any]) -> Tuple[List[ColumnInfo], DatasetMetadata]:
    """Normalize raw metadata payload into column info and dataset summary.

    Args:
        data: Mapping containing a SemMap/DCAT/DSV JSON-LD payload.

    Returns:
        Tuple where the first item is a list of :class:`ColumnInfo` entries and
        the second item is the simplified dataset metadata.
    """

    try:
        metadata = Metadata.from_dcat_dsv(data)
    except Exception:
        logger.exception("Metadata parsing via semmap failed; falling back to direct parser")
        columns, dataset_meta = _parse_columns_direct(data)
        logger.info("Parsed %d columns from metadata payload (direct)", len(columns))
        return columns, dataset_meta

    columns = [_column_to_info(col) for col in metadata.datasetSchema.columns]
    dataset_meta = DatasetMetadata(
        title=_coerce_optional_str(metadata.title),
        description=_coerce_optional_str(metadata.description),
        table_of_contents=_coerce_optional_str(getattr(metadata, "tableOfContents", None)),
    )
    logger.info("Parsed %d columns from metadata payload", len(columns))
    return columns, dataset_meta


def load_columns(path: Path) -> Tuple[List[ColumnInfo], DatasetMetadata]:
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
    text: Optional[str],
    *,
    stop_words: Optional[Iterable[str]] = None,
    min_token_length: int = 2,
) -> FrozenSet[str]:
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
    stop_words: Optional[Iterable[str]] = None,
) -> FrozenSet[str]:
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


def sequence_ratio(lhs: Optional[str], rhs: Optional[str]) -> float:
    """Compute a Sørensen–Dice-like bigram similarity ratio in [0, 1].

    Args:
        lhs: Left-hand text input.
        rhs: Right-hand text input.

    Returns:
        Floating-point similarity ratio.
    """

    if not lhs or not rhs:
        return 0.0

    def _bigrams(value: str) -> FrozenSet[str]:
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
    stop_words: Optional[Iterable[str]] = None,
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
    best_overlap: FrozenSet[str] = frozenset()
    best_pair: Optional[Tuple[str, str]] = None

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
