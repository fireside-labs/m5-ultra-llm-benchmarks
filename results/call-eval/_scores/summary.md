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
| qwen-omlx-think | **97.3** | 100 | 100 | 100 | 95 | 100 | 94 | 93 | 100 | 100 | 98 | 97 | 100 | T_DOUBLE_CHARGE T_FASTING_CONFLICT | 59.06 | 1.79 | 102.21 |
| glm53-omlx-high-dflash | **97.1** | 100 | 100 | 100 | 95 | 95 | 95 | 96 | 96 | 93 | 98 | 100 | 100 | T_DOUBLE_CHARGE T_FASTING_CONFLICT | 29.92 | 2.36 | 58.32 |
| glm53-mtp-high | **96.5** | 100 | 100 | 85 | 95 | 95 | 93 | 98 | 100 | 100 | 96 | 100 | 100 | T_DOUBLE_CHARGE T_FASTING_CONFLICT | 23.13 | 2.51 | 65.54 |
| ds0731-omlx-think | **85.3** | 90 | 85 | 85 | 80 | 90 | 74 | 84 | 90 | 86 | 76 | 88 | 100 | T_DOUBLE_CHARGE T_FASTING_CONFLICT | 49.24 | 4.03 | 56.52 |
