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
- Neither covers the randomness of the generator or of the train/holdout split. Repeat with several seeds for that
  (`semsynth.uncertainty.mean_and_interval` summarizes the results).

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
