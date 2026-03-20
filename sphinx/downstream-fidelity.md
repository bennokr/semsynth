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

The downstream-fidelity module compares real and synthetic datasets by fitting equivalent predictive models and inspecting how coefficients, directions of effect, and uncertainty translate between them. It automatically derives a modeling formula from metadata, performs multiple imputation for missing data, and reports side-by-side parameter estimates to highlight agreement or drift. The example below promotes `num` to the target role for demonstration because the curated metadata omits an explicit target.

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
# Create a target-aware formula (the curated metadata doesn't mark one).
import json
from semsynth.semmap import Metadata
from semsynth.utils import infer_types
from semsynth.downstream_fidelity import auto_formula

disc, cont = infer_types(heart)
inferred = {c: ("discrete" if c in disc else "continuous") for c in heart.columns}
meta = Metadata.from_dcat_dsv(json.load(open("../mappings/uciml-45.metadata.json")))

# Explicitly mark the diagnosis column as the target for this demo.
for col in meta.datasetSchema.columns:
    if col.name == "num":
        col.hadRole = "target"
    else:
        col.hadRole = col.hadRole or "qi"

privacy_frame = meta.to_privacy_frame(inferred)
privacy_frame.loc[privacy_frame.variable == "num", "role"] = "target"
privacy_frame.loc[privacy_frame.role.isna(), "role"] = "qi"

# Pass the enriched SemMap JSON-LD (with roles set) to auto_formula
formula = auto_formula(heart, meta.to_jsonld())
formula
```

This small role override mirrors what the pipeline would do when a target is declared in curated SemMap metadata, so the resulting formula reflects the intended prediction task.

## Multiple imputation and estimation
- `fit_with_mi` recodes categorical variables, replaces missing codes, and runs MICE (`statsmodels.imputation.mice`) to produce pooled estimates for generalized linear models appropriate to the target type (binomial, Poisson, or OLS).

## Comparative reporting
- `compare_real_vs_synth` sanitizes the inputs, fits the auto-discovered model with multiple imputation on real and synthetic data, and returns a dataframe of paired coefficients and standard errors with a sign-match indicator. When model fitting fails, it falls back to a simpler logistic comparison but still surfaces the skipped reason to the caller.

## References
- Patsy formula language: <https://patsy.readthedocs.io/en/latest/>
- Rubin's rules for multiple imputation: <https://doi.org/10.1002/sim.4067>
- statsmodels MICE implementation: <https://www.statsmodels.org/stable/imputation.html>
