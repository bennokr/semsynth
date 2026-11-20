"""Every bundle in configs/ parses, and every model in it names a backend that exists."""

from __future__ import annotations

from pathlib import Path

import pytest

from semsynth.models import load_model_configs
from semsynth.synthesis import BACKENDS

CONFIGS = sorted((Path(__file__).resolve().parent.parent / "configs").glob("*.toml"))


def test_there_are_configs() -> None:
    assert {path.stem for path in CONFIGS} >= {"minimal_config", "simple_config", "demo_config", "full_config", "synthcity_config"}


@pytest.mark.parametrize("path", CONFIGS, ids=lambda path: path.stem)
def test_a_bundle_parses_and_its_models_have_a_backend_and_a_unique_name(path: Path) -> None:
    bundle = load_model_configs(path.read_text(encoding="utf-8"))
    names = [spec.name for spec in bundle.specs]
    assert len(names) == len(set(names))
    assert all(spec.backend in BACKENDS for spec in bundle.specs), [spec.backend for spec in bundle.specs]
