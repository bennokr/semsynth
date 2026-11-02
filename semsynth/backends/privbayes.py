"""DataSynthesizer PrivBayes backend.

This module owns synthesis and privacy behavior. It does not import LinkedBayes
or emit an editor-specific model. Consumers adapt learned_model from the
returned SynthesisResult.

:func:`synthesize` takes a table; :func:`synthesize_privbayes_csv` takes CSV text and is the entry point that
LinkedBayes imports, so its signature stays as it is.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.metadata
import io
import math
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np

from semsynth.result import SynthesisResult


class SerialPool:
    """Synchronous Pool replacement for runtimes without multiprocessing."""

    def __init__(
        self,
        processes: int | None = None,
        initializer: Callable[..., Any] | None = None,
        initargs: Sequence[Any] = (),
        **_: Any,
    ) -> None:
        self.processes = processes
        if initializer is not None:
            initializer(*initargs)

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        return False

    def map(
        self,
        function: Callable[[Any], Any],
        iterable: Iterable[Any],
        chunksize: int | None = None,
    ) -> list[Any]:
        del chunksize
        return [function(item) for item in iterable]

    def close(self) -> None:
        return None

    def join(self) -> None:
        return None

    def terminate(self) -> None:
        return None


def patch_datasynthesizer_pool() -> Any:
    """Patch DataSynthesizer's module-local Pool binding and return its module."""

    try:
        module = importlib.import_module("DataSynthesizer.lib.PrivBayes")
    except ImportError as exc:
        raise ImportError(
            "The PrivBayes backend needs DataSynthesizer; install it with `pip install 'semsynth[privbayes]'`."
        ) from exc
    module.Pool = SerialPool
    return module


def _validated_bins(column: str, profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    declared = [dict(item) for item in (profile.get("bins") or [])]
    seen: set[str] = set()
    previous_upper: float | None = None
    previous_closed = "left"

    for index, semantic_bin in enumerate(declared):
        identifier = str(semantic_bin.get("id") or f"bin-{index}")
        if identifier in seen:
            raise ValueError(f"Semantic bins for {column!r} repeat id {identifier!r}.")
        seen.add(identifier)
        semantic_bin["id"] = identifier
        semantic_bin.setdefault("label", identifier)

        closed = str(semantic_bin.get("closed", "left"))
        if closed not in {"left", "right", "both", "neither"}:
            raise ValueError(
                f"Semantic bin {identifier!r} for {column!r} has invalid closed={closed!r}."
            )
        semantic_bin["closed"] = closed

        lower_raw, upper_raw = semantic_bin.get("lower"), semantic_bin.get("upper")
        lower = None if lower_raw is None else float(lower_raw)
        upper = None if upper_raw is None else float(upper_raw)
        if lower is not None and not math.isfinite(lower):
            raise ValueError(f"Semantic bin {identifier!r} has a non-finite lower bound.")
        if upper is not None and not math.isfinite(upper):
            raise ValueError(f"Semantic bin {identifier!r} has a non-finite upper bound.")
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"Semantic bin {identifier!r} has lower > upper.")
        if previous_upper is not None and lower is not None:
            overlaps = lower < previous_upper or (
                lower == previous_upper
                and previous_closed in {"right", "both"}
                and closed in {"left", "both"}
            )
            if overlaps:
                raise ValueError(f"Semantic bins for {column!r} overlap at {lower:g}.")
        previous_upper = upper
        previous_closed = closed

    return declared


def _apply_semantic_binning(
    frame: Any, column_semantics: Mapping[str, Mapping[str, Any]]
) -> tuple[Any, dict[str, Any]]:
    """Apply declared meaning as executable preprocessing constraints."""

    actions: dict[str, Any] = {}
    for column, profile in column_semantics.items():
        if column not in frame.columns:
            raise ValueError(f"Column semantics reference unknown column {column!r}.")
        declared = _validated_bins(column, profile)
        if not declared:
            continue

        def classify(
            raw: Any,
            bins: list[dict[str, Any]] = declared,
            column_name: str = column,
        ) -> Any:
            if _is_missing(raw):
                return raw
            value = float(raw)
            for semantic_bin in bins:
                lower, upper = semantic_bin.get("lower"), semantic_bin.get("upper")
                closed = semantic_bin["closed"]
                lower_ok = lower is None or value > float(lower) or (
                    value == float(lower) and closed in {"left", "both"}
                )
                upper_ok = upper is None or value < float(upper) or (
                    value == float(upper) and closed in {"right", "both"}
                )
                if lower_ok and upper_ok:
                    return str(semantic_bin["label"])
            raise ValueError(
                f"Value {value:g} in column {column_name!r} is outside its semantic bins."
            )

        frame[column] = frame[column].map(classify)
        actions[column] = {
            "action": "semantic-binning",
            "bin_ids": [item["id"] for item in declared],
            "unit": profile.get("unit"),
            "provenance": profile.get("provenance") or "user-declared",
        }
    return frame, actions



def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(np.isscalar(value) and np.isnan(value))
    except TypeError:
        return False


def _marginal_tv(original: Any, synthetic: Any, cardinality: int) -> float:
    original_counts = original.value_counts(normalize=True).reindex(
        range(cardinality), fill_value=0.0
    )
    synthetic_counts = synthetic.value_counts(normalize=True).reindex(
        range(cardinality), fill_value=0.0
    )
    return float(
        0.5 * np.abs(original_counts.to_numpy() - synthetic_counts.to_numpy()).sum()
    )


def _network(description: Mapping[str, Any]) -> tuple[str, list[str], dict[str, list[str]]]:
    raw_network = description.get("bayesian_network") or []
    if not raw_network:
        raise ValueError("DataSynthesizer did not produce a Bayesian network.")
    root = str(raw_network[0][1][0])
    order = [root]
    parents: dict[str, list[str]] = {}
    for child_raw, parent_raw in raw_network:
        child = str(child_raw)
        parents[child] = [str(item) for item in parent_raw]
        if child not in order:
            order.append(child)
    return root, order, parents


def _cardinalities(
    description: Mapping[str, Any], root: str, order: Sequence[str]
) -> dict[str, int]:
    conditional = description.get("conditional_probabilities") or {}
    attributes = description.get("attribute_description") or {}
    result: dict[str, int] = {}
    for name in order:
        default = len((attributes.get(name) or {}).get("distribution_probabilities") or [])
        raw = conditional.get(name)
        if name == root and isinstance(raw, Sequence) and not isinstance(
            raw, (str, bytes, dict)
        ):
            result[name] = max(default, len(raw), 1)
        elif isinstance(raw, Mapping) and raw:
            result[name] = max(default, max(len(values) for values in raw.values()), 1)
        else:
            result[name] = max(default, 1)
    return result


_MAX_CSV_BYTES = 5_000_000
_MAX_SYNTHETIC_ROWS = 20_000
_MAX_INPUT_ROWS = 50_000


def _check_options(
    epsilon: float, k: int, rows: int, histogram_bins: int, category_threshold: int
) -> tuple[float, int, int, int, int]:
    """Validate and normalize the numeric settings, with limits that suit an interactive session."""

    epsilon = float(epsilon)
    if not math.isfinite(epsilon) or epsilon < 0:
        raise ValueError("epsilon must be finite and zero or positive.")
    k = int(k)
    if k < 0 or k > 6:
        raise ValueError("k must be between 0 and 6.")
    rows = int(rows)
    if rows < 1 or rows > _MAX_SYNTHETIC_ROWS:
        raise ValueError("synthetic_rows must be between 1 and 20,000.")
    histogram_bins = int(histogram_bins)
    if histogram_bins < 2 or histogram_bins > 100:
        raise ValueError("histogram_bins must be between 2 and 100.")
    category_threshold = int(category_threshold)
    if category_threshold < 2 or category_threshold > 200:
        raise ValueError("category_threshold must be between 2 and 200.")
    return epsilon, k, rows, histogram_bins, category_threshold


def _check_frame(frame: Any, k: int) -> None:
    if frame.shape[0] < 2 or frame.shape[0] > _MAX_INPUT_ROWS:
        raise ValueError("PrivBayes requires between 2 and 50,000 input rows.")
    if frame.shape[1] < 2 or frame.shape[1] > 20:
        raise ValueError("PrivBayes requires between 2 and 20 columns.")
    if k > 0 and k >= frame.shape[1]:
        raise ValueError("k must be smaller than the number of input columns.")


def _semantic_settings(
    semantic_profiles: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, bool]]:
    """The datatype and categorical constraints that declared column semantics imply."""

    datatypes = {
        column: profile["datatype"] for column, profile in semantic_profiles.items() if profile.get("datatype")
    }
    categorical = {
        column: bool(profile.get("categorical", bool(profile.get("bins"))))
        for column, profile in semantic_profiles.items()
    }
    return datatypes, categorical


def _fit_and_generate(
    frame: Any,
    *,
    epsilon: float,
    k: int,
    rows: int,
    seed: int,
    histogram_bins: int,
    category_threshold: int,
    datatypes: Mapping[str, str],
    categorical: Mapping[str, bool],
) -> tuple[Any, Any, str]:
    """Run DataSynthesizer's correlated mode; returns the describer, the generator and the captured log."""

    patch_datasynthesizer_pool()
    from DataSynthesizer.DataDescriber import DataDescriber
    from DataSynthesizer.DataGenerator import DataGenerator

    with tempfile.TemporaryDirectory(prefix="semsynth-privbayes-") as temp_dir:
        input_path = Path(temp_dir) / "input.csv"
        description_path = Path(temp_dir) / "description.json"
        frame.to_csv(input_path, index=False)
        describer = DataDescriber(histogram_bins=histogram_bins, category_threshold=category_threshold)
        generator = DataGenerator()
        log_buffer = io.StringIO()
        with contextlib.redirect_stdout(log_buffer):
            describer.describe_dataset_in_correlated_attribute_mode(
                dataset_file=str(input_path),
                k=k,
                epsilon=epsilon,
                attribute_to_datatype=dict(datatypes),
                attribute_to_is_categorical=dict(categorical),
                seed=seed,
            )
            describer.save_dataset_description_to_file(str(description_path))
            generator.generate_dataset_in_correlated_attribute_mode(rows, str(description_path), seed=seed)
    return describer, generator, log_buffer.getvalue()


def _marginals(describer: Any, generator: Any) -> tuple[dict[str, float], list[str]]:
    """Total variation per column between the encoded real and synthetic data, and the excluded columns."""

    description = describer.data_description
    root, order, _parents = _network(description)
    cards = _cardinalities(description, root, order)
    marginal_tv: dict[str, float] = {}
    if describer.df_encoded is not None and generator.encoded_dataset is not None:
        for attribute in order:
            if attribute in describer.df_encoded and attribute in generator.encoded_dataset:
                marginal_tv[attribute] = _marginal_tv(
                    describer.df_encoded[attribute],
                    generator.encoded_dataset[attribute],
                    cards[attribute],
                )
    excluded = sorted(set(description.get("meta", {}).get("all_attributes", [])) - set(order))
    return marginal_tv, excluded


def synthesize(
    df: Any,
    codebook: Any = None,
    *,
    rows: int | None = None,
    seed: int = 0,
    epsilon: float = 1.0,
    k: int = 1,
    histogram_bins: int = 10,
    category_threshold: int = 20,
    attribute_to_datatype: Mapping[str, str] | None = None,
    attribute_to_is_categorical: Mapping[str, bool] | None = None,
    column_semantics: Mapping[str, Mapping[str, Any]] | None = None,
) -> SynthesisResult:
    """Run correlated-mode PrivBayes on a table and return a neutral synthesis result.

    Args:
        df: The table; between 2 and 50,000 rows and between 2 and 20 columns.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its categorical columns are treated as
            categorical by DataSynthesizer.
        rows: Number of synthetic rows (1 to 20,000); the rows of ``df`` when omitted.
        seed: Random seed.
        epsilon: Privacy budget; ``0`` switches differential privacy off.
        k: Maximum number of parents per node of the Bayesian network.
        histogram_bins: Bins of numeric histograms.
        category_threshold: Columns with fewer distinct values are categorical.
        attribute_to_datatype: DataSynthesizer data types by column.
        attribute_to_is_categorical: Forced categorical flags by column.
        column_semantics: Declared bins, units and types by column; bins are applied before learning.

    Raises:
        ImportError: If DataSynthesizer is missing (extra ``privbayes``).
        ValueError: If a setting or the table is outside the supported limits.
    """

    count = len(df) if rows is None else rows
    epsilon, k, count, histogram_bins, category_threshold = _check_options(
        epsilon, k, count, histogram_bins, category_threshold
    )
    semantic_profiles = dict(column_semantics or {})
    frame, semantic_actions = _apply_semantic_binning(df.copy(), semantic_profiles)
    _check_frame(frame, k)

    semantic_datatypes, semantic_categorical = _semantic_settings(semantic_profiles)
    declared_categorical = (
        {str(c): True for c in frame.columns if codebook.kind(str(c)) == "categorical"}
        if codebook is not None
        else {}
    )
    categorical = {**declared_categorical, **semantic_categorical, **dict(attribute_to_is_categorical or {})}
    describer, generator, log = _fit_and_generate(
        frame,
        epsilon=epsilon,
        k=k,
        rows=count,
        seed=seed,
        histogram_bins=histogram_bins,
        category_threshold=category_threshold,
        datatypes={**semantic_datatypes, **dict(attribute_to_datatype or {})},
        categorical=categorical,
    )
    marginal_tv, excluded = _marginals(describer, generator)

    warnings: list[str] = []
    if epsilon == 0:
        warnings.append("epsilon=0 disables differential privacy in DataSynthesizer.")
    if excluded:
        warnings.append("Excluded from learned network: " + ", ".join(excluded))

    return SynthesisResult(
        synthetic_data=generator.synthetic_dataset,
        backend="privbayes",
        parameters={
            "epsilon": epsilon,
            "k": k,
            "rows": count,
            "synthetic_rows": count,
            "seed": seed,
            "histogram_bins": histogram_bins,
            "category_threshold": category_threshold,
            "input_rows": int(frame.shape[0]),
        },
        metrics={
            "marginal_total_variation": marginal_tv,
            "mean_marginal_total_variation": (
                float(np.mean(list(marginal_tv.values()))) if marginal_tv else None
            ),
        },
        privacy_report={
            "mechanism": "DataSynthesizer correlated mode (PrivBayes)",
            "epsilon": epsilon,
            "network_degree": k,
        },
        provenance={
            "engine": "DataSynthesizer",
            "engine_version": importlib.metadata.version("DataSynthesizer"),
            "log": log,
        },
        learned_model=describer.data_description,
        semantics={
            "column_profiles": semantic_profiles,
            "computational_actions": semantic_actions,
            "datatype_constraints": semantic_datatypes,
            "categorical_constraints": semantic_categorical,
        },
        warnings=warnings,
    )


def synthesize_privbayes_csv(
    csv_text: str,
    *,
    epsilon: float = 1.0,
    k: int = 1,
    synthetic_rows: int = 500,
    seed: int = 0,
    histogram_bins: int = 10,
    category_threshold: int = 20,
    attribute_to_datatype: Mapping[str, str] | None = None,
    attribute_to_is_categorical: Mapping[str, bool] | None = None,
    column_semantics: Mapping[str, Mapping[str, Any]] | None = None,
) -> SynthesisResult:
    """Run correlated-mode PrivBayes on CSV text and return a neutral synthesis result."""

    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError("CSV input is empty.")
    if len(csv_text.encode("utf-8")) > _MAX_CSV_BYTES:
        raise ValueError("CSV input exceeds the 5 MB interactive limit.")
    _check_options(epsilon, k, synthetic_rows, histogram_bins, category_threshold)

    from pandas import read_csv

    frame = read_csv(io.StringIO(csv_text), skipinitialspace=True)
    return synthesize(
        frame,
        rows=synthetic_rows,
        seed=seed,
        epsilon=epsilon,
        k=k,
        histogram_bins=histogram_bins,
        category_threshold=category_threshold,
        attribute_to_datatype=attribute_to_datatype,
        attribute_to_is_categorical=attribute_to_is_categorical,
        column_semantics=column_semantics,
    )


run_privbayes_csv = synthesize_privbayes_csv

__all__ = [
    "SerialPool",
    "patch_datasynthesizer_pool",
    "run_privbayes_csv",
    "synthesize",
    "synthesize_privbayes_csv",
]
