# Per-transcript breakdown

Cells are percentages; `-` = not applicable (no decoys in that call). Missed ids refer to gold/Cxx.json.

## mock_perfect

| call | parse | type | outcome | sent | q(pred/gold) | flagR | flagP | decoy | action | subtle | missed flags | decoys hit | missed subtle |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | strict | 100 | 100 | 100 | 5/5 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C02 | strict | 100 | 100 | 100 | 3/3 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C03 | strict | 100 | 100 | 100 | 2/2 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C04 | strict | 100 | 100 | 100 | 5/5 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C05 | strict | 100 | 100 | 100 | 3/3 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C06 | strict | 100 | 100 | 100 | 3/3 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C07 | strict | 100 | 100 | 100 | 2/2 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C08 | strict | 100 | 100 | 100 | 3/3 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C09 | strict | 100 | 100 | 100 | 4/4 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C10 | strict | 100 | 100 | 100 | 2/2 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C11 | strict | 100 | 100 | 100 | 2/2 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C12 | strict | 100 | 100 | 100 | 5/5 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C13 | strict | 100 | 100 | 100 | 2/2 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C14 | strict | 100 | 100 | 100 | 2/2 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C15 | strict | 100 | 100 | 100 | 3/3 | 100 | 100 | 100 | 100 | 100 |  |  |  |
| C16 | strict | 100 | 100 | 100 | 3/3 | 100 | 100 | 100 | 100 | 100 |  |  |  |

## mock_sloppy

| call | parse | type | outcome | sent | q(pred/gold) | flagR | flagP | decoy | action | subtle | missed flags | decoys hit | missed subtle |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | lenient | 0 | 100 | 50 | 4/5 | 100 | 0 | 0 | 33 | 33 |  | D1 D2 | S1 S3 |
| C02 | strict | 100 | 100 | 50 | 4/3 | 0 | 0 | 0 | 25 | 0 | F1 | D1 D2 | S1 S2 S3 |
| C03 | strict | 100 | 100 | 100 | 4/2 | 50 | 33 | 0 | 25 | 43 | F2 | D1 D2 | S2 S4 S5 S7 |
| C04 | lenient | 100 | 100 | 0 | 4/5 | 100 | 0 | 0 | 50 | 25 |  | D1 D2 | S1 S2 S4 |
| C05 | strict | 100 | 100 | 50 | 4/3 | 50 | 33 | 0 | 14 | 14 | F2 | D1 D2 | S1 S3 S4 S5 S6 S7 |
| C06 | strict | 0 | 100 | 50 | 4/3 | 0 | 0 | 0 | 14 | 14 | F1 F2 | D1 D2 | S1 S2 S4 S5 S6 S7 |
| C07 | lenient | 100 | 0 | 50 | 4/2 | 50 | 25 | 0 | 11 | 12 | F2 | D1 D2 | S2 S3 S4 S5 S6 S7 S8 |
| C08 | strict | 100 | 100 | 100 | 4/3 | 0 | 0 | 0 | 14 | 0 | F1 F2 | D1 D2 | S1 S2 S3 S4 S5 S6 |
| C09 | strict | 100 | 100 | 100 | 4/4 | 100 | 0 | 0 | 14 | 57 |  | D1 D2 D3 | S4 S5 S6 |
| C10 | fail | 0 | 0 | 0 | None/2 | 0 | 0 | 0 | 0 | 0 |  |  |  |
| C11 | strict | 0 | 0 | 50 | 4/2 | 33 | 25 | 0 | 14 | 17 | F2 F3 | D1 D2 D3 | S1 S2 S3 S4 S6 |
| C12 | strict | 100 | 100 | 0 | 4/5 | 100 | 0 | 0 | 33 | 67 |  | D1 D2 | S1 |
| C13 | lenient | 100 | 0 | 50 | 4/2 | 33 | 20 | 0 | 12 | 0 | F2 F3 | D1 D2 D3 | S1 S2 S3 S4 S5 S6 S7 |
| C14 | fail | 0 | 0 | 0 | None/2 | 0 | 0 | 0 | 0 | 0 |  |  |  |
| C15 | strict | 100 | 0 | 50 | 4/3 | 100 | 33 | 0 | 20 | 25 |  | D1 | S1 S3 S4 |
| C16 | lenient | 0 | 100 | 50 | 4/3 | 0 | 0 | 0 | 38 | 57 | F1 F2 | D1 D2 | S2 S5 S6 |

## mock_shuffled

| call | parse | type | outcome | sent | q(pred/gold) | flagR | flagP | decoy | action | subtle | missed flags | decoys hit | missed subtle |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | strict | 0 | 100 | 50 | 3/5 | 100 | 0 | 100 | 0 | 0 |  |  | S1 S2 S3 |
| C02 | strict | 0 | 0 | 50 | 2/3 | 0 | 0 | 100 | 0 | 0 | F1 |  | S1 S2 S3 |
| C03 | strict | 100 | 100 | 100 | 5/2 | 0 | 100 | 100 | 0 | 0 | F1 F2 |  | S1 S2 S3 S4 S5 S6 S7 |
| C04 | strict | 0 | 100 | 100 | 3/5 | 100 | 0 | 100 | 0 | 0 |  |  | S1 S2 S3 S4 |
| C05 | strict | 0 | 100 | 100 | 3/3 | 0 | 0 | 100 | 0 | 0 | F1 F2 |  | S1 S2 S3 S4 S5 S6 S7 |
| C06 | strict | 0 | 0 | 100 | 2/3 | 0 | 0 | 100 | 0 | 0 | F1 F2 |  | S1 S2 S3 S4 S5 S6 S7 |
| C07 | strict | 0 | 0 | 100 | 3/2 | 0 | 0 | 100 | 0 | 0 | F1 F2 |  | S1 S2 S3 S4 S5 S6 S7 S8 |
| C08 | strict | 0 | 100 | 100 | 4/3 | 0 | 100 | 100 | 0 | 0 | F1 F2 |  | S1 S2 S3 S4 S5 S6 |
| C09 | strict | 0 | 100 | 100 | 2/4 | 100 | 0 | 100 | 0 | 0 |  |  | S1 S2 S3 S4 S5 S6 S7 |
| C10 | strict | 0 | 0 | 50 | 2/2 | 0 | 0 | 100 | 12 | 12 | F1 F2 |  | S1 S2 S3 S5 S6 S7 S8 |
| C11 | strict | 0 | 0 | 100 | 5/2 | 0 | 100 | 100 | 0 | 0 | F1 F2 F3 |  | S1 S2 S3 S4 S5 S6 |
| C12 | strict | 0 | 0 | 50 | 2/5 | 100 | 0 | 100 | 0 | 33 |  |  | S1 S2 |
| C13 | strict | 0 | 100 | 100 | 2/2 | 0 | 0 | 100 | 12 | 0 | F1 F2 F3 |  | S1 S2 S3 S4 S5 S6 S7 |
| C14 | strict | 0 | 100 | 50 | 3/2 | 0 | 0 | 100 | 0 | 0 | F1 F2 F3 |  | S1 S2 S3 S4 S5 S6 S7 |
| C15 | strict | 100 | 100 | 100 | 3/3 | 0 | 0 | 100 | 0 | 0 | F1 |  | S1 S2 S3 S4 |
| C16 | strict | 0 | 100 | 100 | 5/3 | 0 | 100 | 100 | 0 | 0 | F1 F2 |  | S1 S2 S3 S4 S5 S6 S7 |
