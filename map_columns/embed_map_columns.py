#!/usr/bin/env python3
"""Embed-based column-to-code matching with lexical overlap diagnostics."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import defopt
import torch
from sentence_transformers import SentenceTransformer, util

from map_columns.codes_map_columns import (
    DEFAULT_JUSTIFICATION,
    DEFAULT_PREDICATE,
    CodeEntry,
    MatchResult,
    load_codes,
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


def _format_column_text(column: ColumnInfo, dataset_meta: DatasetMetadata) -> str:
    parts: List[str] = []
    if column.name:
        parts.append(f"Column name: {column.name}")
    if column.description:
        parts.append(f"Description: {column.description}")
    if column.about:
        parts.append(f"About: {column.about}")
    if column.unit:
        parts.append(f"Unit: {column.unit}")
    if column.role:
        parts.append(f"Role: {column.role}")
    if column.statistical_data_type:
        parts.append(f"Data type: {column.statistical_data_type}")
    if dataset_meta.description:
        parts.append(f"Dataset description: {dataset_meta.description}")
    return "\n".join(parts).strip()


def _normalize_cosine(score: float) -> float:
    # Map cosine similarity [-1, 1] into [0, 1].
    return max(0.0, min(1.0, (score + 1.0) / 2.0))


def generate_matches(
    columns: Sequence[ColumnInfo],
    dataset_meta: DatasetMetadata,
    codes: Sequence[CodeEntry],
    *,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    top_k: int = 5,
    candidate_pool_multiplier: int = 5,
    cosine_threshold: float = 0.0,
    lexical_threshold: float = 0.2,
) -> List[MatchResult]:
    """Generate embedding-assisted matches between columns and codes."""

    if not codes:
        return []

    LOGGER.info("Loading sentence-transformer model %s", model_name)
    model = SentenceTransformer(model_name)

    code_texts = [
        " ".join(
            part
            for part in (
                code.label,
                f"[{code.system} {code.code}]",
                "; ".join(code.synonyms) if code.synonyms else "",
            )
            if part
        )
        for code in codes
    ]
    LOGGER.info("Encoding %d codes for embedding lookup", len(codes))
    code_embeddings = model.encode(
        code_texts,
        convert_to_tensor=True,
        show_progress_bar=True,
    )

    matches: List[MatchResult] = []
    for column in columns:
        column_text = _format_column_text(column, dataset_meta)
        if not column_text:
            LOGGER.info("Column %s has no descriptive text; skipping", column.column_id)
            continue

        LOGGER.info("Encoding column %s", column.column_id or column.name)
        column_embedding = model.encode(column_text, convert_to_tensor=True)
        cosine_scores = util.cos_sim(column_embedding, code_embeddings)[0]

        pool_size = min(
            max(top_k * max(candidate_pool_multiplier, 1), top_k),
            len(codes),
        )
        pool_scores, pool_indices = torch.topk(cosine_scores, k=pool_size)

        scored_candidates: List[Tuple[float, MatchResult]] = []
        for cosine_value, idx in zip(pool_scores, pool_indices):
            cosine_float = float(cosine_value)
            if cosine_float < cosine_threshold:
                continue
            code = codes[int(idx)]
            similarity = score_column_against_texts(
                column,
                code.synonyms + (code.label,),
                stop_words=DEFAULT_STOP_WORDS,
            )
            if similarity.score < lexical_threshold:
                LOGGER.debug(
                    "Discarded %s for column %s due to lexical score %.3f",
                    code.curie,
                    column.column_id or column.name,
                    similarity.score,
                )
                continue
            normalized_cosine = _normalize_cosine(cosine_float)
            combined_score = min(
                1.0, (0.5 * similarity.score) + (0.5 * normalized_cosine)
            )
            comment = (
                f"{format_similarity_comment(similarity)}; "
                f"cosine={cosine_float:.3f} (normalized={normalized_cosine:.3f})"
            )
            scored_candidates.append(
                (
                    combined_score,
                    MatchResult(
                        column=column,
                        code=code,
                        score=combined_score,
                        predicate_id=DEFAULT_PREDICATE,
                        mapping_justification=DEFAULT_JUSTIFICATION,
                        comment=comment,
                    ),
                )
            )

        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        matches.extend(match for _, match in scored_candidates[:top_k])
        LOGGER.info(
            "Column %s: retained %d embedding matches",
            column.name or column.column_id,
            min(len(scored_candidates), top_k),
        )

    return matches


def main(
    dataset_json: Path,
    codes_tsv: Path,
    *,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    top_k: int = 5,
    candidate_pool_multiplier: int = 5,
    cosine_threshold: float = 0.0,
    lexical_threshold: float = 0.2,
    systems: Optional[Sequence[str]] = None,
    output: Optional[Path] = None,
    verbose: bool = False,
) -> None:
    """Match dataset columns to terminology codes using embeddings."""

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    columns, dataset_meta = load_columns(dataset_json)
    if not columns:
        LOGGER.warning("No columns found in %s", dataset_json)
        return

    codes_dict: Dict[str, CodeEntry] = load_codes(
        codes_tsv, allowed_systems=systems or None
    )
    codes = list(codes_dict.values())
    if not codes:
        LOGGER.warning("No codes loaded from %s", codes_tsv)
        return

    matches = generate_matches(
        columns,
        dataset_meta,
        codes,
        model_name=model_name,
        top_k=top_k,
        candidate_pool_multiplier=candidate_pool_multiplier,
        cosine_threshold=cosine_threshold,
        lexical_threshold=lexical_threshold,
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
