"""Runs inside Pyodide 0.27.x (see pyodide_smoke.cjs): PrivBayes, MetaSyn, missingness and downstream metrics."""

import json
import sys
from pathlib import Path

import micropip
import numpy as np
import pandas as pd

LINGUA_STUB = """
class LanguageDetectorBuilder:
    @staticmethod
    def from_all_languages():
        return LanguageDetectorBuilder()

    def with_low_accuracy_mode(self):
        return self

    def build(self):
        return self

    def detect_language_of(self, text):
        return None
"""
Path("/home/pyodide/lingua.py").write_text(LINGUA_STUB)
sys.path.insert(0, "/home/pyodide")


async def install() -> None:
    await micropip.install(SEMSYNTH_WHEEL, deps=False)  # noqa: F821 - set by pyodide_smoke.cjs
    await micropip.install(LINKED_CODEBOOK_WHEEL)  # noqa: F821
    await micropip.install(["makeprov", "tabulate", "markdown", "DataSynthesizer==0.1.13", "metasyn==3.0.0"])


def table(n: int = 300) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    age = rng.normal(55, 10, n).round()
    chol = 180 + 0.8 * age + rng.normal(0, 20, n)
    smoker = rng.choice(["no", "yes"], n, p=[0.7, 0.3])
    risk = (0.03 * (age - 55) + 0.01 * (chol - 230) + (smoker == "yes") + rng.normal(0, 1, n)) > 0.8
    frame = pd.DataFrame(
        {
            "age": age,
            "sex": rng.choice(["female", "male"], n),
            "chol": chol,
            "smoker": smoker,
            "disease": np.where(risk, "yes", "no"),
        }
    )
    frame.loc[rng.random(n) < 0.1, "chol"] = np.nan
    return frame


async def main() -> dict:
    await install()
    from semsynth.backends.privbayes import synthesize_privbayes_csv

    frame = table()
    result = synthesize_privbayes_csv(
        frame.dropna().to_csv(index=False), epsilon=1.0, seed=1, synthetic_rows=200
    )
    out = {"privbayes_rows": len(result.synthetic_data), "privbayes_columns": list(result.synthetic_data.columns)}

    from semsynth.models import ModelConfigBundle, ModelSpec
    from semsynth.pipeline import PipelineConfig, process_dataset
    from semsynth.specs import DatasetSpec

    spec = DatasetSpec("openml", name="smoke", target="disease")
    bundle = ModelConfigBundle(specs=[ModelSpec(name="metasyn", backend="metasyn", seed=1)])
    config = PipelineConfig(
        generate_umap=False, compute_privacy=False, compute_downstream=True, enable_missingness_wrapping=True
    )
    process_dataset(spec, frame, frame["disease"], Path("/tmp/out"), model_bundle=bundle, pipeline_config=config)
    run = next(Path("/tmp/out/smoke/models").iterdir())
    metrics = json.loads((run / "metrics.json").read_text())
    downstream = json.loads((run / "metrics.downstream.json").read_text())
    out["metasyn_disc_jsd_mean"] = metrics["summary"]["disc_jsd_mean"]
    out["missingness_wrapped"] = metrics["missingness_wrapped"]
    out["sign_match_rate"] = downstream["sign_match_rate"]
    return out


await main()  # noqa: F704
