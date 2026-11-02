"""Tests covering pipeline flag behaviours and dependency loading."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from semsynth.config import PipelineConfig
from semsynth.models import ModelConfigBundle, ModelRun
from semsynth.runner import PipelineDeps
from semsynth.specs import DatasetSpec


class _DummyUtils:
    """Lightweight stand-in for :mod:`semsynth.utils`."""

    @staticmethod
    def ensure_dir(path: str) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def infer_types(df: pd.DataFrame) -> tuple[list[str], list[str]]:
        cont = list(df.select_dtypes(include=["number"]).columns)
        disc = [c for c in df.columns if c not in cont]
        return disc, cont

    @staticmethod
    def coerce_discrete_to_category(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        return df

    @staticmethod
    def rename_categorical_categories_to_str(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        return df

    @staticmethod
    def coerce_continuous_to_float(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        return df

    @staticmethod
    def seed_all(seed: int) -> np.random.Generator:
        return np.random.default_rng(seed)


class _DummyReporting:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def write_report_md(self, **kwargs) -> None:  # type: ignore[override]
        self.calls.append(kwargs)


@pytest.fixture()
def dummy_utils() -> _DummyUtils:
    return _DummyUtils()


@pytest.fixture()
def dummy_reporting() -> _DummyReporting:
    return _DummyReporting()


def _block_import(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Make ``import semsynth.<name>`` raise, even if the module was imported by an earlier test."""

    import semsynth

    monkeypatch.setitem(sys.modules, f"semsynth.{name}", None)
    monkeypatch.delattr(semsynth, name, raising=False)


def test_process_dataset_skips_umap_when_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_utils: _DummyUtils,
    dummy_reporting: _DummyReporting,
) -> None:
    """Disable UMAP and ensure the heavy module is never imported."""

    import semsynth.runner as runner_module

    # The doubles are injected; umap_utils is deliberately left out of the injected set and
    # `semsynth.umap_utils` is blocked, so any attempt to import it fails the test.
    deps = PipelineDeps(utils=dummy_utils, reporting=dummy_reporting)
    _block_import(monkeypatch, "umap_utils")
    monkeypatch.setattr(runner_module, "resolve_mapping_json", lambda *_: None)
    monkeypatch.setattr(runner_module, "get_uciml_variable_descriptions", lambda *_: {})
    monkeypatch.setattr(runner_module, "discover_model_runs", lambda *_: [])
    monkeypatch.setattr("semsynth.utils.coerce_discrete_to_category", lambda df, cols: df)
    monkeypatch.setattr("semsynth.utils.rename_categorical_categories_to_str", lambda df, cols: df)
    monkeypatch.setattr("semsynth.utils.coerce_continuous_to_float", lambda df, cols: df)

    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    spec = DatasetSpec(provider="openml", name="demo", id=1, target=None)
    cfg = PipelineConfig(generate_umap=False)
    bundle = ModelConfigBundle(specs=[])

    runner_module.process_dataset(
        spec, df, None, str(tmp_path), model_bundle=bundle, pipeline_config=cfg, deps=deps
    )

    assert dummy_reporting.calls, "reporting should still run"


def test_existing_umap_is_respected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_utils: _DummyUtils,
    dummy_reporting: _DummyReporting,
) -> None:
    """Ensure synthetic UMAPs are not regenerated when files already exist."""

    calls: list[tuple[str, str]] = []

    class _Artifacts:
        def __init__(self) -> None:
            self.embedding = np.zeros((2, 2))
            self.color_labels = None

    def fake_build_umap(*_args, **_kwargs) -> _Artifacts:
        return _Artifacts()

    def fake_plot_umap(_embedding, outfile, title, **_kwargs):
        calls.append((outfile, title))
        return ((0.0, 1.0), (0.0, 1.0))

    def fake_transform_with_umap(_art, df: pd.DataFrame) -> np.ndarray:
        return np.zeros((len(df), 2))

    import semsynth.runner as runner_module

    fake_umap_module = SimpleNamespace(
        build_umap=fake_build_umap,
        plot_umap=fake_plot_umap,
        transform_with_umap=fake_transform_with_umap,
    )
    deps = PipelineDeps(utils=dummy_utils, reporting=dummy_reporting, umap_utils=fake_umap_module)
    monkeypatch.setattr(runner_module, "resolve_mapping_json", lambda *_: None)
    monkeypatch.setattr(runner_module, "get_uciml_variable_descriptions", lambda *_: {})
    monkeypatch.setattr("semsynth.utils.coerce_discrete_to_category", lambda df, cols: df)
    monkeypatch.setattr("semsynth.utils.rename_categorical_categories_to_str", lambda df, cols: df)
    monkeypatch.setattr("semsynth.utils.coerce_continuous_to_float", lambda df, cols: df)

    run_dir = tmp_path / "demo" / "models" / "model_a"
    run_dir.mkdir(parents=True, exist_ok=True)
    synth_csv = run_dir / "synthetic.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_csv(synth_csv, index=False)
    existing_png = run_dir / "umap.png"
    existing_png.write_bytes(b"")

    run = ModelRun(
        name="model_a",
        backend="dummy",
        run_dir=run_dir,
        synthetic_csv=synth_csv,
        per_variable_csv=None,
        metrics_json=None,
        metrics={},
        umap_png=existing_png,
        manifest={},
        privacy_json=None,
        privacy_metrics={},
        downstream_json=None,
        downstream_metrics={},
    )

    monkeypatch.setattr("semsynth.runner.discover_model_runs", lambda *_: [run])

    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"], "target": [0, 1, 0]})
    spec = DatasetSpec(provider="openml", name="demo", id=1, target="target")
    bundle = ModelConfigBundle(specs=[])

    runner_module.process_dataset(
        spec, df, None, str(tmp_path), model_bundle=bundle, deps=deps
    )

    assert len(calls) == 1, "only the real-data UMAP should be plotted"


def test_process_dataset_does_not_load_optional_metrics_when_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dummy_utils: _DummyUtils,
    dummy_reporting: _DummyReporting,
) -> None:
    """Avoid loading privacy/downstream dependencies during metadata-only runs."""

    import semsynth.runner as runner_module

    deps = PipelineDeps(utils=dummy_utils, reporting=dummy_reporting)
    _block_import(monkeypatch, "downstream_fidelity")
    _block_import(monkeypatch, "privacy_metrics")
    monkeypatch.setattr(runner_module, "resolve_mapping_json", lambda *_: None)
    monkeypatch.setattr(runner_module, "get_uciml_variable_descriptions", lambda *_: {})
    monkeypatch.setattr(runner_module, "discover_model_runs", lambda *_: [])

    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    spec = DatasetSpec(provider="openml", name="demo", id=1, target=None)
    cfg = PipelineConfig(compute_privacy=False, compute_downstream=False)
    bundle = ModelConfigBundle(specs=[])

    runner_module.process_dataset(
        spec,
        df,
        None,
        str(tmp_path),
        model_bundle=bundle,
        pipeline_config=cfg,
        deps=deps,
    )

    assert dummy_reporting.calls, "reporting should complete for metadata-only runs"
