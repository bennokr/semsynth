# Privacy metrics

SemSynth summarizes disclosure risk by combining SynthCity's privacy and sanity checks with quasi-identifier analysis derived from dataset metadata. The `DatasetPrivacySummary` dataclass captures row counts, quasi-identifier lists, overlap/duplicate rates, nearest-neighbor distances, k-anonymity figures, t-closeness diagnostics, and (when available) identifiability and delta-presence metrics.

## Metric suite
- SynthCity's `CommonRowsProportion`, `CloseValuesProbability`, and `NearestSyntheticNeighborDistance` quantify exact overlaps, near-duplicates (using SynthCity's fixed 0.2 threshold), and neighbor distance statistics between real and synthetic records.
- k-map and k-anonymity values are computed on quasi-identifier groupings drawn from the metadata roles, while rare quasi-identifier reproduction rates flag synthetic groups that repeat sparse real combinations.
- t-closeness is reported per sensitive attribute: numerical sensitive variables use a Wasserstein-1 distance between group and global distributions, and categorical variables use total variation distance on normalized counts.
- Optional identifiability and delta-presence scores are attempted via SynthCity; failures emit warnings but do not halt reporting, keeping the pipeline resilient to missing optional dependencies.

## References
- SynthCity metric APIs: <https://synthcity.readthedocs.io/en/latest/generated/synthcity.metrics.eval_privacy.html>
- k-map and k-anonymity background: <https://doi.org/10.1145/1401890.1401904>
- t-closeness definition: <https://doi.org/10.1109/ICDE.2007.367856>
