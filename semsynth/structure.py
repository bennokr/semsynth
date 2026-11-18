"""What the codebook declares about missing values and subgroups, applied to a table.

The codebook (linked-codebook 0.10) already says which codes mean "no value" (``missing_values``, ``missing_range``,
a value with ``missing: true``) and when a column applies at all (``applies_when``, a REDCap-style condition). This
module reads those declarations and applies them:

* :func:`recode_declared_missing` turns declared codes (77 = refused, 9999 = unknown) into ``NaN``;
* :func:`applicability` and :func:`structural_violations` say which cells a skip rule leaves empty, and where a table
  has a value that the rule forbids; :func:`enforce_applicability` empties them;
* :class:`Subgroup` names a condition over rows (same language as ``applies_when``). Subgroups are a setting of the
  evaluation (``PipelineConfig.subgroups``), not part of the codebook.

linked-codebook does not treat a pandas ``NaN`` as blank (``[x] < 60`` is False, not unknown, and ``missingness()``
counts it as present), so every table goes through :func:`as_rows` first, which turns ``NaN`` into ``None``.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

    from .codebook import Codebook

LOGGER = logging.getLogger(__name__)


def _is_blank(cell: Any) -> bool:
    return cell is None or (isinstance(cell, float) and math.isnan(cell)) or (isinstance(cell, str) and not cell.strip())


def as_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """The rows of a table as dictionaries, with ``NaN``, ``NA`` and ``NaT`` as ``None`` (see the module note)."""
    import pandas as pd

    clean = frame.astype(object).where(frame.notna(), None)
    return [{str(k): (None if _is_blank(v) or v is pd.NA else v) for k, v in row.items()} for row in clean.to_dict("records")]


def _number(text: Any) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def declared_mask(series: pd.Series, column: Mapping[str, Any]) -> pd.Series:
    """Which cells of a column hold a declared missing code (``77`` equals ``77.0``)."""
    import pandas as pd

    codes = {str(c) for c in column.get("missing_values", [])} | {
        str(v["code"]) for v in column.get("values", []) if v.get("missing")
    }
    limits = column.get("missing_range")
    numbers = {n for n in map(_number, codes) if n is not None}
    values = pd.to_numeric(series, errors="coerce")
    hit = series.astype("string").isin(codes).fillna(False) | values.isin(numbers)
    if limits:
        hit |= (values >= limits["low"]) & (values <= limits["high"])
    return hit.fillna(False).astype(bool)


def recode_declared_missing(df: pd.DataFrame, codebook: Codebook) -> tuple[pd.DataFrame, dict[str, int]]:
    """A copy of the table in which every declared missing code is ``NaN``, and the number of cells recoded per column."""
    import numpy as np

    out, counts = df.copy(), {}
    for column in codebook.columns:
        name = column.get("name")
        if name not in out.columns:
            continue
        mask = declared_mask(out[name], column)
        if mask.any():
            out[name] = out[name].astype(object).where(~mask, np.nan) if out[name].dtype == object else out[name].mask(mask)
            counts[str(name)] = int(mask.sum())
    return out, counts


def conditions_of(codebook: Codebook) -> dict[str, Any]:
    """The parsed ``applies_when`` of each column that has one; a rule that does not parse is skipped and logged."""
    from linked_codebook.condition import parse_condition

    found: dict[str, Any] = {}
    for column in codebook.columns:
        rule = column.get("applies_when")
        if not rule:
            continue
        try:
            found[str(column["name"])] = parse_condition(rule)
        except ValueError as error:
            LOGGER.warning("applies_when of %s does not parse: %s", column.get("name"), error)
    return found


def _fields(node: Any) -> set[str]:
    """The variables a parsed condition refers to."""
    if isinstance(node, dict):
        return {node["var"]} if "var" in node else {v for child in node.values() for v in _fields(child)}
    if isinstance(node, list):
        return {v for child in node for v in _fields(child)}
    return set()


def check_rules(codebook: Codebook, columns: Iterable[str]) -> list[str]:
    """Problems of the skip rules: one that does not parse, or one that refers to a field that is no column.

    linked-codebook evaluates a condition on a missing field as False without an error, so a typo in a rule means that
    its column is never applicable; this is the check that catches it.
    """
    from linked_codebook.condition import parse_condition

    known, problems = set(columns), []
    for column in codebook.columns:
        rule = column.get("applies_when")
        if not rule:
            continue
        try:
            fields = _fields(parse_condition(rule))
        except ValueError as error:
            problems.append(f"{column.get('name')}: {error}")
            continue
        problems += [f"{column.get('name')}: [{f}] is not a column" for f in sorted(fields - known)]
    return problems


def applicability(df: pd.DataFrame, codebook: Codebook) -> pd.DataFrame:
    """For each column with an ``applies_when`` rule: True if it applies to the row, False if not, ``NA`` if unknown.

    Declared missing codes count as blank in the rule, so a refused answer does not decide whether a follow-up applies.
    """
    import pandas as pd
    from linked_codebook.condition import evaluate

    rules = conditions_of(codebook)
    rows = as_rows(recode_declared_missing(df, codebook)[0])
    out = {name: pd.array([evaluate(tree, row, blank="unknown") for row in rows], dtype="boolean") for name, tree in rules.items()}
    return pd.DataFrame(out, index=df.index)


def structural_violations(df: pd.DataFrame, codebook: Codebook) -> dict[str, Any]:
    """Cells with a value where the column's rule says the question does not apply.

    Returns:
        ``rate`` (violating cells over cells the rules say do not apply, NaN if there are none) and, per column,
        ``not_applicable`` rows and ``answered`` among them.
    """
    state = applicability(df, codebook)
    columns: dict[str, dict[str, int]] = {}
    total = answered_total = 0
    for name in state.columns:
        none = state[name].eq(False).fillna(False).to_numpy(dtype=bool)
        has_value = df[name].notna().to_numpy(dtype=bool)
        columns[name] = {"not_applicable": int(none.sum()), "answered": int((none & has_value).sum())}
        total += columns[name]["not_applicable"]
        answered_total += columns[name]["answered"]
    return {"rate": answered_total / total if total else float("nan"), "columns": columns}


def enforce_applicability(df: pd.DataFrame, codebook: Codebook) -> pd.DataFrame:
    """A copy in which every cell that its column's rule marks as not applicable is empty."""
    import numpy as np

    out, state = df.copy(), applicability(df, codebook)
    for name in state.columns:
        none = state[name].eq(False).fillna(False).to_numpy(dtype=bool)
        if none.any():
            out[name] = out[name].astype(object).where(~none, np.nan) if out[name].dtype == object else out[name].mask(none)
    return out


def fill_not_applicable(df: pd.DataFrame, codebook: Codebook) -> pd.DataFrame:
    """A copy in which cells that a skip rule marks as not applicable hold a neutral value instead of being empty.

    A generator that cannot take missing values then still sees the whole table and can learn that the value depends
    on the rule's variables; :func:`enforce_applicability` empties the cells again afterwards. The neutral value is
    the median of the column's applicable values (the most common one for a category).
    """
    out, state = df.copy(), applicability(df, codebook)
    for name in state.columns:
        none = state[name].eq(False).fillna(False).to_numpy(dtype=bool)
        kept = out.loc[~none, name].dropna()
        if none.any() and len(kept):
            neutral = kept.median() if kept.dtype.kind in "fiu" else kept.mode().iloc[0]
            out.loc[none, name] = neutral
    return out


@dataclass(frozen=True)
class Subgroup:
    """A named condition over rows, in the language of ``applies_when``, for example ``[age] >= 80``."""

    name: str
    condition: str
    label: str | None = None

    def tree(self) -> Any:
        from linked_codebook.condition import parse_condition

        return parse_condition(self.condition)


def subgroups_from(items: Iterable[Mapping[str, Any]]) -> list[Subgroup]:
    """Subgroups from settings, each a mapping with ``name``, ``condition`` and optionally ``label``."""
    return [Subgroup(str(item["name"]), str(item["condition"]), item.get("label")) for item in items]


def check_subgroups(groups: Iterable[Subgroup], columns: Iterable[str]) -> list[str]:
    """Problems of subgroup definitions: a condition that does not parse, a name used twice, a field that is no column.

    A field that is not a column makes linked-codebook evaluate the condition as False without an error, so a typo
    gives an empty group; this is the check that catches it.
    """
    known, problems, seen = set(columns), [], set()
    for group in groups:
        if group.name in seen:
            problems.append(f"{group.name}: defined twice")
        seen.add(group.name)
        try:
            tree = group.tree()
        except ValueError as error:
            problems.append(f"{group.name}: {error}")
            continue
        problems += [f"{group.name}: [{field}] is not a column" for field in sorted(_fields(tree) - known)]
    return problems


def membership(df: pd.DataFrame, groups: Iterable[Subgroup]) -> pd.DataFrame:
    """A boolean column per subgroup: True for rows where the condition is True (unknown counts as not a member)."""
    import pandas as pd
    from linked_codebook.condition import evaluate

    rows = as_rows(df)
    out = {g.name: [evaluate(g.tree(), row, blank="unknown") is True for row in rows] for g in groups}
    return pd.DataFrame(out, index=df.index).astype(bool)
