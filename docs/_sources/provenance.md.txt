---
filetype: mystnb
jupytext:
  text_representation:
    extension: .md
    format_name: myst
    format_version: 0.13
    jupytext_version: 1.16.3
kernelspec:
  name: python3
  display_name: Python 3
---

# Provenance

SemSynth writes provenance for every report run using `makeprov`. For each dataset, files land under `output/<dataset>/prov/` and capture inputs, outputs, and processing steps.

```{code-cell} python
# Peek at the generated provenance files for Heart Disease
from pathlib import Path
prov_dir = Path("../output/Heart Disease/prov")
sorted(p.name for p in prov_dir.glob("*") if p.is_file())[:5]
```

## How it is wired
- `search` and `report` CLI commands in `semsynth/__main__.py` are decorated with `@rule(merge=True)`, so makeprov tracks their inputs/outputs automatically.
- The reporting pipeline (`semsynth/pipeline.py`) marks major artifacts (UMAPs, metrics, reports) as provenance outputs, and `ProvenanceConfig.prov_dir` is set per dataset before processing starts.
- Default settings live in `prov-config.toml` (base IRI and output directory). You can override them via CLI flags or config.

## Browser catalog
The generated `output/index.html` includes a SPARQL/YASGUI panel wired to the static catalog and provenance files. Open it in a browser to explore datasets, mappings, and provenance artifacts without running a server.

## Handy commands
- Regenerate a missing file: `python -m semsynth --build output/<dataset>/index.html`
- Inspect the DAG without executing: `python -m semsynth --conf @prov-config.toml --dry-run output/<dataset>/index.html`

## Reference links
- [makeprov README](https://github.com/bennokr/makeprov#readme)
- [makeprov SHACL shapes](https://raw.githubusercontent.com/bennokr/makeprov/refs/heads/main/tests/prov_shapes.ttl)
- [PROV-O primer](https://www.w3.org/TR/prov-o/)
