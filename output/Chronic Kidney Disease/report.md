# Data Report — Chronic Kidney Disease

**Source**: [UCI dataset 336](https://archive.ics.uci.edu/dataset/336)

**SemMap JSON-LD**: [dataset.semmap.json](dataset.semmap.json) · [RDFa HTML](dataset.semmap.html)
## Overview

| Metric      | Value                                                                         |
|:------------|:------------------------------------------------------------------------------|
| Dataset     | Chronic Kidney Disease                                                        |
| Source      | [UCI dataset 336](https://archive.ics.uci.edu/dataset/336)                    |
| Rows        | 158                                                                           |
| Columns     | 25                                                                            |
| Discrete    | 13                                                                            |
| Continuous  | 12                                                                            |
| SemMap      | [SemMap JSON-LD](dataset.semmap.json)<br />[SemMap HTML](dataset.semmap.html) |
| Missingness | Not modeled                                                                   |

## Variables and summary

| variable   | inferred   | dist                                                                                                                                                                                               |
|:-----------|:-----------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| age        | continuous | 49.5633 ± 15.5122 [6, 39.25, 50.5, 60, 83]                                                                                                                                                         |
| bp         | continuous | 74.0506 ± 11.1754 [50, 60, 80, 80, 110]                                                                                                                                                            |
| sg         | continuous | 1.0199 ± 0.0055 [1.005, 1.02, 1.02, 1.025, 1.025]                                                                                                                                                  |
| al         | discrete   | Albumin negative [0]: 116 (73.42%)<br />Albumin 2+ [3]: 15 (9.49%)<br />Albumin 3+ [4]: 15 (9.49%)<br />Albumin 1+ [2]: 9 (5.70%)<br />Trace albumin [1]: 3 (1.90%)<br />Albumin 4+ [5]: 0 (0.00%) |
| su         | discrete   | Sugar negative [0]: 140 (88.61%)<br />Trace sugar [1]: 6 (3.80%)<br />Sugar 1+ [2]: 6 (3.80%)<br />Sugar 2+ [3]: 3 (1.90%)<br />Sugar 3+ [4]: 2 (1.27%)<br />Sugar 4+ [5]: 1 (0.63%)               |
| rbc        | discrete   | Normal [normal]: 140 (88.61%)                                                                                                                                                                      |
| pc         | discrete   | Normal [normal]: 129 (81.65%)                                                                                                                                                                      |
| pcc        | discrete   | Not present [notpresent]: 144 (91.14%)                                                                                                                                                             |
| ba         | discrete   | Not present [notpresent]: 146 (92.41%)                                                                                                                                                             |
| bgr        | continuous | 131.3418 ± 64.9398 [70, 97, 115.5, 131.75, 490]                                                                                                                                                    |
| bu         | continuous | 52.5759 ± 47.3954 [10, 26, 39.5, 49.75, 309]                                                                                                                                                       |
| sc         | continuous | 2.1886 ± 3.0776 [0.4, 0.7, 1.1, 1.6, 15.2]                                                                                                                                                         |
| sod        | continuous | 138.8481 ± 7.4894 [111, 135, 139, 144, 150]                                                                                                                                                        |
| pot        | continuous | 4.6367 ± 3.4764 [2.5, 3.7, 4.5, 4.9, 47]                                                                                                                                                           |
| hemo       | continuous | 13.6873 ± 2.8822 [3.1, 12.6, 14.25, 15.775, 17.8]                                                                                                                                                  |
| pcv        | continuous | 41.9177 ± 9.1052 [9, 37.5, 44, 48, 54]                                                                                                                                                             |
| wbcc       | continuous | 8475.9494 ± 3126.8802 [3800, 6525, 7800, 9775, 26400]                                                                                                                                              |
| rbcc       | continuous | 4.8918 ± 1.0194 [2.1, 4.5, 4.95, 5.6, 8]                                                                                                                                                           |
| htn        | discrete   | Yes [yes]: 34 (21.52%)                                                                                                                                                                             |
| dm         | discrete   | No [no]: 130 (82.28%)<br />Yes [yes]: 28 (17.72%)<br />No [no]: 0 (0.00%)                                                                                                                          |
| cad        | discrete   | Yes [yes]: 11 (6.96%)                                                                                                                                                                              |
| appet      | discrete   | Good appetite [good]: 139 (87.97%)                                                                                                                                                                 |
| pe         | discrete   | Yes [yes]: 20 (12.66%)                                                                                                                                                                             |
| ane        | discrete   | Yes [yes]: 16 (10.13%)                                                                                                                                                                             |
| class      | discrete   | Not chronic kidney disease [notckd]: 115 (72.78%)<br />Chronic kidney disease [ckd]: 43 (27.22%)<br />Chronic kidney disease [ckd]: 0 (0.00%)                                                      |

## Fidelity summary

| umap                                                 | model      | backend   |   disc jsd mean |   disc jsd median |   cont ks mean |   cont w1 mean |   downstream sign match |
|:-----------------------------------------------------|:-----------|:----------|----------------:|------------------:|---------------:|---------------:|------------------------:|
| <img src='models/metasyn/umap.png' height='48' />    | metasyn    | metasyn   |          0.0646 |            0.0514 |         0.216  |        56.8532 |                  0.5263 |
| <img src='models/clg_mi2/umap.png' height='48' />    | clg_mi2    | pybnesian |          0.0744 |            0.0752 |         0.1996 |        62.539  |                         |
| <img src='models/semi_mi5/umap.png' height='48' />   | semi_mi5   | pybnesian |          0.0744 |            0.0752 |         0.1996 |        62.539  |                         |
| <img src='models/ctgan_fast/umap.png' height='48' /> | ctgan_fast | synthcity |          0.1733 |            0.1798 |         0.7529 |      1042.22   |                         |
| <img src='models/tvae_quick/umap.png' height='48' /> | tvae_quick | synthcity |          0.1744 |            0.193  |         0.2715 |        86.9495 |                         |

## Privacy summary

| model      | backend   |   n real |   n synth |   exact overlap rate |   near duplicate rate eps |   nn distance mean |   k min |   k pct lt5 |   k map |   rare qi reproduction rate | identifiability score   |   delta presence |
|:-----------|:----------|---------:|----------:|---------------------:|--------------------------:|-------------------:|--------:|------------:|--------:|----------------------------:|:------------------------|-----------------:|
| metasyn    | metasyn   |      158 |       400 |                    0 |                    0.9937 |             0.0165 |       1 |           1 |       1 |                           0 |                         |           2.5714 |
| clg_mi2    | pybnesian |      158 |       400 |                    0 |                    0.9873 |             0.0271 |       1 |           1 |       1 |                           0 |                         |           3.5    |
| semi_mi5   | pybnesian |      158 |       400 |                    0 |                    0.9873 |             0.0271 |       1 |           1 |       1 |                           0 |                         |           3.5    |
| ctgan_fast | synthcity |      158 |       256 |                    0 |                    0.3987 |             0.3484 |       1 |           1 |       1 |                           0 |                         |          28.6    |
| tvae_quick | synthcity |      158 |       256 |                    0 |                    0.9873 |             0.0241 |       1 |           1 |       1 |                           0 |                         |          11      |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
<tr><td><img src='umap_real.png' width='280'/></td><td>
<h3>Real data</h3></td><td></td></tr>
<tr><td><img src='models/metasyn/umap.png' width='280'/></td><td>

<h3>Model: metasyn (metasyn)</h3>
<ul>
<li>Seed: 42, rows: 400</li>
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
      <td>0.1125</td>
      <td>2.3701</td>
      <td></td>
    </tr>
    <tr>
      <td>bp</td>
      <td>continuous</td>
      <td>0.3</td>
      <td>3.9054</td>
      <td></td>
    </tr>
    <tr>
      <td>sg</td>
      <td>continuous</td>
      <td>0.4062</td>
      <td>0.0019</td>
      <td></td>
    </tr>
    <tr>
      <td>al</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.094</td>
    </tr>
    <tr>
      <td>su</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1747</td>
    </tr>
    <tr>
      <td>rbc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0228</td>
    </tr>
    <tr>
      <td>pc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0535</td>
    </tr>
    <tr>
      <td>pcc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0514</td>
    </tr>
    <tr>
      <td>ba</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1342</td>
    </tr>
    <tr>
      <td>bgr</td>
      <td>continuous</td>
      <td>0.2425</td>
      <td>23.229</td>
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
      <td>0.5263</td>
    </tr>
    <tr>
      <td>formula</td>
      <td>col_class ~ Q('age') + Q('bp') + Q('sg') + Q('al') + Q('su') + C(Q('rbc'), levels=['normal', 'abnormal']) + C(Q('pc'), levels=['normal', 'abnormal']) + C(Q('pcc'), levels=['present', 'notpresent']) + C(Q('ba'), levels=['present', 'notpresent']) + Q('bgr') + Q('bu') + Q('sc') + Q('sod') + Q('pot') + Q('hemo') + Q('pcv') + Q('wbcc') + Q('rbcc') + C(Q('htn'), levels=['yes', 'no']) + C(Q('dm'), levels=['yes', 'no']) + C(Q('cad'), levels=['yes', 'no']) + C(Q('appet'), levels=['good', 'poor']) + C(Q('pe'), levels=['yes', 'no']) + C(Q('ane'), levels=['yes', 'no']) + Q('age'):Q('bp') + Q('bp'):Q('sg') + Q('sg'):Q('al') + Q('al'):Q('su') + Q('su'):C(Q('rbc'), levels=['normal', 'abnormal'])</td>
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
      <td>158</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>400</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9937</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0165</td>
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
      <td>1</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>2.5714</td>
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
      <td>bp</td>
      <td>core.lognormal</td>
    </tr>
    <tr>
      <td>sg</td>
      <td>core.truncated_normal</td>
    </tr>
    <tr>
      <td>al</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>su</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>rbc</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>pc</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>pcc</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>ba</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>bgr</td>
      <td>core.truncated_normal</td>
    </tr>
    <tr>
      <td>bu</td>
      <td>core.lognormal</td>
    </tr>
    <tr>
      <td>sc</td>
      <td>core.lognormal</td>
    </tr>
    <tr>
      <td>sod</td>
      <td>core.truncated_normal</td>
    </tr>
    <tr>
      <td>pot</td>
      <td>core.normal</td>
    </tr>
    <tr>
      <td>hemo</td>
      <td>core.truncated_normal</td>
    </tr>
    <tr>
      <td>pcv</td>
      <td>core.truncated_normal</td>
    </tr>
    <tr>
      <td>wbcc</td>
      <td>core.lognormal</td>
    </tr>
    <tr>
      <td>rbcc</td>
      <td>core.normal</td>
    </tr>
    <tr>
      <td>htn</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>dm</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>cad</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>appet</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>pe</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>ane</td>
      <td>core.multinoulli</td>
    </tr>
    <tr>
      <td>class</td>
      <td>core.multinoulli</td>
    </tr>
  </tbody>
</table></td></tr>

<tr><td><img src='models/clg_mi2/umap.png' width='280'/></td><td>

<h3>Model: clg_mi2 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 400</li>
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
      <td>0.1275</td>
      <td>2.6951</td>
      <td></td>
    </tr>
    <tr>
      <td>bp</td>
      <td>continuous</td>
      <td>0.3025</td>
      <td>3.9078</td>
      <td></td>
    </tr>
    <tr>
      <td>sg</td>
      <td>continuous</td>
      <td>0.3162</td>
      <td>0.0019</td>
      <td></td>
    </tr>
    <tr>
      <td>al</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0925</td>
    </tr>
    <tr>
      <td>su</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.202</td>
    </tr>
    <tr>
      <td>rbc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.016</td>
    </tr>
    <tr>
      <td>pc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.095</td>
    </tr>
    <tr>
      <td>pcc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0585</td>
    </tr>
    <tr>
      <td>ba</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0919</td>
    </tr>
    <tr>
      <td>bgr</td>
      <td>continuous</td>
      <td>0.12</td>
      <td>12.7667</td>
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
      <td>158</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>400</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9873</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0271</td>
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
      <td>1</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>3.5</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<a href='models/clg_mi2/structure.png'><img src='models/clg_mi2/structure.png' width='280'/></a></td></tr>

<tr><td><img src='models/semi_mi5/umap.png' width='280'/></td><td>

<h3>Model: semi_mi5 (pybnesian)</h3>
<ul>
<li>Seed: 42, rows: 400</li>
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
      <td>0.1275</td>
      <td>2.6951</td>
      <td></td>
    </tr>
    <tr>
      <td>bp</td>
      <td>continuous</td>
      <td>0.3025</td>
      <td>3.9078</td>
      <td></td>
    </tr>
    <tr>
      <td>sg</td>
      <td>continuous</td>
      <td>0.3162</td>
      <td>0.0019</td>
      <td></td>
    </tr>
    <tr>
      <td>al</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0925</td>
    </tr>
    <tr>
      <td>su</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.202</td>
    </tr>
    <tr>
      <td>rbc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.016</td>
    </tr>
    <tr>
      <td>pc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.095</td>
    </tr>
    <tr>
      <td>pcc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0585</td>
    </tr>
    <tr>
      <td>ba</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.0919</td>
    </tr>
    <tr>
      <td>bgr</td>
      <td>continuous</td>
      <td>0.12</td>
      <td>12.7667</td>
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
      <td>158</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>400</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9873</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0271</td>
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
      <td>1</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>3.5</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<a href='models/semi_mi5/structure.png'><img src='models/semi_mi5/structure.png' width='280'/></a></td></tr>

<tr><td><img src='models/ctgan_fast/umap.png' width='280'/></td><td>

<h3>Model: ctgan_fast (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 256</li>
<li> Params: <tt>{"batch_size": 256, "n_iter": 5}</tt></li><li> <a href="models/ctgan_fast/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/ctgan_fast/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/ctgan_fast/metrics.json">Metrics JSON</a></li>
<li> <a href="models/ctgan_fast/metrics.privacy.json">Privacy metrics</a></li>
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
      <td>1</td>
      <td>34.0312</td>
      <td></td>
    </tr>
    <tr>
      <td>bp</td>
      <td>continuous</td>
      <td>0.1016</td>
      <td>2.5</td>
      <td></td>
    </tr>
    <tr>
      <td>sg</td>
      <td>continuous</td>
      <td>0.2461</td>
      <td>0.0028</td>
      <td></td>
    </tr>
    <tr>
      <td>al</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.3647</td>
    </tr>
    <tr>
      <td>su</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.2342</td>
    </tr>
    <tr>
      <td>rbc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1798</td>
    </tr>
    <tr>
      <td>pc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.2748</td>
    </tr>
    <tr>
      <td>pcc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.073</td>
    </tr>
    <tr>
      <td>ba</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1057</td>
    </tr>
    <tr>
      <td>bgr</td>
      <td>continuous</td>
      <td>0.9062</td>
      <td>178.988</td>
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
      <td>158</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>256</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.3987</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.3484</td>
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
      <td>1</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>28.6</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<img src="box.svg" width="120" /></td></tr>

<tr><td><img src='models/tvae_quick/umap.png' width='280'/></td><td>

<h3>Model: tvae_quick (synthcity)</h3>
<ul>
<li>Seed: 42, rows: 256</li>
<li> Params: <tt>{"batch_size": 256}</tt></li><li> <a href="models/tvae_quick/synthetic.csv">Synthetic CSV</a></li>
<li> <a href="models/tvae_quick/per_variable_metrics.csv">Per-variable metrics</a></li>
<li> <a href="models/tvae_quick/metrics.json">Metrics JSON</a></li>
<li> <a href="models/tvae_quick/metrics.privacy.json">Privacy metrics</a></li>
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
      <td>0.1562</td>
      <td>4.4251</td>
      <td></td>
    </tr>
    <tr>
      <td>bp</td>
      <td>continuous</td>
      <td>0.1328</td>
      <td>2.7344</td>
      <td></td>
    </tr>
    <tr>
      <td>sg</td>
      <td>continuous</td>
      <td>0.168</td>
      <td>0.0018</td>
      <td></td>
    </tr>
    <tr>
      <td>al</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.2962</td>
    </tr>
    <tr>
      <td>su</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.175</td>
    </tr>
    <tr>
      <td>rbc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.1031</td>
    </tr>
    <tr>
      <td>pc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.2671</td>
    </tr>
    <tr>
      <td>pcc</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.073</td>
    </tr>
    <tr>
      <td>ba</td>
      <td>discrete</td>
      <td></td>
      <td></td>
      <td>0.193</td>
    </tr>
    <tr>
      <td>bgr</td>
      <td>continuous</td>
      <td>0.1992</td>
      <td>13.2205</td>
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
      <td>158</td>
    </tr>
    <tr>
      <td>n_synth</td>
      <td>256</td>
    </tr>
    <tr>
      <td>exact_overlap_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>near_duplicate_rate_eps</td>
      <td>0.9873</td>
    </tr>
    <tr>
      <td>nn_distance_mean</td>
      <td>0.0241</td>
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
      <td>1</td>
    </tr>
    <tr>
      <td>rare_qi_reproduction_rate</td>
      <td>0</td>
    </tr>
    <tr>
      <td>delta_presence</td>
      <td>11</td>
    </tr>
  </tbody>
</table>
</details>
</td><td>
<img src="box.svg" width="120" /></td></tr>

</table>