"""Framework-neutral synthesis results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SynthesisResult:
    """Result shared by synthesis backends and downstream applications.

    synthetic_data and learned_model deliberately remain backend-neutral
    Python objects. Batch runners may serialize them as files; interactive
    consumers may adapt them directly without round-tripping through disk.
    """

    synthetic_data: Any
    backend: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    privacy_report: Mapping[str, Any] | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    learned_model: Any = None
    semantics: Mapping[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        """Return JSON-friendly metadata without serializing data or model."""

        return {
            "backend": self.backend,
            "parameters": dict(self.parameters),
            "metrics": dict(self.metrics),
            "privacy_report": (
                dict(self.privacy_report) if self.privacy_report is not None else None
            ),
            "provenance": dict(self.provenance),
            "semantics": dict(self.semantics),
            "warnings": list(self.warnings),
        }


__all__ = ["SynthesisResult"]
