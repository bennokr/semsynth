"""Privacy metadata role handling tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pandas as pd

from semsynth.pipeline import MetricWriter
from semsynth.semmap import Column, DatasetSchema, Metadata


@dataclass
class _PrivacyCapture:
    qi: List[str]
    sensitive: List[str]
    used: List[str]


def _capture_privacy(real_df: pd.DataFrame, synth_df: pd.DataFrame, meta_df: pd.DataFrame) -> _PrivacyCapture:
    use_meta = meta_df[~meta_df.role.isin(["ignore", "id"])]
    use_cols = [c for c in use_meta.variable if c in real_df.columns and c in synth_df.columns]
    qi_cols = [c for c in use_meta.loc[use_meta.role == "qi", "variable"] if c in use_cols]
    sensitive_cols = [
        c for c in use_meta.loc[use_meta.role == "sensitive", "variable"] if c in use_cols
    ]
    return _PrivacyCapture(qi=qi_cols, sensitive=sensitive_cols, used=use_cols)


def test_privacy_metadata_uses_roles_and_target(tmp_path):
    real_df = pd.DataFrame(
        {
            "identifier": [1, 2, 3],
            "feature": ["a", "b", "c"],
            "sensitive_attr": ["x", "y", "x"],
            "target": [0, 1, 0],
            "ignore_me": [9, 9, 8],
        }
    )
    inferred = {
        "identifier": "discrete",
        "feature": "discrete",
        "sensitive_attr": "discrete",
        "target": "discrete",
        "ignore_me": "continuous",
    }
    metadata = Metadata(
        datasetSchema=DatasetSchema(
            columns=[
                Column(name="identifier", hadRole="identifier"),
                Column(name="feature", hadRole="predictor"),
                Column(name="sensitive_attr", hadRole="Sensitive"),
                Column(name="target"),
                Column(name="ignore_me", hadRole="ignore"),
            ]
        )
    )
    writer = MetricWriter(privacy_summarizer=_capture_privacy, downstream_compare=None)

    payload = writer.write_privacy(
        tmp_path,
        real_df,
        inferred,
        synth_df=real_df.copy(),
        metadata=metadata,
        target="target",
    )

    assert payload["qi"] == ["feature"]
    assert payload["sensitive"] == ["sensitive_attr"]
    assert "target" not in payload["qi"]
    assert "ignore_me" not in payload["used"]


def test_privacy_metadata_supports_role_overrides(tmp_path):
    real_df = pd.DataFrame(
        {
            "identifier": [1, 2, 3],
            "feature": ["a", "b", "c"],
            "sensitive_attr": ["x", "y", "x"],
            "target": [0, 1, 0],
            "ignore_me": [9, 9, 8],
        }
    )
    inferred = {
        "identifier": "discrete",
        "feature": "discrete",
        "sensitive_attr": "discrete",
        "target": "discrete",
        "ignore_me": "continuous",
    }
    writer = MetricWriter(privacy_summarizer=_capture_privacy, downstream_compare=None)

    payload = writer.write_privacy(
        tmp_path,
        real_df,
        inferred,
        synth_df=real_df.copy(),
        metadata=None,
        role_overrides={
            "identifier": "id",
            "sensitive_attr": "sensitive",
            "ignore_me": "ignore",
        },
        target="target",
    )

    assert payload["qi"] == ["feature"]
    assert payload["sensitive"] == ["sensitive_attr"]
    assert "target" not in payload["qi"]
    assert "ignore_me" not in payload["used"]
