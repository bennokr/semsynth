#!/usr/bin/env python3
"""LLM-assisted mapping of dataset columns via Datasette-backed vocabularies."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import defopt
import llm
from llm_tools_datasette import Datasette

from map_columns.codes_map_columns import (
    DEFAULT_JUSTIFICATION,
    DEFAULT_PREDICATE,
    CodeEntry,
    MatchResult,
    write_sssom,
)
from map_columns.shared import ColumnInfo, DatasetMetadata, load_columns

LOGGER = logging.getLogger(__name__)

# Core SSSOM columns + a couple of useful extras for backwards compatibility.
SSSOM_COLUMNS = [
    "subject_id",
    "subject_label",
    "predicate_id",
    "object_id",
    "object_label",
    "mapping_justification",
    "confidence",
    "comment",
]


def build_system_prompt(dataset_meta: Any, extra_prompt: str = "") -> str:
    """Build the system prompt, including dataset-level metadata and codebook."""
    title = getattr(dataset_meta, "title", None) or ""
    desc = getattr(dataset_meta, "description", None) or ""
    toc = getattr(dataset_meta, "tableOfContents", None) or getattr(
        dataset_meta, "table_of_contents", None
    ) or ""

    base = f"""
You map dataset variables to codes from one or more vocabularies loaded into a Datasette `codes` table.

Dataset metadata:
- title: {title}
- description: {desc}

Additional dataset documentation (may include full codebook and value definitions):
{toc}

The `codes` table has columns:

- system: short identifier for the vocabulary (for example "SNOMED", "LOINC",
          "WD", "ICD10", etc.)
- code: the code/id string within that vocabulary
- label: preferred label
- synonyms: optional synonyms / alternate labels

You have a Datasette tool connected to this database. Use it to run SQL queries
against `codes` whenever you need to find candidate codes.

General guidance:

- Use SQL queries that search `label` and `synonyms` and filter by `system` when helpful.
- Inspect the returned rows and pick the best one or two candidates per variable.
- Be conservative: do not map identifiers, free text, dates, or non-semantic flags
  unless there is a clear and widely used code.
- Use skos:exactMatch only for very tight equivalence, skos:closeMatch for strong
  but imperfect matches, and skos:relatedMatch for looser associations.

You will always return SSSOM-style mappings as JSON objects but you must not
invent codes that are not actually present in the `codes` table.
""".strip()

    if extra_prompt:
        base += "\n\nAdditional hints from the user:\n" + extra_prompt.strip()

    return base


def map_column(
    model: llm.Model,
    ds_tool: Datasette,
    column: ColumnInfo,
    system_prompt: str,
    subject_prefix: str = "dataset",
) -> List[Dict[str, Any]]:
    """
    Ask the LLM (with the Datasette tool) to map one column.
    Returns a list of mapping dicts compatible with SSSOM core columns.
    """
    var_id = column.column_id or column.name or "unknown"
    column_name = column.name or var_id
    role = column.role or ""
    description = column.description or ""
    about = column.about or ""
    unit = column.unit or ""
    data_type = column.statistical_data_type or ""

    user_prompt = f"""
You are mapping ONE dataset variable to one or more codes from the vocabularies
available in the Datasette `codes` table.

Variable:
- internal_id: {var_id}
- column_name: {column_name}
- role: {role}
- description: {description}
- about: {about}
- unit: {unit}
- statistical_data_type: {data_type}

Tasks:

1. Decide if this variable should be mapped to codes in any of the vocabularies
   present in the `system` column (for example SNOMED, LOINC, WD,
   ICD10, or others), or not mapped at all (e.g. identifiers, free
   text, etc.).

2. When mapping, you MUST:
   - Use the Datasette tool to query table `codes`.
   - Use SQL queries that search `label` and `synonyms` and filter by `system`
     where helpful. For example (you do NOT need to quote this in the final answer):

       SELECT system, code, label, synonyms
       FROM codes
       WHERE system IN ('WD', 'SNOMED')
         AND label MATCH 'exercise induced angina'
       LIMIT 10;

   - Inspect the returned rows and pick the best candidate codes.

3. Emit your final result as a JSON array of mapping objects.
   Use this structure exactly:

[
  {{
    "subject_id": "{subject_prefix}:{var_id}",
    "subject_label": "<short human label for the column>",
    "predicate_id": "skos:exactMatch | skos:closeMatch | skos:relatedMatch",
    "object_id": "<SYSTEM>:<code>",
    "object_label": "<preferred term label>",
    "mapping_justification": "semapv:ManualMappingCuration or semapv:LexicalMatching or semapv:LogicalReasoning",
    "confidence": <float between 0 and 1>,
    "comment": "<short free-text justification, may be empty>"
  }}
]

Rules:
- If you find multiple clearly useful mappings (e.g. a measurement that should
  be mapped both to a LOINC lab test and a SNOMED observable entity), include
  multiple objects in the JSON array.
- If you cannot find a suitable concept, return an empty JSON array: [].
- Do NOT include any text before or after the JSON. The entire response must be valid JSON.
"""

    LOGGER.info("Requesting mapping for column %s", var_id)

    chain = model.chain(
        user_prompt,
        system=system_prompt,
        tools=[ds_tool],
    )

    text = chain.text().strip()
    if not text:
        LOGGER.warning("Empty response for column %s", var_id)
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        LOGGER.warning("Invalid JSON for column %s; skipping", var_id)
        return []

    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        LOGGER.warning("Unexpected JSON structure for column %s; skipping", var_id)
        return []

    cleaned: List[Dict[str, Any]] = []
    for mapping in data:
        if not isinstance(mapping, dict):
            continue
        object_id = mapping.get("object_id", "")
        if not object_id:
            continue
        cleaned.append(
            {
                "subject_id": mapping.get("subject_id", f"{subject_prefix}:{var_id}"),
                "subject_label": mapping.get("subject_label", column_name),
                "predicate_id": mapping.get("predicate_id", ""),
                "object_id": object_id,
                "object_label": mapping.get("object_label", ""),
                "mapping_justification": mapping.get(
                    "mapping_justification", DEFAULT_JUSTIFICATION
                ),
                "confidence": mapping.get("confidence", 0.0),
                "comment": mapping.get("comment", ""),
            }
        )

    LOGGER.info("Column %s: produced %d mappings", var_id, len(cleaned))
    return cleaned


def generate_matches(
    columns: Sequence[ColumnInfo],
    dataset_meta: DatasetMetadata,
    *,
    datasette_url: str,
    model: str,
    extra_prompt: str = "",
    subject_prefix: str = "dataset",
    allowed_systems: Optional[Iterable[str]] = None,
    top_k: int = 3,
    confidence_threshold: float = 0.0,
) -> List[MatchResult]:
    """Run the LLM mapping workflow and convert to MatchResult objects."""

    allowed = {system.strip() for system in allowed_systems or [] if system.strip()}
    system_prompt = build_system_prompt(dataset_meta, extra_prompt)
    model_obj = llm.get_model(model)
    datasette_tool = Datasette(datasette_url)

    matches: List[MatchResult] = []
    for column in columns:
        raw_mappings = map_column(
            model=model_obj,
            ds_tool=datasette_tool,
            column=column,
            system_prompt=system_prompt,
            subject_prefix=subject_prefix,
        )

        def _confidence(mapping: Dict[str, Any]) -> float:
            try:
                return float(mapping.get("confidence", 0.0))
            except (TypeError, ValueError):
                return 0.0

        filtered = [
            mapping
            for mapping in raw_mappings
            if _confidence(mapping) >= confidence_threshold
        ]
        if allowed:
            filtered = [
                mapping
                for mapping in filtered
                if mapping.get("object_id", "").split(":", 1)[0] in allowed
            ]

        filtered.sort(key=_confidence, reverse=True)
        for mapping in filtered[:top_k]:
            object_id = mapping.get("object_id", "")
            if ":" not in object_id:
                continue
            system, code = object_id.split(":", 1)
            confidence = _confidence(mapping)
            code_entry = CodeEntry(
                system=system,
                code=code,
                label=mapping.get("object_label", ""),
                synonyms=tuple(),
            )
            matches.append(
                MatchResult(
                    column=column,
                    code=code_entry,
                    score=confidence,
                    predicate_id=mapping.get("predicate_id") or DEFAULT_PREDICATE,
                    mapping_justification=mapping.get(
                        "mapping_justification", DEFAULT_JUSTIFICATION
                    ),
                    comment=mapping.get("comment", ""),
                )
            )

    return matches


def write_rows(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Write raw LLM rows in SSSOM TSV form (legacy helper)."""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SSSOM_COLUMNS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in SSSOM_COLUMNS})
    LOGGER.info("Wrote %d mappings to %s", len(rows), out_path)


def main(
    dataset_json: Path,
    *,
    datasette_url: str = "http://127.0.0.1:8001/terminology",
    model: str = "gpt-4.1-mini",
    extra_prompt: str = "",
    subject_prefix: str = "dataset",
    top_k: int = 3,
    confidence_threshold: float = 0.0,
    systems: Optional[Sequence[str]] = None,
    output: Optional[Path] = None,
    verbose: bool = False,
) -> None:
    """Map dataset columns (from JSON/JSON-LD) to terminology codes via Datasette."""

    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    columns, dataset_meta = load_columns(dataset_json)
    if not columns:
        LOGGER.warning("No columns found in %s; nothing to do", dataset_json)
        return

    matches = generate_matches(
        columns,
        dataset_meta,
        datasette_url=datasette_url,
        model=model,
        extra_prompt=extra_prompt,
        subject_prefix=subject_prefix,
        allowed_systems=systems,
        top_k=top_k,
        confidence_threshold=confidence_threshold,
    )

    if output is None:
        for match in matches:
            row = match.to_sssom_row()
            print(
                f"{row['subject_id']}\t{row['object_id']}\t"
                f"confidence={row['confidence']}\t{row['comment']}"
            )
        return

    write_sssom(matches, output, dataset_meta=dataset_meta)


if __name__ == "__main__":
    defopt.run(main)
