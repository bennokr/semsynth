"""The synthesis entry point, the file writer and the adapter around file-based backends."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from semsynth.backends._legacy import synthesize_via_run_experiment
from semsynth.codebook import Codebook
from semsynth.result import SynthesisResult
from semsynth.synthesis import load_backend, synthesize, write_run


def _table(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    region = rng.choice(["north", "south"], n)
    return pd.DataFrame(
        {
            "region": region,
            "education": np.where((region == "north") & (rng.random(n) < 0.8), "college", "school"),
            "age": rng.integers(18, 80, n).astype(float),
        }
    )


def test_unknown_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown backend"):
        load_backend("nope")


def test_rows_must_be_positive() -> None:
    with pytest.raises(ValueError, match="rows"):
        synthesize(_table(), backend="metasyn", rows=0)


def test_metasyn_makes_dummy_data_from_a_table_and_a_codebook() -> None:
    pytest.importorskip("metasyn")
    frame = _table()
    codebook = Codebook.from_frame(frame)

    first = synthesize(frame, codebook, backend="metasyn", rows=50, seed=4)
    second = synthesize(frame, codebook, backend="metasyn", rows=50, seed=4)

    assert isinstance(first, SynthesisResult)
    assert first.synthetic_data.shape == (50, 3)
    assert list(first.synthetic_data.columns) == list(frame.columns)
    assert set(first.synthetic_data["region"].astype(str)) <= {"north", "south"}
    assert first.synthetic_data.equals(second.synthetic_data)


def test_privbayes_synthesizes_a_table() -> None:
    pytest.importorskip("DataSynthesizer")

    result = synthesize(_table(), backend="privbayes", rows=30, seed=1, epsilon=1.0, k=1, histogram_bins=5)

    assert result.backend == "privbayes"
    assert result.synthetic_data.shape == (30, 3)
    assert result.parameters["rows"] == 30
    assert result.privacy_report is not None and result.privacy_report["epsilon"] == 1.0


def test_privbayes_limits_are_checked_before_the_engine_is_needed() -> None:
    with pytest.raises(ValueError, match="epsilon"):
        synthesize(_table(), backend="privbayes", epsilon=-1)


def test_write_run_writes_the_files_of_a_run(tmp_path: Path) -> None:
    result = SynthesisResult(
        synthetic_data=pd.DataFrame({"x": [1, 2]}),
        backend="example",
        parameters={"seed": 3, "rows": 2, "params": {"a": 1}, "test_size": 0.2},
        metrics={
            "summary": {"disc_jsd_mean": 0.1},
            "per_variable": [{"variable": "x", "type": "continuous", "KS": 0.1}],
            "privacy": {"k_min": 5},
            "downstream": {"sign_match_rate": 1.0},
        },
        privacy_report={"epsilon": 1.0},
        provenance={"engine": "example", "engine_version": "1"},
        artifacts={"extra.txt": "hello", "extra.bin": b"\x00"},
        warnings=["careful"],
    )

    run_dir = write_run(
        result,
        tmp_path / "models" / "a",
        label="a",
        dataset={"provider": "openml", "dataset_name": "demo", "provider_id": None},
    )

    names = {path.name for path in run_dir.iterdir()}
    assert names == {
        "synthetic.csv",
        "metrics.json",
        "per_variable_metrics.csv",
        "metrics.privacy.json",
        "metrics.downstream.json",
        "extra.txt",
        "extra.bin",
        "manifest.json",
        "provenance.json",
    }
    metrics = json.loads((run_dir / "metrics.json").read_text())
    assert metrics == {"backend": "example", "summary": {"disc_jsd_mean": 0.1}}
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["name"] == "a" and manifest["dataset_name"] == "demo" and manifest["seed"] == 3
    assert manifest["privacy_report"] == {"epsilon": 1.0} and manifest["warnings"] == ["careful"]
    provenance = json.loads((run_dir / "provenance.json").read_text())
    kinds = {node["@id"]: node["@type"] for node in provenance["@graph"]}
    assert "prov:Activity" in kinds.values()
    generated = [n for n in provenance["@graph"] if n.get("prov:wasGeneratedBy")]
    assert {n["dcterms:title"] for n in generated} >= {"synthetic.csv", "metrics.json", "extra.txt"}


def test_adapter_reads_back_what_a_file_based_backend_wrote() -> None:
    seen: dict[str, Any] = {}

    def run_experiment(*, df: pd.DataFrame, outdir: str, label: str, model_info: dict, rows: int, seed: int,
                       test_size: float, **_kwargs: Any) -> Path:
        seen.update(model_info=model_info, rows=rows, seed=seed, test_size=test_size)
        run_dir = Path(outdir) / "models" / label
        run_dir.mkdir(parents=True)
        df.head(rows).to_csv(run_dir / "synthetic.csv", index=False)
        (run_dir / "metrics.json").write_text(json.dumps({"backend": "fake", "heldout_loglik": {"mean_loglik": -1.0}}))
        (run_dir / "manifest.json").write_text(json.dumps({"backend": "fake", "name": label, "type": "clg", "seed": seed}))
        (run_dir / "structure.graphml").write_text("<graphml/>")
        return run_dir

    result = synthesize_via_run_experiment(
        run_experiment, "fake", _table(), rows=5, seed=9, options={"type": "clg", "test_size": 0.3}
    )

    assert seen == {"model_info": {"type": "clg"}, "rows": 5, "seed": 9, "test_size": 0.3}
    assert len(result.synthetic_data) == 5
    assert result.metrics == {"heldout_loglik": {"mean_loglik": -1.0}}
    assert result.parameters == {"type": "clg", "seed": 9}
    assert result.artifacts == {"structure.graphml": b"<graphml/>"}
