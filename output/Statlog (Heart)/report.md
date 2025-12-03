# Data Report — Statlog (Heart)

Cost Matrix

_______	 abse  pres
absence	 0	1
presence  5	0

where the rows represent the true values and the columns the predicted.


**Documentation**: 
Attribute Information:
------------------------
      -- 1. age       
      -- 2. sex       
      -- 3. chest pain type  (4 values)       
      -- 4. resting blood pressure  
      -- 5. serum cholestoral in mg/dl      
      -- 6. fasting blood sugar > 120 mg/dl       
      -- 7. resting electrocardiographic results  (values 0,1,2) 
      -- 8. maximum heart rate achieved  
      -- 9. exercise induced angina    
      -- 10. oldpeak = ST depression induced by exercise relative to rest   
      -- 11. the slope of the peak exercise ST segment     
      -- 12. number of major vessels (0-3) colored by flourosopy        
      -- 13.  thal: 3 = normal; 6 = fixed defect; 7 = reversable defect     

Attributes types
-----------------

Real: 1,4,5,8,10,12
Ordered:11,
Binary: 2,6,9
Nominal:7,3,13

Variable to be predicted
------------------------
Absence (1) or presence (2) of heart disease



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

| variable             | description                                                  | inferred   | dist                                                                       |
|:---------------------|:-------------------------------------------------------------|:-----------|:---------------------------------------------------------------------------|
| age                  |                                                              | continuous | 54.4333 ± 9.1091 [29, 48, 55, 61, 77]                                      |
| sex                  |                                                              | discrete   | 1: 183 (67.78%)                                                            |
| chest-pain           | chest pain type                                              | discrete   | 4: 129 (47.78%)<br />3: 79 (29.26%)<br />2: 42 (15.56%)<br />1: 20 (7.41%) |
| rest-bp              | resting blood pressure                                       | continuous | 131.3444 ± 17.8616 [94, 120, 130, 140, 200]                                |
| serum-chol           | serum cholesterol                                            | continuous | 249.6593 ± 51.6862 [126, 213, 245, 280, 564]                               |
| fasting-blood-sugar  | fasting blood sugar > 120 mg/dl                              | discrete   | 1: 40 (14.81%)                                                             |
| electrocardiographic | resting electrocardiographic results                         | discrete   | 2: 137 (50.74%)<br />0: 131 (48.52%)<br />1: 2 (0.74%)                     |
| max-heart-rate       | maximum heart rate achieved                                  | continuous | 149.6778 ± 23.1657 [71, 133, 153.5, 166, 202]                              |
| angina               | exercise induced anigna                                      | discrete   | 1: 89 (32.96%)                                                             |
| oldpeak              | oldpeak = ST depression induced by exercise relative to rest | continuous | 1.0500 ± 1.1452 [0, 0, 0.8, 1.6, 6.2]                                      |
| slope                | the slope of the peak exercise ST sgment                     | discrete   | 1: 130 (48.15%)<br />2: 122 (45.19%)<br />3: 18 (6.67%)                    |
| major-vessels        | number of major vessels (0-3) colored by fluorosopy          | discrete   | 0: 160 (59.26%)<br />1: 58 (21.48%)<br />2: 33 (12.22%)<br />3: 19 (7.04%) |
| thal                 | thal: 3 = normal; 6 = fixed defect; 7 = reversable defect    | discrete   | 3: 152 (56.30%)<br />7: 104 (38.52%)<br />6: 14 (5.19%)                    |
| heart-disease        |                                                              | discrete   | 1: 150 (55.56%)                                                            |

## Fidelity summary

| model        | backend   |   disc_jsd_mean |   disc_jsd_median |   cont_ks_mean |   cont_w1_mean | privacy_overlap   | downstream_sign_match   |
|:-------------|:----------|----------------:|------------------:|---------------:|---------------:|:------------------|:------------------------|
| metasyn_full | metasyn   |          0.1044 |            0.0935 |         0.1889 |         4.2565 |                   |                         |

## Models

<table>
<tr><th>UMAP</th><th>Details</th><th>Structure</th></tr>
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

</table>
