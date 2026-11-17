"""Gower distance between records with missing values, and nearest-record search.

The Gower distance of two rows is the mean over columns of a per-column distance in [0, 1]: the absolute difference
over the reference range for a number, 0 or 1 for a category. What a missing value does is a modelling decision, and
it differs by column, so it is a *policy* per column:

``category``
    Missing is a value of its own. Both missing: distance 0 (agreement). One missing: 1. Use it when a missing value is
    informative and shared absence is a real similarity (a lab test that is only ordered for sick patients).
``observed``
    Classic Gower: a column where either row is missing is left out of both the sum and the count. Use it for
    item non-response that carries no information about the person.
``asymmetric``
    Both missing: the column is left out. One missing: 1. Both observed: the usual distance. Use it for structural
    missingness (a question that does not apply to either person says nothing about how alike they are, but being
    asked in one record and skipped in the other does).

Two rows with nothing comparable (no column counted) are at distance 1.

Numbers are scaled by the range of the reference rows and a difference larger than the range counts as 1; a category that the reference never contains
differs from everything, including another such category. There is no limit on the number of levels.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

POLICIES = ("category", "observed", "asymmetric")
MAX_REFERENCE_ROWS = 20000
MAX_QUERY_ROWS = 5000
_TINY = 1e-12  # the span of a constant column: any difference is then a full distance
_BLOCK = 2_000_000  # query rows times reference rows handled at once


def resolve_policies(columns: list[str], missing: str | Mapping[str, str]) -> dict[str, str]:
    """The policy of each column: one name for all, or a mapping with the default under ``"*"`` (``category``)."""

    default = missing if isinstance(missing, str) else missing.get("*", "category")
    chosen = {c: default if isinstance(missing, str) else missing.get(c, default) for c in columns}
    unknown = sorted({p for p in [*chosen.values(), default] if p not in POLICIES})
    if unknown:
        raise ValueError(f"Unknown missing-value policy {unknown}; use one of {POLICIES}.")
    return chosen


class GowerIndex:
    """Nearest-record search over a reference table.

    Args:
        reference: The rows to search in. Numeric columns are floats with ``NaN`` for missing; the others hold
            labels with ``NaN`` for missing.
        missing: Policy for missing values: one of :data:`POLICIES` or a per-column mapping (see
            :func:`resolve_policies`).
        seed: Seed for subsampling.
        max_reference: A larger reference is subsampled to this many rows, once, so that every query set is
            compared with the same rows. Distances then are upper bounds of the full-reference distances.
    """

    def __init__(
        self,
        reference: pd.DataFrame,
        *,
        missing: str | Mapping[str, str] = "category",
        seed: int = 0,
        max_reference: int = MAX_REFERENCE_ROWS,
    ) -> None:
        import numpy as np

        if len(reference) > max_reference:
            reference = reference.sample(max_reference, random_state=seed)
        self.columns = list(reference.columns)
        self.policies = resolve_policies(self.columns, missing)
        self.seed = seed
        self.numeric = [c for c in self.columns if reference[c].dtype.kind == "f"]
        self.categorical = [c for c in self.columns if c not in self.numeric]
        self.lo = {c: float(np.nanmin(reference[c])) if reference[c].notna().any() else 0.0 for c in self.numeric}
        self.span = {
            c: (float(np.nanmax(reference[c])) - self.lo[c]) if reference[c].notna().any() else 0.0
            for c in self.numeric
        }
        self.levels = {c: _levels(reference[c]) for c in self.categorical}
        self.n_reference = len(reference)
        self._numbers, self._labels = self._encode(reference)

    def _encode(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Numbers scaled to [0, 1] (``NaN`` kept), and label codes (-1 missing, -2 not in the reference)."""
        import numpy as np
        import pandas as pd

        numbers = np.empty((len(frame), len(self.numeric)), dtype=np.float32)
        for j, column in enumerate(self.numeric):
            values = frame[column].to_numpy(float)
            numbers[:, j] = (values - self.lo[column]) / (self.span[column] or _TINY)
        labels = np.empty((len(frame), len(self.categorical)), dtype=np.int32)
        for j, column in enumerate(self.categorical):
            series = frame[column]
            codes = pd.Categorical(series, categories=self.levels[column]).codes.astype(np.int32)
            labels[:, j] = np.where((codes == -1) & series.notna().to_numpy(), -2, codes)
        return numbers, labels

    def _pairwise(self, numbers: np.ndarray, labels: np.ndarray) -> np.ndarray:
        """Distances from each of the given encoded rows to every reference row."""
        import numpy as np

        shape = (len(numbers), self.n_reference)
        total = np.zeros(shape, dtype=np.float32)
        count = np.zeros(shape, dtype=np.float32)
        for j, column in enumerate(self.numeric):
            a, b = numbers[:, j, None], self._numbers[None, :, j]
            gap = np.minimum(np.abs(a - b), 1.0)
            _accumulate(total, count, gap, np.isnan(a), np.isnan(b), self.policies[column])
        for j, column in enumerate(self.categorical):
            a, b = labels[:, j, None], self._labels[None, :, j]
            gap = ((a != b) | (a == -2)).astype(np.float32)
            _accumulate(total, count, gap, a == -1, b == -1, self.policies[column])
        return np.where(count > 0, total / np.maximum(count, 1), 1.0).astype(np.float32)

    def _blocks(self, queries: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
        numbers, labels = self._encode(queries[self.columns])
        step = max(1, _BLOCK // max(self.n_reference, 1))
        return [(numbers[i : i + step], labels[i : i + step]) for i in range(0, len(queries), step)]

    def nearest(self, queries: pd.DataFrame) -> np.ndarray:
        """Distance from each query row to its closest reference row, in [0, 1].

        More than :data:`MAX_QUERY_ROWS` queries are subsampled (seeded).
        """
        import numpy as np

        if len(queries) > MAX_QUERY_ROWS:
            queries = queries.sample(MAX_QUERY_ROWS, random_state=self.seed)
        return np.concatenate([self._pairwise(n, c).min(axis=1) for n, c in self._blocks(queries)])

    def matrix(self, queries: pd.DataFrame) -> np.ndarray:
        """All distances, queries by reference rows. For small tables and tests."""
        import numpy as np

        return np.concatenate([self._pairwise(n, c) for n, c in self._blocks(queries)])


def _levels(series: pd.Series) -> list[object]:
    """The distinct non-missing labels of a column, in a stable order."""
    return sorted(series.dropna().unique().tolist(), key=str)


def _accumulate(
    total: np.ndarray, count: np.ndarray, gap: np.ndarray, na: np.ndarray, nb: np.ndarray, policy: str
) -> None:
    """Add one column to the running sum and count of a block, under the column's policy."""
    import numpy as np

    either, both = na | nb, na & nb
    if policy == "observed":
        total += np.where(either, 0.0, gap)
        count += ~either
    elif policy == "asymmetric":
        total += np.where(both, 0.0, np.where(either, 1.0, gap))
        count += ~both
    else:
        total += np.where(both, 0.0, np.where(either, 1.0, gap))
        count += 1.0
