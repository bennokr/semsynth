"""Unit tests for the pipeline helper classes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from semsynth.codebook import Codebook
from semsynth.config import PipelineConfig
from semsynth.dataproviders._helpers import clean_dataset_frame
from semsynth.dataproviders.openml import load_openml_by_name
from semsynth.dataproviders.uciml import load_uciml_by_id
from semsynth.models import ModelConfigBundle, ModelSpec
from semsynth.preprocess import DatasetPreprocessor, PreprocessingResult, UmapArtifacts
from semsynth.result import SynthesisResult
from semsynth.runner import BackendExecutor, ReportWriter, plot_real_umap
from semsynth.specs import DatasetSpec


class _StubUtils:
    """Small helper mimicking the subset of utils used by the preprocessor."""

    def __init__(self) -> None:
        self._dirs: list[str] = []

    def ensure_dir(self, path: str) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)
        self._dirs.append(path)

    def infer_types(self, df: pd.DataFrame) -> Any:
        discrete: list[str] = []
        continuous: list[str] = []
        for column in df.columns:
            series = df[column]
            if pd.api.types.is_numeric_dtype(series):
                continuous.append(column)
            else:
                discrete.append(column)
        return discrete, continuous

    def coerce_discrete_to_category(self, df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        df = df.copy()
        for column in cols:
            df[column] = pd.Categorical(df[column])
        return df

    def rename_categorical_categories_to_str(
        self, df: pd.DataFrame, cols: list[str]
    ) -> pd.DataFrame:
        return df

    def coerce_continuous_to_float(self, df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        df = df.copy()
        for column in cols:
            df[column] = df[column].astype(float)
        return df

    def seed_all(self, seed: int) -> Any:
        import numpy as np

        return np.random.default_rng(seed)


class _StubUmapModule:
    """Simple module stub recording calls to UMAP helpers."""

    def __init__(self) -> None:
        self.build_calls: list[dict[str, Any]] = []
        self.transform_calls: list[dict[str, Any]] = []
        self.plot_calls: list[dict[str, Any]] = []

    def build_umap(self, *args: Any, **kwargs: Any) -> Any:
        self.build_calls.append({"args": args, "kwargs": kwargs})
        return SimpleNamespace(embedding=[[0.0, 0.0]], color_labels=None)

    def plot_umap(self, embedding: Any, path: str, **kwargs: Any) -> dict[str, float]:
        self.plot_calls.append({"embedding": embedding, "path": path, "kwargs": kwargs})
        Path(path).write_text("png")
        return {"x": 1.0, "y": 2.0}

    def transform_with_umap(self, transformer: Any, df: pd.DataFrame) -> pd.DataFrame:
        self.transform_calls.append({"transformer": transformer, "df": df})
        return pd.DataFrame([[0.0, 0.0]], columns=["x", "y"])


def _create_preprocessing_result(df: pd.DataFrame, tmp_path) -> PreprocessingResult:
    target_series = df["value"].copy()
    target_series.attrs["prov:hadRole"] = "target"
    return PreprocessingResult(
        df_processed=df,
        df_no_na=df,
        df_fit_sample=df,
        disc_cols=["category"],
        cont_cols=["value"],
        inferred_types={"category": "discrete", "value": "continuous"},
        codebook_jsonld={"dummy": True},
        color_series=target_series,
        umap_png_real=None,
        umap_artifacts=UmapArtifacts(transformer=None, real_png=tmp_path / "umap.png", limits=None),
        missingness_model=None,
    )


def test_dataset_preprocessor_basic(tmp_path):
    df = pd.DataFrame({"category": ["a", "b"], "value": [1.0, 2.0]})
    spec = DatasetSpec(provider="demo", name="example", target="value")
    utils_stub = _StubUtils()
    preprocessor = DatasetPreprocessor(
        utils_module=utils_stub,
        load_mapping=lambda path: {},
        resolve_mapping=lambda _: None,
    )
    cfg = PipelineConfig(generate_umap=False)
    rng = utils_stub.seed_all(cfg.random_state)

    result = preprocessor.preprocess(
        spec,
        df,
        None,
        cfg,
        rng,
        generate_umap=False,
        umap_utils=None,
    )

    assert list(result.disc_cols) == ["category"]
    assert list(result.cont_cols) == ["value"]
    assert result.umap_artifacts is None
    assert result.umap_png_real is None
    assert result.df_processed["category"].dtype.name == "category"


def test_dataset_preprocessor_with_umap(tmp_path):
    df = pd.DataFrame({"category": ["a", "b"], "value": [1.0, 2.0]})
    spec = DatasetSpec(provider="demo", name="example", target="value")
    utils_stub = _StubUtils()
    preprocessor = DatasetPreprocessor(
        utils_module=utils_stub,
        load_mapping=lambda path: {},
        resolve_mapping=lambda _: None,
    )
    cfg = PipelineConfig(generate_umap=True)
    rng = utils_stub.seed_all(cfg.random_state)
    umap_stub = _StubUmapModule()

    result = preprocessor.preprocess(
        spec,
        df,
        None,
        cfg,
        rng,
        generate_umap=True,
        umap_utils=umap_stub,
    )

    assert result.umap_artifacts is not None
    assert umap_stub.build_calls, "UMAP build should be invoked"
    assert not umap_stub.plot_calls, "preprocessing does not draw anything"

    plot_real_umap(result, tmp_path, spec, umap_stub, generated=True)

    assert result.umap_png_real == tmp_path / "umap_real.png"
    assert result.umap_artifacts.limits == {"x": 1.0, "y": 2.0}
    assert umap_stub.plot_calls, "UMAP plot should be invoked"


def test_clean_dataset_frame_detects_target_hint():
    df = pd.DataFrame(
        {
            "id": [1, 2],
            "feature": [0.1, 0.2],
            "label": ["a", "b"],
        }
    )
    cleaned, target_name, color_series = clean_dataset_frame(df, target="label")

    assert list(cleaned.columns) == ["feature", "label"]
    assert target_name == "label"
    assert color_series.equals(cleaned["label"])
    assert color_series.attrs.get("prov:hadRole") == "target"


def test_clean_dataset_frame_detects_role_in_metadata():
    df = pd.DataFrame(
        {
            "feature": [0.1, 0.2],
            "class": ["a", "b"],
        }
    )
    metadata = {
        "dsv:datasetSchema": {
            "dsv:column": [
                {"schema:name": "class", "prov:hadRole": "target"},
                {"schema:name": "feature"},
            ]
        }
    }

    _cleaned, target_name, color_series = clean_dataset_frame(
        df, metadata=metadata
    )

    assert target_name == "class"
    assert color_series.attrs.get("prov:hadRole") == "target"


def test_openml_cached_uses_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cache_dir = tmp_path / "openml"
    by_name_dir = cache_dir / "by_name"
    by_name_dir.mkdir(parents=True)
    dataset_name = "demo"
    dataset_id = 123
    meta = {"name": dataset_name, "id": dataset_id, "target": None}
    (by_name_dir / f"{dataset_name}.json").write_text(json.dumps(meta))
    df = pd.DataFrame(
        {
            "id": [1, 2],
            "value": [0.1, 0.2],
            "class": ["a", "b"],
        }
    )
    df.to_csv(cache_dir / f"{dataset_id}.csv.gz", index=False, compression="infer")

    called: dict[str, Any] = {}

    def fake_helper(
        data: pd.DataFrame,
        *,
        target: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        cleaned = data.drop(columns=["id"], errors="ignore")
        series = cleaned["class"].copy()
        called.update(
            {
                "called": True,
                "target": target,
                "metadata": metadata,
                "series_id": id(series),
            }
        )
        return cleaned, "class", series

    monkeypatch.setattr(
        "semsynth.dataproviders.openml.clean_dataset_frame", fake_helper
    )

    payload = load_openml_by_name(dataset_name, cache_dir)

    assert called["called"] is True
    assert called["target"] is None
    assert isinstance(called["metadata"], dict)
    assert "id" not in payload.frame.columns
    assert payload.color is not None
    assert id(payload.color) == called["series_id"]
    assert payload.spec.target == "class"


def test_uciml_cached_uses_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cache_dir = tmp_path
    dataset_id = 456
    meta_path = cache_dir / f"{dataset_id}.meta.json"
    meta_path.write_text(json.dumps({"name": "demo", "target": None}))
    df = pd.DataFrame(
        {
            "index": [0, 1],
            "feature": [1, 2],
            "target": ["x", "y"],
        }
    )
    df.to_csv(cache_dir / f"{dataset_id}.csv.gz", index=False, compression="infer")

    called: dict[str, Any] = {}

    def fake_helper(
        data: pd.DataFrame,
        *,
        target: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        cleaned = data.drop(columns=["index"], errors="ignore")
        series = cleaned["target"].copy()
        called.update(
            {
                "called": True,
                "target": target,
                "metadata": metadata,
                "series_id": id(series),
            }
        )
        return cleaned, "target", series

    monkeypatch.setattr(
        "semsynth.dataproviders.uciml.clean_dataset_frame", fake_helper
    )

    payload = load_uciml_by_id(dataset_id, cache_dir)

    assert called["called"] is True
    assert called["target"] is None
    assert isinstance(called["metadata"], dict)
    assert "index" not in payload.frame.columns
    assert payload.color is not None
    assert id(payload.color) == called["series_id"]
    assert payload.spec.target == "target"


def test_uciml_cached_metadata_becomes_a_codebook(tmp_path: Path):
    dataset_id = 789
    cache_dir = tmp_path / "uciml"
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_path = cache_dir / f"{dataset_id}.meta.json"
    data_path = cache_dir / f"{dataset_id}.csv.gz"

    df = pd.DataFrame({"feature": [1, 2], "target": ["x", "y"]})
    df.to_csv(data_path, index=False, compression="infer")

    dcat_dsv = {
        "dcterms:identifier": dataset_id,
        "dcterms:title": "Demo UCI",
        "dcterms:description": "Example dataset",
        "dcat:landingPage": "https://example.invalid/demo",
        "dcat:distribution": [
            {
                "@type": "dcat:Distribution",
                "dcat:downloadURL": "https://example.invalid/demo.csv",
            }
        ],
        "dsv:summaryStatistics": {
            "dsv:numberOfRows": 2,
            "dsv:numberOfColumns": 2,
        },
        "dsv:datasetSchema": {
            "dsv:column": [
                {
                    "schema:name": "feature",
                    "prov:hadRole": "qi",
                    "dsv:summaryStatistics": {
                        "dsv:statisticalDataType": "dsv:NumericalDataType"
                    },
                },
                {
                    "schema:name": "target",
                    "prov:hadRole": "target",
                    "dsv:summaryStatistics": {
                        "dsv:statisticalDataType": "dsv:CategoricalDataType"
                    },
                },
            ]
        },
    }
    meta_path.write_text(
        json.dumps(
            {
                "id": dataset_id,
                "name": "Demo UCI",
                "target": "target",
                "dcat_dsv": dcat_dsv,
            }
        )
    )

    payload = load_uciml_by_id(dataset_id, cache_dir)

    utils_stub = _StubUtils()
    preprocessor = DatasetPreprocessor(
        utils_module=utils_stub,
        load_mapping=lambda path: {},
        resolve_mapping=lambda _: None,
    )
    cfg = PipelineConfig(generate_umap=False)
    rng = utils_stub.seed_all(cfg.random_state)

    preprocessed = preprocessor.preprocess(
        payload.spec,
        payload.frame,
        payload.color,
        cfg,
        rng,
        generate_umap=False,
        umap_utils=None,
    )

    codebook = preprocessed.codebook
    assert codebook is not None
    assert [column["name"] for column in codebook.columns] == ["feature", "target"]
    assert codebook.roles["target"] == "target"
    assert codebook.kind("target") == "categorical"
    export_columns = preprocessed.codebook_jsonld["datasetSchema"]["columns"]
    assert any(col.get("prov:hadRole") == "target" and col["name"] == "target" for col in export_columns)
    assert preprocessed.codebook_jsonld["title"] == "Demo UCI"
    assert any(
        (
            col.get("dsv:summaryStatistics", {}).get("dsv:statisticalDataType")
            == "dsv:NumericalDataType"
        )
        or (
            col.get("summaryStatistics", {})
            and (
                col["summaryStatistics"].get("statisticalDataType")
                == "dsv:NumericalDataType"
                or col["summaryStatistics"].get("dsv:statisticalDataType")
                == "dsv:NumericalDataType"
            )
        )
        for col in export_columns
        if col.get("schema:name") == "feature" or col.get("name") == "feature"
    )


def test_backend_executor_runs_models(tmp_path):
    df = pd.DataFrame({"category": pd.Categorical(["a", "b"] * 5), "value": [1.0, 2.0, 3.0, 4.0, 5.0] * 2})
    spec = DatasetSpec(provider="demo", name="example", target="value")
    preprocessed = _create_preprocessing_result(df, tmp_path)
    seen: dict[str, Any] = {}

    def fake_synthesize(frame: pd.DataFrame, codebook: Any, *, backend: str, rows: int, seed: int, **options: Any):
        seen.update(frame=frame, codebook=codebook, backend=backend, rows=rows, seed=seed, options=options)
        return SynthesisResult(
            synthetic_data=frame.head(rows).copy(),
            backend=backend,
            parameters={"rows": rows, "seed": seed, "params": options},
        )

    privacy_calls: list[pd.DataFrame] = []

    def summarizer(_real: pd.DataFrame, synth: pd.DataFrame, _meta: pd.DataFrame) -> dict[str, float]:
        privacy_calls.append(synth)
        return {"score": 0.5}

    def comparer(_real: pd.DataFrame, _synth: pd.DataFrame, _meta: Codebook) -> dict[str, Any]:
        return {"formula": "value ~ category", "compare": pd.DataFrame({"sign_match": [1, 1]})}

    bundle = ModelConfigBundle(
        specs=[
            ModelSpec(
                name="demo",
                backend="dummy",
                model={"epsilon": 2.0},
                rows=4,
                seed=3,
                compute_privacy=True,
                compute_downstream=True,
            )
        ]
    )
    executor = BackendExecutor(
        PipelineConfig(compute_privacy=True, compute_downstream=True),
        synthesize_fn=fake_synthesize,
        privacy_summarizer=summarizer,
        downstream_compare=comparer,
    )

    executor.run_models(spec, bundle, preprocessed, tmp_path)

    assert seen["backend"] == "dummy" and seen["rows"] == 4 and seen["seed"] == 3
    assert seen["options"] == {"epsilon": 2.0}
    assert len(seen["frame"]) == 8, "the model is fitted on the training split only"
    run_dir = tmp_path / "models" / "demo"
    assert json.loads((run_dir / "metrics.privacy.json").read_text()) == {"score": 0.5}
    downstream = json.loads((run_dir / "metrics.downstream.json").read_text())
    assert downstream == {"formula": "value ~ category", "sign_match_rate": 1.0}
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics["train_rows"] == 8 and metrics["test_rows"] == 2
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["backend"] == "dummy" and manifest["dataset_name"] == "example"
    assert manifest["test_size"] == 0.2 and manifest["seed"] == 3
    assert (run_dir / "synthetic.csv").exists() and (run_dir / "provenance.json").exists()
    assert (run_dir / "synthetic.parquet").exists() or not preprocessed.codebook_jsonld
    assert len(privacy_calls) == 1


def test_a_failing_model_does_not_stop_the_others(tmp_path):
    df = pd.DataFrame({"category": pd.Categorical(["a", "b"] * 5), "value": [1.0, 2.0, 3.0, 4.0, 5.0] * 2})
    spec = DatasetSpec(provider="demo", name="example", target="value")
    preprocessed = _create_preprocessing_result(df, tmp_path)

    def flaky(frame: pd.DataFrame, codebook: Any, *, backend: str, rows: int, seed: int, **_options: Any):
        if backend == "broken":
            raise ImportError("needs the 'broken' extra")
        return SynthesisResult(synthetic_data=frame.head(rows).copy(), backend=backend, parameters={"seed": seed})

    bundle = ModelConfigBundle(
        specs=[ModelSpec(name="a", backend="broken"), ModelSpec(name="b", backend="fine")]
    )

    BackendExecutor(PipelineConfig(), synthesize_fn=flaky).run_models(spec, bundle, preprocessed, tmp_path)

    assert not (tmp_path / "models" / "a").exists()
    assert (tmp_path / "models" / "b" / "synthetic.csv").exists()


def test_report_writer_generates_outputs(tmp_path):
    df = pd.DataFrame({"category": ["a", "b"], "value": [1.0, 2.0]})
    preprocessed = _create_preprocessing_result(df, tmp_path)
    preprocessed = PreprocessingResult(
        df_processed=preprocessed.df_processed,
        df_no_na=preprocessed.df_no_na,
        df_fit_sample=preprocessed.df_fit_sample,
        disc_cols=preprocessed.disc_cols,
        cont_cols=preprocessed.cont_cols,
        inferred_types=preprocessed.inferred_types,
        codebook_jsonld=preprocessed.codebook_jsonld,
        color_series=None,
        umap_png_real=tmp_path / "umap_real.png",
        umap_artifacts=UmapArtifacts(
            transformer=SimpleNamespace(),
            real_png=tmp_path / "umap_real.png",
            limits={"x": 1.0},
        ),
        missingness_model=None,
    )

    umap_stub = _StubUmapModule()
    run_dir = tmp_path / "models" / "demo"
    run_dir.mkdir(parents=True, exist_ok=True)
    synth_path = run_dir / "synthetic.csv"
    synth_path.write_text("category,value\na,1.0\n")

    run = SimpleNamespace(
        name="demo",
        synthetic_csv=synth_path,
        run_dir=run_dir,
        umap_png=None,
    )

    class ReportingModule:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def write_report_md(self, **kwargs: Any) -> None:
            self.calls.append(kwargs)

    reporting_stub = ReportingModule()

    reporter = ReportWriter(reporting_stub, umap_stub)

    cfg = PipelineConfig()
    reporter.generate_synthetic_umaps([run], DatasetSpec(provider="demo", name="example"), preprocessed, cfg)
    reporter.write_report(
        outdir=tmp_path,
        dataset_spec=DatasetSpec(provider="demo", name="example"),
        preprocessed=preprocessed,
        model_runs=[run],
        inferred_types=preprocessed.inferred_types,
        variable_descriptions={"category": "demo"},
    )

    assert umap_stub.transform_calls, "UMAP transform should be invoked"
    assert umap_stub.plot_calls, "UMAP plot should be invoked"
    assert run.umap_png is not None and run.umap_png.exists()
    assert reporting_stub.calls, "Report should be written"
