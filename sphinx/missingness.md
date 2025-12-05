# Missingness handling

SemSynth provides utilities for learning realistic missingness patterns from real datasets and applying them to synthetic samples. The design pairs per-column logistic models with a dataframe-level wrapper so generators can emit data that mirrors conditional dropout rates observed in the source data.

## Column-level modeling
- `ColumnMissingnessModel` estimates the probability that a specific column is missing by fitting a logistic regression on one-hot encoded features of all other columns. It tracks the marginal missingness rate and skips modeling when a column is always present or always absent, ensuring stable behavior on edge cases.
- The model samples boolean masks by scaling predicted probabilities back to the observed missingness rate when needed, preventing over- or under-estimation of missing cells during synthesis.

## Dataframe-level application
- `DataFrameMissingnessModel` fits a `ColumnMissingnessModel` for each column in the real dataset and stores them in a mapping. When applied to a synthetic dataframe, it iterates over the learned masks to inject `NaN` values column by column, respecting the fitted conditional patterns.
- `MissingnessWrappedGenerator` wraps any base generator callable and first fits missingness on the real data. Subsequent calls to `.sample(n)` produce synthetic rows with the learned missingness applied, enabling drop-in realism without modifying the underlying generator implementation.

## References
- Logistic regression missingness modeling with scikit-learn: <https://scikit-learn.org/stable/modules/linear_model.html#logistic-regression>
- One-hot encoding for categorical features: <https://scikit-learn.org/stable/modules/generated/sklearn.preprocessing.OneHotEncoder.html>
