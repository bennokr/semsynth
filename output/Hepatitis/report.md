# Data Report — Hepatitis

**Source**: [UCI dataset 46](https://archive.ics.uci.edu/dataset/46)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Hepatitis                                                                     |
| Source      | [UCI dataset 46](https://archive.ics.uci.edu/dataset/46)                      |
| Rows        | 155                                                                           |
| Columns     | 20                                                                            |
| Discrete    | 20                                                                            |
| Continuous  | 0                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | Not modeled                                                                   |

## Variables and summary

| variable        | inferred   | dist   |
|:----------------|:-----------|:-------|
| Age             | discrete   |        |
| Sex             | discrete   |        |
| Steroid         | discrete   |        |
| Antivirals      | discrete   |        |
| Fatigue         | discrete   |        |
| Malaise         | discrete   |        |
| Anorexia        | discrete   |        |
| Liver Big       | discrete   |        |
| Liver Firm      | discrete   |        |
| Spleen Palpable | discrete   |        |
| Spiders         | discrete   |        |
| Ascites         | discrete   |        |
| Varices         | discrete   |        |
| Bilirubin       | discrete   |        |
| Alk Phosphate   | discrete   |        |
| Sgot            | discrete   |        |
| Albumin         | discrete   |        |
| Protime         | discrete   |        |
| Histology       | discrete   |        |
| Class           | discrete   |        |

## Fidelity summary

| model      | backend   |   disc_jsd_mean |   disc_jsd_median | cont_ks_mean   | cont_w1_mean   |   privacy_overlap |   downstream_sign_match |
|:-----------|:----------|----------------:|------------------:|:---------------|:---------------|------------------:|------------------------:|
| metasyn    | metasyn   |                 |                   |                |                |                 0 |                  0.2414 |
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
<li> <a href="models/metasyn/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn/metrics.json">Metrics JSON</a></li>
<li> <a href="models/metasyn/metrics.privacy.json">Privacy metrics</a></li>
<li> <a href="models/metasyn/metrics.downstream.json">Downstream metrics</a></li>
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
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li><li> <a href="models/ctgan_fast/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/ctgan_fast/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/ctgan_fast/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 155</li>
<li> Params: <tt>{"batch_size": 256}</tt></li><li> <a href="models/tvae_quick/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/tvae_quick/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/tvae_quick/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

</table>
