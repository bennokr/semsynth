# Data Report — Statlog (Heart)

**Source**: [UCI dataset 145](https://archive.ics.uci.edu/dataset/145)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Statlog (Heart)                                                               |
| Source      | [UCI dataset 145](https://archive.ics.uci.edu/dataset/145)                    |
| Rows        | 270                                                                           |
| Columns     | 14                                                                            |
| Discrete    | 1                                                                             |
| Continuous  | 13                                                                            |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | modeled 0 of 14 (seed 42)                                                     |

## Variables and summary

| variable             | inferred   | dist                                          |
|:---------------------|:-----------|:----------------------------------------------|
| age                  | continuous | 54.4333 ± 9.1091 [29, 48, 55, 61, 77]         |
| sex                  | continuous | 0.6778 ± 0.4682 [0, 0, 1, 1, 1]               |
| chest-pain           | continuous | 3.1741 ± 0.9501 [1, 3, 3, 4, 4]               |
| rest-bp              | continuous | 131.3444 ± 17.8616 [94, 120, 130, 140, 200]   |
| serum-chol           | continuous | 249.6593 ± 51.6862 [126, 213, 245, 280, 564]  |
| fasting-blood-sugar  | continuous | 0.1481 ± 0.3559 [0, 0, 0, 0, 1]               |
| electrocardiographic | continuous | 1.0222 ± 0.9979 [0, 0, 2, 2, 2]               |
| max-heart-rate       | continuous | 149.6778 ± 23.1657 [71, 133, 153.5, 166, 202] |
| angina               | continuous | 0.3296 ± 0.4710 [0, 0, 0, 1, 1]               |
| oldpeak              | continuous | 1.0500 ± 1.1452 [0, 0, 0.8, 1.6, 6.2]         |
| slope                | continuous | 1.5852 ± 0.6144 [1, 1, 2, 2, 3]               |
| major-vessels        | continuous | 0.6704 ± 0.9439 [0, 0, 0, 1, 3]               |
| thal                 | continuous | 4.6963 ± 1.9407 [3, 3, 3, 7, 7]               |
| heart-disease        | discrete   | 1: 150 (55.56%)                               |

## Missingness model

- Columns with learned missingness: 0 of 14
- Columns without missingness: 14No columns required missingness injection.

## Fidelity summary

| model        | backend   |   disc_jsd_mean |   disc_jsd_median |   cont_ks_mean |   cont_w1_mean | privacy_overlap   | downstream_sign_match   |
|:-------------|:----------|----------------:|------------------:|---------------:|---------------:|:------------------|:------------------------|
| metasyn      | metasyn   |          0.1074 |            0.0871 |         0.1859 |         3.779  |                   |                         |
| metasyn_full | metasyn   |          0.1044 |            0.0935 |         0.1889 |         4.2565 |                   |                         |
| clg_mi2      | pybnesian |          0.0928 |            0.078  |         0.1504 |         3.3633 |                   |                         |
| semi_mi5     | pybnesian |          0.0928 |            0.078  |         0.1459 |         3.23   |                   |                         |
| ctgan_fast   | synthcity |          0.3521 |            0.3518 |         0.6933 |        35.8363 |                   |                         |
| tvae_quick   | synthcity |          0.1147 |            0.134  |         0.2578 |         8.0448 |                   |                         |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 270</li>
<li> <a href="models/metasyn/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: metasyn_full (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 270</li>
<li> <a href="models/metasyn_full/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn_full/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn_full/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 270</li>
<li> Params: <tt>{"max_indegree": 2, "operators": ["arcs"], "score": "bic", "type": "clg"}</tt></li><li> <a href="models/clg_mi2/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/clg_mi2/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/clg_mi2/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 270</li>
<li> Params: <tt>{"max_indegree": 5, "operators": ["arcs"], "score": "bic", "type": "semiparametric"}</tt></li><li> <a href="models/semi_mi5/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/semi_mi5/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/semi_mi5/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: ctgan_fast (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 270</li>
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li><li> <a href="models/ctgan_fast/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/ctgan_fast/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/ctgan_fast/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 270</li>
<li> Params: <tt>{"batch_size": 256}</tt></li><li> <a href="models/tvae_quick/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/tvae_quick/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/tvae_quick/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

</table>
