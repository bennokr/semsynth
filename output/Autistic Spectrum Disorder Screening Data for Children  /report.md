# Data Report — Autistic Spectrum Disorder Screening Data for Children  

**Source**: [UCI dataset 419](https://archive.ics.uci.edu/dataset/419)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Autistic Spectrum Disorder Screening Data for Children                        |
| Source      | [UCI dataset 419](https://archive.ics.uci.edu/dataset/419)                    |
| Rows        | 248                                                                           |
| Columns     | 21                                                                            |
| Discrete    | 20                                                                            |
| Continuous  | 1                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | Not modeled                                                                   |

## Variables and summary

| variable        | inferred   | dist                                                                                                                                                                                                                                                                                                            |
|:----------------|:-----------|:----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A1_Score        | discrete   | 1: 170 (68.55%)                                                                                                                                                                                                                                                                                                 |
| A2_Score        | discrete   | 1: 128 (51.61%)                                                                                                                                                                                                                                                                                                 |
| A3_Score        | discrete   | 1: 185 (74.60%)                                                                                                                                                                                                                                                                                                 |
| A4_Score        | discrete   | 1: 142 (57.26%)                                                                                                                                                                                                                                                                                                 |
| A5_Score        | discrete   | 1: 187 (75.40%)                                                                                                                                                                                                                                                                                                 |
| A6_Score        | discrete   | 1: 177 (71.37%)                                                                                                                                                                                                                                                                                                 |
| A7_Score        | discrete   | 1: 155 (62.50%)                                                                                                                                                                                                                                                                                                 |
| A8_Score        | discrete   | 1: 119 (47.98%)                                                                                                                                                                                                                                                                                                 |
| A9_Score        | discrete   | 1: 134 (54.03%)                                                                                                                                                                                                                                                                                                 |
| A10_Score       | discrete   | 1: 182 (73.39%)                                                                                                                                                                                                                                                                                                 |
| age             | continuous | 6.4274 ± 2.3864 [4, 4, 6, 8, 11]                                                                                                                                                                                                                                                                                |
| gender          | discrete   | m: 174 (70.16%)                                                                                                                                                                                                                                                                                                 |
| ethnicity       | discrete   | White-European: 108 (43.55%)<br />Asian: 46 (18.55%)<br />'Middle Eastern ': 26 (10.48%)<br />'South Asian': 21 (8.47%)<br />Black: 14 (5.65%)<br />Others: 14 (5.65%)<br />Latino: 8 (3.23%)<br />Hispanic: 7 (2.82%)<br />Pasifika: 2 (0.81%)<br />Turkish: 2 (0.81%)                                         |
| jaundice        | discrete   | yes: 61 (24.60%)                                                                                                                                                                                                                                                                                                |
| autism          | discrete   | yes: 45 (18.15%)                                                                                                                                                                                                                                                                                                |
| country_of_res  | discrete   | 'United Kingdom': 49 (19.76%)<br />'United States': 42 (16.94%)<br />India: 42 (16.94%)<br />Australia: 23 (9.27%)<br />'New Zealand': 13 (5.24%)<br />Jordan: 9 (3.63%)<br />Canada: 7 (2.82%)<br />Bangladesh: 6 (2.42%)<br />'United Arab Emirates': 5 (2.02%)<br />Philippines: 4 (1.61%)<br />… (+42 more) |
| used_app_before | discrete   | yes: 6 (2.42%)                                                                                                                                                                                                                                                                                                  |
| result          | discrete   | 8: 37 (14.92%)<br />7: 36 (14.52%)<br />6: 34 (13.71%)<br />9: 32 (12.90%)<br />4: 30 (12.10%)<br />5: 28 (11.29%)<br />10: 21 (8.47%)<br />3: 16 (6.45%)<br />2: 8 (3.23%)<br />1: 5 (2.02%)<br />… (+1 more)                                                                                                  |
| age_desc        | discrete   | '4-11 years': 248 (100.00%)                                                                                                                                                                                                                                                                                     |
| relation        | discrete   | Parent: 213 (85.89%)<br />Relative: 17 (6.85%)<br />'Health care professional': 13 (5.24%)<br />Self: 4 (1.61%)<br />self: 1 (0.40%)                                                                                                                                                                            |
| class           | discrete   | YES: 126 (50.81%)                                                                                                                                                                                                                                                                                               |

## Fidelity summary

| model      | backend   |   disc_jsd_mean |   disc_jsd_median |   cont_ks_mean |   cont_w1_mean | privacy_overlap   | downstream_sign_match   |
|:-----------|:----------|----------------:|------------------:|---------------:|---------------:|:------------------|:------------------------|
| metasyn    | metasyn   |          0.1038 |            0.0714 |         0.28   |         0.6037 |                   |                         |
| clg_mi2    | pybnesian |          0.1018 |            0.0576 |         0.2759 |         0.8696 |                   |                         |
| semi_mi5   | pybnesian |          0.1018 |            0.0576 |         0.2759 |         0.8696 |                   |                         |
| ctgan_fast | synthcity |          0.3058 |            0.2503 |         0.1834 |         0.777  |                   |                         |
| tvae_quick | synthcity |          0.1649 |            0.1167 |         0.131  |         0.3644 |                   |                         |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 292</li>
<li> <a href="models/metasyn/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 292</li>
<li> Params: <tt>{"max_indegree": 2, "operators": ["arcs"], "score": "bic", "type": "clg"}</tt></li><li> <a href="models/clg_mi2/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/clg_mi2/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/clg_mi2/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 292</li>
<li> Params: <tt>{"max_indegree": 5, "operators": ["arcs"], "score": "bic", "type": "semiparametric"}</tt></li><li> <a href="models/semi_mi5/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/semi_mi5/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/semi_mi5/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: ctgan_fast (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 292</li>
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li><li> <a href="models/ctgan_fast/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/ctgan_fast/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/ctgan_fast/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

<tr><td></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 292</li>
<li> Params: <tt>{"batch_size": 256}</tt></li><li> <a href="models/tvae_quick/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/tvae_quick/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/tvae_quick/metrics.json">Metrics JSON</a></li>
</ul>

</td><td>
</td></tr>

</table>
