# Downstream fidelity

The downstream-fidelity module compares real and synthetic datasets by fitting equivalent predictive models and inspecting how coefficients, directions of effect, and uncertainty translate between them. It automatically derives a modeling formula from metadata, performs multiple imputation for missing data, and reports side-by-side parameter estimates to highlight agreement or drift.

## Formula discovery
- `auto_formula` builds a Patsy formula by inferring target roles from the dataset schema, coercing dtypes (including categorical levels from codebooks), and generating main effects plus interaction candidates. Cross-validated feature screening enforces strong heredity, keeping parents of any retained interactions to stabilize the model.

## Multiple imputation and estimation
- `fit_with_mi` recodes categorical variables, replaces missing codes, and runs MICE (`statsmodels.imputation.mice`) to produce pooled estimates for generalized linear models appropriate to the target type (binomial, Poisson, or OLS).

## Comparative reporting
- `compare_real_vs_synth` sanitizes the inputs, fits the auto-discovered model with multiple imputation on real and synthetic data, and returns a dataframe of paired coefficients and standard errors with a sign-match indicator. When model fitting fails, it falls back to a simpler logistic comparison but still surfaces the skipped reason to the caller.

## References
- Patsy formula language: <https://patsy.readthedocs.io/en/latest/>
- Rubin's rules for multiple imputation: <https://doi.org/10.1002/sim.4067>
- statsmodels MICE implementation: <https://www.statsmodels.org/stable/imputation.html>
