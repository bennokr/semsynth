"""The Flask helper calls the same workflow functions as the command line."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from semsynth import app, workflow


def test_search_form_runs_the_workflow_search(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_search(provider: str, **options: Any) -> pd.DataFrame:
        seen.update(provider=provider, **options)
        return pd.DataFrame({"id": [1], "name": ["Heart"]})

    monkeypatch.setattr(workflow, "search_datasets", fake_search)

    result = app.search({"provider": "uciml", "name_substr": "heart", "cat_min": "2"})

    assert seen == {
        "provider": "uciml",
        "name_substr": "heart",
        "area": "Health and Medicine",
        "cat_min": 2,
        "num_min": 1,
    }
    assert result.output == "id\tname\n1\tHeart\n"


def test_report_form_runs_the_workflow_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_reports(provider: str, **options: Any) -> list[str]:
        seen.update(provider=provider, **options)
        return []

    monkeypatch.setattr(workflow, "run_reports", fake_reports)
    toml = "[[models]]\nname = 'm'\nbackend = 'metasyn'"

    message = app.report({"provider": "uciml", "datasets": "45, 336", "configs_toml": toml}, "out/")

    assert seen["datasets"] == ["45", "336"] and seen["outdir"] == "out/" and seen["pipeline_configs"] == toml
    assert "45, 336" in message and "out/" in message


def test_report_form_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(workflow, "run_reports", lambda *_args, **_kwargs: ["uciml:45: boom"])

    assert "boom" in app.report({"provider": "uciml", "datasets": "45"}, "out/")


@pytest.mark.parametrize("text", ["@/etc/passwd", "/etc/passwd", "configs/simple_config.toml"])
def test_report_form_refuses_file_paths(text: str) -> None:
    with pytest.raises(ValueError, match="inline TOML"):
        app.report({"provider": "uciml", "configs_toml": text}, "out/")


def test_routes_show_workflow_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("flask")

    def refuse(*_args: Any, **_kwargs: Any) -> pd.DataFrame:
        raise ValueError("provider must be 'openml' or 'uciml'")

    monkeypatch.setattr(workflow, "search_datasets", refuse)
    client = app.create_app("out/").test_client()

    assert client.get("/").status_code == 200
    page = client.post("/", data={"action": "search", "provider": "nope"}).get_data(as_text=True)
    assert "provider must be" in page
