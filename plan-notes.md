# Open items

Carried over from an earlier audit; everything else on it is done.

- Global mutable state (`GLOBAL_CONFIG.prov_dir`, `_BACKEND_CACHE`) complicates reuse.
- `process_dataset()` does too much in one pass; split it into explicit stages.
- Missing-value handling may distort distributions; needs a product-level policy.
- Type inference heuristics are brittle.
- Reproducibility is partial.
