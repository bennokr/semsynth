from __future__ import annotations

import importlib.metadata
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

from ..result import SynthesisResult
from ..utils import (
    coerce_continuous_to_float,
    coerce_discrete_to_category,
    rename_categorical_categories_to_str,
    split_columns,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_ROOTS = ("age", "sex", "race")


@dataclass
class BNArtifacts:
    model: object
    discrete_cols: list[str]
    continuous_cols: list[str]


def _load_pybnesian():
    try:
        from pybnesian import CLGNetworkType, SemiparametricBNType, hc
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "PyBNesian backend requires 'pybnesian'; install with pip install semsynth[pybnesian]"
        ) from exc
    return hc, CLGNetworkType, SemiparametricBNType


def _bn_type_from_str(bn_type: str):
    t = bn_type.lower().strip()
    if t in {"clg", "clgnetwork", "clgnetworktype"}:
        _, CLGNetworkType, _ = _load_pybnesian()
        return CLGNetworkType()
    if t in {
        "semiparametric",
        "semiparametricbn",
        "semiparametricbntype",
        "spbn",
        "semi",
    }:
        _, _, SemiparametricBNType = _load_pybnesian()
        return SemiparametricBNType()
    raise ValueError(
        f"Unsupported bn_type: {bn_type!r}. Supported: 'clg', 'semiparametric'"
    )


def learn_bn(
    train_df,
    bn_type: str = "clg",
    random_state: int = 42,
    arc_blacklist: list[tuple[str, str]] | None = None,
    *,
    score: str | None = None,
    operators: list[str] | None = None,
    max_indegree: int | None = None,
) -> BNArtifacts:
    hc, _, _ = _load_pybnesian()
    bn_type_obj = _bn_type_from_str(bn_type)
    score = score or "bic"
    operators = list(operators) if operators is not None else ["arcs"]
    max_indegree = 5 if max_indegree is None else int(max_indegree)
    model = hc(
        train_df,
        bn_type=bn_type_obj,
        score=score,
        operators=operators,
        max_indegree=max_indegree,
        seed=random_state,
        arc_blacklist=arc_blacklist,
    )
    model.fit(train_df)
    node_types = model.node_types()
    discrete_cols, continuous_cols = [], []
    for node, ftype in node_types.items():
        name = type(ftype).__name__.lower()
        if "discrete" in name:
            discrete_cols.append(node)
        else:
            continuous_cols.append(node)
    return BNArtifacts(
        model=model, discrete_cols=discrete_cols, continuous_cols=continuous_cols
    )


def bn_to_graphviz(
    model, node_types: dict[str, object], out_png: str, title: str = "Learned BN"
) -> None:
    try:
        from graphviz import Digraph
    except Exception:  # pragma: no cover - optional dependency
        logging.warning("graphviz not installed; skipping BN visualization")
        return

    dot = Digraph(comment=title, format="png")
    dot.attr(rankdir="LR")
    for node, ftype in node_types.items():
        tname = type(ftype).__name__
        if "Discrete" in tname:
            shape = "box"
            fillcolor = "#f3d19c"
        else:
            shape = "ellipse"
            fillcolor = "#9cc9f3"
        dot.node(node, label=node, shape=shape, style="filled", fillcolor=fillcolor)
    for u, v in model.arcs():
        dot.edge(u, v)
    dot.render(filename=out_png.replace(".png", ""), cleanup=True)


def save_graphml_structure(
    model, node_types: dict[str, object], out_graphml: str
) -> None:
    try:
        import networkx as nx
    except Exception:  # pragma: no cover - optional dependency
        logging.warning("networkx not installed; skipping GraphML export")
        return

    G = nx.DiGraph()
    for n in model.nodes():
        ftype = node_types[n]
        G.add_node(n, bn_type=type(ftype).__name__)
    for u, v in model.arcs():
        G.add_edge(u, v)
    nx.write_graphml(G, out_graphml)


def _structure_artifacts(model: Any, title: str) -> tuple[dict[str, bytes | str], list[str]]:
    """The GraphML, the picture and the pickle of the learned network; what cannot be made is named in the warnings."""

    artifacts: dict[str, bytes | str] = {}
    warnings: list[str] = []
    node_types = model.node_types()
    with tempfile.TemporaryDirectory(prefix="semsynth-pybnesian-") as directory:
        folder = Path(directory)
        steps = {
            "structure.graphml": lambda: save_graphml_structure(model, node_types, str(folder / "structure.graphml")),
            "structure.png": lambda: bn_to_graphviz(model, node_types, str(folder / "structure.png"), title=title),
            "model.pickle": lambda: model.save(str(folder / "model.pickle")),
        }
        for name, step in steps.items():
            try:
                step()
            except Exception as error:
                warnings.append(f"{name} was not written: {error}")
            if (folder / name).exists():
                artifacts[name] = (folder / name).read_bytes()
    return artifacts, warnings


def _blacklist(columns: list[str], roots: list[str]) -> list[tuple[str, str]]:
    """Arcs that may not be learned: nothing causes the roots (by default age, sex and race)."""

    by_lower = {str(column).lower(): column for column in columns}
    found = [by_lower[root.lower()] for root in roots if root.lower() in by_lower]
    return [(column, root) for root in found for column in columns]


def _version() -> str:
    try:
        return importlib.metadata.version("pybnesian")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - vendored copy
        return "unknown"


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    rows: int | None = None,
    seed: int = 0,
    **options: Any,
) -> SynthesisResult:
    """Learn a Bayesian network from ``df`` and draw ``rows`` rows from it.

    Args:
        df: The table to learn from.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its levels decide which columns are discrete.
        rows: Number of rows to draw; the rows of ``df`` when omitted.
        seed: Random seed.
        **options: ``type`` (``clg`` or ``semiparametric``), ``score``, ``operators``, ``max_indegree`` and ``roots``
            (columns that no other column may cause; default age, sex, race).

    Returns:
        The synthetic table, with ``learned_model`` set to the network and its GraphML, picture and pickle as
        artifacts.
    """

    bn_type = str(options.get("type", "clg"))
    disc_cols, cont_cols = split_columns(df, codebook)
    working = coerce_discrete_to_category(df.copy(), disc_cols)
    working = rename_categorical_categories_to_str(working, disc_cols)
    working = coerce_continuous_to_float(working, cont_cols).reset_index(drop=True)

    LOGGER.info("Learning a %s network on %d rows", bn_type, len(working))
    learned = learn_bn(
        working,
        bn_type=bn_type,
        random_state=seed,
        arc_blacklist=_blacklist(list(working.columns), list(options.get("roots") or DEFAULT_ROOTS)),
        score=options.get("score"),
        operators=options.get("operators"),
        max_indegree=options.get("max_indegree"),
    )
    count = int(rows or len(working))
    synthetic = learned.model.sample(count, seed=seed).to_pandas().reindex(columns=working.columns)  # type: ignore[attr-defined]
    for column in disc_cols:
        synthetic[column] = synthetic[column].astype("category")
    artifacts, warnings = _structure_artifacts(learned.model, f"{bn_type} network")
    return SynthesisResult(
        synthetic_data=synthetic,
        backend="pybnesian",
        parameters={
            "type": bn_type,
            "score": options.get("score"),
            "operators": options.get("operators"),
            "max_indegree": options.get("max_indegree"),
            "rows": count,
            "seed": seed,
        },
        provenance={"engine": "pybnesian", "engine_version": _version()},
        learned_model=learned.model,
        warnings=warnings,
        artifacts=artifacts,
    )
