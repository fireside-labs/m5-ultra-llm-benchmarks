# reason-eval scores

Task score = weighted mean of the components that apply to the task; headline = mean task score.
Categories: A = what did this analysis miss, B = what variables matter, C = debate/cruxes, D = steering/estimation.

| component | weight | applies to |
|---|---|---|
| coverage | 55 | all |
| priorities | 15 | A, B, D |
| decoy_avoidance | 15 | A |
| cruxes | 15 | C |
| balance | 10 | C |
| estimate | 15 | R10 |
| structure | 5 | all |

| label | headline | A | B | C | D | coverage | priorities | decoy_avoidance | cruxes | balance | estimate | structure | empty | med words | med s/task | med TTFT s | decode tok/s | truncated |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dsv4_r1 | **94.2** | 95.0 | 94.0 | 89.8 | 97.4 | 95 | 92 | 100 | 64 | 95 | 100 | 100 | 0 | 886 | 78.96 | 0.73 | 51.98 | 0 |
| dsv4_r2 | **92.7** | 91.1 | 92.7 | 91.0 | 97.4 | 94 | 88 | 92 | 71 | 95 | 100 | 100 | 0 | 881 | 84.66 | 0.12 | 52.87 | 0 |
| glm53_r2 | **91.8** | 96.5 | 90.1 | 81.2 | 94.6 | 91 | 96 | 100 | 71 | 82 | 100 | 100 | 0 | 944 | 146.09 | 0.08 | 56.87 | 0 |
| qwen38_r1 | **90.2** | 93.5 | 90.7 | 98.1 | 75.1 | 96 | 67 | 100 | 100 | 98 | 0 | 86 | 0 | 931 | 120.91 | 0.63 | 93.39 | 2 |
| glm53_r1 | **86.8** | 78.6 | 92.2 | 91.1 | 93.3 | 85 | 83 | 100 | 71 | 95 | 100 | 93 | 0 | 955 | 166.63 | 0.63 | 59.55 | 1 |
| qwen38_r2 | **73.5** | 64.7 | 92.7 | 95.6 | 50.0 | 76 | 58 | 67 | 86 | 98 | 0 | 73 | 2 | 922 | 100.43 | 0.41 | 97.78 | 3 |

## Per-task scores

| label | R01 | R02 | R03 | R04 | R05 | R06 | R07 | R08 | R09 | R10 |
|---|---|---|---|---|---|---|---|---|---|---|
| dsv4_r1 | 94 | 100 | 86 | 100 | 96 | 92 | 89 | 91 | 95 | 100 |
| dsv4_r2 | 89 | 94 | 91 | 89 | 96 | 89 | 86 | 96 | 95 | 100 |
| glm53_r2 | 95 | 100 | 91 | 100 | 88 | 92 | 84 | 79 | 95 | 94 |
| qwen38_r1 | 94 | 80 | 100 | 100 | 96 | 85 | 96 | 100 | 100 | 50 |
| glm53_r1 | 94 | 100 | 91 | 29 | 88 | 96 | 87 | 95 | 95 | 92 |
| qwen38_r2 | 95 | 94 | 0 | 69 | 96 | 89 | 91 | 100 | 100 | 0 |

## Repeat groups (labels `<base>_rN`)

| base | n | mean headline | stdev | R01 | R02 | R03 | R04 | R05 | R06 | R07 | R08 | R09 | R10 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dsv4 | 2 | **93.5** | 1.1 | 92 | 97 | 88 | 95 | 96 | 91 | 87 | 94 | 95 | 100 |
| glm53 | 2 | **89.3** | 3.6 | 95 | 100 | 91 | 64 | 88 | 94 | 85 | 87 | 95 | 93 |
| qwen38 | 2 | **81.9** | 11.8 | 95 | 87 | 50 | 85 | 96 | 87 | 94 | 100 | 100 | 25 |
