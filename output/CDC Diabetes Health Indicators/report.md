# Data Report — CDC Diabetes Health Indicators

**Source**: [UCI dataset 891](https://archive.ics.uci.edu/dataset/891)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | CDC Diabetes Health Indicators                                                |
| Source      | [UCI dataset 891](https://archive.ics.uci.edu/dataset/891)                    |
| Rows        | 253,680                                                                       |
| Columns     | 22                                                                            |
| Discrete    | 19                                                                            |
| Continuous  | 3                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | Not modeled                                                                   |

## Variables and summary

| variable             | inferred   | dist                                                                                                                                                                                                                                            |
|:---------------------|:-----------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| HighBP               | discrete   | 1: 108829 (42.90%)                                                                                                                                                                                                                              |
| HighChol             | discrete   | 1: 107591 (42.41%)                                                                                                                                                                                                                              |
| CholCheck            | discrete   | 1: 244210 (96.27%)                                                                                                                                                                                                                              |
| BMI                  | continuous | 28.3824 ± 6.6087 [12, 24, 27, 31, 98]                                                                                                                                                                                                           |
| Smoker               | discrete   | 1: 112423 (44.32%)                                                                                                                                                                                                                              |
| Stroke               | discrete   | 1: 10292 (4.06%)                                                                                                                                                                                                                                |
| HeartDiseaseorAttack | discrete   | 1: 23893 (9.42%)                                                                                                                                                                                                                                |
| PhysActivity         | discrete   | 1: 191920 (75.65%)                                                                                                                                                                                                                              |
| Fruits               | discrete   | 1: 160898 (63.43%)                                                                                                                                                                                                                              |
| Veggies              | discrete   | 1: 205841 (81.14%)                                                                                                                                                                                                                              |
| HvyAlcoholConsump    | discrete   | 1: 14256 (5.62%)                                                                                                                                                                                                                                |
| AnyHealthcare        | discrete   | 1: 241263 (95.11%)                                                                                                                                                                                                                              |
| NoDocbcCost          | discrete   | 1: 21354 (8.42%)                                                                                                                                                                                                                                |
| GenHlth              | discrete   | 2: 89084 (35.12%)<br />3: 75646 (29.82%)<br />1: 45299 (17.86%)<br />4: 31570 (12.44%)<br />5: 12081 (4.76%)                                                                                                                                    |
| MentHlth             | continuous | 3.1848 ± 7.4128 [0, 0, 0, 2, 30]                                                                                                                                                                                                                |
| PhysHlth             | continuous | 4.2421 ± 8.7180 [0, 0, 0, 3, 30]                                                                                                                                                                                                                |
| DiffWalk             | discrete   | 1: 42675 (16.82%)                                                                                                                                                                                                                               |
| Sex                  | discrete   | 1: 111706 (44.03%)                                                                                                                                                                                                                              |
| Age                  | discrete   | 9: 33244 (13.10%)<br />10: 32194 (12.69%)<br />8: 30832 (12.15%)<br />7: 26314 (10.37%)<br />11: 23533 (9.28%)<br />6: 19819 (7.81%)<br />13: 17363 (6.84%)<br />5: 16157 (6.37%)<br />12: 15980 (6.30%)<br />4: 13823 (5.45%)<br />… (+3 more) |
| Education            | discrete   | 6: 107325 (42.31%)<br />5: 69910 (27.56%)<br />4: 62750 (24.74%)<br />3: 9478 (3.74%)<br />2: 4043 (1.59%)<br />1: 174 (0.07%)                                                                                                                  |
| Income               | discrete   | 8: 90385 (35.63%)<br />7: 43219 (17.04%)<br />6: 36470 (14.38%)<br />5: 25883 (10.20%)<br />4: 20135 (7.94%)<br />3: 15994 (6.30%)<br />2: 11783 (4.64%)<br />1: 9811 (3.87%)                                                                   |
| Diabetes_binary      | discrete   | 1: 35346 (13.93%)                                                                                                                                                                                                                               |

## Fidelity summary

| model      | backend   |   disc_jsd_mean |   disc_jsd_median |   cont_ks_mean |   cont_w1_mean | privacy_overlap   | downstream_sign_match   |
|:-----------|:----------|----------------:|------------------:|---------------:|---------------:|:------------------|:------------------------|
| metasyn    | metasyn   |          0.0408 |            0.0369 |         0.4563 |         2.2709 |                   |                         |
| clg_mi2    | pybnesian |          0.0436 |            0.0312 |         0.2663 |         3.0082 |                   |                         |
| semi_mi5   | pybnesian |          0.0388 |            0.0244 |         0.263  |         2.9479 |                   |                         |
| ctgan_fast | synthcity |          0.2383 |            0.2151 |         0.8227 |         6.1013 |                   |                         |
| tvae_quick | synthcity |          0.1005 |            0.0882 |         0.394  |         1.949  |                   |                         |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td><img src='umap_real.png' width='280'/></td><td>
<h3>Real data</h3></td><td></td></tr>
<tr><td><img src='models/metasyn/umap.png' width='280'/></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 1000</li>
<li> <a href="models/metasyn/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td><img src='models/clg_mi2/umap.png' width='280'/></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 1000</li>
<li> Params: <tt>{"max_indegree": 2, "operators": ["arcs"], "score": "bic", "type": "clg"}</tt></li><li> <a href="models/clg_mi2/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/clg_mi2/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/clg_mi2/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
<a href='models/clg_mi2/structure.png'><img src='models/clg_mi2/structure.png' width='280'/></a></td></tr>

<tr><td><img src='models/semi_mi5/umap.png' width='280'/></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 1000</li>
<li> Params: <tt>{"max_indegree": 5, "operators": ["arcs"], "score": "bic", "type": "semiparametric"}</tt></li><li> <a href="models/semi_mi5/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/semi_mi5/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/semi_mi5/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
<a href='models/semi_mi5/structure.png'><img src='models/semi_mi5/structure.png' width='280'/></a></td></tr>

<tr><td><img src='models/ctgan_fast/umap.png' width='280'/></td><td>

<h3>Model: ctgan_fast (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 1000</li>
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li><li> <a href="models/ctgan_fast/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/ctgan_fast/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/ctgan_fast/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 1000</li>
<li> Params: <tt>{"batch_size": 256}</tt></li><li> <a href="models/tvae_quick/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/tvae_quick/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/tvae_quick/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

</table>
