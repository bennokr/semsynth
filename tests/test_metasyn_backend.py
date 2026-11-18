"""Unit tests for the MetaSyn backend, with a fake MetaFrame so that the tests do not need MetaSyn."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from semsynth.backends import metasyn as metasyn_backend
from semsynth.synthesis import write_run


class _FakeMetaFrame:
    """Minimal stand-in for :class:`metasyn.metaframe.MetaFrame`."""

    def __init__(self, train_df: pd.DataFrame) -> None:
        self._train_df = train_df

    @classmethod
    def fit_dataframe(cls, train_df: pd.DataFrame, **_options: Any) -> _FakeMetaFrame:
        return cls(train_df)

    def save(self, path: str) -> None:
        Path(path).write_text("{}", encoding="utf-8")

    def synthesize(self, n: int, seed: int | None = None, **_options: Any) -> pd.DataFrame:
        self.seed = seed
        return self._train_df.head(n).copy()


@pytest.fixture()
def fake_metasyn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metasyn_backend, "_load_metasyn", lambda: _FakeMetaFrame)


def test_synthesize_returns_the_frame_with_the_real_dtypes(fake_metasyn: None) -> None:
    df = pd.DataFrame(
        {
            "a": pd.Categorical(["x", "y", "x", "z"], categories=["x", "y", "z", "w"]),
            "b": [0.1, 0.2, 0.3, 0.4],
        }
    )

    result = metasyn_backend.synthesize(df, rows=3, seed=7)

    assert result.backend == "metasyn"
    assert len(result.synthetic_data) == 3
    assert list(result.synthetic_data.columns) == ["a", "b"]
    assert list(result.synthetic_data["a"].cat.categories) == ["x", "y", "z", "w"]
    assert result.parameters["seed"] == 7
    assert result.learned_model.seed == 7


def test_missing_metasyn_names_the_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "metasyn", None)
    monkeypatch.setitem(sys.modules, "metasyn.metaframe", None)

    with pytest.raises(ImportError, match=r"semsynth\[metasyn\]"):
        metasyn_backend._load_metasyn()


def test_write_run_writes_the_files_the_report_reads(tmp_path: Path, fake_metasyn: None) -> None:
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [0.1, 0.2, 0.3, 0.4]})
    dataset = {"provider": "openml", "dataset_name": "demo", "provider_id": 1}

    result = metasyn_backend.synthesize(df, rows=2, seed=7, type="fake")
    run_dir = write_run(result, tmp_path / "models" / "model_a", label="model_a", dataset=dataset, codebook_jsonld=None)

    assert run_dir == tmp_path / "models" / "model_a"
    for name in ("synthetic.csv", "manifest.json", "provenance.json"):
        assert (run_dir / name).exists(), name
    assert len(pd.read_csv(run_dir / "synthetic.csv")) == 2
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["backend"] == "metasyn"
