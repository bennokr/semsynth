"""Minimal Flask application for dataset search and report launching.

It calls the same functions as the command line (:mod:`semsynth.workflow`); Flask is only imported when the app is
created (extra ``app``).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask

LOGGER = logging.getLogger(__name__)

_PAGE = """
<!doctype html>
<title>SemSynth</title>
<h1>SemSynth CLI Helper</h1>
<section>
    <h2>Search</h2>
    <form method="post">
        <input type="hidden" name="action" value="search">
        <label>Provider
            <select name="provider">
                <option value="openml" {% if form_state.get('provider', 'openml') == 'openml' %}selected{% endif %}>OpenML</option>
                <option value="uciml" {% if form_state.get('provider') == 'uciml' %}selected{% endif %}>UCI ML</option>
            </select>
        </label>
        <label>Name contains <input name="name_substr" value="{{ form_state.get('name_substr', '') }}"></label>
        <label>Area <input name="area" value="{{ form_state.get('area', 'Health and Medicine') }}"></label>
        <label>Min categorical <input type="number" name="cat_min" value="{{ form_state.get('cat_min', 1) }}"></label>
        <label>Min numeric <input type="number" name="num_min" value="{{ form_state.get('num_min', 1) }}"></label>
        <button type="submit">Search</button>
    </form>
    {% if search_result %}
    <pre style="white-space: pre-wrap; border: 1px solid #ccc; padding: 1rem;">{{ search_result.output }}</pre>
    {% endif %}
</section>
<section>
    <h2>Report</h2>
    <form method="post">
        <input type="hidden" name="action" value="report">
        <label>Provider
            <select name="provider">
                <option value="openml">OpenML</option>
                <option value="uciml">UCI ML</option>
            </select>
        </label>
        <label>Datasets (comma-separated)<input name="datasets" value="{{ form_state.get('datasets', '') }}"></label>
        <label>Configs (inline TOML) <textarea name="configs_toml">{{ form_state.get('configs_toml', '') }}</textarea></label>
        <label>Area <input name="area" value="{{ form_state.get('area', 'Health and Medicine') }}"></label>
        <button type="submit">Run report</button>
    </form>
    {% if status_message %}
    <p>{{ status_message }}</p>
    {% endif %}
</section>
"""


@dataclass
class SearchResult:
    """Structured search output to render in the UI."""

    provider: str
    output: str


def _inline_toml(text: str) -> str:
    """The configuration text of the form; file paths are refused because the form is reachable over the network."""

    text = text.strip()
    if text.startswith("@") or (text and "=" not in text and "[" not in text):
        raise ValueError("Configs must be inline TOML, not a file path.")
    return text


def search(form: Mapping[str, str]) -> SearchResult:
    """Run :func:`semsynth.workflow.search_datasets` for the search form and render its table as TSV."""

    from .workflow import search_datasets

    provider = form.get("provider", "openml")
    table = search_datasets(
        provider,
        name_substr=form.get("name_substr") or None,
        area=form.get("area", "Health and Medicine"),
        cat_min=int(form.get("cat_min", 1)),
        num_min=int(form.get("num_min", 1)),
    )
    return SearchResult(provider=provider, output=table.to_csv(sep="\t", index=False))


def report(form: Mapping[str, str], outdir: str) -> str:
    """Run :func:`semsynth.workflow.run_reports` for the report form and describe the outcome."""

    from .workflow import run_reports

    provider = form.get("provider", "openml")
    names = [value.strip() for value in form.get("datasets", "").split(",") if value.strip()]
    failures = run_reports(
        provider,
        datasets=names or None,
        outdir=outdir,
        pipeline_configs=_inline_toml(form.get("configs_toml", "")),
        area=form.get("area", "Health and Medicine"),
    )
    label = ", ".join(names) if names else "default selection"
    if failures:
        return f"Report for {provider} datasets {label} failed: {'; '.join(failures)}"
    return f"Report finished for {provider} datasets: {label}, written to {outdir}."


def create_app(outdir: str = "output/") -> Flask:
    """Create and configure the Flask application.

    Args:
        outdir: Directory that the reports are written to.
    """

    from flask import Flask, render_template_string, request

    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST"])
    def index() -> str:
        search_result: SearchResult | None = None
        status_message: str | None = None
        form_state = request.form if request.method == "POST" else request.args
        action = form_state.get("action") if request.method == "POST" else None
        try:
            if action == "search":
                search_result = search(form_state)
            elif action == "report":
                status_message = report(form_state, outdir)
        except (ValueError, ImportError) as exc:
            status_message = str(exc)
        return render_template_string(
            _PAGE, search_result=search_result, status_message=status_message, form_state=form_state
        )

    return app


def run_app(*, host: str = "127.0.0.1", port: int = 5000, debug: bool = False, outdir: str = "output/") -> None:
    """Create and run the Flask development server.

    Args:
        host: Host interface for the server.
        port: Port to bind the server to.
        debug: Whether to enable Flask debug mode.
        outdir: Directory that the reports are written to.
    """

    logging.basicConfig(level=logging.INFO)
    LOGGER.info("Starting SemSynth app on %s:%s (debug=%s)", host, port, debug)
    create_app(outdir).run(host=host, port=port, debug=debug)
