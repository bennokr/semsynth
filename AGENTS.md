# SemSynth: notes for coding agents

Synthetic-data generation and evaluation (PrivBayes, MetaSyn, PyBNesian, SynthCity), driven by a
linked-codebook profile; plus the report/catalog site. Target shape: python API + CLI + Pyodide app.

Direction, decisions and status: `SPEC.md`.

## Commands
- Setup: `uv sync --locked --extra dev --extra app --extra privbayes --extra pybnesian --extra metasyn --extra statsmodels --extra language --extra privacy` (NumPy 2; `--extra synthcity` needs NumPy 1 and is installed alone, without `pybnesian`, `umap`, `language`, `privacy` or `all`).
- Check (what CI runs): `uv run make check` = ruff, `mypy --strict` on the core, pytest, statement budgets.
- After shrinking a module: `python scripts/check_size.py --update` (budgets only go down).
- Golden safety net: `tests/test_golden_pipeline.py` runs MetaSyn + missingness + downstream end to end.

## Layout
- `semsynth/`, by job:
  - Data and codebook: `codebook.py` (profile + roles), `structure.py` (declared codes, skip rules, subgroup definitions),
    `preprocess.py`, `dataproviders/`, `mappings/` (curated codebooks).
  - Generate: `backends/` (privbayes, metasyn, pybnesian, synthcity), `missingness.py`, `synthesis.py` (`synthesize` +
    `write_run`, the one backend contract).
  - Evaluate (pure functions): `evaluate.py`, `metrics.py`, `privacy_metrics.py`, `distance.py` (Gower with missing-value
    policies), `joint_fidelity.py`, `downstream_fidelity.py`, `subgroups.py`, `baselines.py` (reference tables),
    `uncertainty.py` (bootstrap for row-level statistics, permutation null for distances), `benchmark.py` (injected truth).
  - Run and report: `runner.py` (`process_dataset`, the part that writes files), `workflow.py` (what the CLI and the app
    call), `browser.py` (entry points for Pyodide), `provenance.py` (run PROV-O and DQV), `reporting.py` + `report_tables.py`,
    `catalog.py` (DCAT and the merged RDF), `iris.py`. makeprov `@rule`s exist only in `__main__.py`.
- The SPARQL page is the data-catalog-sparql-playground, run as a step of the Pages workflow over `output/semsynth.ttl` (the merge
  of the catalog, codebooks and provenance) and `queries/*.rq`. All IRIs come from `semsynth/iris.py`: slugs, one base, no `urn:`.
  Comunica does not deduplicate a triple that two source files both state, which is why the files are merged. The catalog and a run's provenance are plain `.json` with an `@context` (a `.json` file counts as RDF exactly when its top
  level has one, `catalog.is_rdf`); the codebook stays `.jsonld`. Keep queries free of
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
