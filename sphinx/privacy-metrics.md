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

# Privacy metrics

SemSynth summarizes how close a synthetic table is to the real rows it was learned from, independently of the generator. `semsynth.privacy_metrics.summarize_privacy` returns a `PrivacySummary`; the pipeline writes it as `metrics.privacy.json`. Every number is read against a reference: real *holdout* rows that the generator never saw, or a random baseline. A synthetic table that is as close to the training rows as fresh real rows are is not leaking more than the population does; one that is much closer is memorizing.

```{code-cell} python
# Build the privacy metadata frame derived from curated roles/types.
import pandas as pd
from semsynth.codebook import Codebook
from semsynth.utils import infer_types

heart = pd.read_csv("../downloads-cache/uciml/45.csv.gz")
disc, cont = infer_types(heart)
inferred = {c: ("discrete" if c in disc else "continuous") for c in heart.columns}

codebook = Codebook.read("../mappings/uciml-45.metadata.json")
privacy_frame = codebook.privacy_frame(inferred)
privacy_frame.head()
```

## Metric suite
Core (no extra needed):
- All distances are Gower distances (the mean of per-column distances in [0, 1]) with a choice of how a missing value counts: `category` (shared absence agrees), `observed` (classic Gower: columns with a missing value are left out) or `asymmetric` (shared absence is ignored, one-sided absence is a difference), per column if needed. See {doc}`evaluation`. They come with 95% bootstrap intervals (`intervals`).
- `exact_match_rate`: share of synthetic rows identical to a training row, next to `exact_match_rate_holdout` for real holdout rows. With coarse or few columns the holdout rate can be high, which is why it is reported.
- `dcr_synthetic` and `dcr_holdout`: distance to the closest training record (Gower-style, 0 to 1; a missing value is its own category). `dcr_below_holdout_p05` is the share of synthetic rows closer to the training data than the 5th percentile of the holdout rows: about 0.05 for a faithful generator, near 1 for a copy.
- `rare_qi_reproduction_rate`: share of rare real quasi-identifier combinations (at most 5 rows or 1%) that the synthetic table repeats.
- t-closeness per sensitive attribute: Wasserstein-1 for numeric and total variation for categorical columns, between each synthetic quasi-identifier group and the real distribution.

With the `privacy` extra (`sdmetrics`), recorded under `sdmetrics`, 1 is safest:
- `disclosure_protection`: attribute inference from the quasi-identifiers to the sensitive columns, against a random-guess baseline. It needs columns with the roles `qi` and `sensitive`; without them it is not computed.
- `dcr_baseline_protection` and `dcr_overfitting_protection`: distances against random data and against the holdout.

A metric that is requested but cannot run is recorded (`status: skipped` or `failed`, with the reason), not dropped. The scores are evaluated on the complete synthetic table, before the learned missingness is applied.

None of this is a privacy guarantee. Only a differentially private generator (PrivBayes, with its epsilon) gives one.

```{code-cell} python
# Group sizes of the quasi-identifier combinations (the rare ones feed `rare_qi_reproduction_rate`).
qi = list(privacy_frame.loc[privacy_frame.role == "qi", "variable"])
group_sizes = heart[qi].value_counts().head()
group_sizes
```

These counts show how often quasi-identifier combinations appear in the real table.

## References
- sdmetrics privacy metrics: <https://docs.sdv.dev/sdmetrics>
- t-closeness definition: <https://doi.org/10.1109/ICDE.2007.367856>
