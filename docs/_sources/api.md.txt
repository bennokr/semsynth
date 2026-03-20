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

# API reference

```{code-cell} python
from semsynth.datasets import DatasetSpec, load_dataset

spec = DatasetSpec(provider="uciml", id=45)
payload = load_dataset(spec)
payload.frame.head(3)
```

```{eval-rst}
.. autosummary::
   :toctree: _autosummary
   :recursive:
   
   semsynth
```
