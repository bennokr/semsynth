"""Merge SSSOM mappings into a codebook."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

import defopt
from linked_codebook import from_sssom

from semsynth.codebook import Codebook

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


def _load_sssom(tsv_path: Path) -> list[dict[str, str]]:
    """Load mappings from an SSSOM TSV file."""

    with tsv_path.open("r", encoding="utf-8") as f:
        rows = [line for line in f if not line.lstrip().startswith("#")]
    reader = csv.DictReader(rows, delimiter="\t")
    return list(reader)


def _to_tsv(mappings: list[dict[str, str]]) -> str:
    """Write mapping rows as SSSOM TSV text, with Wikidata CURIEs expanded to URIs."""

    def cell(value: str | None) -> str:
        return re.sub(r"[\t\r\n]+", " ", value or "")

    lines = ["\t".join(SSSOM_COLUMNS)]
    for row in mappings:
        full = {**row, "object_id": _normalise_object_id(row.get("object_id") or "")}
        lines.append("\t".join(cell(full.get(name)) for name in SSSOM_COLUMNS))
    return "\n".join(lines) + "\n"


def integrate_sssom(codebook: Codebook, mappings: list[dict[str, str]], *, reviewer: str) -> Codebook:
    """Adds SSSOM mappings to the columns of a codebook, approved by ``reviewer``.

    Rows are matched to columns and read by linked-codebook: a subject is a column when its IRI,
    its label or the end of its IRI is the column name, ignoring case, spaces, hyphens and underscores.
    Rows with another subject, or with a predicate that is not a SKOS mapping, are skipped.

    linked-codebook writes only approved mappings to JSON-LD, so a mapping without a reviewer in the file gets
    ``reviewer``. Name the tool or person who stands behind the mappings.
    """

    profile = {"columns": [{"name": column["name"]} for column in codebook.columns]}
    found = from_sssom(_to_tsv(mappings), profile)
    for entry in found["columns"]:
        unique = {(mapping["match_type"], mapping["object_id"]): mapping for mapping in entry.get("mappings", [])}
        entry["mappings"] = [{"reviewer_id": reviewer, **mapping} for mapping in unique.values()]
    return codebook.merged(Codebook(found))


def main(
    dataset_json: Path,
    sssom_tsv: Path,
    *,
    output_json: Path | None = None,
    indent: int = 2,
) -> None:
    """Merge SSSOM mappings into a codebook and write JSON-LD.

    Args:
        dataset_json: Path to DSV JSON-LD metadata.
        sssom_tsv: Path to an SSSOM TSV file with subject/object pairs.
        output_json: Optional output path for the merged JSON-LD. When omitted,
            the original ``dataset_json`` is overwritten.
        indent: JSON indentation level for the saved metadata.
    """

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

    codebook = Codebook.read(json.loads(dataset_json.read_text()))
    mappings = _load_sssom(sssom_tsv)
    for row in mappings:
        if "object_id" in row and isinstance(row["object_id"], str):
            row["object_id"] = _normalise_object_id(row["object_id"])
    updated = integrate_sssom(codebook, mappings, reviewer=sssom_tsv.name)

    target = output_json or dataset_json
    target.write_text(
        json.dumps(updated.to_jsonld(), indent=indent, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Wrote merged codebook to %s", target)


if __name__ == "__main__":
    defopt.run(main)
