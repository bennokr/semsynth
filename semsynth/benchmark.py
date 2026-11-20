"""Injected-truth benchmark: break a complete table in known ways, and check what the pipeline recovers.

No real clinical dataset says why its values are missing. A complete table does not either, but when *we* remove
values we know the answer. :func:`inject` applies :class:`Mechanism` objects to a complete table and returns the
incomplete table, a codebook that declares what a person could declare (skip rules, missing codes), and the truth: the
complete table, the cells each mechanism emptied, and its parameters. :func:`recovery_scores` then compares a synthetic
table with that truth, and :func:`run_injected_benchmark` runs the pipeline's own steps on the result.

Mechanisms (all act on cells that are still observed, in the order given):

``mcar``
    Each cell is missing with probability ``rate``, regardless of anything.
``mar``
    Probability rises with the (observed) numeric ``driver`` column: ``sigmoid(a + strength * z(driver))``, with ``a``
    chosen so that the average equals ``rate``.
``mnar``
    The same, but driven by the column's *own* value, which is gone afterwards. Nothing observed can recover it exactly;
    only correlated columns help.
``structural``
    The column is empty where the ``rule`` (an ``applies_when`` condition) is False. The codebook declares the rule.
``coded``
    A share ``rate`` of observed cells is replaced by the codes of ``codes`` (77 refused, 99 don't know). The codebook
    declares them; the table keeps them until they are recoded.
``censored``
    Values below the ``rate`` quantile (the limit of detection) are replaced by ``limit / sqrt(2)`` and a column
    ``<column>_below_lod`` flags them.

The recovery numbers are deliberately plain: missing rates, and the *gradient* (the difference in missing rate between
the top and bottom third of a driver), real against synthetic.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

    from .codebook import Codebook

LOGGER = logging.getLogger(__name__)

KINDS = ("mcar", "mar", "mnar", "structural", "coded", "censored")
LOD_SUFFIX = "_below_lod"
MIN_LEARNABLE_ROWS = 30
VARIANTS = ("learned", "learned_with_rules", "structure_aware")


@dataclass(frozen=True)
class Mechanism:
    """One way of making values missing; see the module documentation for what each ``kind`` means."""

    column: str
    kind: str
    rate: float = 0.2
    driver: str | None = None
    strength: float = 2.0
    rule: str | None = None
    codes: tuple[str, ...] = ("77", "99")


@dataclass
class Injection:
    """An incomplete table and everything known about how it was made."""

    frame: pd.DataFrame
    complete: pd.DataFrame
    codebook: Codebook
    cells: dict[str, pd.Series]
    truth: list[dict[str, Any]] = field(default_factory=list)


def _calibrated(score: np.ndarray, rate: float, strength: float, rng: np.random.Generator) -> np.ndarray:
    """A Bernoulli draw with probability ``sigmoid(a + strength * score)``, ``a`` chosen so that the mean is ``rate``."""
    import numpy as np

    low, high = -30.0, 30.0
    for _ in range(60):
        mid = (low + high) / 2
        mean = float(np.mean(1 / (1 + np.exp(-(mid + strength * score)))))
        low, high = (mid, high) if mean < rate else (low, mid)
    probability = 1 / (1 + np.exp(-((low + high) / 2 + strength * score)))
    return rng.random(len(score)) < probability


def _z(values: pd.Series) -> np.ndarray:
    import numpy as np
    import pandas as pd

    numbers = pd.to_numeric(values, errors="coerce")
    if numbers.isna().all() or numbers.std() == 0:
        raise ValueError(f"{values.name}: a numeric column with some variation is needed to drive missingness")
    return np.asarray(((numbers - numbers.mean()) / numbers.std()).fillna(0.0).to_numpy(float))


def _chosen(table: pd.DataFrame, complete: pd.DataFrame, m: Mechanism, rng: np.random.Generator) -> pd.Series:
    """The cells (rows) of the column that the mechanism hits, among those still observed."""
    import numpy as np
    import pandas as pd

    observed = table[m.column].notna().to_numpy()
    if m.kind == "mcar" or m.kind == "coded":
        hit = rng.random(len(table)) < m.rate
    elif m.kind in ("mar", "mnar"):
        driver = m.driver or (m.column if m.kind == "mnar" else None)
        if driver is None:
            raise ValueError("mar needs a driver column")
        hit = _calibrated(_z(complete[driver]), m.rate, m.strength, rng)
    elif m.kind == "structural":
        from linked_codebook.condition import evaluate, parse_condition

        from .structure import as_rows

        tree = parse_condition(m.rule or "")
        hit = np.array([evaluate(tree, row, blank="unknown") is False for row in as_rows(complete)])
    else:
        raise ValueError(f"unknown mechanism {m.kind!r}; use one of {KINDS}")
    return pd.Series(hit & observed, index=table.index)


def _declare(codebook: Codebook, m: Mechanism) -> None:
    column = codebook.column(m.column)
    if column is None:
        return
    if m.kind == "structural":
        column["applies_when"] = m.rule or ""
    elif m.kind == "coded":
        column["missing_values"] = list(m.codes)


def inject(complete: pd.DataFrame, mechanisms: Sequence[Mechanism], *, seed: int = 0) -> Injection:
    """Apply the mechanisms to a complete table.

    Args:
        complete: A table without missing values (rows with some are dropped).
        mechanisms: What to do to which column, in order.
        seed: Seed of every random draw.

    Returns:
        The :class:`Injection`; ``cells[column]`` marks the rows each column lost (or had coded) and ``truth`` holds
        the parameters and the realized rates.
    """
    import numpy as np

    from .codebook import Codebook

    rng = np.random.default_rng(seed)
    complete = complete.dropna().reset_index(drop=True)
    table = complete.copy()
    cells: dict[str, pd.Series] = {}
    truth: list[dict[str, Any]] = []
    for m in mechanisms:
        if m.column not in table.columns:
            raise ValueError(f"{m.column}: not a column of the table")
        if m.kind == "censored":
            truth.append(_censor(table, m))
            continue
        hit = _chosen(table, complete, m, rng)
        if m.kind == "coded":
            codes = [float(c) if table[m.column].dtype.kind in "fiu" else c for c in m.codes]
            table[m.column] = table[m.column].astype(object if table[m.column].dtype.kind not in "fiu" else float)
            table.loc[hit, m.column] = [codes[i % len(codes)] for i in range(int(hit.sum()))]
        else:
            table.loc[hit, m.column] = np.nan
        cells[m.column] = hit | cells.get(m.column, hit & False)
        truth.append({**_params(m), "realized_rate": float(hit.mean())})
    codebook = Codebook.from_frame(table)
    for m in mechanisms:
        _declare(codebook, m)
    return Injection(table, complete, codebook, cells, truth)


def _params(m: Mechanism) -> dict[str, Any]:
    keep = {"column": m.column, "kind": m.kind, "target_rate": m.rate}
    if m.kind in ("mar", "mnar"):
        keep |= {"driver": m.driver or m.column, "strength": m.strength}
    if m.kind == "structural":
        keep["rule"] = m.rule
    if m.kind == "coded":
        keep["codes"] = list(m.codes)
    return keep


def _censor(table: pd.DataFrame, m: Mechanism) -> dict[str, Any]:
    import numpy as np

    values = table[m.column].astype(float)
    limit = float(values.quantile(m.rate))
    below = values < limit
    table[m.column] = values.mask(below, limit / math.sqrt(2))
    table[m.column + LOD_SUFFIX] = below.astype(int)
    return {**_params(m), "limit": limit, "substituted": limit / math.sqrt(2), "realized_rate": float(np.mean(below))}


def _gradient(values: pd.Series, missing: pd.Series) -> float | None:
    """Missing rate in the top third of the driver minus the rate in the bottom third."""
    import pandas as pd

    numbers = pd.to_numeric(values, errors="coerce")
    low, high = numbers.quantile([1 / 3, 2 / 3])
    bottom, top = missing[numbers <= low], missing[numbers >= high]
    if len(bottom) == 0 or len(top) == 0:
        return None
    return float(top.mean() - bottom.mean())


def _gap(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else abs(a - b)


def recovery_scores(injection: Injection, pristine: pd.DataFrame, released: pd.DataFrame) -> dict[str, Any]:
    """Compare a synthetic table with the injected truth, mechanism by mechanism.

    Args:
        injection: What :func:`inject` returned.
        pristine: The synthetic table before its missing values were put in, so that a missing cell's underlying
            value is still known (needed to judge a self-driven mechanism).
        released: The synthetic table as released, with missing values.

    Returns:
        ``mechanisms`` (one record per injected mechanism with real and synthetic rates and gradients, and their
        gaps) and ``summary`` (mean gaps, and the rate of values that break a declared skip rule).
    """
    from .structure import recode_declared_missing, structural_violations

    released = recode_declared_missing(released, injection.codebook)[0]  # a table that still holds codes is scored as missing
    records: list[dict[str, Any]] = []
    for item in injection.truth:
        name, kind = item["column"], item["kind"]
        record: dict[str, Any] = {k: item[k] for k in ("column", "kind", "target_rate", "realized_rate") if k in item}
        if kind == "censored":
            record["synthetic_share_below_limit"] = float((released[name] < item["limit"]).mean())
        elif name in released.columns:
            real_miss = injection.cells[name]
            synth_miss = released[name].isna()
            record["rate_real"], record["rate_synthetic"] = float(real_miss.mean()), float(synth_miss.mean())
            record["rate_gap"] = abs(record["rate_real"] - record["rate_synthetic"])
            driver = item.get("driver")
            if driver in injection.complete.columns and driver in pristine.columns:
                record["gradient_real"] = _gradient(injection.complete[driver], real_miss)
                record["gradient_synthetic"] = _gradient(pristine[driver], synth_miss)
                record["gradient_gap"] = _gap(record["gradient_real"], record["gradient_synthetic"])
        records.append(record)
    violations = structural_violations(released, injection.codebook)
    return {"mechanisms": records, "summary": _summary(records, violations)}


def _summary(records: list[dict[str, Any]], violations: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    def mean(key: str) -> float | None:
        values = [r[key] for r in records if r.get(key) is not None]
        return float(np.mean(values)) if values else None

    rate = violations["rate"]
    return {
        "rate_gap_mean": mean("rate_gap"),
        "gradient_gap_mean": mean("gradient_gap"),
        "structural_violation_rate": None if rate != rate else rate,
    }


def run_injected_benchmark(
    complete: pd.DataFrame,
    mechanisms: Sequence[Mechanism],
    *,
    backend: str = "metasyn",
    seed: int = 0,
    rows: int | None = None,
    **options: Any,
) -> dict[str, Any]:
    """Inject, run the pipeline's own steps, and score what comes out.

    The steps are those of :mod:`semsynth.runner`: declared codes become missing, the generator learns from the
    complete rows only, a missingness model learned from the incomplete rows is applied to its output. Two variants are
    scored: ``learned`` (that, and nothing else), ``learned_with_rules`` (the same, with the declared skip rules then
    enforced) and ``structure_aware`` (cells that a skip rule marks as not applicable are filled for learning, so rows
    are not lost for them, and the rules are enforced afterwards). Each reports the share of rows the generator could
    learn from, and how close its table is to the complete truth before masking.
    """
    from .structure import enforce_applicability, fill_not_applicable, recode_declared_missing

    injection = inject(complete, mechanisms, seed=seed)
    incomplete, recoded = recode_declared_missing(injection.frame, injection.codebook)
    disc = [c for c in incomplete.columns if incomplete[c].dtype.kind not in "fiu"]
    cont = [c for c in incomplete.columns if c not in disc]
    out: dict[str, Any] = {"status": "ok", "recoded_codes": recoded, "truth": injection.truth}
    for variant, learn_from, rules in (
        (VARIANTS[0], incomplete, False),
        (VARIANTS[1], incomplete, True),
        (VARIANTS[2], fill_not_applicable(incomplete, injection.codebook), True),
    ):
        learnable = learn_from.dropna().reset_index(drop=True)
        record: dict[str, Any] = {"complete_rows": len(learnable), "complete_share": len(learnable) / len(incomplete)}
        if len(learnable) < MIN_LEARNABLE_ROWS:
            out[variant] = {**record, "status": "too_few_complete_rows"}
            continue
        pristine, released = _generate(injection, incomplete, learnable, disc, cont, backend, rows, seed, options)
        if rules:
            released = enforce_applicability(released, injection.codebook)
        out[variant] = {
            **record,
            "status": "ok",
            "fidelity_to_truth": _fidelity_to_truth(injection.complete, pristine, disc, cont),
            **recovery_scores(injection, pristine, released),
        }
    return out


def _fidelity_to_truth(complete: pd.DataFrame, pristine: pd.DataFrame, disc: list[str], cont: list[str]) -> dict[str, float]:
    """How close the synthetic table (before masking) is to the complete truth, which the pipeline never sees."""
    from .metrics import per_variable_distances, summarize_distance_metrics

    columns = [c for c in pristine.columns if c in complete.columns]
    return summarize_distance_metrics(
        per_variable_distances(complete[columns], pristine[columns], [c for c in disc if c in columns], [c for c in cont if c in columns])
    )


def _generate(
    injection: Injection,
    incomplete: pd.DataFrame,
    learnable: pd.DataFrame,
    disc: list[str],
    cont: list[str],
    backend: str,
    rows: int | None,
    seed: int,
    options: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The generator learns from ``learnable`` and a missingness model learned from ``incomplete`` is applied to it."""
    from .missingness import apply_missingness, fit_missingness_model
    from .synthesis import synthesize

    result = synthesize(
        learnable, injection.codebook, backend=backend, rows=rows or len(learnable), seed=seed, **options
    )
    pristine = result.synthetic_data.convert_dtypes()
    model = fit_missingness_model(incomplete, random_state=seed)
    if model is None:
        raise RuntimeError("the missingness model could not be fitted")
    released, _ = apply_missingness(model, pristine, learnable, disc, cont)
    return pristine, released


DEMO_MECHANISMS = (
    Mechanism("chol", "mar", 0.3, driver="age", strength=2.5),
    Mechanism("bmi", "mnar", 0.25, strength=2.5),
    Mechanism("cigs", "structural", rule="[smoker] == 'yes'"),
    Mechanism("sbp", "coded", 0.05),
)
"""One mechanism of each kind that matters in a clinical table, for the table of :func:`demo_table`."""


def demo_table(n: int = 1500, seed: int = 0) -> pd.DataFrame:
    """A complete table (age, sex, bmi, chol, sbp, smoker, cigs) with relations between its columns, for the benchmark demo."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    age = rng.normal(55, 12, n)
    return pd.DataFrame(
        {
            "age": age,
            "sex": rng.choice(["f", "m"], n),
            "bmi": 24 + 0.05 * (age - 55) + rng.normal(0, 3, n),
            "chol": 180 + 0.8 * age + rng.normal(0, 20, n),
            "sbp": 110 + 0.5 * age + rng.normal(0, 10, n),
            "smoker": rng.choice(["yes", "no"], n, p=[0.3, 0.7]),
            "cigs": rng.poisson(12, n).astype(float),
        }
    )


def mechanisms_from(items: Sequence[dict[str, Any]]) -> list[Mechanism]:
    """The mechanisms of a configuration: one dictionary per mechanism, with the fields of :class:`Mechanism`.

    Raises:
        ValueError: For a mechanism with an unknown ``kind`` or an unknown field.
    """
    found = []
    for item in items:
        try:
            mechanism = Mechanism(**item)
        except TypeError as exc:
            raise ValueError(f"not a mechanism: {item!r} ({exc})") from exc
        if mechanism.kind not in KINDS:
            raise ValueError(f"unknown kind {mechanism.kind!r}; choose one of {', '.join(KINDS)}")
        found.append(mechanism)
    return found


def summary_table(result: dict[str, Any]) -> str:
    """The three variants of a benchmark result in one Markdown table (rows kept, fidelity to the truth, recovery)."""
    import pandas as pd

    rows = []
    for variant in VARIANTS:
        record = result.get(variant) or {}
        scores, fidelity = record.get("summary") or {}, record.get("fidelity_to_truth") or {}
        rows.append(
            {
                "variant": variant,
                "rows kept": record.get("complete_share"),
                "discrete JSD": fidelity.get("disc_jsd_mean"),
                "numeric KS": fidelity.get("cont_ks_mean"),
                "rate gap": scores.get("rate_gap_mean"),
                "gradient gap": scores.get("gradient_gap_mean"),
                "rule violations": scores.get("structural_violation_rate"),
            }
        )
    frame = pd.DataFrame(rows).astype(object).where(lambda f: f.notna(), None)  # a rate of 0 cells is shown as "-"
    return frame.to_markdown(index=False, floatfmt=".3f", missingval="-")
