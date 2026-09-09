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
