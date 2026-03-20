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

SemSynth summarizes disclosure risk by combining SynthCity's privacy and sanity checks with quasi-identifier analysis derived from dataset metadata. The `DatasetPrivacySummary` dataclass captures row counts, quasi-identifier lists, overlap/duplicate rates, nearest-neighbor distances, k-anonymity figures, t-closeness diagnostics, and (when available) identifiability and delta-presence metrics.

```{code-cell} python
# Build the privacy metadata frame derived from curated roles/types.
import json
import pandas as pd
from semsynth.semmap import Metadata
from semsynth.utils import infer_types

heart = pd.read_csv("../downloads-cache/uciml/45.csv.gz")
disc, cont = infer_types(heart)
inferred = {c: ("discrete" if c in disc else "continuous") for c in heart.columns}

meta = Metadata.from_dcat_dsv(json.load(open("../mappings/uciml-45.metadata.json")))
privacy_frame = meta.to_privacy_frame(inferred)
privacy_frame.head()
```

## Metric suite
- SynthCity's `CommonRowsProportion`, `CloseValuesProbability`, and `NearestSyntheticNeighborDistance` quantify exact overlaps, near-duplicates (using SynthCity's fixed 0.2 threshold), and neighbor distance statistics between real and synthetic records.
- k-map and k-anonymity values are computed on quasi-identifier groupings drawn from the metadata roles, while rare quasi-identifier reproduction rates flag synthetic groups that repeat sparse real combinations.
- t-closeness is reported per sensitive attribute: numerical sensitive variables use a Wasserstein-1 distance between group and global distributions, and categorical variables use total variation distance on normalized counts.
- Optional identifiability and delta-presence scores are attempted via SynthCity; failures emit warnings but do not halt reporting, keeping the pipeline resilient to missing optional dependencies.

```{code-cell} python
# Check quasi-identifier group sizes that feed k-anonymity.
qi = list(privacy_frame.loc[privacy_frame.role == "qi", "variable"])
group_sizes = heart[qi].value_counts().head()
group_sizes
```

These counts show how often common quasi-identifier combinations appear; higher counts typically boost k-anonymity in the privacy report.

## References
- SynthCity metric APIs: <https://synthcity.readthedocs.io/en/latest/generated/synthcity.metrics.eval_privacy.html>
- k-map and k-anonymity background: <https://doi.org/10.1145/1401890.1401904>
- t-closeness definition: <https://doi.org/10.1109/ICDE.2007.367856>
