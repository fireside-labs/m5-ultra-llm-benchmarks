# Call-eval scores

Headline = sum(weight x component mean); components are 0-1, weights sum to 100.

| component | weight |
|---|---|
| call_type | 5 |
| outcome | 10 |
| sentiment | 5 |
| quality_pm1 | 10 |
| quality_reasons | 5 |
| flag_recall | 20 |
| flag_precision | 10 |
| decoy_avoidance | 5 |
| action_recall | 10 |
| subtle_recall | 15 |
| themes | 5 |

| model | headline | parse % | call_type | outcome | sentiment | quality_pm1 | quality_reasons | flag_recall | flag_precision | decoy_avoidance | action_recall | subtle_recall | themes | themes found | median s/call | median TTFT s | decode tok/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| mock_perfect | **100.0** | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | T_DOUBLE_CHARGE T_FASTING_CONFLICT |  |  |  |
| mock_sloppy | **39.2** | 90 | 70 | 45 | 52 | 50 | 0 | 62 | 15 | 0 | 34 | 25 | 50 | T_DOUBLE_CHARGE |  |  |  |
| mock_shuffled | **26.3** | 100 | 5 | 25 | 48 | 45 | 25 | 35 | 35 | 96 | 1 | 0 | 0 |  |  |  |  |
