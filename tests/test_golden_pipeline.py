"""End-to-end safety net: the report pipeline with MetaSyn, missingness and downstream metrics.

It runs the whole path on a small simulated table (no network) and checks the structure and the
orders of magnitude of the outputs, so that refactoring cannot silently disable a stage.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("metasyn")
pytest.importorskip("statsmodels")


def _table(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    age = rng.normal(55, 10, n).round()
    sex = rng.choice(["female", "male"], n)
    chol = 180 + 0.8 * age + rng.normal(0, 20, n)
    smoker = rng.choice(["no", "yes"], n, p=[0.7, 0.3])
    risk = (0.03 * (age - 55) + 0.01 * (chol - 230) + (smoker == "yes") + rng.normal(0, 1, n)) > 0.8
    frame = pd.DataFrame(
        {"age": age, "sex": sex, "chol": chol, "smoker": smoker, "disease": np.where(risk, "yes", "no")}
    )
    frame.loc[rng.random(n) < 0.1, "chol"] = np.nan
    return frame


def test_report_pipeline_runs_every_stage(tmp_path: Path) -> None:
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.pipeline import PipelineConfig, process_dataset
    from semsynth.specs import DatasetSpec

    frame = _table()
    spec = DatasetSpec("openml", name="golden", target="disease")
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
    config = PipelineConfig(
        generate_umap=False, compute_privacy=False, compute_downstream=True, enable_missingness_wrapping=True
    )

    process_dataset(spec, frame, frame["disease"], tmp_path, model_bundle=bundle, pipeline_config=config)

    run = next((tmp_path / "golden" / "models").iterdir())
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["missingness_wrapped"] is True
    assert metrics["summary"]["disc_jsd_mean"] < 0.3
    downstream = json.loads((run / "metrics.downstream.json").read_text())
    assert downstream["formula"].startswith("disease ~")
    assert 0.0 <= downstream["sign_match_rate"] <= 1.0
    synthetic = pd.read_csv(run / "synthetic.csv")
    assert list(synthetic.columns) == list(frame.columns)
    assert synthetic["chol"].isna().any()
    assert (tmp_path / "golden" / "report.md").exists()
