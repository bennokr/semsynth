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

# Downstream fidelity

The downstream-fidelity module compares real and synthetic datasets by fitting equivalent predictive models and inspecting how coefficients, directions of effect, and uncertainty translate between them. It automatically derives a modeling formula from metadata, fits the same model on the complete rows of each dataset, and reports side-by-side parameter estimates to highlight agreement or drift. The example below uses the curated codebook (which marks `num` as the target).

```{code-cell} python
# Visualize correlations to motivate downstream modeling choices.
import pandas as pd
import matplotlib.pyplot as plt

heart = pd.read_csv("../downloads-cache/uciml/45.csv.gz")
corr = heart.corr(numeric_only=True)
fig, ax = plt.subplots(figsize=(6, 5))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(corr.columns)))
ax.set_xticklabels(corr.columns, rotation=90)
ax.set_yticks(range(len(corr.index)))
ax.set_yticklabels(corr.index)
ax.set_title("Numeric correlation (Heart Disease)")
fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
plt.tight_layout()
```

## Formula discovery
- `auto_formula` builds a Patsy formula by inferring target roles from the dataset schema, coercing dtypes (including categorical levels from codebooks), and generating main effects plus interaction candidates. Cross-validated feature screening enforces strong heredity, keeping parents of any retained interactions to stabilize the model.

```{code-cell} python
# Create a target-aware formula straight from the codebook.
import json
import sys
from pathlib import Path
from importlib import reload
sys.path.insert(0, str(Path("..").resolve()))
import semsynth.downstream_fidelity as dfid
dfid = reload(dfid)

meta = json.load(open("../mappings/uciml-45.metadata.json"))
formula = dfid.auto_formula(heart, meta, dfid.DownstreamConfig())
formula
```

The curated metadata already declares the `num` diagnosis column as the target, so `auto_formula` discovers the correct prediction task without manual overrides.

## Estimation
- The model is fitted on the rows without missing values: a binomial GLM for a binary target, a multinomial logit for several classes, a Poisson GLM for counts and OLS otherwise. Predictors without variation are dropped first.

## Comparative reporting
- `compute_downstream` sanitizes both datasets, fits the discovered formula on each, and returns the formula and a data frame of paired coefficients and standard errors with a sign-match indicator. When the formula or the fit fails, it returns `compare=None` and a `skipped_reason`. The pipeline calls it for every model run when `compute_downstream` is enabled and writes the share of matching signs to `metrics.downstream.json`.

## References
- Patsy formula language: <https://patsy.readthedocs.io/en/latest/>
- Rubin's rules for multiple imputation: <https://doi.org/10.1002/sim.4067>
- statsmodels MICE implementation: <https://www.statsmodels.org/stable/imputation.html>
