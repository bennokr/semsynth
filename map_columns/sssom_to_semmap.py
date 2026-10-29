"""Merge SSSOM mappings into SemMap/DSV metadata."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import defopt
from linked_codebook import from_sssom

from semsynth.semmap import ColumnProperty, Metadata

logger = logging.getLogger(__name__)


SSSOM_COLUMNS = ("subject_id", "subject_label", "predicate_id", "object_id", "object_label")


def _normalise_object_id(object_id: str) -> str:
    """Return a fully-qualified URI for supported vocabularies."""

    if ":" not in object_id:
        return object_id
    prefix, local_id = object_id.split(":", 1)
    if prefix.lower().startswith("wd"):
        return f"https://www.wikidata.org/entity/{local_id}"
    return object_id


def _load_sssom(tsv_path: Path) -> List[Dict[str, str]]:
    """Load mappings from an SSSOM TSV file."""

    with tsv_path.open("r", encoding="utf-8") as f:
        rows = [line for line in f if not line.lstrip().startswith("#")]
    reader = csv.DictReader(rows, delimiter="\t")
    return [row for row in reader]


def _to_tsv(mappings: List[Dict[str, str]]) -> str:
    """Write mapping rows as SSSOM TSV text, with Wikidata CURIEs expanded to URIs."""

    def cell(value: Optional[str]) -> str:
        return re.sub(r"[\t\r\n]+", " ", value or "")

    lines = ["\t".join(SSSOM_COLUMNS)]
    for row in mappings:
        full = {**row, "object_id": _normalise_object_id(row.get("object_id") or "")}
        lines.append("\t".join(cell(full.get(name)) for name in SSSOM_COLUMNS))
    return "\n".join(lines) + "\n"


def _ensure_column_property(prop: Optional[ColumnProperty]) -> ColumnProperty:
    if prop is None:
        return ColumnProperty()
    return prop


def integrate_sssom(
    metadata: Metadata, mappings: List[Dict[str, str]]
) -> Metadata:
    """Attach SSSOM mappings to column properties in the SemMap metadata.

    Rows are matched to columns and read by linked-codebook: a subject is a column when its IRI,
    its label or the end of its IRI is the column name, ignoring case, spaces, hyphens and underscores.
    Rows with another subject, or with a predicate that is not a SKOS mapping, are skipped.
    """

    columns = {col.name: col for col in metadata.datasetSchema.columns if col.name}
    profile = {"columns": [{"name": name} for name in columns]}
    found = from_sssom(_to_tsv(mappings), profile)
    for entry in found["columns"]:
        column = columns[entry["name"]]
        for mapping in entry.get("mappings", []):
            field = f"{mapping['match_type']}Match"
            column.columnProperty = _ensure_column_property(column.columnProperty)
            existing = getattr(column.columnProperty, field)
            values = existing if isinstance(existing, list) else ([] if existing is None else [existing])
            if mapping["object_id"] not in values:
                values.append(mapping["object_id"])
            setattr(column.columnProperty, field, values)
    return metadata


def main(
    dataset_json: Path,
    sssom_tsv: Path,
    *,
    output_json: Optional[Path] = None,
    indent: int = 2,
) -> None:
    """Merge SSSOM mappings into SemMap metadata and write JSON-LD.

    Args:
        dataset_json: Path to SemMap/DSV JSON-LD metadata file.
        sssom_tsv: Path to an SSSOM TSV file with subject/object pairs.
        output_json: Optional output path for the merged JSON-LD. When omitted,
            the original ``dataset_json`` is overwritten.
        indent: JSON indentation level for the saved metadata.
    """

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

    metadata = Metadata.from_dcat_dsv(json.loads(dataset_json.read_text()))
    mappings = _load_sssom(sssom_tsv)
    for row in mappings:
        if "object_id" in row and isinstance(row["object_id"], str):
            row["object_id"] = _normalise_object_id(row["object_id"])
    updated = integrate_sssom(metadata, mappings)

    target = output_json or dataset_json
    target.write_text(
        json.dumps(updated.to_jsonld(), indent=indent, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote merged SemMap metadata to %s", target)


if __name__ == "__main__":
    defopt.run(main)
