"""Dataset metadata: a linked-codebook profile.

The profile is read and written as DSV JSON-LD by `linked-codebook <https://bennokr.github.io/linked-codebook/>`_.
Dataset properties that a profile has no slot for, such as the DCAT fields of a provider, are kept as they are.
A codebook says nothing about how a column is used: the target and the columns of a privacy check are settings of
the run.
"""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from linked_codebook import build, infer, is_identifier_name, merge, parse
from linked_codebook.types import Column, Profile

from .language import detector

CATEGORICAL_LEVELS = frozenset({"categorical", "nominal", "ordinal"})
NUMERIC_LEVELS = frozenset({"numerical", "interval", "ratio"})
PARQUET_KEY = b"linked-codebook"

# Keys of a document that a profile reads, or that describe its structure.
_STRUCTURE = {"@context", "@id", "@type", "@graph", "datasetSchema", "summaryStatistics", "column", "columns"}
# Local names of dataset properties and the profile slot that holds them.
_DATASET_SLOTS = {
    "title": "title",
    "description": "description",
    "identifier": "identifier",
    "license": "license",
    "rights": "license",
    "accessRights": "access_rights",
    "citation": "citation",
    "bibliographicCitation": "citation",
    "landingPage": "landing_page",
}


def _local(key: str) -> str:
    return key.rsplit(":", 1)[-1].rsplit("#", 1)[-1]


def _cell(value: Any) -> Any:
    """A value of a data frame as JSON: missing values become ``None`` and other types text."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    try:
        return None if pd.isna(value) else str(value)
    except (TypeError, ValueError):
        return str(value)


def infer_profile(df: pd.DataFrame) -> Profile:
    """Proposes the datatype, level, observed codes and, with ``py3langid``, the language of every column."""
    return infer({str(name): [_cell(value) for value in df[name].tolist()] for name in df.columns}, detector())


@dataclass
class Codebook:
    """A profile and the dataset properties that it has no slot for."""

    profile: Profile = field(default_factory=lambda: Profile(columns=[]))
    extras: dict[str, Any] = field(default_factory=dict)
    prefixes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def read(cls, document: Any) -> Codebook:
        """Reads a codebook, profile JSON or DSV JSON-LD (nested or a flat ``@graph``)."""
        if isinstance(document, Codebook):
            return copy.deepcopy(document)
        if isinstance(document, (str, Path)):
            document = json.loads(Path(document).read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            return cls()
        if isinstance(document.get("columns"), list) and not any(key.startswith("@") for key in document):
            return cls(copy.deepcopy(dict(document)))  # type: ignore[arg-type]
        try:
            profile = parse(document)
        except ValueError:  # a document without a dataset schema, such as a plain schema.org Dataset
            profile = {"columns": []}
        profile["columns"] = [column for column in profile.get("columns", []) if column.get("name")]
        context = document.get("@context")
        prefixes = {key: value for key, value in context.items() if isinstance(value, str)} if isinstance(context, Mapping) else {}
        extras = {
            key: copy.deepcopy(value)
            for key, value in document.items()
            if key not in _STRUCTURE
            and _local(key) not in _STRUCTURE
            and not (_local(key) in _DATASET_SLOTS and _DATASET_SLOTS[_local(key)] in profile)
        }
        return cls(profile, extras, prefixes)

    @classmethod
    def from_frame(cls, df: pd.DataFrame, document: Any = None) -> Codebook:
        """The codebook of ``document`` completed with what linked-codebook infers from ``df``."""
        declared = cls.read(document)
        return cls(merge(infer_profile(df), declared.profile), declared.extras, declared.prefixes)

    def merged(self, other: Codebook) -> Codebook:
        """This codebook completed with ``other``; what ``other`` says wins."""
        return Codebook(
            merge(self.profile, other.profile),
            {**self.extras, **other.extras},
            {**self.prefixes, **other.prefixes},
        )

    @property
    def columns(self) -> list[Column]:
        return list(self.profile.get("columns", []))

    def column(self, name: str) -> Column | None:
        return next((column for column in self.columns if column["name"] == name), None)

    def kind(self, name: str) -> str | None:
        """``categorical`` or ``numeric`` according to the level of the column, or ``None`` if it has none."""
        column: Column = self.column(name) or Column(name=name)
        level = column.get("level")
        if level in CATEGORICAL_LEVELS or column.get("datatype") == "boolean":
            return "categorical"
        if level in NUMERIC_LEVELS:
            return "numeric"
        return "categorical" if column.get("values") else None

    def codes(self, name: str) -> list[str]:
        """The declared codes of a column, in order."""
        column = self.column(name)
        return [value["code"] for value in (column.get("values", []) if column else [])]

    def privacy_frame(self, inferred: Mapping[str, str], target: str | None = None) -> pd.DataFrame:
        """The ``variable``, ``role`` and ``type`` of every column, as the privacy metrics expect them.

        The role is ``target`` for the target, ``id`` for a column whose name is that of an identifier
        (``is_identifier_name``) and ``qi`` for every other column.

        Args:
            inferred: Column names mapped to ``discrete`` or ``continuous``, used where a column has no level.
            target: The target column, if there is one.
        """
        rows = []
        for column in self.columns:
            name = column["name"]
            fallback = "numeric" if inferred.get(name, "continuous") == "continuous" else "categorical"
            role = "target" if name == target else "id" if is_identifier_name(name) else "qi"
            rows.append({"variable": name, "role": role, "type": self.kind(name) or fallback})
        return pd.DataFrame(rows, columns=["variable", "role", "type"])

    def set_statistics(self, df: pd.DataFrame, missingness_model: Any | None = None) -> None:
        """Sets the number of rows and the completeness of each column, from a fitted missingness model if given."""
        models = getattr(missingness_model, "models_", {}) or {}
        self.profile["rows"] = len(df)
        for column in self.profile.get("columns", []):
            name = column["name"]
            if name not in df.columns:
                continue
            model = models.get(name)
            rate = float(getattr(model, "p_missing_", 0.0) or 0.0) if model is not None else float(df[name].isna().mean())
            column["completeness"] = min(1.0, max(0.0, 1.0 - rate))

    def rename(self, names: Mapping[str, str]) -> Codebook:
        """A copy with columns renamed."""
        renamed = copy.deepcopy(self)
        for column in renamed.profile.get("columns", []):
            column["name"] = names.get(column["name"], column["name"])
        return renamed

    def to_jsonld(self) -> dict[str, Any]:
        """DSV JSON-LD written by linked-codebook, with the other dataset properties added."""
        document = build(self.profile)
        context = dict(document["@context"])
        for prefix, iri in self.prefixes.items():
            context.setdefault(prefix, iri)
        document["@context"] = context
        for key, value in self.extras.items():
            document.setdefault(key, copy.deepcopy(value))
        return document


def write_parquet(df: pd.DataFrame, path: str | Path, document: Mapping[str, Any] | None = None) -> None:
    """Writes ``df`` as Parquet, with ``document`` (JSON-LD) in the metadata of the schema."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    table = pa.Table.from_pandas(df, preserve_index=False)
    if document:
        metadata = {**(table.schema.metadata or {}), PARQUET_KEY: json.dumps(document, ensure_ascii=False).encode("utf-8")}
        table = table.replace_schema_metadata(metadata)
    pq.write_table(table, str(path))


def read_parquet(path: str | Path) -> tuple[pd.DataFrame, Codebook | None]:
    """Reads Parquet written by :func:`write_parquet`, with its codebook if it has one."""
    import pyarrow.parquet as pq

    table = pq.read_table(str(path))
    raw = (table.schema.metadata or {}).get(PARQUET_KEY)
    return table.to_pandas(), Codebook.read(json.loads(raw.decode("utf-8"))) if raw else None
