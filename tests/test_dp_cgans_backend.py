"""The privacy budget of the DP-CGANS backend; skipped where ``dp-cgans`` is not installed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from semsynth.synthesis import synthesize

pytest.importorskip("dp_cgans")


def _table() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({"group": rng.choice(["a", "b"], 100), "x": rng.normal(size=100)})


def test_a_private_run_reports_epsilon_and_delta_and_a_plain_run_does_not() -> None:
    options = {"epochs": 2, "batch_size": 20, "generator_dim": (16, 16), "discriminator_dim": (16, 16)}
    private = synthesize(_table(), None, backend="dp_cgans", rows=20, private=True, **options)
    assert private.privacy_report and private.privacy_report["epsilon"] > 0 and private.privacy_report["delta"] > 0
    plain = synthesize(_table(), None, backend="dp_cgans", rows=20, **options)
    assert plain.privacy_report is None
