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
| glm53-mtp-high | **92.3** | 100 | 100 | 94 | 97 | 94 | 88 | 88 | 91 | 93 | 93 | 100 | 75 | T_IVR_MISROUTE T_PA_FAX T_SAAS_DUE DECOY:D_DOUBLE_CHARGE | 75.09 | 9.78 | 65.29 |
| qwen-omlx070-think | **84.1** | 94 | 94 | 94 | 88 | 94 | 83 | 75 | 80 | 83 | 91 | 89 | 50 | T_IVR_MISROUTE T_PA_FAX DECOY:D_DOUBLE_CHARGE | 105.32 | 5.15 | 98.49 |
| ds0731-omlx070-think | **71.9** | 88 | 88 | 75 | 84 | 69 | 64 | 55 | 81 | 84 | 75 | 82 | 50 | T_PA_FAX T_SAAS_DUE DECOY:D_DOUBLE_CHARGE | 92.51 | 15.08 | 56.53 |
