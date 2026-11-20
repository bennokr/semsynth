"""DP-CGANS backend (optional): a conditional GAN that can be trained with differential privacy.

`DP-CGANS <https://github.com/sunchang0124/dp_cgans>`_ (Sun et al., *Generating synthetic personal health data using
conditional generative adversarial networks combining with differential privacy*, J. Biomed. Inform. 2023) is a CTGAN whose
conditional vector and loss emphasize the relations between variables. With ``private=True`` the discriminator is trained with
DP-SGD and the spent privacy budget is reported with Rényi accounting; the backend returns it in ``privacy_report``.

The ontology-informed variant of the package (``Onto_DP_CGAN``) needs ontology embeddings and a column of ICD codes, and is not
wired in here; a package that wraps it can register through the ``semsynth.backends`` entry-point group.

Needs ``pip install 'semsynth[dp_cgans]'``: PyTorch (a CPU build is enough) and NumPy 2. Not for Pyodide. The package depends on
``copulas``, which is licensed under BUSL-1.1.
"""

from __future__ import annotations

import contextlib
import importlib.metadata
import io
import logging
import re
import tempfile
from typing import TYPE_CHECKING, Any

from ..result import SynthesisResult
from ..utils import coerce_continuous_to_float, numbers_back, split_columns

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

LOGGER = logging.getLogger(__name__)
_NUMBER = r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
_BUDGET = re.compile(rf"eps = ({_NUMBER}) and delta = ({_NUMBER})")


def _version() -> str:
    try:
        return importlib.metadata.version("dp-cgans")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _budget(log: str) -> dict[str, Any] | None:
    """The last ``eps = ... and delta = ...`` that the model printed while training, as a privacy report."""
    found = _BUDGET.findall(log)
    if not found:
        return None
    epsilon, delta = found[-1]
    return {"epsilon": float(epsilon), "delta": float(delta), "mechanism": "DP-SGD, Renyi accounting (dp_cgans)"}


def synthesize(
    df: pd.DataFrame,
    codebook: Any = None,
    *,
    rows: int | None = None,
    seed: int = 0,
    epochs: int = 100,
    batch_size: int = 100,
    private: bool = False,
    device: str = "cpu",
    **options: Any,
) -> SynthesisResult:
    """Fit DP-CGANS on ``df`` and draw ``rows`` rows.

    Args:
        df: The table to learn from; rows with missing values are not supported.
        codebook: Optional :class:`~semsynth.codebook.Codebook`; its levels decide which columns are categorical.
        rows: Number of rows to draw; the rows of ``df`` when omitted.
        seed: Random seed (PyTorch and NumPy).
        epochs: Training epochs.
        batch_size: Rows per step; with ``private`` it also sets the sampling rate of the privacy accounting.
        private: Train with differential privacy; the budget is in ``privacy_report``.
        device: ``cpu``, or a PyTorch device such as ``cuda``.
        **options: Further settings of ``dp_cgans.DP_CGAN``, such as ``generator_dim``, ``discriminator_dim``, ``pac`` or
            ``discriminator_steps``.

    Raises:
        ImportError: If ``dp-cgans`` is missing (extra ``dp_cgans``).
    """
    import numpy as np

    try:
        import torch
        from dp_cgans import DP_CGAN
    except ImportError as exc:
        raise ImportError(f"The DP-CGANS backend needs 'dp-cgans'; install it with `pip install 'semsynth[dp_cgans]'` ({exc}).") from exc

    count = int(rows or len(df))
    disc_cols, cont_cols = split_columns(df, codebook)
    working = coerce_continuous_to_float(df.copy(), cont_cols)
    for column in disc_cols:
        working[column] = working[column].astype(str).astype(object)
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = DP_CGAN(epochs=epochs, batch_size=batch_size, private=private, cuda=False if device == "cpu" else device, **options)
    log = io.StringIO()
    # The package writes its loss log and the fitted transformer into the working directory; keep them out of the user's.
    with tempfile.TemporaryDirectory() as scratch, contextlib.chdir(scratch), contextlib.redirect_stdout(log):
        model.fit(working)
        drawn = model.sample(count).reindex(columns=df.columns)
    report = _budget(log.getvalue()) if private else None
    warnings = [] if report or not private else ["DP-CGANS did not report a privacy budget"]
    for column in disc_cols:
        drawn[column] = numbers_back(drawn[column], df[column].dtype)
    return SynthesisResult(
        synthetic_data=coerce_continuous_to_float(drawn, cont_cols),
        backend="dp_cgans",
        parameters={"rows": count, "seed": seed, "epochs": epochs, "batch_size": batch_size, "private": private, "params": dict(options)},
        privacy_report=report,
        provenance={"engine": "dp-cgans", "engine_version": _version()},
        learned_model=model,
        warnings=warnings,
    )
