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
| mock_perfect | **100.0** | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | 100 | T_IVR_MISROUTE T_PA_FAX T_SAAS_DUE |  |  |  |
| mock_sloppy | **35.0** | 88 | 62 | 62 | 47 | 62 | 7 | 45 | 11 | 0 | 20 | 23 | 25 | T_PA_FAX DECOY:D_DOUBLE_CHARGE |  |  |  |
| mock_shuffled | **30.0** | 100 | 12 | 62 | 84 | 56 | 3 | 25 | 25 | 100 | 2 | 3 | 0 |  |  |  |  |
