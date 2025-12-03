Use Google-style docstrings, logging and dataclasses.
Maintain a short pyproject.toml with separate dev dependencies.
Check whether AGENTS.md and README.md need updating at every commit.
Maintain a brief repo structure and project intent guardrails in AGENTS.md.

Repo structure guardrails:
- `semsynth/` holds the reporting pipeline, backends, metadata utilities, and CLI entrypoints.
- `map_columns/` contains terminology helpers; use `codes_map_columns.py` + `codes.tsv` for offline Wikidata mappings and keep manual override JSONs alongside datasets.
- `configs/` stores runnable bundles. `maximal_config.yaml` must finish without GPU/shared-memory features, so keep it metasyn-first and ensure optional toggles degrade gracefully.
- Cache roots (`downloads-cache/`, `uciml-cache/`) may include synthetic stand-ins when the original sources are unreachable; document such fallbacks in README when they change.
