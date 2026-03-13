# Data Report — Fertility

**Source**: [UCI dataset 244](https://archive.ics.uci.edu/dataset/244)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Fertility                                                                     |
| Source      | [UCI dataset 244](https://archive.ics.uci.edu/dataset/244)                    |
| Rows        | 100                                                                           |
| Columns     | 10                                                                            |
| Discrete    | 6                                                                             |
| Continuous  | 4                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | modeled 0 of 10 (seed 42)                                                     |

## Variables and summary

| variable              | inferred   | dist                                                    |
|:----------------------|:-----------|:--------------------------------------------------------|
| season                | continuous | -0.0789 ± 0.7967 [-1, -1, -0.33, 1, 1]                  |
| age                   | continuous | 0.6690 ± 0.1213 [0.5, 0.56, 0.67, 0.75, 1]              |
| child_diseases        | discrete   | 1: 87 (87.00%)                                          |
| accident              | discrete   | 1: 44 (44.00%)                                          |
| surgical_intervention | discrete   | 1: 51 (51.00%)                                          |
| high_fevers           | discrete   | 0: 63 (63.00%)<br />1: 28 (28.00%)<br />-1: 9 (9.00%)   |
| alcohol               | continuous | 0.8320 ± 0.1675 [0.2, 0.8, 0.8, 1, 1]                   |
| smoking               | discrete   | -1: 56 (56.00%)<br />0: 23 (23.00%)<br />1: 21 (21.00%) |
| hrs_sitting           | continuous | 0.4068 ± 0.1864 [0.06, 0.25, 0.38, 0.5, 1]              |
| diagnosis             | discrete   | N: 88 (88.00%)                                          |

## Missingness model

- Columns with learned missingness: 0 of 10
- Columns without missingness: 10No columns required missingness injection.

## Fidelity summary

| model      | backend   |   disc_jsd_mean |   disc_jsd_median |   cont_ks_mean |   cont_w1_mean | privacy_overlap   | downstream_sign_match   |
|:-----------|:----------|----------------:|------------------:|---------------:|---------------:|:------------------|:------------------------|
| metasyn    | metasyn   |          0.1592 |            0.1304 |         0.2725 |         0.1284 |                   |                         |
| clg_mi2    | pybnesian |          0.1179 |            0.1088 |         0.235  |         0.1188 |                   |                         |
| semi_mi5   | pybnesian |          0.1179 |            0.1088 |         0.235  |         0.1188 |                   |                         |
| ctgan_fast | synthcity |          0.402  |            0.4298 |         0.3225 |         0.1808 |                   |                         |
| tvae_quick | synthcity |          0.1649 |            0.1524 |         0.2175 |         0.1154 |                   |                         |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 100</li>
<li> <a href="models/metasyn/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 100</li>
<li> Params: <tt>{"max_indegree": 2, "operators": ["arcs"], "score": "bic", "type": "clg"}</tt></li><li> <a href="models/clg_mi2/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/clg_mi2/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/clg_mi2/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 100</li>
<li> Params: <tt>{"max_indegree": 5, "operators": ["arcs"], "score": "bic", "type": "semiparametric"}</tt></li><li> <a href="models/semi_mi5/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/semi_mi5/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/semi_mi5/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: ctgan_fast (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 100</li>
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li><li> <a href="models/ctgan_fast/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/ctgan_fast/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/ctgan_fast/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 100</li>
<li> Params: <tt>{"batch_size": 256}</tt></li><li> <a href="models/tvae_quick/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/tvae_quick/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/tvae_quick/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

</table>
