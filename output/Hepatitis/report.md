# Data Report — Hepatitis

**Source**: [UCI dataset 46](https://archive.ics.uci.edu/dataset/46)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Hepatitis                                                                     |
| Source      | [UCI dataset 46](https://archive.ics.uci.edu/dataset/46)                      |
| Rows        | 80                                                                            |
| Columns     | 20                                                                            |
| Discrete    | 14                                                                            |
| Continuous  | 6                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | modeled 15 of 20 (seed 42)                                                    |

## Variables and summary

| variable        | inferred   | dist                                             |
|:----------------|:-----------|:-------------------------------------------------|
| Age             | continuous | 40.6625 ± 11.2800 [20, 32, 38.5, 49.25, 72]      |
| Sex             | discrete   | 1: 69 (86.25%)                                   |
| Steroid         | discrete   | 1: 38 (47.50%)                                   |
| Antivirals      | discrete   | 1: 21 (26.25%)                                   |
| Fatigue         | discrete   | 1: 52 (65.00%)                                   |
| Malaise         | discrete   | 1: 31 (38.75%)                                   |
| Anorexia        | discrete   | 1: 12 (15.00%)                                   |
| Liver Big       | discrete   | 1: 13 (16.25%)                                   |
| Liver Firm      | discrete   | 1: 38 (47.50%)                                   |
| Spleen Palpable | discrete   | 1: 15 (18.75%)                                   |
| Spiders         | discrete   | 1: 25 (31.25%)                                   |
| Ascites         | discrete   | 1: 12 (15.00%)                                   |
| Varices         | discrete   | 1: 10 (12.50%)                                   |
| Bilirubin       | continuous | 1.2212 ± 0.8752 [0.3, 0.7, 1, 1.3, 4.8]          |
| Alk Phosphate   | continuous | 102.9125 ± 53.6848 [26, 68.25, 85, 133.5, 280]   |
| Sgot            | continuous | 82.0250 ± 71.6000 [14, 30.75, 56.5, 102.75, 420] |
| Albumin         | continuous | 3.8438 ± 0.5763 [2.1, 3.5, 4, 4.2, 5]            |
| Protime         | continuous | 62.5125 ± 23.4278 [0, 46, 62, 77.25, 100]        |
| Histology       | discrete   | 1: 47 (58.75%)                                   |
| Class           | discrete   | 1: 13 (16.25%)                                   |

## Missingness model

- Columns with learned missingness: 15 of 20
- Columns without missingness: 5| Column          |   Missing rate |   Missing % |
|:----------------|---------------:|------------:|
| Protime         |         0.4323 |       43.23 |
| Alk Phosphate   |         0.1871 |       18.71 |
| Albumin         |         0.1032 |       10.32 |
| Liver Firm      |         0.071  |        7.1  |
| Liver Big       |         0.0645 |        6.45 |
| Bilirubin       |         0.0387 |        3.87 |
| Ascites         |         0.0323 |        3.23 |
| Varices         |         0.0323 |        3.23 |
| Spiders         |         0.0323 |        3.23 |
| Spleen Palpable |         0.0323 |        3.23 |
| Sgot            |         0.0258 |        2.58 |
| Fatigue         |         0.0065 |        0.65 |
| Anorexia        |         0.0065 |        0.65 |
| Malaise         |         0.0065 |        0.65 |
| Steroid         |         0.0065 |        0.65 |
## Fidelity summary

| model      | backend   |   disc_jsd_mean |   disc_jsd_median | cont_ks_mean   | cont_w1_mean   |   privacy_overlap |   downstream_sign_match |
|:-----------|:----------|----------------:|------------------:|:---------------|:---------------|------------------:|------------------------:|
| metasyn    | metasyn   |                 |                   |                |                |                   |                         |
| clg_mi2    | pybnesian |          0.0805 |            0.0329 |                |                |                 0 |                  0.2931 |
| semi_mi5   | pybnesian |          0.0805 |            0.0329 |                |                |                 0 |                  0.3103 |
| ctgan_fast | synthcity |                 |                   |                |                |                   |                         |
| tvae_quick | synthcity |                 |                   |                |                |                   |                         |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 155</li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 155</li>
<li> Params: <tt>{"max_indegree": 2, "operators": ["arcs"], "score": "bic", "type": "clg"}</tt></li><li> <a href="models/clg_mi2/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/clg_mi2/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/clg_mi2/metrics.json">Metrics JSON</a></li>
<li> <a href="models/clg_mi2/metrics.privacy.json">Privacy metrics</a></li>
<li> <a href="models/clg_mi2/metrics.downstream.json">Downstream metrics</a></li>
</ul>

</td><td>
<a href='models/clg_mi2/structure.png'><img src='models/clg_mi2/structure.png' width='280'/></a></td></tr>

<tr><td></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 155</li>
<li> Params: <tt>{"max_indegree": 5, "operators": ["arcs"], "score": "bic", "type": "semiparametric"}</tt></li><li> <a href="models/semi_mi5/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/semi_mi5/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/semi_mi5/metrics.json">Metrics JSON</a></li>
<li> <a href="models/semi_mi5/metrics.privacy.json">Privacy metrics</a></li>
<li> <a href="models/semi_mi5/metrics.downstream.json">Downstream metrics</a></li>
</ul>

</td><td>
<a href='models/semi_mi5/structure.png'><img src='models/semi_mi5/structure.png' width='280'/></a></td></tr>

<tr><td></td><td>

<h3>Model: ctgan_fast (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 155</li>
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li></ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 155</li>
<li> Params: <tt>{"batch_size": 256}</tt></li></ul>

</td><td>
</td></tr>

</table>
