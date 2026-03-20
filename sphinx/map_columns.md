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

Mapping helpers are easiest to demonstrate on the curated Heart Disease payload.

This quick count shows which codelists appear most often, illustrating how curated mappings guide downstream roles and privacy handling.

```{include} ../map_columns/README.md
:relative-images:
```

```{code-cell} python
# Summarize the most common codebook notations in the curated mapping.
import json
from collections import Counter

meta = json.load(open("../mappings/uciml-45.metadata.json"))
codes = []
for col in meta["datasetSchema"]["columns"]:
    cb = col.get("columnProperty", {}).get("hasCodeBook") or {}
    concepts = cb.get("hasConcept") or []
    codes.extend([c.get("notation") for c in concepts if isinstance(c, dict) and c.get("notation")])

Counter(codes).most_common(5)
```
