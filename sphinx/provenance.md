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

## SPARQL
The catalog, the codebooks and the run provenance use the same IRIs (`semsynth/iris.py`), so `queries/*.rq` join them without string handling. The Pages workflow builds the explorer at `explore/` from those files with the data-catalog-sparql-playground, which queries them as one graph. See the README.

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
`schema:additionalProperty`, start, end and duration, and a sha256 for every file written. The synthetic dataset
(`<base><dataset>/models/<model>/`) `prov:wasDerivedFrom` the dataset and `prov:wasGeneratedBy` the run, which `prov:used` the
dataset, its codebook and the engine. The scores are `dqv:QualityMeasurement` nodes of a `dqv:Metric` with an id and a version
(`dct:hasVersion`). The Data Quality Vocabulary has no property for uncertainty, and no term of ours is used for it: a bound
of the 95% bootstrap interval, the ends of the noise floor and the p-value are measurements of their own metrics, each
`prov:wasDerivedFrom` the metric of the score and in a `dqv:Dimension` (`lower95`, `upper95`, `noise-lower95`, `noise-upper95`,
`p-value`), so a query can pick them by IRI. The CLI's own records come from makeprov with `record_environment` and `stream` on
(`prov-config.toml`).
