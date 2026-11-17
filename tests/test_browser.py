"""The browser entry points: JSON-friendly in and out, no files left behind, problems reported before generation."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from semsynth.browser import capabilities, inspect_table, run


def _csv() -> str:
    rng = np.random.default_rng(0)
    n = 300
    smoker = rng.choice(["yes", "no"], n, p=[0.3, 0.7])
    frame = pd.DataFrame(
        {
            "age": rng.normal(55, 10, n).round(),
            "smoker": smoker,
            "cigs": np.where(smoker == "yes", rng.poisson(12, n), 77),
        }
    )
    frame.loc[:5, "cigs"] = 5  # answers to a question that does not apply to non-smokers... for some rows
    return frame.to_csv(index=False)


CODEBOOK = {
    "columns": [
        {"name": "age", "datatype": "integer"},
        {"name": "smoker", "datatype": "string"},
        {"name": "cigs", "datatype": "integer", "applies_when": "[smoker] == 'yes'", "missing_values": ["77"]},
    ]
}


def test_capabilities_is_plain_json_and_names_the_installed_backends() -> None:
    caps = capabilities()
    assert json.loads(json.dumps(caps)) == caps
    assert caps["pyodide"] is False and caps["row_limit"] is None
    assert set(caps["backends"]) == {"metasyn", "privbayes", "pybnesian", "synthcity"}
    assert caps["backends"]["synthcity"] is False  # needs NumPy 1, never in this environment


def test_inspect_reports_codes_rule_breaks_and_subgroup_problems_before_generating() -> None:
    report = inspect_table(
        _csv(), CODEBOOK, [{"name": "older", "condition": "[age] >= 65"}, {"name": "typo", "condition": "[smokr] == 'yes'"}]
    )
    assert report["rows"] == 300 and report["declared_missing"]["cigs"] > 100
    assert report["structural"]["columns"]["cigs"]["answered"] >= 1 and report["incomplete_rows"] > 100
    assert report["subgroups"]["problems"] == ["typo: [smokr] is not a column"] and report["subgroups"]["sizes"] == {}
    ok = inspect_table(_csv(), CODEBOOK, [{"name": "older", "condition": "[age] >= 65"}])
    assert ok["subgroups"]["problems"] == [] and 0 < ok["subgroups"]["sizes"]["older"] < 300
    json.dumps(report)


def test_run_returns_text_files_and_metrics_and_leaves_nothing_behind(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pytest.importorskip("metasyn")
    monkeypatch.chdir(tmp_path)
    result = run(
        _csv(),
        codebook=CODEBOOK,
        target="smoker",
        name="demo",
        config={
            "pipeline": {"compute_privacy": True, "structure_aware": True, "bootstrap_reps": 5},
            "models": [{"name": "metasyn", "backend": "metasyn", "seed": 1}],
        },
    )
    assert "report.md" in result["files"] and "models/metasyn/synthetic.csv" in result["files"]
    assert not any(name.endswith((".png", ".parquet")) for name in result["files"])
    assert result["metrics"]["metasyn"]["metrics.privacy.json"]["n_synth"] > 0
    assert result["metrics"]["metasyn"]["metrics.json"]["structure"]["columns"]["cigs"]["not_applicable"] > 0
    assert list(tmp_path.iterdir()) == [], "everything is written to a temporary folder"
    json.dumps(result)
