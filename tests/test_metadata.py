"""Tests for metadata utilities."""

from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

import pandas as pd

dummy_makeprov = types.ModuleType("makeprov")
dummy_makeprov.RDFMixin = object
dummy_makeprov.OutPath = lambda path: path
dummy_makeprov.rule = lambda *_args, **_kwargs: (lambda func: func)
sys.modules.setdefault("makeprov", dummy_makeprov)

from semsynth.metadata import get_uciml_variable_descriptions
from semsynth.pipeline import PreprocessingResult, ReportWriter
from semsynth.specs import DatasetSpec


class DummyReporting:
    """Capture calls made to the reporting module."""

    def __init__(self) -> None:
        self.kwargs = None

    def write_report_md(self, **kwargs):
        self.kwargs = kwargs


def test_get_uciml_variable_descriptions_reads_cache(tmp_path, monkeypatch):
    """Descriptions should come from cached UCI metadata and reach reports."""

    fixture = Path(__file__).parent / "fixtures" / "uciml-cache" / "123.json"
    cache_root = tmp_path / "uciml-cache"
    cache_root.mkdir()
    shutil.copy(fixture, cache_root / "123.json")
    monkeypatch.chdir(tmp_path)

    desc_map = get_uciml_variable_descriptions(123)
    assert desc_map == {
        "feature_a": "Description for feature A",
        "feature_b": "Description for feature B",
    }

    dummy_reporting = DummyReporting()
    writer = ReportWriter(dummy_reporting, umap_utils=None)
    dataset_spec = DatasetSpec(provider="uciml", name="fixture", id=123)
    df = pd.DataFrame({"feature_a": [1], "feature_b": [2]})
    preprocessed = PreprocessingResult(
        df_processed=df,
        df_no_na=df,
        df_fit_sample=df,
        disc_cols=[],
        cont_cols=list(df.columns),
        inferred_types={},
        semmap_export=None,
        semmap_metadata=None,
        color_series=None,
        umap_png_real=None,
        umap_artifacts=None,
        missingness_model=None,
    )

    writer.write_report(
        outdir=tmp_path,
        dataset_spec=dataset_spec,
        preprocessed=preprocessed,
        model_runs=[],
        inferred_types=None,
        variable_descriptions=desc_map,
    )

    assert dummy_reporting.kwargs["variable_descriptions"] == desc_map
