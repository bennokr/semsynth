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

# Dataset metadata

SemSynth describes each dataset with a [linked-codebook](https://bennokr.github.io/linked-codebook/) profile:
the name, label, description, datatype, level of measurement, unit, value labels, missing codes and concept
mappings of every column. linked-codebook reads and writes the profile as
[DSV](https://w3id.org/dsv-ontology) JSON-LD and as [SSSOM](https://w3id.org/sssom/) TSV.

`semsynth.codebook.Codebook` adds what a codebook does not cover: dataset properties that a profile has no slot
for, such as the DCAT, Dublin Core and schema.org fields that the UCI provider writes. They are kept as they are.
A codebook says nothing about how a column is used. The target is a setting of the dataset, and the columns of a
privacy check are settings of the run.

```{code-cell} python
# The first columns of a curated codebook, with their levels.
from semsynth.codebook import Codebook

codebook = Codebook.read("../mappings/uciml-45.metadata.json")
[(c["name"], c.get("level")) for c in codebook.columns[:5]]
```

## Sources

1. **Providers**: `semsynth/dataproviders/uciml.py` turns UCI metadata into a codebook and writes it as JSON-LD.
2. **Curated files**: `mappings/<provider>-<id>.metadata.json` are codebooks written as JSON-LD. They complete
   the provider metadata; where both describe a column, the curated file wins.
3. **SSSOM**: `semsynth/sssom_codebook.py` adds the mappings of an SSSOM file to the columns.
   linked-codebook writes only approved mappings to JSON-LD, so mappings without a reviewer get the name of the
   file or the matching method as reviewer.
4. **Inference**: during preprocessing, linked-codebook infers the datatype, level and observed codes of every
   column. Declared metadata wins over inference.

## Use in the pipeline

- **Types**: the level decides whether a column is treated as discrete or continuous, so integer-coded
  categoricals stay categorical.
- **Missingness**: `Codebook.set_statistics` sets the number of rows and the completeness of each column, from
  the fitted missingness model when there is one.
- **Privacy metrics**: `Codebook.privacy_frame` gives the target the role `target`, a column named like an
  identifier `id` and every other column `qi`, and maps levels to `numeric` or `categorical`. The pipeline setting
  `sensitive_columns` marks the columns that the attribute-inference check tries to infer.
- **Downstream fidelity**: the target comes from the dataset, every other column is a predictor, and value
  codes become categorical levels.
- **Exports**: each report folder has `dataset.codebook.jsonld` and an RDFa rendering, `dataset.codebook.html`.
  Backends write `synthetic.parquet` with the JSON-LD in the Parquet schema metadata.
