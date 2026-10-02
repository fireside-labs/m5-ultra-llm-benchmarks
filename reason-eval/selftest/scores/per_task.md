# Per-task breakdown

Cells are percentages; blank = not applicable. Ids refer to gold/Rxx.json.

## mock_perfect

| task | score | coverage | prio | decoy | crux | balance | est | struct | words | missed items | decoys hit | missing sections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R01 | 100 | 100 | 100 | 100 |  |  |  | 100 | 347 |   |  |  |
| R02 | 100 | 100 | 100 | 100 |  |  |  | 100 | 340 |   |  |  |
| R03 | 100 | 100 | 100 | 100 |  |  |  | 100 | 390 |   |  |  |
| R04 | 100 | 100 | 100 | 100 |  |  |  | 100 | 384 |   |  |  |
| R05 | 100 | 100 | 100 |  |  |  |  | 100 | 269 |   |  |  |
| R06 | 100 | 100 | 100 |  |  |  |  | 100 | 326 |   |  |  |
| R07 | 100 | 100 |  |  | 100 | 100 |  | 100 | 309 |   |  |  |
| R08 | 100 | 100 |  |  | 100 | 100 |  | 100 | 266 |   |  |  |
| R09 | 100 | 100 | 100 |  |  |  |  | 100 | 277 |   |  |  |
| R10 | 100 | 100 | 100 |  |  |  | 100 | 100 | 290 |   |  |  |

## mock_padded

| task | score | coverage | prio | decoy | crux | balance | est | struct | words | missed items | decoys hit | missing sections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R01 | 44 | 67 | 0 | 0 |  |  |  | 67 | 253 | G6 G7 G8 G9  | D1 D2 D3 | bottom |
| R02 | 43 | 64 | 0 | 0 |  |  |  | 67 | 261 | G6 G7 G8  | D1 D2 D3 | bottom |
| R03 | 39 | 57 | 0 | 0 |  |  |  | 67 | 304 | G6 G7 G8 G9  | D1 D2 D3 | bottom |
| R04 | 50 | 75 | 0 | 0 |  |  |  | 67 | 291 | G6 G7 G8  | D1 D2 D3 | bottom |
| R05 | 55 | 68 | 0 |  |  |  |  | 67 | 255 | V9 V10 V11 V12 V13  |  | mind |
| R06 | 66 | 83 | 0 |  |  |  |  | 67 | 291 | V10 V12 V13  |  | mind |
| R07 | 34 | 50 |  |  | 0 | 0 |  | 20 | 327 | A1 A2 A3 A4 A5 A6 / cruxes: C1 C2 C3 C4 |  | against cruxes mind lean |
| R08 | 35 | 53 |  |  | 0 | 0 |  | 20 | 284 | A1 A2 A3 A4 A5 A6 / cruxes: C1 C2 C3 C4 |  | against cruxes mind lean |
| R09 | 66 | 86 | 0 |  |  |  |  | 50 | 235 | G9 G10  |  | measure kill |
| R10 | 56 | 87 | 0 |  |  |  | 0 | 50 | 227 | F9 F10  |  | result recommendation |

## mock_sloppy

| task | score | coverage | prio | decoy | crux | balance | est | struct | words | missed items | decoys hit | missing sections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R01 | 29 | 42 | 0 | 0 |  |  |  | 67 | 144 | G2 G3 G6 G8 G9  | D1 D2 D3 | bottom |
| R02 | 39 | 57 | 0 | 0 |  |  |  | 67 | 155 | G2 G3 G6  | D3 D1 D2 | bottom |
| R03 | 34 | 50 | 0 | 0 |  |  |  | 67 | 154 | G3 G6 G8 G9  | D1 D2 D3 | bottom |
| R04 | 29 | 42 | 0 | 0 |  |  |  | 67 | 158 | G2 G3 G5 G8  | D1 D2 D3 | bottom |
| R05 | 47 | 58 | 0 |  |  |  |  | 67 | 129 | V2 V5 V9 V11 V12  |  | mind |
| R06 | 0 | 0 | 0 |  |  |  |  | 0 | 0 |   |  |  |
| R07 | 36 | 50 |  |  | 0 | 9 |  | 50 | 95 | A1 A2 A3 A4 A5 A6 / cruxes: C1 C2 C3 C4 |  | cruxes mind |
| R08 | 38 | 53 |  |  | 0 | 12 |  | 50 | 77 | A1 A2 A3 A4 A5 A6 / cruxes: C1 C2 C3 C4 |  | cruxes mind |
| R09 | 52 | 57 | 33 |  |  |  |  | 50 | 122 | G2 G3 G8 G9  |  | measure kill |
| R10 | 12 | 13 | 0 |  |  |  | 0 | 75 | 59 | F1 F2 F3 F4 F5 F6 F7 F9 F10  |  | recommendation |

## mock_shuffled

| task | score | coverage | prio | decoy | crux | balance | est | struct | words | missed items | decoys hit | missing sections |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R01 | 22 | 0 | 0 | 100 |  |  |  | 100 | 340 | G1 G2 G3 G4 G5 G6 G7 G8 G9  |  |  |
| R02 | 22 | 0 | 0 | 100 |  |  |  | 100 | 390 | G1 G2 G3 G4 G5 G6 G7 G8  |  |  |
| R03 | 22 | 0 | 0 | 100 |  |  |  | 100 | 384 | G1 G2 G3 G4 G5 G6 G7 G8 G9  |  |  |
| R04 | 12 | 8 | 0 | 33 |  |  |  | 33 | 269 | G1 G2 G3 G4 G5 G6 G7  | D3 D1 | issues bottom |
| R05 | 18 | 16 | 0 |  |  |  |  | 100 | 326 | V1 V2 V3 V4 V6 V8 V9 V10 V11 V12 V13  |  |  |
| R06 | 10 | 11 | 0 |  |  |  |  | 33 | 309 | V1 V2 V4 V5 V6 V7 V8 V9 V10 V11 V12 V13  |  | variables priorities |
| R07 | 18 | 10 |  |  | 0 | 50 |  | 100 | 266 | F1 F2 F3 F5 F6 A1 A2 A3 A4 A5 A6 / cruxes: C1 C2 C3 C4 |  |  |
| R08 | 0 | 0 |  |  | 0 | 0 |  | 0 | 277 | F1 F2 F3 F4 F5 F6 A1 A2 A3 A4 A5 A6 / cruxes: C1 C2 C3 C4 |  | for against cruxes mind lean |
| R09 | 2 | 0 | 0 |  |  |  |  | 25 | 290 | G1 G2 G3 G4 G5 G6 G7 G8 G9 G10  |  | steps measure kill |
| R10 | 1 | 0 | 0 |  |  |  | 0 | 25 | 347 | F1 F2 F3 F4 F5 F6 F7 F8 F9 F10  |  | chain result recommendation |
