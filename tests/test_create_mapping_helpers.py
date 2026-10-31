"""The small helpers that ``create-mapping`` uses to name its files."""

from __future__ import annotations

from pathlib import Path

from semsynth.__main__ import _dataset_slug, _override_file
from semsynth.specs import DatasetSpec


def test_slug_uses_the_id_or_the_slugged_name() -> None:
    assert _dataset_slug(DatasetSpec("uciml", id=336), "Chronic Kidney Disease") == "uciml-336"
    assert _dataset_slug(DatasetSpec("openml", name="Heart Disease"), "Heart Disease!") == "openml-heart-disease"


def test_override_file_prefers_the_slug_and_falls_back_to_provider_and_id(tmp_path: Path) -> None:
    spec = DatasetSpec("uciml", id=45)
    assert _override_file(None, spec, "uciml-45") is None
    assert _override_file(tmp_path, spec, "uciml-45") is None
    (tmp_path / "uciml-45.json").write_text("{}")
    assert _override_file(tmp_path, spec, "uciml-45") == tmp_path / "uciml-45.json"
