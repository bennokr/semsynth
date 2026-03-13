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
| Discrete    | 9                                                                             |
| Continuous  | 5                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | Not modeled                                                                   |

## Variables and summary

| variable             | inferred   | dist                                                                       |
|:---------------------|:-----------|:---------------------------------------------------------------------------|
| age                  | continuous | 54.4333 ± 9.1091 [29, 48, 55, 61, 77]                                      |
| sex                  | discrete   | 1: 183 (67.78%)                                                            |
| chest-pain           | discrete   | 4: 129 (47.78%)<br />3: 79 (29.26%)<br />2: 42 (15.56%)<br />1: 20 (7.41%) |
| rest-bp              | continuous | 131.3444 ± 17.8616 [94, 120, 130, 140, 200]                                |
| serum-chol           | continuous | 249.6593 ± 51.6862 [126, 213, 245, 280, 564]                               |
| fasting-blood-sugar  | discrete   | 1: 40 (14.81%)                                                             |
| electrocardiographic | discrete   | 2: 137 (50.74%)<br />0: 131 (48.52%)<br />1: 2 (0.74%)                     |
| max-heart-rate       | continuous | 149.6778 ± 23.1657 [71, 133, 153.5, 166, 202]                              |
| angina               | discrete   | 1: 89 (32.96%)                                                             |
| oldpeak              | continuous | 1.0500 ± 1.1452 [0, 0, 0.8, 1.6, 6.2]                                      |
| slope                | discrete   | 1: 130 (48.15%)<br />2: 122 (45.19%)<br />3: 18 (6.67%)                    |
| major-vessels        | discrete   | 0: 160 (59.26%)<br />1: 58 (21.48%)<br />2: 33 (12.22%)<br />3: 19 (7.04%) |
| thal                 | discrete   | 3: 152 (56.30%)<br />7: 104 (38.52%)<br />6: 14 (5.19%)                    |
| heart-disease        | discrete   | 1: 150 (55.56%)                                                            |

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
