# Backends overview

SemSynth ships three interchangeable generation backends—MetaSyn, PyBNesian, and SynthCity—that follow the common `run_experiment` contract and produce aligned artifacts (synthetic CSVs, per-variable metrics, and manifests). The backends share the same type inference and train/test splitting utilities so synthetic rows and downstream metrics remain comparable across runs. If a backend's optional dependency is missing, the implementation raises a clear runtime error suggesting the corresponding extras install (for example, `pip install semsynth[metasyn]`).

## MetaSyn
- Uses `MetaFrame.fit_dataframe` to learn column-wise distributions after inferring discrete and continuous fields, then synthesizes a user-specified number of rows. The backend coerces continuous features to floats, preserves categorical categories, and writes a `synthetic.csv` aligned to the original schema.
- Persists evaluation artifacts alongside the dataset, including per-variable distance metrics and summary statistics derived from the held-out test split. A manifest records the backend name, dataset identifiers, seed, requested rows, and split ratio to keep runs auditable.

## PyBNesian
- Learns a Bayesian network with hill climbing and configurable network types (`clg` or `semiparametric`) and scoring/structure-search options. Sensitive roots (age, sex, race by default) are blacklisted from being child nodes to avoid trivial leakage pathways.
- Samples synthetic rows from the fitted network, exports optional SemMap parquet, and computes per-variable distances plus a held-out log-likelihood statistic. The backend serializes GraphViz and GraphML structures (when optional dependencies are present) and stores a manifest capturing structure parameters and dataset metadata.

## SynthCity
- Normalizes generator aliases (e.g., `ctgan`, `pategan`, `bayesiannetwork`) to the canonical SynthCity plugin names, then loads the chosen plugin with sanitized parameters. Continuous features are coerced to numeric types and categories are string-safe before fitting on the training split.
- Generates synthetic rows through the plugin's `generate` API, aligns columns to the training schema, and writes synthetic CSVs and optional SemMap parquet. Per-variable distances and summary statistics are emitted alongside a manifest documenting the generator, seed, row count, and split settings.

## References
- MetaSyn documentation: <https://metasyn.readthedocs.io/>
- PyBNesian documentation: <https://pybnesian.readthedocs.io/>
- SynthCity documentation: <https://synthcity.readthedocs.io/>
