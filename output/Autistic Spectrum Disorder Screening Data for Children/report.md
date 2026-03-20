# Data Report — Autistic Spectrum Disorder Screening Data for Children

see attached file for variables' description 

**Documentation**: see attached file for variables' description 

**Source**: [UCI dataset 419](https://archive.ics.uci.edu/dataset/419)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Autistic Spectrum Disorder Screening Data for Children                        |
| Source      | [UCI dataset 419](https://archive.ics.uci.edu/dataset/419)                    |
| Rows        | 248                                                                           |
| Columns     | 21                                                                            |
| Discrete    | 21                                                                            |
| Continuous  | 0                                                                             |
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
| age             | discrete   | 4: 78 (31.45%)<br />5: 36 (14.52%)<br />6: 33 (13.31%)<br />7: 24 (9.68%)<br />11: 23 (9.27%)<br />8: 20 (8.06%)<br />9: 17 (6.85%)<br />10: 17 (6.85%)                                                                                                                                                         |
| gender          | discrete   | m: 174 (70.16%)                                                                                                                                                                                                                                                                                                 |
| ethnicity       | discrete   | White-European: 108 (43.55%)<br />Asian: 46 (18.55%)<br />'Middle Eastern ': 26 (10.48%)<br />'South Asian': 21 (8.47%)<br />Others: 14 (5.65%)<br />Black: 14 (5.65%)<br />Latino: 8 (3.23%)<br />Hispanic: 7 (2.82%)<br />Pasifika: 2 (0.81%)<br />Turkish: 2 (0.81%)                                         |
| jaundice        | discrete   | yes: 61 (24.60%)                                                                                                                                                                                                                                                                                                |
| autism          | discrete   | yes: 45 (18.15%)                                                                                                                                                                                                                                                                                                |
| country_of_res  | discrete   | 'United Kingdom': 49 (19.76%)<br />'United States': 42 (16.94%)<br />India: 42 (16.94%)<br />Australia: 23 (9.27%)<br />'New Zealand': 13 (5.24%)<br />Jordan: 9 (3.63%)<br />Canada: 7 (2.82%)<br />Bangladesh: 6 (2.42%)<br />'United Arab Emirates': 5 (2.02%)<br />Philippines: 4 (1.61%)<br />… (+42 more) |
| used_app_before | discrete   | yes: 6 (2.42%)                                                                                                                                                                                                                                                                                                  |
| result          | discrete   | 8: 37 (14.92%)<br />7: 36 (14.52%)<br />6: 34 (13.71%)<br />9: 32 (12.90%)<br />4: 30 (12.10%)<br />5: 28 (11.29%)<br />10: 21 (8.47%)<br />3: 16 (6.45%)<br />2: 8 (3.23%)<br />1: 5 (2.02%)<br />… (+1 more)                                                                                                  |
| age_desc        | discrete   | '4-11 years': 248 (100.00%)                                                                                                                                                                                                                                                                                     |
| relation        | discrete   | Parent: 213 (85.89%)<br />Relative: 17 (6.85%)<br />'Health care professional': 13 (5.24%)<br />Self: 4 (1.61%)<br />self: 1 (0.40%)                                                                                                                                                                            |
| class           | discrete   | YES: 126 (50.81%)                                                                                                                                                                                                                                                                                               |

## Fidelity summary

| model   | backend   |   disc jsd mean |   disc jsd median | cont ks mean   | cont w1 mean   |   downstream sign match |
|:--------|:----------|----------------:|------------------:|:---------------|:---------------|------------------------:|
| metasyn | metasyn   |          0.1032 |            0.0714 |                |                |                  0.6111 |

## Privacy summary

| model   | backend   |   n real |   n synth |   exact overlap rate |   near duplicate rate eps |   nn distance mean |   k min |   k pct lt5 |   k map |   rare qi reproduction rate | identifiability score   |   delta presence |
|:--------|:----------|---------:|----------:|---------------------:|--------------------------:|-------------------:|--------:|------------:|--------:|----------------------------:|:------------------------|-----------------:|
| metasyn | metasyn   |      248 |       292 |                    0 |                    0.1411 |             0.3179 |       1 |           1 |       7 |                           0 |                         |           2.2143 |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td><img src='umap_real.png' width='280'/></td><td>
<h3>Real data</h3></td><td></td></tr>
<tr><td><img src='models/metasyn/umap.png' width='280'/></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 292</li>
<li> <a href="models/metasyn/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/metasyn/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/metasyn/metrics.json">Metrics JSON</a></li>
<li> <a href="models/metasyn/metrics.privacy.json">Privacy metrics</a></li>
<li> <a href="models/metasyn/metrics.downstream.json">Downstream metrics</a></li>
</ul>
<details class="model-subtable"><summary><strong>Per-variable fidelity</strong></summary>
<table class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th>variable</th>
      <th>type</th>
      <th>JSD</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A1_Score</td>
      <td>discrete</td>
      <td>0.0172</td>
    </tr>
    <tr>
      <td>A2_Score</td>
      <td>discrete</td>
      <td>0.0191</td>
    </tr>
    <tr>
      <td>A3_Score</td>
      <td>discrete</td>
      <td>0.076</td>
    </tr>
    <tr>
      <td>A4_Score</td>
      <td>discrete</td>
      <td>0.019</td>
    </tr>
    <tr>
      <td>A5_Score</td>
      <td>discrete</td>
      <td>0.1533</td>
    </tr>
    <tr>
      <td>A6_Score</td>
      <td>discrete</td>
      <td>0.0064</td>
    </tr>
    <tr>
      <td>A7_Score</td>
      <td>discrete</td>
      <td>0.1116</td>
    </tr>
    <tr>
      <td>A8_Score</td>
      <td>discrete</td>
      <td>0.0078</td>
    </tr>
    <tr>
      <td>A9_Score</td>
      <td>discrete</td>
      <td>0.0535</td>
    </tr>
    <tr>
      <td>A10_Score</td>
      <td>discrete</td>
      <td>0.0659</td>
    </tr>
  </tbody>
</table>
</details><details class="model-subtable"><summary><strong>Downstream metrics</strong></summary>
<table class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th>metric</th>
      <th>value</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>sign_match_rate</td>
      <td>0.6111</td>
    </tr>
    <tr>
      <td>formula</td>
      <td>col_class ~ Q('A1_Score') + Q('A2_Score') + Q('A3_Score') + Q('A4_Score') + Q('A5_Score') + Q('A6_Score') + Q('A7_Score') + Q('A8_Score') + Q('A9_Score') + Q('A10_Score') + Q('age') + Q('result') + Q('A1_Score'):Q('A2_Score') + Q('A2_Score'):Q('A3_Score') + Q('A3_Score'):Q('A4_Score') + Q('A4_Score'):Q('A5_Score') + Q('A5_Score'):Q('A6_Score')</td>
    </tr>
    <tr>
      <td>skipped_reason</td>
      <td></td>
    </tr>
  </tbody>
</table>
</details><details class="model-subtable"><summary><strong>Privacy metrics</strong></summary>
<table class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th>metric</th>
      <th>value</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>n_real</td>
      <td>248</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>292</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.1411</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.3179</td>
    </tr>
    <tr>
      <td>k_min</td>
      <td>1</td>
    </tr>
    <tr>
      <td>k_pct_lt5</td>
      <td>1</td>
    </tr>
    <tr>
      <td>k_map</td>
      <td>7</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>2.2143</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<table class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th>variable</th>
      <th>distribution</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A1_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A2_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A3_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A4_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A5_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A6_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A7_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A8_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A9_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>A10_Score</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>age</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>gender</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>ethnicity</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>jaundice</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>autism</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>country_of_res</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>used_app_before</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>result</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>age_desc</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>relation</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>class</td>
      <td>core.multinoulli</td>
    </tr>
  </tbody>
</table></td></tr>

</table>