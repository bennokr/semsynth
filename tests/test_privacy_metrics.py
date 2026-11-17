"""Privacy metrics move the right way on the two extremes: a copy of the training data and independent noise."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from semsynth.privacy_metrics import summarize_privacy

META = pd.DataFrame(
    {
        "variable": ["age", "sex", "dx"],
        "role": ["qi", "qi", "sensitive"],
        "type": ["numeric", "categorical", "categorical"],
    }
)


def _real(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    age = rng.normal(50, 12, n)
    sex = rng.choice(["f", "m"], n)
    dx = np.where(age + rng.normal(0, 5, n) > 52, "high", "low")
    return pd.DataFrame({"age": age, "sex": sex, "dx": dx})


@pytest.fixture(scope="module")
def tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    return _real(600, 1), _real(300, 2)


def test_a_copy_of_the_training_data_is_flagged(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, holdout = tables
    summary = summarize_privacy(train, train.copy(), META, holdout)
    assert summary.exact_match_rate == 1.0
    assert summary.exact_match_rate_holdout is not None and summary.exact_match_rate_holdout < 0.1
    assert summary.dcr_synthetic["median"] == 0.0
    assert summary.dcr_below_holdout_p05 is not None and summary.dcr_below_holdout_p05 > 0.9


def test_fresh_draws_look_like_the_holdout(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, holdout = tables
    summary = summarize_privacy(train, _real(300, 3), META, holdout)
    assert summary.exact_match_rate < 0.1
    assert summary.dcr_below_holdout_p05 is not None and summary.dcr_below_holdout_p05 < 0.15
    assert summary.dcr_holdout is not None
    assert abs(summary.dcr_synthetic["median"] - summary.dcr_holdout["median"]) < 0.05


def test_independent_draws_are_no_closer_than_the_holdout(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, holdout = tables
    rng = np.random.default_rng(4)
    independent = pd.DataFrame(
        {
            "age": rng.normal(train.age.mean(), train.age.std(), 300),
            "sex": rng.choice(["f", "m"], 300),
            "dx": rng.choice(["low", "high"], 300),
        }
    )
    summary = summarize_privacy(train, independent, META, holdout)
    assert summary.exact_match_rate < 0.05
    assert summary.dcr_holdout is not None
    assert summary.dcr_synthetic["median"] >= summary.dcr_holdout["median"] - 0.02


def test_missing_values_are_a_category_and_do_not_crash(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, holdout = tables
    synth = _real(100, 5)
    synth.loc[:20, "age"] = np.nan
    synth.loc[10:30, "sex"] = None
    summary = summarize_privacy(train, synth, META, holdout)
    assert 0.0 <= summary.dcr_synthetic["median"] <= 1.0


def test_without_a_holdout_only_the_synthetic_side_is_reported(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    train, _ = tables
    summary = summarize_privacy(train, _real(100, 6), META)
    assert summary.dcr_holdout is None and summary.dcr_below_holdout_p05 is None
    assert summary.exact_match_rate_holdout is None


def test_sdmetrics_scores_are_recorded_when_installed(tables: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    pytest.importorskip("sdmetrics")
    train, holdout = tables
    block = summarize_privacy(train, _real(300, 7), META, holdout).sdmetrics
    assert {"dcr_baseline_protection", "dcr_overfitting_protection", "disclosure_protection"} <= set(block)
    assert all(entry["status"] == "ok" for entry in block.values()), block
    json.dumps(block)


def test_a_missing_extra_is_recorded_not_silent(
    tables: tuple[pd.DataFrame, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "sdmetrics", None)
    monkeypatch.setitem(sys.modules, "sdmetrics.single_table", None)
    train, holdout = tables
    block = summarize_privacy(train, _real(50, 8), META, holdout).sdmetrics
    assert block["status"] == "skipped" and "semsynth[privacy]" in block["reason"]


def test_the_pipeline_writes_privacy_metrics(tmp_path: Path) -> None:
    pytest.importorskip("metasyn")
    from semsynth.config import PipelineConfig
    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.runner import process_dataset
    from semsynth.specs import DatasetSpec

    frame = _real(400, 9)
    frame["disease"] = frame["dx"]
    spec = DatasetSpec("openml", name="priv", target="disease")
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
    config = PipelineConfig(
        generate_umap=False, compute_privacy=True, compute_downstream=False, enable_missingness_wrapping=False
    )
    process_dataset(spec, frame, frame["disease"], tmp_path, model_bundle=bundle, pipeline_config=config)
    run = next((tmp_path / "priv" / "models").iterdir())
    privacy = json.loads((run / "metrics.privacy.json").read_text())
    assert privacy.get("status", "ok") == "ok", privacy
    assert privacy["n_holdout"] > 0 and 0.0 <= privacy["exact_match_rate"] <= 1.0
