"""Shared helpers for parsing dataset column metadata."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        if col.summaryStatistics.statisticalDataType:
            statistical_data_type = col.summaryStatistics.statisticalDataType.value
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
    metadata = Metadata.from_dcat_dsv(data)
    columns = [_column_to_info(col) for col in metadata.datasetSchema.columns]

    logger.info("Loaded %d columns from %s", len(columns), path)
    dataset_meta = DatasetMetadata(
        title=_coerce_optional_str(metadata.title),
        description=_coerce_optional_str(metadata.description),
        table_of_contents=_coerce_optional_str(getattr(metadata, "tableOfContents", None)),
    )
    return columns, dataset_meta
