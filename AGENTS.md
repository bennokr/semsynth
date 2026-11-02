# SemSynth: notes for coding agents

Synthetic-data generation and evaluation (PrivBayes, MetaSyn, PyBNesian, SynthCity), driven by a
linked-codebook profile; plus the report/catalog site. Target shape: python API + CLI + Pyodide app.

## Commands
- Setup: `uv sync --locked --extra dev --extra privbayes --extra metasyn --extra statsmodels`
- Check (what CI runs): `uv run make check` = ruff, `mypy --strict` on the core, pytest, statement budgets.
- After shrinking a module: `python scripts/check_size.py --update` (budgets only go down).
- Golden safety net: `tests/test_golden_pipeline.py` runs MetaSyn + missingness + downstream end to end.

## Layout
- `semsynth/`: `codebook.py` (profile + roles), `backends/` (privbayes, metasyn, pybnesian, synthcity), `missingness.py`,
  `metrics.py`, `downstream_fidelity.py`, `synthesis.py` (`synthesize` + `write_run`, the one backend contract),
  `evaluate.py` (pure metrics), `pipeline.py` (being split), `reporting.py`, `catalog.py`, `dataproviders/`.
- `mappings/` curated codebooks; `map_columns/` holds only terminology data (matchers live in entailmap).
- Core modules listed in the `Makefile` (`CORE`) are `mypy --strict`; add a module there when it is clean.

## Hard rules
- No network in tests; build small tables in `tmp_path`. Cached datasets are for manual runs only.
- Do not compress statements to satisfy ruff/complexity limits; split functions. Ruff debt is the `ignore` list in
  `pyproject.toml`; remove entries as modules are fixed, never add new ones.
- A new dependency goes into a named extra, not `dependencies`; keep `import semsynth` light (lazy heavy imports).
- Check at every commit whether README.md and this file need updating.
- Google-style docstrings, logging, dataclasses.

## Known debt
- `pipeline.py` / `reporting.py` do too much (pipeline is being split); global state (`ProvenanceConfig`, backend cache) hinders reuse.
- Missing-value policy and type inference heuristics are brittle; reproducibility is partial.
- PyBNesian and SynthCity still implement the file-writing `run_experiment` (`backends/base.py` keeps its contract
  check); their `synthesize` wraps it (`backends/_legacy.py`) and has never run in CI because the engines are not
  installed. Call the engines directly, then delete `ensure_backend_contract` and `_legacy.py`.
- `map_columns/` data (codes.tsv, terminology.db) should become an entailmap release asset.
