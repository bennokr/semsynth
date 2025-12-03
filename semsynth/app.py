"""Minimal Flask application exposing SemSynth search and report actions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from makeprov import rule, GLOBAL_CONFIG

LOGGER = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Structured search output to render in the UI."""

    provider: str
    output: str


def _run_search(
    provider: str,
    name_substr: Optional[str] = None,
    area: str = "Health and Medicine",
    cat_min: int = 1,
    num_min: int = 1,
) -> SearchResult:
    """Execute the search command and capture its text output.

    Args:
        provider: Data provider identifier.
        name_substr: Substring filter for dataset names.
        area: Topic area filter for UCI ML datasets.
        cat_min: Minimum number of categorical columns.
        num_min: Minimum number of numeric columns.

    Returns:
        SearchResult containing the provider and captured TSV output.
    """
    from .datasets import list_openml, list_uciml  # defer heavy imports
    provider_key = provider.lower()
    if provider_key == "openml":
        df = list_openml(name_substr=name_substr, cat_min=cat_min, num_min=num_min)
    elif provider_key == "uciml":
        df = list_uciml(
            area=area,
            name_substr=name_substr,
            cat_min=cat_min,
            num_min=num_min,
        )
    else:
        raise SystemExit("provider must be 'openml' or 'uciml'")
    output_text = df.to_csv(sep="\t", index=None)
    return SearchResult(provider=provider, output=output_text)


def _run_report(
    provider: str,
    datasets: Optional[list[str]] = None,
    configs_yaml: str = "",
    area: str = "Health and Medicine",
    outdir = Path('outputs'),
) -> str:
    """Execute the report command and return a status message.

    Args:
        provider: Dataset provider.
        datasets: Dataset identifiers supplied by the user.
        configs_yaml: Path to a configuration file for models.
        area: Topic area filter for UCI ML datasets.

    Returns:
        Status text summarizing the invocation.
    """
    from .datasets import DatasetSpec, load_dataset, specs_from_input
    from .models import ModelConfigBundle, load_model_configs
    from .pipeline import PipelineConfig, process_dataset
    from .utils import ensure_dir

    outdir_path = Path(outdir)
    ensure_dir(str(outdir_path))
    
    dataset_specs = specs_from_input(provider=provider, datasets=datasets, area=area)
    bundle = load_model_configs(configs_yaml.strip() or None)
    cfg = PipelineConfig()

    for dataset_spec in dataset_specs:
        logging.info("Loading dataset %s", dataset_spec)
        payload = load_dataset(dataset_spec)
        resolved_spec = payload.spec
        dataset_label = resolved_spec.name or str(resolved_spec.id)
        dataset_outdir = outdir_path / str(dataset_label).replace("/", "_")
        GLOBAL_CONFIG.prov_dir = str(dataset_outdir / "prov")
        process_dataset(
            resolved_spec,
            payload.frame,
            payload.color,
            str(outdir_path),
            model_bundle=bundle,
            pipeline_config=cfg,
        )
    dataset_label = ", ".join(datasets) if datasets else "default selection"
    return f"Report launched for {provider} datasets: {dataset_label}."


def create_app() -> Flask:
    """Create and configure the Flask application."""

    from flask import Flask, render_template_string, request # defer

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.route("/", methods=["GET", "POST"])
    def index() -> str:
        search_result: Optional[SearchResult] = None
        status_message: Optional[str] = None

        form_state = request.form if request.method == "POST" else request.args
        if request.method == "POST":
            action = form_state.get("action")
            if action == "search":
                search_result = _run_search(
                    form_state.get("provider", "openml"),
                    name_substr=form_state.get("name_substr") or None,
                    area=form_state.get("area", "Health and Medicine"),
                    cat_min=int(form_state.get("cat_min", 1)),
                    num_min=int(form_state.get("num_min", 1)),
                )
            elif action == "report":
                datasets_text = form_state.get("datasets", "").strip()
                datasets = [value.strip() for value in datasets_text.split(",") if value.strip()]
                status_message = _run_report(
                    form_state.get("provider", "openml"),
                    datasets=datasets or None,
                    configs_yaml=form_state.get("configs_yaml", ""),
                    area=form_state.get("area", "Health and Medicine"),
                )

        return render_template_string(
            """
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
                    <label>Configs YAML <input name="configs_yaml" value="{{ form_state.get('configs_yaml', '') }}"></label>
                    <label>Area <input name="area" value="{{ form_state.get('area', 'Health and Medicine') }}"></label>
                <button type="submit">Run report</button>
                </form>
                {% if status_message %}
                <p>{{ status_message }}</p>
                {% endif %}
            </section>
            """,
            search_result=search_result,
            status_message=status_message,
            form_state=form_state,
        )

    return app

@rule(phony=True)
def run_app(*, host: str = "127.0.0.1", port: int = 5000, debug: bool = False) -> None:
    """Create and run the Flask development server.

    Args:
        host: Host interface for the server.
        port: Port to bind the server to.
        debug: Whether to enable Flask debug mode.
    """

    logging.basicConfig(level=logging.INFO)
    LOGGER.info("Starting SemSynth app on %s:%s (debug=%s)", host, port, debug)
    create_app().run(host=host, port=port, debug=debug)
