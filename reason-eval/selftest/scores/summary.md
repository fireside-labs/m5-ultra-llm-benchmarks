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
| mock_perfect | **100.0** | 100.0 | 100.0 | 100.0 | 100.0 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 0 | 318 |  |  |  |  |
| mock_padded | **48.6** | 43.9 | 60.1 | 34.4 | 61.0 | 69 | 0 | 0 | 0 | 0 | 0 | 54 | 0 | 272 |  |  |  |  |
| mock_sloppy | **31.7** | 32.8 | 23.5 | 37.3 | 32.1 | 42 | 4 | 0 | 0 | 10 | 0 | 56 | 1 | 126 |  |  |  |  |
| mock_shuffled | **12.9** | 19.8 | 14.3 | 9.1 | 1.5 | 4 | 0 | 83 | 0 | 25 | 0 | 62 | 0 | 318 |  |  |  |  |

## Per-task scores

| label | R01 | R02 | R03 | R04 | R05 | R06 | R07 | R08 | R09 | R10 |
|---|---|---|---|---|---|---|---|---|---|---|
| mock_perfect | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 |
| mock_padded | 44 | 43 | 39 | 50 | 55 | 66 | 34 | 35 | 66 | 56 |
| mock_sloppy | 29 | 39 | 34 | 29 | 47 | 0 | 36 | 38 | 52 | 12 |
| mock_shuffled | 22 | 22 | 22 | 12 | 18 | 10 | 18 | 0 | 2 | 1 |
