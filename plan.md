# Plan

## High-impact issues (likely to break installs or common workflows)

- [x] **Broken console entry point**
  - Updated `pyproject.toml` script target to `semsynth.__main__:main`.
- [x] **Templates and curated mappings are not packaged**
  - Copied runtime assets into `semsynth/templates/` and `semsynth/mapping_data/`.
  - Switched template and mapping loading to packaged resources.
  - Declared package data in `pyproject.toml` and package discovery via `find`.
- [x] **Flask app is advertised but not declared as a dependency**
  - Added `flask` dependency and an explicit `app` extra.
- [x] **Optional-dependency gating is inconsistent and can crash minimal runs**
  - Made privacy/downstream loading conditional on enabled flags.
  - Updated pipeline handling to catch `RuntimeError` from dependency registry.

## Behavior mismatches and correctness risks

- [x] **README output filenames do not match code**
  - Updated Outputs docs to match generated report and model artifacts.
- [x] **Exception handling policy is inconsistent**
  - CLI `report` now processes all datasets, records failures, then exits once with a summary.
- [x] **Privacy metrics module contains internal artifacts and unused work**
  - Removed stray artifact text.
  - Removed unused import and surfaced `k_map` in `DatasetPrivacySummary`.
  - Hardened datetime preprocessing for nullable datetimes.
- [x] **Hard-coded filesystem side effects at import time**
  - Removed eager directory creation from `semsynth/datasets.py`; now lazy on call.

## Design and maintainability issues

- [x] **Repo-root path assumptions**
  - Replaced repo-root assumptions for templates/mappings with packaged resources.
- [ ] **Global mutable state complicates reuse**
  - Left `GLOBAL_CONFIG.prov_dir` and `_BACKEND_CACHE` behavior unchanged for now.
- [ ] **Pipeline does too much in one pass**
  - Existing helper classes retained; no major orchestration rewrite in this pass.
- [x] **Dependency definition hygiene**
  - Removed invalid script reference and preserved separable extras.
  - Kept heavyweight deps unchanged in this pass.
- [x] **Missing project essentials for distribution**
  - Added `LICENSE`, CI workflow, and formatter/linter/type-checker tool configuration scaffolding.

## Data/science-specific concerns (quality and reproducibility)

- [ ] **Missing-value handling may distort distributions**
  - Current behavior retained; requires product-level policy decision.
- [ ] **Type inference heuristics are brittle**
  - Current behavior retained.
- [ ] **Reproducibility is partial**
  - Current behavior retained.

## Recommended fixes (ordered)

### Immediate (unblocks installs and core flows)

- [x] Fix console script target (point it at an existing `main`) or add `semsynth/cli.py`.
- [x] Package templates and curated mappings properly.
- [x] Make privacy/downstream loading strictly conditional and catch `RuntimeError`.
- [x] Add a `flask` dependency and document it.

### Short-term (reduces fragility)

- [x] Remove import-time filesystem side effects.
- [x] Align README “Outputs” section with actual filenames.
- [x] Normalize optional-dep behavior toward warn-and-continue.

### Medium-term (improves maintainability)

- [ ] Split `process_dataset()` into clearer explicit stages.
- [x] Replace repo-relative paths with resource-based loading for templates/mappings.
- [x] Add lint/type/format tooling + CI and a minimal-run integration test.
