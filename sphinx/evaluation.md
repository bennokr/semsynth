# Evaluation: joint fidelity, reference tables and uncertainty

Marginal fidelity (`metrics.json`), privacy ({doc}`privacy-metrics`) and downstream utility ({doc}`downstream-fidelity`)
each say something about a synthetic table. This page covers what was added so that the numbers can be *read*.
Everything is computed on rows the generator never saw (the holdout), by the same code for every generator.

## Reference tables

A score alone does not say whether it is good, so each score of the synthetic table is computed again, with the same
functions and the same holdout, for two stand-ins (`metrics.baselines.json`, the "Reference comparison" table of the report):

| table | what it is | read it as |
| --- | --- | --- |
| `real_sample` | rows of the training data | fidelity ceiling (a perfect generator scores like a fresh real sample); privacy worst case (a leak of the whole table) |
| `independent_marginals` | every column drawn on its own from the training values | floor for joint fidelity: right marginals, no relations, no co-missingness |

The privacy scores have a third reference built in: the holdout rows, "other real people", against the training rows.

## Utility: train on synthetic, test on real

`compute_utility` trains a gradient-boosting model on the synthetic rows to predict the dataset's target and scores it on real rows
that no table was learned from (`utility` in `metrics.json`; `semsynth.utility`). The score is the area under the ROC curve for a
categorical target (balanced accuracy when the held-out rows have one class) and R² for a numeric one. Three references use
the same model and the same number of training rows:

- the **ceiling**: a model trained on real training rows (`real_sample`);
- the **floor**: a model trained on `independent_marginals`, which has no relation between columns to learn;
- the **prior**: the class frequencies or the mean, with no model (AUC 0.5, R² 0).

`recovered` is `(synthetic - floor) / (ceiling - floor)`, the share of what real data gains over the floor that the synthetic table
keeps. It is left out when the ceiling and the floor are less than 0.02 apart. The interval of a single split comes from
resampling the held-out rows (paired across the tables); it does not include the variation of the training rows.

## Cross-validation (`cv_folds`)

With `cv_folds = k` (2 or more) the rows are split into k folds, stratified by the target where there is a categorical one. The
first fold produces the released synthetic table, and the model is fitted again on the other k - 1 training sets. Every fold scores
the synthetic table and both references with the same functions, and `cv` in `metrics.json` has the mean and an interval of each
score. The interval is the corrected resampled t interval of Nadeau and Bengio (2003): the k scores share most of their
training rows, so the plain interval is too narrow, and the correction multiplies the variance by `(1/k + n_test/n_train)` in
place of `1/k`. The interval keeps the range of the score (a share never goes below 0). It covers other samples of rows from the
same population and not the seed of the generator. `recovered` is computed from the mean scores and has no interval, because the
ratio of two close numbers in one fold is unstable. The report's scorecard shows these cells; without folds it shows the one split.

Cost: a model is fitted k times, so keep `fit_on_sample` modest for slow generators.

## Joint fidelity (`metrics.joint.json`)

- `pairwise`: total variation distance between the real and synthetic contingency tables of each column pair (numbers cut
  at the quantiles of the real column). A missing value is a level of its own, so the test also asks whether the
  missingness of one column depends on the others in the same way. `tvd_mean`, `tvd_max` and the worst pairs.
- `classifier`: how well gradient boosting separates real from synthetic rows (cross-validated AUC; 0.5 means it cannot).
  Missing values are given to the classifier as they are. `pmse` is the mean squared distance of the predicted
  probability from 0.5.
- `missingness`: per-column missing rates and whole-row missingness patterns against the real table *with* its
  missing values (the generators learn from complete rows, so this compares the released table with the real incomplete one).

With few holdout rows these scores are noisy. That is what the reference tables and the noise floors are for.

## Uncertainty

- **Row-level statistics** (match rates, DCR medians, the share of synthetic rows closer than the holdout's 5th percentile,
  AUC) get 95% percentile bootstrap intervals, `bootstrap_reps` resamples.
- **Distances between two samples** (JSD, KS, Wasserstein, pairwise TVD) do not: such a distance is above zero even for two
  samples of one population, and a bootstrap interval of it is biased upwards (we saw an interval that did not contain
  its own estimate). They get a **noise floor** instead: the pooled real and synthetic rows are split at random into
  samples of the original sizes, and the score is recomputed (`null_interval`, `p_value`). A score inside the interval
  cannot be told from a fresh real sample at this sample size. Scores above it are a real difference.
- A single split does not cover the randomness of the generator or of the train/holdout split; cross-validation covers the
  split, and only repeated seeds cover the generator (`semsynth.uncertainty.mean_and_interval` summarizes the results).

## Distances with missing values

`semsynth.distance.GowerIndex` implements the three policies per column:

| policy | both missing | one missing | use for |
| --- | --- | --- | --- |
| `category` | 0 (agree) | 1 | informative missingness where shared absence is a real similarity (a lab test ordered only for sick patients) |
| `observed` | column left out | column left out | item non-response that says nothing about the person (classic Gower) |
| `asymmetric` | column left out | 1 | structural missingness: a question that does not apply to either person (skip logic) |

Numbers are scaled by the reference range (a larger difference counts as 1); there is no limit on the number of
categories. The sdmetrics DCR scores use the `category` convention. Choosing the policy per column from the dataset
profile (missingness kind: structural, item non-response, coded) is planned; until then it is set by `privacy_missing`.

## Declared structure, subgroups and the injected-truth benchmark

**Declared structure** (`semsynth.structure`). The codebook's `missing_values`, `missing_range` and `missing: true` values are
recoded to missing when a table is loaded, so a refused answer coded 77 is no longer a number. `applies_when` rules (a
REDCap-style condition such as `[smoker] == 'yes'`) say which cells a skip rule leaves empty; `structural_violations`
counts values where the rule says the question does not apply. With `structure_aware = true` the generator learns from rows
that are complete over the cells that apply (the others are filled with a neutral value), and the rules are enforced on the
output. A pandas `NaN` is not blank for linked-codebook's evaluator, so tables go through `structure.as_rows` first.

**Subgroups** (`semsynth.subgroups`). Named conditions in the same language, given in the settings (`subgroups`, a list of `name`, `condition` and
optionally `label`); they are not part of the codebook. For each group: its size in the training, holdout and synthetic table, marginal fidelity, exact-match
rate and the share of synthetic rows closer to a training record than the 5th percentile of the group's holdout rows (with
bootstrap intervals), the gap to the overall score and the worst group. A group with fewer than `subgroup_min_size` holdout or
synthetic rows is listed with its sizes only. `inspect_table` (in `semsynth.browser`) reports misspelt fields and group
sizes before anything is generated.

**Injected-truth benchmark** (`semsynth.benchmark`). `inject` breaks a complete table with `mcar`, `mar`, `mnar`, `structural`,
`coded` and `censored` mechanisms and returns the truth; `run_injected_benchmark` runs the pipeline's own steps and scores how
much of each mechanism comes back (missing rates, and the gradient: the difference in missing rate between the top and bottom
third of a driver). A MAR dependence on an observed column is recovered; an MNAR dependence on the column's own value is
not, and nothing a mask model learned from observed columns could change that.
