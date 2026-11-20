"""One entry point for synthetic data: :func:`synthesize`, and :func:`write_run` for the files.

``synthesize`` fits a backend on a table and returns a :class:`~semsynth.result.SynthesisResult` in memory. It
never touches the disk, so it can run in a browser. ``write_run`` is the only function here that writes files.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from .iris import DEFAULT_BASE
from .provenance import run_provenance
from .result import SynthesisResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)

__all__ = ["BACKENDS", "CAPABILITIES", "Capabilities", "available_backends", "capabilities", "load_backend", "synthesize", "write_run"]

BACKENDS = ("chain", "dp_cgans", "metasyn", "mostlyai", "privbayes", "pybnesian", "synthcity")
"""The built-in backend names; each (``chain`` excepted) is also the name of the extra that installs its engine. ``chain``
has no extra: it uses scikit-learn, which is a core dependency."""

PLUGIN_GROUP = "semsynth.backends"
"""The entry-point group of backends that another package provides (see :func:`load_backend`)."""


@dataclass(frozen=True)
class Capabilities:
    """What a backend can do, so that a configuration or an app can choose one without fitting it first.

    - ``nulls``: The backend accepts a table with blanks without failing (``tests/test_backend_contract.py`` checks it). What it
      does with them differs: MetaSyn and PrivBayes reproduce blanks, while PyBNesian's output has none. The pipeline learns the
      missingness separately (``enable_missingness_wrapping``) and gives complete rows to the other backends.
    - ``categoricals``: Text and low-cardinality columns are learned as categories.
    - ``browser``: The backend runs in Pyodide (no PyTorch, no compiled engine outside Pyodide's packages).
    - ``dp``: The backend has an option that gives a differential-privacy guarantee.
    """

    nulls: bool = False
    categoricals: bool = True
    browser: bool = False
    dp: bool = False


CAPABILITIES: dict[str, Capabilities] = {
    "chain": Capabilities(browser=True),
    "dp_cgans": Capabilities(nulls=True, dp=True),
    "metasyn": Capabilities(nulls=True, browser=True),
    "mostlyai": Capabilities(nulls=True, dp=True),
    "privbayes": Capabilities(nulls=True, browser=True, dp=True),
    "pybnesian": Capabilities(nulls=True),
    "synthcity": Capabilities(dp=True),
}
"""The capabilities of the built-in backends. ``tests/test_backend_contract.py`` checks them against the backends that are
installed."""


def _plugins() -> dict[str, Any]:
    """The entry points of :data:`PLUGIN_GROUP` by name, without importing them."""
    return {entry.name.lower(): entry for entry in importlib.metadata.entry_points(group=PLUGIN_GROUP)}


def available_backends() -> tuple[str, ...]:
    """The built-in backends and the plugins that are installed, by name. Nothing is imported."""
    return tuple(sorted({*BACKENDS, *_plugins()}))


def load_backend(name: str) -> ModuleType:
    """Import the module of a backend.

    A backend is a module (or an object) with a function ``synthesize(df, codebook, *, rows, seed, **options)`` that returns a
    :class:`~semsynth.result.SynthesisResult`, and optionally ``CAPABILITIES`` (a :class:`Capabilities`). The built-in
    backends are in ``semsynth.backends``. Another package provides one with an entry point::

        [project.entry-points."semsynth.backends"]
        mygan = "mypackage.semsynth_backend"   # a module, or ``module:object``

    Args:
        name: One of :data:`BACKENDS`, or the name of an entry point of the group :data:`PLUGIN_GROUP`.

    Raises:
        ValueError: For an unknown name, or a plugin without ``synthesize``.
        ImportError: If the backend cannot be imported; the message names the extra to install.
    """

    key = str(name).strip().lower().replace("-", "_")
    if key in BACKENDS:
        try:
            return importlib.import_module(f"semsynth.backends.{key}")
        except ImportError as exc:
            raise ImportError(
                f"The {key!r} backend could not be imported ({exc}); install it with `pip install 'semsynth[{key}]'`."
            ) from exc
    plugin = _plugins().get(key) or _plugins().get(str(name).strip().lower())
    if plugin is None:
        raise ValueError(f"Unknown backend {name!r}; choose one of {', '.join(available_backends())}.")
    loaded = plugin.load()
    if not callable(getattr(loaded, "synthesize", None)):
        raise ValueError(f"The plugin {plugin.name!r} ({plugin.value}) has no function 'synthesize'.")
    return loaded  # type: ignore[no-any-return]


def capabilities(name: str) -> Capabilities:
    """What a backend can do. A built-in is read from :data:`CAPABILITIES` without importing it; a plugin is loaded and its
    ``CAPABILITIES`` is read (a plugin that declares none can do nothing in particular: all ``False`` except ``categoricals``)."""

    key = str(name).strip().lower().replace("-", "_")
    if key in CAPABILITIES:
        return CAPABILITIES[key]
    declared = getattr(load_backend(name), "CAPABILITIES", None)
    if isinstance(declared, Capabilities):
        return declared
    return Capabilities(**declared) if isinstance(declared, Mapping) else Capabilities()


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    backend: str = "metasyn",
    rows: int | None = None,
    seed: int = 0,
    **options: Any,
) -> SynthesisResult:
    """Fit ``backend`` on ``df`` and draw synthetic rows.

    Args:
        df: The real table.
        codebook: A :class:`~semsynth.codebook.Codebook` (or a document that it can read) that tells which
            columns are categorical and which are numeric; inferred from ``df`` when omitted.
        backend: One of :func:`available_backends`: a built-in (:data:`BACKENDS`) or an installed plugin.
        rows: Number of synthetic rows; the number of rows of ``df`` when omitted.
        seed: Random seed.
        **options: Settings of the backend, such as ``epsilon`` for ``privbayes``.

    Returns:
        The synthetic table, the learned model and what is known about the run, all in memory.
    """

    module = load_backend(backend)
    count = len(df) if rows is None else int(rows)
    if count < 1:
        raise ValueError("rows must be at least 1.")
    if codebook is not None and not hasattr(codebook, "kind"):
        from .codebook import Codebook

        codebook = Codebook.read(codebook)
    started = datetime.now(UTC).isoformat()
    result: SynthesisResult = module.synthesize(df, codebook, rows=count, seed=int(seed), **options)
    result.provenance = {**result.provenance, "started_at": started, "ended_at": datetime.now(UTC).isoformat()}
    return result


def write_run(
    result: SynthesisResult,
    run_dir: str | Path,
    *,
    label: str | None = None,
    dataset: Mapping[str, Any] | None = None,
    codebook_jsonld: Mapping[str, Any] | None = None,
    base_iri: str = DEFAULT_BASE,
    parent_activity: str | None = None,
) -> Path:
    """Write a result as the files of a model run and return the directory.

    Writes ``synthetic.csv`` and, when the pieces exist, ``synthetic.parquet`` (with the codebook in its
    metadata), ``metrics.json``, ``per_variable_metrics.csv`` (``metrics["per_variable"]``),
    ``metrics.privacy.json`` (``metrics["privacy"]``), ``metrics.downstream.json`` (``metrics["downstream"]``),
    ``metasyn_gmf.json``, the result's ``artifacts``, ``manifest.json`` and a PROV-O ``provenance.json``.

    Args:
        result: What :func:`synthesize` returned, possibly with metrics added.
        run_dir: Directory of the run; created if missing.
        label: Name of the run; the backend name when omitted.
        dataset: ``provider``, ``dataset_name`` and ``provider_id`` of the real data, for the manifest.
        codebook_jsonld: DSV JSON-LD to store in the Parquet metadata.
        base_iri: Base of the IRIs in the provenance (see :mod:`semsynth.iris`); ``run_dir`` is expected to be
            ``<base>/<dataset>/models/<model>`` in the folder that the base is served from.
    """

    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    name = label or result.backend
    result.synthetic_data.to_csv(directory / "synthetic.csv", index=False)
    written: list[str] = []
    if codebook_jsonld and _write_parquet(result.synthetic_data, directory / "synthetic.parquet", codebook_jsonld):
        written.append("synthetic.parquet")
    written += _write_metrics(result, directory)
    written += _write_artifacts(result, directory)
    manifest = _manifest(result, name, dataset or {})
    _write_json(directory / "manifest.json", manifest)
    _write_json(
        directory / "provenance.json",
        run_provenance(
            result,
            name,
            dataset or {},
            written,
            directory,
            base_iri=base_iri,
            codebook=bool(codebook_jsonld),
            parent_activity=parent_activity,
        ),
    )
    LOGGER.info("Wrote run %s to %s", name, directory)
    return directory


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _write_parquet(frame: pd.DataFrame, path: Path, codebook_jsonld: Mapping[str, Any]) -> bool:
    """Write the Parquet file with the codebook in its metadata; ``False`` if that failed."""

    try:
        from .codebook import write_parquet

        write_parquet(frame, path, dict(codebook_jsonld))
    except Exception:
        LOGGER.exception("Failed to write Parquet with the codebook")
        return False
    return True


def _write_metrics(result: SynthesisResult, directory: Path) -> list[str]:
    import pandas as pd

    metrics = dict(result.metrics)
    per_variable = metrics.pop("per_variable", None)
    privacy = metrics.pop("privacy", None)
    downstream = metrics.pop("downstream", None)
    sidecars = {name: metrics.pop(name, None) for name in ("joint", "baselines", "subgroups")}
    written = ["metrics.json"]
    _write_json(directory / "metrics.json", {"backend": result.backend, **metrics})
    if per_variable is not None:
        pd.DataFrame(per_variable).to_csv(directory / "per_variable_metrics.csv", index=False)
        written.append("per_variable_metrics.csv")
    if privacy is not None:
        _write_json(directory / "metrics.privacy.json", privacy)
        written.append("metrics.privacy.json")
    if downstream is not None:
        _write_json(directory / "metrics.downstream.json", downstream)
        written.append("metrics.downstream.json")
    for name, payload in sidecars.items():
        if payload is not None:
            _write_json(directory / f"metrics.{name}.json", payload)
            written.append(f"metrics.{name}.json")
    return written


def _write_artifacts(result: SynthesisResult, directory: Path) -> list[str]:
    written: list[str] = []
    if result.backend == "metasyn" and hasattr(result.learned_model, "save"):
        try:
            result.learned_model.save(str(directory / "metasyn_gmf.json"))
            written.append("metasyn_gmf.json")
        except Exception:
            LOGGER.warning("Could not serialize the MetaSyn model", exc_info=True)
    for name, content in result.artifacts.items():
        target = directory / name
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        written.append(name)
    return written


def _manifest(result: SynthesisResult, label: str, dataset: Mapping[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "backend": result.backend,
        "name": label,
        "provider": dataset.get("provider"),
        "dataset_name": dataset.get("dataset_name"),
        "provider_id": dataset.get("provider_id"),
        **result.parameters,
    }
    if result.privacy_report is not None:
        manifest["privacy_report"] = dict(result.privacy_report)
    if result.warnings:
        manifest["warnings"] = list(result.warnings)
    return manifest
