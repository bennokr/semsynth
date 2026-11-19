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
| IRIs under one base, DCAT writer, SPARQL explorer | done: `iris.py`, `catalog.py`, `queries/`; the Pages step has not run on CI |
| linked-codebook 0.11 (IRIs for the extension terms, `dsvo`, NaN is blank) | done, released on PyPI and npm; semsynth depends on it from PyPI |
| Utility (train on synthetic, test on real) with ceiling, floor and interval | done: `utility.py`; the share recovered needs a ceiling above the floor |
| k-fold cross-validation with corrected intervals | done: `crossval.py`, `cv_folds`; the demo uses 5 folds |
| Report page: scorecard between floor and ceiling, details sections | done: `report_scorecard.py`, `templates/report.md.j2` |
| makeprov record linked to run provenance (`prov:wasInfluencedBy`) | done: needs makeprov 0.8.2 (`current_activity`), not released |
| Missingness evaluation in the pipeline (violation rate, mask dependence on real incomplete data) | next |
| Distance policy chosen per column from the codebook | next (needs `missing_reason`) |
| Mechanism declared in the codebook; sensitivity analysis for MNAR | next |
| NHANES provider and benchmark | next |
| Backends: `mostlyai` (TabularARGN) and `chain` (sequential MLP or gradient boosting, runs in Pyodide) | spiked, experimental: see `sphinx/evaluation.md` for the first comparison |
| PrivBayes with NumPy 2 | fixed: DataSynthesizer reads back keys written as `np.int64(1)`; generation runs in the NumPy 1.25 print mode |

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
- **Codebook (linked-codebook 0.11) already has** `applies_when`, `missing_values`, `missing_range`, `Value.missing`,
  `completeness`. SemSynth now reads them. The condition language is REDCap-style (`[var]`, comparisons, `in`,
  `is null`, `and`/`or`/`not`; no arithmetic, `between`, `like` or functions). Do not extend it: compute derived
  columns (BMI, age bands) at load time.
- **Subgroups**: named conditions in that language, a setting of the evaluation (`PipelineConfig.subgroups`,
  `subgroup_min_size`), not part of the codebook. A misspelt field makes linked-codebook evaluate a condition as False
  without an error, so `check_subgroups` (and `check_rules` for skip rules) are required.
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

## linked-codebook
Done in 0.11.0 (local clone, `make check` passes, not released): the extension keys (`appliesWhen`, `missingRange`, `codeBookClosed`,
`columnGroup`, `identifying`, `minimumValue`, `maximumValue`, `columnFormat`) have IRIs, so skip rules and limits stay in the RDF;
before, JSON-LD dropped them. `csvw:minInclusive`, `csvw:maxInclusive` and `csvw:format` (checked against the CSVW context and
by `make pin`; `csvw:minimum` and `csvw:maximum` are not RDF properties) and the slots of linked-codebook's own data model
(`lc:applies_when`, `lc:closed`, `lc:group`, `lc:identifying`, `lc:missing_range`, namespace
`https://bennokr.github.io/linked-codebook/profile#`). The DSV prefix is `dsvo` (`dsv` is also the Data Specification
Vocabulary); the IRIs are unchanged. A float `NaN` is blank. SemSynth tests that need this skip on 0.10.0; bump the pin after the release.

Still to ask for: `Value.missing_reason` (`refused`, `dont_know`, `not_applicable`, `not_collected`), `Column.missing_mechanism`
(`mcar`, `mar`, `mnar`; absent means undeclared) with `missing_depends_on`, and a lint for a skip rule that names no column
(SemSynth has `check_rules`). Not now: subgroups (a SemSynth setting), censoring, roles, survey weights, MNAR parameters.

## Publishing and querying
- **IRIs** (`semsynth/iris.py`): one base, `https://bennokr.github.io/semsynth/output/`, a setting (`iri_base`) so that it can move to
  w3id.org later. `<base><dataset>/` is the dataset and its report page and the dataset node of its codebook;
  `…/models/<model>/` the synthetic dataset; `…/#run` the run; a file's URL is its IRI. Slugs only: no space, capital or `urn:`.
  The identity of a thing is its IRI whether or not the host serves it; renaming the GitHub user or repository breaks them.
- **No terms of our own**: DCAT, DSV (`dsvo`), CSVW, PROV-O, DQV, schema.org, SKOS and linked-codebook's own `lc` slots.
- **The explorer loads the RDF files and the playground merges them**: Comunica federates sources and does not
  deduplicate a triple that two of them state, so queries over the separate files returned 1,920 rows where 108 are right.
  The playground now reads each source and queries their union as one source (`data-merge-sources="false"` turns that off).
  The `data` patterns of the Pages step list the RDF files only, and `tests/test_catalog.py` checks the list.
  Named graphs in TriG are invisible to a plain query in the playground (no `unionDefaultGraph`); there are none.
- **Queries** (`queries/*.rq`) use no string functions; the links are modelled, and `tests/test_catalog.py` checks both that
  and that the queries join the catalog, codebook and provenance.
- **The explorer** is the data-catalog-sparql-playground's composite action as a step of the Pages job (pinned to a commit), not
  its reusable workflow, which also deploys and cannot take generated files.
- **SynthCity** is to be dropped: the backend, `torch_compat.py`, the extra and its `[tool.uv]` conflicts, two CI jobs, three configs,
  docs and tests. Not done yet.

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
  `dqv:Metric` with a version (`dct:hasVersion`). Intervals, noise floors and p-values are measurements of derived metrics
  (`prov:wasDerivedFrom` the metric, in a `dqv:Dimension`); SemSynth defines no namespace, prefix or predicate of its own.
- Not done: the evaluation protocol (split, control size, quasi-identifiers) as its own node; `ArtifactRef.external` for
  the source dataset's landing page.

## Open questions
- Learn from observed values per column instead of complete rows (MetaSyn takes NaN; the others do not).
- Survey weights: synthesize and evaluate unweighted, weighted, or both?
- Repeated generator seeds: where do they enter the report?
