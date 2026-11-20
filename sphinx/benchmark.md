# Injected-truth benchmark

No real clinical table says why its values are missing, so no real table can show whether the pipeline handles missing values
well. A complete table can. The benchmark takes one, removes values in ways that are known, runs the pipeline's own steps on
what is left, and compares the result with the complete table that the pipeline never sees.

## Run it

```bash
python -m semsynth benchmark                      # a demo table and one mechanism of each kind; about 4 seconds
python -m semsynth benchmark my_complete.csv -m mechanisms.toml -b chain --out result.json
```

Without a file the command uses the demo table of `semsynth.benchmark.demo_table` and the mechanisms in
`semsynth.benchmark.DEMO_MECHANISMS`. The full result is written as JSON and a summary is printed:

| variant            |   rows kept |   discrete JSD |   numeric KS |   rate gap |   gradient gap |   rule violations |
|:-------------------|------------:|---------------:|-------------:|-----------:|---------------:|------------------:|
| learned            |       0.139 |          0.399 |        0.168 |      0.030 |          0.264 |                 - |
| learned_with_rules |       0.139 |          0.399 |        0.168 |      0.030 |          0.264 |                 - |
| structure_aware    |       0.492 |          0.014 |        0.180 |      0.017 |          0.310 |             0.000 |

This is MetaSyn on the demo table (1,500 rows, seed 0). The `-` is a rate over no cells: the generator that learned from the 14% of
rows without a missing value saw only smokers, so it drew no cell that the skip rule marks as not applicable.

## The mechanisms

A mechanism acts on the cells that are still observed, in the order given. Write one `[[mechanisms]]` table for each in the file
that `--mechanisms` reads:

```toml
[[mechanisms]]
column = "chol"
kind = "mar"          # missing more often where `driver` is high
rate = 0.3
driver = "age"
strength = 2.5

[[mechanisms]]
column = "cigs"
kind = "structural"   # empty where the rule is false; the codebook declares the rule
rule = "[smoker] == 'yes'"
```

| kind | what it does |
| --- | --- |
| `mcar` | each cell is missing with probability `rate` |
| `mar` | the probability rises with the observed numeric column `driver` |
| `mnar` | the same, driven by the column's own value, which is gone afterwards |
| `structural` | the column is empty where the `rule` (an `applies_when` condition) is false |
| `coded` | a share `rate` of the cells holds the codes of `codes` (77 refused, 99 don't know) |
| `censored` | values below the `rate` quantile are replaced by the limit divided by the square root of 2, and a column `<column>_below_lod` flags them |

The codebook of the injection declares what a person could declare: the skip rules and the missing codes. Nothing else is
told to the pipeline.

## The three variants

- `learned`: declared codes become missing, the generator learns from the complete rows only, and a missingness model learned from the
  incomplete rows is applied to its output.
- `learned_with_rules`: the same, with the declared skip rules enforced afterwards.
- `structure_aware`: cells that a skip rule marks as not applicable are filled for learning, so those rows are not lost, and the
  rules are enforced afterwards (`structure_aware = true` in a pipeline configuration).

## What the scores mean

- **rows kept**: the share of rows the generator could learn from.
- **discrete JSD**, **numeric KS**: the distance between the synthetic table before masking and the complete truth.
- **rate gap**: the mean difference between the missing rate that was injected and the rate in the synthetic table.
- **gradient gap**: the mean difference between the injected and the synthetic *gradient*, which is the difference in missing rate
  between the top and the bottom third of the `driver` column.
- **rule violations**: the share of synthetic values that break a declared skip rule.

The JSON file has one record for each mechanism with the real and synthetic rates and gradients.

## What it has found

On a 1,500-row run with a MAR, an MNAR, a skip rule and coded values, learning across skip rules kept 49% of the rows against 14%,
and brought the discrete distance to the truth from 0.40 to 0.01. A MAR dependence on an observed column was recovered; an MNAR
dependence on the column's own value was not, which no mask model that sees only observed columns can do. The numeric columns stay
biased, because rows with a missing value are dropped from learning. The tests keep these as known limits
(`tests/test_benchmark.py`).
