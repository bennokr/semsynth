# SemSynth: notes for coding agents

Synthetic-data generation and evaluation (PrivBayes, MetaSyn, PyBNesian, SynthCity), driven by a
linked-codebook profile; plus the report/catalog site. Target shape: python API + CLI + Pyodide app.

## Commands
- Setup: `uv sync --locked --extra dev --extra app --extra privbayes --extra metasyn --extra statsmodels`
- Check (what CI runs): `uv run make check` = ruff, `mypy --strict` on the core, pytest, statement budgets.
- After shrinking a module: `python scripts/check_size.py --update` (budgets only go down).
- Golden safety net: `tests/test_golden_pipeline.py` runs MetaSyn + missingness + downstream end to end.

## Layout
- `semsynth/`: `codebook.py` (profile + roles), `backends/` (privbayes, metasyn, pybnesian, synthcity), `missingness.py`,
  `metrics.py`, `downstream_fidelity.py`, `synthesis.py` (`synthesize` + `write_run`, the one backend contract),
  `preprocess.py`, `evaluate.py` (pure metrics), `runner.py` (`process_dataset`, the part that writes files),
  `pipeline.py` (re-exports), `workflow.py` (what the CLI and the app call), `reporting.py` + `report_tables.py`,
  `catalog.py`, `dataproviders/`. makeprov `@rule`s exist only in `__main__.py`.
- The catalog page loads YASGUI and Comunica from `../templates/`. They are not in the repository or the wheel:
  `scripts/fetch_site_assets.sh <dir>` downloads them with pinned SHA-256 checks (the Pages workflow runs it).
- `mappings/` curated codebooks; `map_columns/` holds only terminology data (matchers live in entailmap).
- Core modules listed in the `Makefile` (`CORE`) are `mypy --strict`; add a module there when it is clean.

## Hard rules
- No network in tests; build small tables in `tmp_path`. Cached datasets are for manual runs only.
- Do not compress statements to satisfy ruff/complexity limits; split functions. Ruff debt is the `ignore` list in
  `pyproject.toml`; remove entries as modules are fixed, never add new ones.
- A new dependency goes into a named extra, not `dependencies`; keep `import semsynth` and `--help` light: import
  pandas/sklearn/statsmodels/jinja2/requests inside the function that needs them, and raise an `ImportError` that names
  the extra. `tests/test_lazy_imports.py` enforces this by blocking those libraries.
- Check at every commit whether README.md and this file need updating.
- Google-style docstrings, logging, dataclasses.

## Known debt
- Functions over 60 lines remain in `dataproviders/`, `privacy_metrics.py`, `catalog.py`, `metadata.py`, `umap_utils.py`,
  `downstream_fidelity.py`, `utils.py` and in `pybnesian`/`synthcity` `run_experiment` (not split: they cannot be run here).
- `semsynth.pipeline` only re-exports; `MetricWriter` became `evaluate.privacy_scores` / `downstream_scores`. Delete
  the shim when no caller imports `semsynth.pipeline` any more.
- Missing-value policy and type inference heuristics are brittle; reproducibility is partial.
- PyBNesian and SynthCity still implement the file-writing `run_experiment` (`backends/base.py` keeps its contract
  check); their `synthesize` wraps it (`backends/_legacy.py`) and has never run in CI because the engines are not
  installed. Call the engines directly, then delete `ensure_backend_contract` and `_legacy.py`.
- `map_columns/` data (codes.tsv, terminology.db) should become an entailmap release asset.
