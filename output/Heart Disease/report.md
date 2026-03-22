# Data Report — Heart Disease (UCI id 45)

4 databases: Cleveland, Hungary, Switzerland, and the VA Long Beach

**Source**: [UCI dataset 45](https://archive.ics.uci.edu/dataset/45)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Heart Disease (UCI id 45)                                                     |
| Source      | [UCI dataset 45](https://archive.ics.uci.edu/dataset/45)                      |
| Rows        | 297                                                                           |
| Columns     | 14                                                                            |
| Discrete    | 9                                                                             |
| Continuous  | 5                                                                             |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | Not modeled                                                                   |

## Variables and summary

| variable   | inferred   | dist                                                                                                                                                  |
|:-----------|:-----------|:------------------------------------------------------------------------------------------------------------------------------------------------------|
| age        | continuous | 54.5421 ± 9.0497 [29, 48, 56, 61, 77]                                                                                                                 |
| sex        | discrete   | male [1]: 201 (67.68%)                                                                                                                                |
| cp         | discrete   | Asymptomatic [4]: 142 (47.81%)<br />Non-cardiac chest pain [3]: 83 (27.95%)<br />Atypical angina [2]: 49 (16.50%)<br />Typical angina [1]: 23 (7.74%) |
| trestbps   | continuous | 131.6936 ± 17.7628 [94, 120, 130, 140, 200]                                                                                                           |
| chol       | continuous | 247.3502 ± 51.9976 [126, 211, 243, 276, 564]                                                                                                          |
| fbs        | discrete   | >120 mg/dL [1]: 43 (14.48%)                                                                                                                           |
| restecg    | discrete   | normal [0]: 147 (49.49%)<br />LVH (Estes) [2]: 146 (49.16%)<br />ST-T abnormality [1]: 4 (1.35%)                                                      |
| thalach    | continuous | 149.5993 ± 22.9416 [71, 133, 153, 166, 202]                                                                                                           |
| exang      | discrete   | yes [1]: 97 (32.66%)                                                                                                                                  |
| oldpeak    | continuous | 1.0556 ± 1.1661 [0, 0, 0.8, 1.6, 6.2]                                                                                                                 |
| slope      | discrete   | upsloping [1]: 139 (46.80%)<br />flat [2]: 137 (46.13%)<br />downsloping [3]: 21 (7.07%)                                                              |
| ca         | discrete   | 0: 174 (58.59%)<br />1: 65 (21.89%)<br />2: 38 (12.79%)<br />3: 20 (6.73%)                                                                            |
| thal       | discrete   | normal [3]: 164 (55.22%)<br />reversible defect [7]: 115 (38.72%)<br />fixed defect [6]: 18 (6.06%)                                                   |
| num        | discrete   | <50% narrowing [0]: 160 (53.87%)<br />≥50% narrowing [1]: 54 (18.18%)<br />2: 35 (11.78%)<br />3: 35 (11.78%)<br />4: 13 (4.38%)                      |

## Fidelity summary

| model    | backend   |   disc jsd mean |   disc jsd median |   cont ks mean |   cont w1 mean |   downstream sign match |
|:---------|:----------|----------------:|------------------:|---------------:|---------------:|------------------------:|
| metasyn  | metasyn   |          0.0842 |            0.0876 |         0.1837 |         4.0301 |                  0.6316 |
| clg_mi2  | pybnesian |          0.1002 |            0.0941 |         0.1604 |         4.7232 |                         |
| semi_mi5 | pybnesian |          0.1002 |            0.0941 |         0.1604 |         4.7232 |                         |

## Privacy summary

| model    | backend   |   n real |   n synth |   exact overlap rate |   near duplicate rate eps |   nn distance mean |   k min |   k pct lt5 |   k map |   rare qi reproduction rate | identifiability score   |   delta presence |
|:---------|:----------|---------:|----------:|---------------------:|--------------------------:|-------------------:|--------:|------------:|--------:|----------------------------:|:------------------------|-----------------:|
| metasyn  | metasyn   |      297 |       303 |                    0 |                    0.9899 |             0.0644 |       1 |           1 |       4 |                           0 |                         |           1.6923 |
| clg_mi2  | pybnesian |      297 |       303 |                    0 |                    0.9865 |             0.0658 |       1 |           1 |       8 |                           0 |                         |           2.75   |
| semi_mi5 | pybnesian |      297 |       303 |                    0 |                    0.9865 |             0.0658 |       1 |           1 |       8 |                           0 |                         |           2.75   |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td><img src='umap_real.png' width='280'/></td><td>
<h3>Real data</h3></td><td></td></tr>
<tr><td><img src='models/metasyn/umap.png' width='280'/></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 303</li>
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
      <th>KS</th>
      <th>W1</th>
      <th>JSD</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>age</td>
      <td>continuous</td>
      <td>0.0997</td>
      <td>1.296</td>
      <td></td>
    </tr>
    <tr>
      <td>sex</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1341</td>
    </tr>
    <tr>
      <td>cp</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1054</td>
    </tr>
    <tr>
      <td>trestbps</td>
      <td>continuous</td>
      <td>0.1965</td>
      <td>4.2461</td>
      <td></td>
    </tr>
    <tr>
      <td>chol</td>
      <td>continuous</td>
      <td>0.1223</td>
      <td>8.3576</td>
      <td></td>
    </tr>
    <tr>
      <td>fbs</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0414</td>
    </tr>
    <tr>
      <td>restecg</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0718</td>
    </tr>
    <tr>
      <td>thalach</td>
      <td>continuous</td>
      <td>0.2168</td>
      <td>6.0568</td>
      <td></td>
    </tr>
    <tr>
      <td>exang</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0705</td>
    </tr>
    <tr>
      <td>oldpeak</td>
      <td>continuous</td>
      <td>0.2833</td>
      <td>0.194</td>
      <td></td>
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
      <td>0.6316</td>
    </tr>
    <tr>
      <td>formula</td>
      <td>num ~ Q('age') + Q('sex') + Q('cp') + Q('fbs') + Q('trestbps') + Q('chol') + Q('restecg') + Q('thalach') + Q('exang') + Q('oldpeak') + Q('slope') + Q('ca') + Q('thal') + Q('age'):Q('sex') + Q('sex'):Q('cp') + Q('cp'):Q('fbs') + Q('fbs'):Q('trestbps') + Q('trestbps'):Q('chol')</td>
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
      <td>297</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>303</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9899</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0644</td>
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
      <td>4</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>1.6923</td>
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
      <td>age</td>
      <td>core.normal</td>
    </tr>
    <tr>
      <td>sex</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>cp</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>trestbps</td>
      <td>core.lognormal</td>
    </tr>
    <tr>
      <td>chol</td>
      <td>core.lognormal</td>
    </tr>
    <tr>
      <td>fbs</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>restecg</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>thalach</td>
      <td>core.normal</td>
    </tr>
    <tr>
      <td>exang</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>oldpeak</td>
      <td>core.truncated_normal</td>
    </tr>
    <tr>
      <td>slope</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>ca</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>thal</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>num</td>
      <td>core.multinoulli</td>
    </tr>
  </tbody>
</table></td></tr>

<tr><td><img src='models/clg_mi2/umap.png' width='280'/></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 303</li>
<li> Params: <tt>{"max_indegree": 2, "operators": ["arcs"], "score": "bic", "type": "clg"}</tt></li><li> <a href="models/clg_mi2/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/clg_mi2/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/clg_mi2/metrics.json">Metrics JSON</a></li>
<li> <a href="models/clg_mi2/metrics.privacy.json">Privacy metrics</a></li>
</ul>
<details class="model-subtable"><summary><strong>Per-variable fidelity</strong></summary>
<table class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th>variable</th>
      <th>type</th>
      <th>KS</th>
      <th>W1</th>
      <th>JSD</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>age</td>
      <td>continuous</td>
      <td>0.0838</td>
      <td>1.1178</td>
      <td></td>
    </tr>
    <tr>
      <td>sex</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0941</td>
    </tr>
    <tr>
      <td>cp</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1516</td>
    </tr>
    <tr>
      <td>trestbps</td>
      <td>continuous</td>
      <td>0.1645</td>
      <td>3.4709</td>
      <td></td>
    </tr>
    <tr>
      <td>chol</td>
      <td>continuous</td>
      <td>0.1784</td>
      <td>11.0214</td>
      <td></td>
    </tr>
    <tr>
      <td>fbs</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1171</td>
    </tr>
    <tr>
      <td>restecg</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.126</td>
    </tr>
    <tr>
      <td>thalach</td>
      <td>continuous</td>
      <td>0.2135</td>
      <td>7.7047</td>
      <td></td>
    </tr>
    <tr>
      <td>exang</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1121</td>
    </tr>
    <tr>
      <td>oldpeak</td>
      <td>continuous</td>
      <td>0.1617</td>
      <td>0.301</td>
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
      <td>297</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>303</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9865</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0658</td>
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
      <td>8</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>2.75</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<a href='models/clg_mi2/structure.png'><img src='models/clg_mi2/structure.png' width='280'/></a></td></tr>

<tr><td><img src='models/semi_mi5/umap.png' width='280'/></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 303</li>
<li> Params: <tt>{"max_indegree": 5, "operators": ["arcs"], "score": "bic", "type": "semiparametric"}</tt></li><li> <a href="models/semi_mi5/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/semi_mi5/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/semi_mi5/metrics.json">Metrics JSON</a></li>
<li> <a href="models/semi_mi5/metrics.privacy.json">Privacy metrics</a></li>
</ul>
<details class="model-subtable"><summary><strong>Per-variable fidelity</strong></summary>
<table class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th>variable</th>
      <th>type</th>
      <th>KS</th>
      <th>W1</th>
      <th>JSD</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>age</td>
      <td>continuous</td>
      <td>0.0838</td>
      <td>1.1178</td>
      <td></td>
    </tr>
    <tr>
      <td>sex</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0941</td>
    </tr>
    <tr>
      <td>cp</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1516</td>
    </tr>
    <tr>
      <td>trestbps</td>
      <td>continuous</td>
      <td>0.1645</td>
      <td>3.4709</td>
      <td></td>
    </tr>
    <tr>
      <td>chol</td>
      <td>continuous</td>
      <td>0.1784</td>
      <td>11.0214</td>
      <td></td>
    </tr>
    <tr>
      <td>fbs</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1171</td>
    </tr>
    <tr>
      <td>restecg</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.126</td>
    </tr>
    <tr>
      <td>thalach</td>
      <td>continuous</td>
      <td>0.2135</td>
      <td>7.7047</td>
      <td></td>
    </tr>
    <tr>
      <td>exang</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1121</td>
    </tr>
    <tr>
      <td>oldpeak</td>
      <td>continuous</td>
      <td>0.1617</td>
      <td>0.301</td>
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
      <td>297</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>303</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9865</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0658</td>
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
      <td>8</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>2.75</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<a href='models/semi_mi5/structure.png'><img src='models/semi_mi5/structure.png' width='280'/></a></td></tr>

</table>