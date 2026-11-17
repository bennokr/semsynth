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
- The CLI commands in `semsynth/__main__.py` are thin wrappers decorated with `@rule`, so makeprov tracks their inputs and outputs. The library (`semsynth.synthesis`, `semsynth.runner`, ...) does not use makeprov rules, which keeps it importable from a notebook or a browser; `ProvenanceConfig.prov_dir` is set per dataset before processing starts.
- Every model run additionally gets a PROV-O `provenance.json` (`semsynth.synthesis.write_run`): the synthesis activity, the dataset and engine it used, the software agent, and the files it generated. The catalog and its SPARQL queries read these files.
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

## Run provenance (`provenance.json`)
Since makeprov 0.7 a script is a `prov:Plan`, not an agent; `semsynth.provenance` writes a run in the same shape: the plan
(semsynth at a version), the runtime (CPython), a qualified association tying them to the activity, the parameters as
`schema:additionalProperty`, start, end and duration, and a sha256 for every file written. The scores are
`dqv:QualityMeasurement` nodes of a `dqv:Metric` with an id and a version (`METRICS_VERSION`). The Data Quality Vocabulary has
no property for uncertainty, so `ss:lowerBound` / `ss:upperBound` (bootstrap interval) and `ss:noiseLower` / `ss:noiseUpper` /
`ss:pValue` (permutation noise floor) are used; the `ss:` namespace is a placeholder. The CLI's own records come from makeprov
with `record_environment` and `stream` on (`prov-config.toml`).
