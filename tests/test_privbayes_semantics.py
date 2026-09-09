import pandas as pd
import pytest

from semsynth.backends.privbayes import _apply_semantic_binning


def test_semantic_bins_change_backend_input_and_record_action():
    frame = pd.DataFrame({"age": [4, 17, 18, 70]})
    profile = {
        "age": {
            "unit": "year",
            "bins": [
                {"id": "minor", "label": "minor", "lower": 0, "upper": 18},
                {"id": "adult", "label": "adult", "lower": 18, "upper": None},
            ],
        }
    }

    transformed, actions = _apply_semantic_binning(frame, profile)

    assert transformed["age"].tolist() == ["minor", "minor", "adult", "adult"]
    assert actions["age"]["action"] == "semantic-binning"


def test_overlapping_semantic_bins_are_rejected():
    frame = pd.DataFrame({"age": [18]})
    profile = {
        "age": {
            "bins": [
                {"id": "a", "lower": 0, "upper": 20, "closed": "both"},
                {"id": "b", "lower": 20, "upper": 30, "closed": "left"},
            ]
        }
    }

    with pytest.raises(ValueError, match="overlap"):
        _apply_semantic_binning(frame, profile)


def test_privbayes_returns_neutral_result():
    pytest.importorskip("DataSynthesizer")
    from semsynth.backends.privbayes import synthesize_privbayes_csv

    rows = ["region,education,income"]
    for index in range(120):
        region = "north" if index % 3 else "south"
        education = "college" if region == "north" and index % 4 else "school"
        income = "high" if education == "college" else "low"
        rows.append(f"{region},{education},{income}")

    result = synthesize_privbayes_csv(
        "\n".join(rows),
        epsilon=1.0,
        k=1,
        synthetic_rows=40,
        seed=7,
        histogram_bins=5,
    )

    assert result.backend == "privbayes"
    assert result.parameters["input_rows"] == 120
    assert result.synthetic_data.shape == (40, 3)
    assert len(result.learned_model["bayesian_network"]) == 3
    assert set(result.metrics["marginal_total_variation"]) == {
        "region",
        "education",
        "income",
    }
    assert result.privacy_report["epsilon"] == 1.0
