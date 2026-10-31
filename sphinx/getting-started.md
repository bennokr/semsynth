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

# Getting started

This guide summarises the minimum commands required to fetch a dataset,
generate semantic mappings, and produce a SemSynth report driven by those
mappings.

## Installation

```bash
python -m pip install -e .
```

Optional extras (UMAP, PyBNesian, SynthCity, etc.) can be layered on top by
supplying the relevant extras group, for example:

```bash
python -m pip install -e .[umap,pybnesian,synthcity]
```

## Create semantic mappings

SemSynth now ships with a dedicated command that orchestrates the full
mapping workflow – metadata parsing, terminology lookup, SSSOM emission, and
codebook enrichment. Pick a strategy with `--method`:

```bash
python -m semsynth create-mapping uciml \
    --datasets 145 \
    --method lexical \
    --codes-tsv map_columns/codes.tsv \
    --manual-overrides-dir map_columns/manual \
    --datasette-url http://127.0.0.1:8001/terminology \
    --lexical-threshold 0.3 \
    --top-k 3 \
    --verbose
```

The command writes `*.sssom.tsv` and `*.metadata.json` artefacts under
`mappings/`. Manual overrides are optional JSON files where each key is a
column identifier pointing to a list of SSSOM-style dictionaries. Alternate
strategies include `--method keyword` (Datasette keyword search),
`--method embed` (sentence-transformer re-ranking), and `--method llm` (LLM +
Datasette). Each honours the flags of `entailmap match --help`. Install the matchers with `pip install "semsynth[mapping]"`.

To rebuild the Wikidata terminology table offline, use the builders in `entailmap.match` (`build_wikidata_medical_codes_table`),
and point `ENTAILMAP_MATCH_DATA` at the directory that holds the result.

## Generate reports

With mappings in place, execute the reporting pipeline. The
`configs/only_metasyn_config.yaml` keeps MetaSyn as the primary backend to ensure
runs complete even without GPU or shared-memory support:

```bash
python -m semsynth report uciml --datasets 145 \
    --configs-yaml configs/only_metasyn_config.yaml \
    --verbose
```

SemSynth merges the curated mappings during preprocessing. Discrete versus
continuous inference now honours the statistical data type hints stored in
the codebook, so integer-coded categoricals remain categorical in the
downstream analysis.

After installation, confirm the cache and curated metadata are available.

```{code-cell} python
# Preview the cached dataset and verify metadata loads cleanly.
import pandas as pd
from semsynth.codebook import Codebook

heart = pd.read_csv("../downloads-cache/uciml/45.csv.gz")
codebook = Codebook.read("../mappings/uciml-45.metadata.json")

heart.head()
```
