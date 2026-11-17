# SemSynth: direction and decisions

What SemSynth is for, what is built, what was decided and why. Commands and layout are in `AGENTS.md`; this file is the
direction. Claims marked *(unverified)* were not checked against a source.

## Goal
Evaluate synthetic tabular health data in a way that does not depend on the generator, and treat **missingness** and
**clinically relevant subgroups** as first-class. What a person knows about the original data (the codebook: codes,
skip rules, subgroup definitions) is part of the original dataset's metadata. What was measured on a synthetic dataset
(scores, their uncertainty, the protocol) is part of that dataset's provenance. Python API, CLI and a Pyodide app share
one code path.

## Principles
1. **A score means something only next to a reference.** Every score comes with a real-sample ceiling, an
   independent-marginals floor, a noise floor or interval, and is computed on rows the generator never saw.
2. **Never a bootstrap interval of a distance.** A distance between two samples is positive for samples of one population
   and its bootstrap interval is biased upwards (observed). Distances get a permutation noise floor; row-level statistics
   (rates, DCR, AUC) get bootstrap intervals (`semsynth/uncertainty.py`).
3. **Mechanisms are declared, never inferred.** Structure, rates, co-missing blocks and observed dependence can be read
   from data. MCAR, MAR or MNAR cannot.
4. **Privacy is a measured claim, not a property.** Distances to the closest record, exact matches and attribute
   inference, each against the holdout. Only a differentially private generator (PrivBayes) gives a guarantee.
5. **The library stays importable in a browser.** No makeprov, git or network inside `semsynth.*` except `__main__`.

## Status
| Step | State |
| --- | --- |
| Privacy without SynthCity (core + sdmetrics), skipped metrics recorded | done |
| Baselines, bootstrap and noise floors | done: `baselines.py`, `uncertainty.py`; repeated generator seeds not wired |
| Joint fidelity (pairwise TVD with missing as a level, pattern TVD, classifier test) | done: `joint_fidelity.py` |
| Missingness-aware distances (`category`, `observed`, `asymmetric`, per column) | done: `distance.py` |
| Declared codes recoded, skip rules read, violations counted, learning across skip rules | done: `structure.py`, `structure_aware` |
| Subgroups: definitions in the codebook, scores per group, minimum size | done: `subgroups.py` |
| Injected-truth benchmark | done: `benchmark.py` |
| Provenance (PROV-O, makeprov 0.7 model, DQV measurements) | done: `provenance.py` |
| Browser entry points | done: `browser.py`, in the Pyodide smoke test |
| Missingness evaluation in the pipeline (violation rate, mask dependence on real incomplete data) | next |
| Distance policy chosen per column from the codebook | next (needs `missing_reason`) |
| Mechanism declared in the codebook; sensitivity analysis for MNAR | next |
| NHANES provider and benchmark | next |
| Backends (mostlyai-engine spike) | after the evaluation work |

## What the injected-truth benchmark found
Complete table, then MAR, MNAR, a skip rule and coded values injected (`run_injected_benchmark`, 1500 rows):
- Learning from complete rows kept 15% of rows, all smokers; fidelity to the truth was poor (discrete JSD 0.38).
- Learning across skip rules (`structure_aware`) kept 50% of rows, discrete JSD 0.018, zero rule violations.
- A MAR dependence on an observed column was recovered (gradient 0.69 real, 0.65 synthetic). An MNAR dependence on the
  column's own value was not (0.60 real, 0.02 synthetic). That is a limit of any mask model that sees only observed
  columns, and it stays in the tests as a known limit.
- Continuous columns stay biased (KS 0.16) because rows with a missing value under MAR/MNAR are dropped from learning.
  Learning from observed values per column is the next fix.

## Decisions
- **Codebook (linked-codebook 0.10) already has** `applies_when`, `missing_values`, `missing_range`, `Value.missing`,
  `completeness`. SemSynth now reads them. The condition language is REDCap-style (`[var]`, comparisons, `in`,
  `is null`, `and`/`or`/`not`; no arithmetic, `between`, `like` or functions). Do not extend it: compute derived
  columns (BMI, age bands) at load time.
- **Subgroups**: definitions are named conditions in that language, stored in the codebook under `ss:subgroups`
  (`Codebook.extras`, written into the JSON-LD) until linked-codebook has a slot. Which groups to evaluate, the
  minimum size and the intersections are run settings (`PipelineConfig.subgroups`, `subgroup_min_size`). A misspelt
  field makes linked-codebook evaluate a condition as False without an error, so `check_subgroups` is required.
- **NaN**: linked-codebook does not treat a pandas `NaN` as blank (`[x] < 60` is False, `missingness()` counts NaN as
  present). Everything passes through `structure.as_rows`, which makes it `None`.
- **Detection-limit censoring** is SemSynth-first: value and flag column, `limit` or limit column, substitution rule
  (`benchmark.py` injects it). Promote to the codebook when a second dataset needs it.
- **Evaluation tables**: scores use the complete synthetic table against the complete holdout, because generators learn
  from complete rows. Missingness fidelity compares the released table with the real rows that have missing values.

## Missingness: kinds, handling, evaluation
| Kind | Declared as | Generated by | Evaluated by |
| --- | --- | --- | --- |
| Structural / designed (skip logic, subsample membership) | `applies_when` | rules, enforced after generation | violation rate |
| Coded (refused, don't know) | `missing_values`, `Value.missing` | recoded to NaN at load | recovered share |
| Item nonresponse (blank where the question applied) | derived: blank and applicable | learned mask model (MAR on observed columns) | rate gap, mask gradient, pattern TVD |
| Latent MNAR | mechanism, declared | not recoverable; needs stated sensitivity assumptions | injected-truth only |
| Censoring below a limit | flag column (SemSynth) | flag plus distribution above the limit | flag rate, not distance on substituted values |

## linked-codebook 0.11: the minimum to ask for
1. `Value.missing_reason`: `refused`, `dont_know`, `not_applicable`, `not_collected` (only with `missing: true`); drives the
   distance policy and the benchmark.
2. `Column.missing_mechanism` (`mcar`, `mar`, `mnar`; absent means undeclared) and `missing_depends_on`, for blanks in rows
   where the column applies.
3. Treat float `NaN` as blank in `blank()`.
4. Lint: a `[field]` in `applies_when` that is not a column; `missing_reason` only with `missing: true`.

Not now: subgroups slot, censoring, roles, survey weights (a SemSynth role), MNAR parameters. Release process, lint
config and budgets of linked-codebook are *(unverified)*: the repository was not available.

## Benchmarks
1. **Injected truth** (done): any complete table; exact answers.
2. **NHANES 2017 to March 2020**: public files, so synthetic output can be published, but confirm the data use terms
   *(unverified)*. Structural missingness from questionnaire skip logic, a fasting subsample with its own weights and
   nonresponse adjustment, unit/component/item nonresponse with value codes (CDC analytic guidelines), oversampled
   subgroups. No ICU-style lab missingness. Needs a provider (CDC XPT files merged on `SEQN`) and a decision on weights.
3. **PhysioNet Challenge 2019** (CC BY 4.0, 40,336 ICU patients): informative lab missingness; aggregate per patient.
4. Existing UCI sets (CKD, Hepatitis, Heart Disease, Diabetes 130) as regression tests. MIMIC-IV is internal only: derived
   data must stay under its agreement.

## Pyodide
- `semsynth.browser`: `capabilities()` (what is installed, whether Pyodide), `inspect_table()` (codes, rule breaks,
  subgroup problems and sizes, before generating), `run()` (text files and metrics back, nothing left on disk).
- Tested in Pyodide 0.27.7 (`scripts/pyodide_smoke.py`): MetaSyn, PrivBayes, privacy with sdmetrics, joint fidelity,
  baselines, subgroups, the benchmark and `browser.run`, about 35 s on a 300-row table. No PyBNesian, UMAP or SynthCity there.
- Above 5000 rows `run()` subsamples in Pyodide. Larger tables were not timed.
- Not built: the page itself (a worker that loads Pyodide, installs the wheel, calls these three functions).

## Provenance
- The CLI commands are makeprov rules (0.8.1, the newest release; floor raised from 0.4.4). `prov-config.toml` records the
  environment and streams a recovery file. `ProvMeta` (record rule arguments) cannot be used: defopt does not parse it.
- A run's `provenance.json` (`provenance.py`) has makeprov's shape: `prov:Plan`, runtime agent, qualified association,
  parameters as `schema:additionalProperty`, duration, sha256 per file. Scores are `dqv:QualityMeasurement` of a
  `dqv:Metric` with a version. DQV has no uncertainty or metric-version property, so `ss:` terms carry intervals and
  noise floors; the `ss` namespace (`https://w3id.org/semsynth/vocab#`) is a placeholder that is not registered.
- Not done: the evaluation protocol (split, control size, quasi-identifiers) as its own node; `ArtifactRef.external` for
  the source dataset's landing page.

## Open questions
- Learn from observed values per column instead of complete rows (MetaSyn takes NaN; the others do not).
- Survey weights: synthesize and evaluate unweighted, weighted, or both?
- Repeated generator seeds: where do they enter the report?
