# SemSynth: notes for coding agents

Synthetic-data generation and evaluation (a chain of trees per column, MetaSyn, PrivBayes, PyBNesian, MOSTLY AI, SynthCity,
DP-CGANS), driven by a linked-codebook profile; plus the report/catalog site. Target shape: python API + CLI + Pyodide app.

Direction, decisions and status: `SPEC.md`.

## Commands
- Setup: `uv sync --locked --extra dev --extra app --extra privbayes --extra pybnesian --extra metasyn --extra statsmodels --extra language --extra privacy` (NumPy 2; `--extra synthcity` needs NumPy 1 and is installed alone, without `pybnesian`, `umap`, `language`, `privacy` or `all`).
- Check (what CI runs): `uv run make check` = ruff, `mypy --strict` on the core, pytest, statement budgets.
- After shrinking a module: `python scripts/check_size.py --update` (budgets only go down).
- Site: the reports are built by hand (`make site`) and uploaded to a release; `.github/workflows/pages.yml` pulls them (`scripts/site_bundle.py`, `scripts/check_output.py`; see README "Publishing the site").
- Golden safety net: `tests/test_golden_pipeline.py` runs MetaSyn + missingness + downstream end to end.

## Layout
- `semsynth/`, by job:
  - Data and codebook: `codebook.py` (linked-codebook profile), `structure.py` (declared codes, skip rules, subgroup definitions),
    `preprocess.py`, `dataproviders/`, `mappings/` (curated codebooks).
  - Generate: `backends/` (chain, metasyn, privbayes, pybnesian, synthcity, mostlyai, dp_cgans; others register through the
    `semsynth.backends` entry point; `CAPABILITIES` in `synthesis.py`; `tests/test_backend_contract.py` fits every installed one), `missingness.py`, `synthesis.py` (`synthesize` +
    `write_run`, the one backend contract).
  - Evaluate (pure functions): `evaluate.py`, `metrics.py`, `privacy_metrics.py`, `distance.py` (Gower with missing-value
    policies), `joint_fidelity.py`, `downstream_fidelity.py`, `subgroups.py`, `baselines.py` (reference tables),
    `uncertainty.py` (bootstrap for row-level statistics, permutation null for distances), `crossval.py` (k folds, corrected
    intervals), `utility.py` (train on synthetic, test on real), `benchmark.py` (injected truth; `python -m semsynth benchmark`).
  - Run and report: `model_run.py` (fit one model and score what it draws: tables in, metrics out, no files), `runner.py`
    (`process_dataset`, the part that writes files), `workflow.py` (what the CLI and the app
    call), `browser.py` (entry points for Pyodide), `provenance.py` (run PROV-O and DQV), `reporting.py` + `report_tables.py` + `report_scorecard.py`,
    `catalog.py` (DCAT), `iris.py`. makeprov `@rule`s exist only in `__main__.py`.
- The SPARQL page is the data-catalog-sparql-playground, run as a step of the Pages workflow over the JSON-LD files of `output/` (the
  catalog, codebooks, run provenance and makeprov record, listed in the `data` input) and `queries/*.rq`. All IRIs come from `semsynth/iris.py`: slugs, one base, no `urn:`.
  Comunica does not deduplicate a triple that two source files both state, so the playground merges its sources into one graph; keep the `data` list to RDF files (`tests/test_catalog.py` checks it). The catalog and a run's provenance are plain `.json` with an `@context`; the codebook stays `.jsonld`. Keep queries free of
  string functions (`tests/test_catalog.py` checks) by modelling the link instead.
- `mappings/` curated codebooks; `map_columns/` holds only terminology data (matchers live in entailmap).
- Core modules listed in the `Makefile` (`CORE`) are `mypy --strict`; add a module there when it is clean.

## Hard rules
- No network in tests; build small tables in `tmp_path`. Cached datasets are for manual runs only.
- Do not compress statements to satisfy ruff/complexity limits; split functions. Ruff debt is the `ignore` list in
  `pyproject.toml`; remove entries as modules are fixed, never add new ones.
- linked-codebook's condition evaluator treats pandas `NaN` as a value: pass tables through `structure.as_rows`.
- A new dependency goes into a named extra, not `dependencies`; keep `import semsynth` and `--help` light: import
  pandas/sklearn/statsmodels/jinja2/requests inside the function that needs them, and raise an `ImportError` that names
  the extra. `tests/test_lazy_imports.py` enforces this by blocking those libraries.
- Check at every commit whether README.md and this file need updating.
- Google-style docstrings, logging, dataclasses.

## Known debt
- Functions over 60 lines remain in `dataproviders/`, `catalog.py`, `metadata.py`, `umap_utils.py`,
  `downstream_fidelity.py`, `utils.py`.
- Missing-value policy and type inference heuristics are brittle; reproducibility is partial.
- `map_columns/` data (codes.tsv, terminology.db) should become an entailmap release asset.
