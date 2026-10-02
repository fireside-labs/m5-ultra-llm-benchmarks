# reason-eval: general thinker / steering benchmark

Which local model is the best *general reasoner who can steer work*? This means seeing the whole problem,
naming the variables that matter, spotting what an analysis missed, telling real problems from
things that only look like problems, prioritising, and finding the crux of a disagreement. It is
not a coding benchmark. The candidates are Qwen3.8-Flash-Next, GLM-5.3-Flash and DeepSeek-V4-Flash,
run locally.

The structure follows `../call-eval-v2`. It uses the same OpenAI-compatible runner (streaming
with TTFT, raw/reasoning/meta files, manifest), keyword-group matchers with paraphrase validation,
and self-test mocks. Two scoring layers are provided:

1. **Deterministic checklist scoring** (`score.py`): recall of gold items, decoy penalty,
   top-3 priority check, debate cruxes and balance, and a Fermi range check.
2. **Blind side-by-side judge pack** (`make_judge_pack.py`): anonymised and shuffled answers, so a
   separate judge can rank insight, prioritisation and decision-usefulness. The checklist cannot
   measure these well.

**Self-contained by design.** The models have no web search, so nothing depends on current events
or real-world numbers. Every fact a task needs is in its prompt: tables, appendices and fact sheets.
Gold items reward reasoning from those facts plus general principles. All organisations, people
and products are fictional. The debate prompts tell the model not to cite studies or statistics
and to argue from mechanisms instead.

## Layout

| path | what |
|---|---|
| `prompts/system.md` | the one fixed system prompt (generalist advisor, use the requested headings) |
| `tasks/R01..R10.md` | user prompts, sent verbatim; each ends with the required `## Section` headings |
| `gold/Rxx.json` | gold checklists: `items` (with `importance` high/normal, `side` for debates), `cruxes`, `decoys`, `estimate` (R10); every entry has keyword-group `match`, ≥ 2 `paraphrases`, optional `negatives` |
| `tools/gold_src/Rxx.py` | authoring source for the gold (raw-string regexes); `tools/build_gold.py` writes `gold/*.json` |
| `tools/validate_gold.py` | gold consistency + prompt-size checks |
| `evallib.py` | shared helpers: prompt loading, `<think>` stripping, Markdown section/unit parser, matcher |
| `run_eval.py` | runner; results default to `../results/reason-eval/<label>/` |
| `score.py` | deterministic scorer → `<root>/_scores/` |
| `make_judge_pack.py` | blind judge pack builder + verdict tally |
| `selftest/make_mocks.py` | perfect / sloppy / shuffled / padded mocks, scored without a model |

## Tasks

| task | cat | what | gold items (high) | cruxes | decoys | prompt tokens* |
|---|---|---|---|---|---|---|
| R01 | A | Vendor-selection memo (payroll platform) with a scoring matrix and an appendix that contradicts it | 9 (3) | – | 3 | 1,206 |
| R02 | A | Readmission-program report with tables: Simpson's paradox, selection, survivorship, confounder, small n, base-rate neglect, metric change | 8 (6) | – | 3 | 1,092 |
| R03 | A | Clinic no-show fee / double-booking / balance-hold / text-only memo + fact sheet (second-order effects) | 9 (5) | – | 3 | 904 |
| R04 | A | GPU purchase memo: one 8-GPU vs two 4-GPU servers (redundancy, utilisation, lead time, power, isolation, cloud burst, resale, capex flexibility) | 8 (4) | – | 3 | 946 |
| R05 | B | Variables for siting a new outpatient clinic (3 sketched sites) | 13 (6) | – | – | 492 |
| R06 | B | Variables for replacing a cloud LLM API with a self-hosted model for sensitive claims data | 13 (5) | – | – | 380 |
| R07 | C | Debate: ban private cars from the downtown core | 12 (6 per side) | 4 | – | 437 |
| R08 | C | Debate: remote work as the default for knowledge workers | 12 (6 per side) | 4 | – | 445 |
| R09 | D | Steering: "reduce call-center wait times", given messy facts → first steps, what to measure, kill criteria | 10 (4) | – | – | 651 |
| R10 | D | Fermi + decision: public DC fast-charging ports for 2030, and whether a $12M budget is enough | 10 (5) | – | – | 677 |

\*System prompt plus task, o200k tokenizer. Every prompt is far under the 20k limit.

Totals: 104 gold items (53 high-importance), 8 cruxes, 12 decoys, 372 validated paraphrases.

- **A, "what did this analysis miss?":** a confident, plausible analysis with 7–9 planted
  gaps and 3 **decoys**. A decoy looks like a problem but is explicitly handled in the text, for
  example SOC 2 already reviewed, ERP connector already tested, readmissions to other hospitals
  already captured by the all-payer data, or networking already in the quote. Flagging a decoy
  costs points. Listing it under the optional *"Looks like a problem but isn't"* section is safe.
  Several gaps are only visible by connecting the memo to its appendix: a year-1 teaser price vs
  renewal pricing, a Medicaid contract clause, a rack power limit, a dedicated-hardware clause.
- **B, "what variables must we consider?":** open prompts. The checklist includes non-obvious
  items, for example cannibalisation of the system's own clinic, workforce recruiting, the real
  threat model behind "the data is sensitive", the fact that self-hosting moves the security
  burden in-house, the model licence, and hybrid redaction/routing. There are 13 gold items but
  the list cap is 12, so the model has to choose.
- **C, debates:** strongest case on each side, the cruxes (empirical vs value), what evidence
  would change the answer, and the model's own lean with a confidence level.
- **D, steering:** R09 rewards the levers buried in messy facts: interval staffing vs the Monday
  peak, refill-status deflection, repeat calls, handle time after the EHR change, abandoned calls
  missing from the metric, and callbacks adding no capacity. R10 rewards the full chain, including
  the large but easily forgotten load from drivers who have home charging, fleets, the per-port
  utilisation ceiling and budget arithmetic. Reference: ~600 ports (430–780). $12M buys ~55–85
  ports, roughly 10–15% of the need.

**Output convention.** Each prompt asks for fixed `## Section` headings: *Missed issues / Looks like
a problem but isn't / Top 3 priorities / Bottom line* (A); *Variables / Top 3 priorities / What would
change my mind* (B); *Case for / Case against / Cruxes / What evidence would change the answer / My
lean* (C); *First steps / Measure first / What would kill the idea / Top 3 priorities* (R09); and
*Estimate chain / Result (ESTIMATE:, RANGE:, DECISION: lines) / Key sensitivities / Recommendation*
(R10). Lists have caps ("at most 10/12").

## How to run against a model

Requires Python with `requests` (e.g. the repo venv, `../.venv/bin/python`). One run is 10 requests.
Prompts are about 0.4k–1.2k tokens, so context is dominated by `--max-tokens` (default 16384).
Use the same settings for every model.

```bash
cd reason-eval
PY=../.venv/bin/python

# defaults: --max-tokens 16384 --temperature 0.6 --top-p 0.95, streaming on
$PY run_eval.py --url http://127.0.0.1:8000 --model <served-model-name> --label qwen38_r1 \
    --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'
$PY run_eval.py --url http://127.0.0.1:8000 --model <served-model-name> --label glm53_r1 \
    --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'
$PY run_eval.py --url http://127.0.0.1:8000 --model <served-model-name> --label dsv4_r1 \
    --extra-body '{"chat_template_kwargs":{"thinking":true}}'
#   (the thinking switch name depends on each model's chat template; check it, and keep thinking
#    on or off consistently across models)

$PY score.py
#   -> ../results/reason-eval/_scores/{summary.md,summary.csv,per_task.md,per_task.csv,details.json}
```

Other options: `--only R02,R07`, `--resume` (skips tasks that already have a non-empty,
untruncated answer), `--seed N`, `--no-stream`, `--api-key`, `--timeout`, `--out-root`.

**Repeats.** At temperature 0.6, single runs are noisy. Run each model 2–3 times as
`<name>_r1`, `<name>_r2`, ... and `score.py` adds a *Repeat groups* table (mean ± stdev per base
name and per task). Treat headline gaps smaller than about 2× the stdev as ties.

Only the answer channel (`Rxx.raw.txt`, with inline `<think>…</think>` stripped) is scored. The
reasoning stream is saved to `Rxx.reasoning.txt` but never scored. An empty answer, for example
when thinking used up `--max-tokens`, scores 0 for that task. `summary.md` reports `empty` and
`truncated` counts so this is visible.

## Blind judge pack

```bash
$PY make_judge_pack.py --labels qwen38_r1,glm53_r1,dsv4_r1
#   -> ../results/reason-eval/_judge/qwen38_r1+glm53_r1+dsv4_r1/
#      JUDGE_INSTRUCTIONS.md, R01..R10.md, all_tasks.md, _key.json/_key.md (HIDDEN)
# give all_tasks.md (or the instructions + one Rxx.md at a time) to a separate judge model or person,
# save its verdict blocks to verdicts.md in that folder, then:
$PY make_judge_pack.py --tally ../results/reason-eval/_judge/qwen38_r1+glm53_r1+dsv4_r1/verdicts.md
#   -> tally.md: mean rank, Borda points, pairwise wins, mean insight / prioritisation / usefulness
```

- **Blinding:**
  - Answers are shuffled independently per task and labelled X/Y/Z, reproducibly via `--seed`.
  - `<think>` blocks are removed and the reasoning stream is never included.
  - Model, vendor and label names in the text are replaced with `[model]`.
  - Answer headings are demoted so they nest under `## Answer X`.
- **Judge rubric:** scores insight, prioritisation and decision-usefulness from 1 to 10, then
  ranks. It tells the judge not to reward length or confident tone, and to penalise flagging
  non-problems.
- **Optional `--with-reference`:** appends the gold checklist, including the decoys and why
  they are not problems, to each task file. Leave it off for a fully independent judgement and
  turn it on for a calibrated one.
- **Validation:** the tally was checked end-to-end on the mocks.

## How scoring works

- **Parsing:** each answer is parsed into sections, matched by flexible regexes on headings,
  including bold-only or "Heading:" lines. Each section is split into **units**:
  - one top-level list item, including its nested bullets;
  - one paragraph;
  - one table row;
  - or one `### 1. Issue name` sub-heading together with everything under it.

  A gold item is credited when a unit satisfies its keyword groups (every group needs at least one
  regex hit, as in call-eval). A unit of ≤ 8 words, such as a bold title line, is also tried merged
  with the next unit.
- **Anti-padding:** only the first **12 units per section** count.

Per-task components, each in [0, 1]. A task's score is the weighted mean of the components that
apply to it. **Headline = mean task score × 100**, so every task counts equally.

| component | weight | applies to | definition |
|---|---|---|---|
| coverage | 55 | all | importance-weighted recall of gold items (high = 2, normal = 1). Units under "Looks like a problem but isn't" never count. Debate arguments count only in their own side's section |
| priorities | 15 | A, B, D | distinct high-importance items hit by the first 3 units of *Top 3 priorities* (R10: *Key sensitivities*) ÷ min(3, #high) |
| decoy_avoidance | 15 | A | 1 − (decoys flagged ÷ decoys). A decoy is flagged if a unit in *Missed issues* or *Top 3 priorities* matches the decoy and no gold item |
| cruxes | 15 | C | importance-weighted recall of gold cruxes, counted only inside the *Cruxes* section |
| balance | 10 | C | see below |
| estimate | 15 | R10 | 0.6 × point estimate (1 if in 250–1,200, 0.5 if in 125–2,400) + 0.4 × the `DECISION:` line says $12M is not enough / covers a fraction |
| structure | 5 | all | share of required sections present; *My lean* needs a % or a confidence statement for full credit |

The effective weights are A 55/15/15/5, B 55/15/5, C 55/15/10/5 (coverage/cruxes/balance/structure),
R09 55/15/5 and R10 55/15/15/5. `summary.md` also reports category means (A–D), component means,
per-task scores, median answer words, speed (median s/task, TTFT, decode tok/s), and empty and
truncated counts.

**Debate balance heuristic.** `balance = 0.5 × min(rf, ra)/max(rf, ra) + 0.5 × min(1, (min(wf, wa)/max(wf, wa)) / 0.6)`.

- rf and ra are the gold-argument recall within the *Case for* and *Case against* sections.
- wf and wa are their word counts.
- In words: both sides should hit a similar share of the strongest known arguments, and neither
  side should be less than ~60% the length of the other.
- If either side section is missing, balance is 0.

## Gold validation and self-test (no model needed)

```bash
$PY tools/build_gold.py        # only after editing tools/gold_src/*.py
$PY tools/validate_gold.py     # -> task table, totals, "gold OK"
$PY selftest/make_mocks.py     # writes selftest/results/*, scores into selftest/scores/
```

`validate_gold.py` checks the following for every item, crux and decoy:
- its own text and **≥ 2 paraphrases** satisfy its matcher;
- each paraphrase still matches after going through the Markdown parser as a list item;
- no `negatives` entry matches;
- no decoy text or paraphrase matches any gold item or crux (so flagging a decoy is never credited);
- every regex compiles.

It also checks that tasks with a priorities section have ≥ 3 high items, that debates have both
sides and ≥ 2 cruxes, that the R10 decision matcher accepts its paraphrases and rejects its
negatives, that every required section is named in the prompt, and that each prompt is < 20k tokens.

| mock | headline | notes |
|---|---|---|
| mock_perfect (gold texts in the right sections, decoys listed as non-issues) | **100.0** | every component 100 |
| mock_padded (every gold item and every decoy in one long list, generic top-3) | **48.6** | coverage 69 (12-unit cap), priorities 0, decoy avoidance 0, no cruxes/balance |
| mock_sloppy (generic filler, ~1/3 of items, takes every decoy, low-importance priorities, one-sided debate without a cruxes section, wrong Fermi answer, 1 empty reply) | **31.7** | coverage 42, priorities 4, decoys 0, Fermi 0 |
| mock_shuffled (the perfect answer for the wrong task) | **12.9** | matcher-specificity control: coverage 4. The rest is structure, plus "not flagging" another task's decoys |

Hand-written natural-language answers, using bold titles, `###` per item, nested bullets and
non-gold wording, scored 94–100 on R02, R03, R04, R05 (85: 10 of 13 variables), R07, R09 and R10
during development. This means the matchers credit paraphrases, not just the gold wording.

## Limitations

- **Keyword matching measures coverage, not depth.** A model can name the right issue with a
  shallow or wrong explanation and still get credit. Use the blind judge pack for quality,
  prioritisation and usefulness, and check `details.json` (`items_hit` shows the unit that matched
  each item) before trusting small differences.
- **Missed credit is possible.** Unusual wording may be missed. Look at `items_missed` in
  `per_task.md` and the answer itself before concluding that a model missed something. The
  matchers lean lenient: one unit can credit several items.
- **Small n, high variance.** There are 10 tasks with about 8–13 items each, so one task is 10% of
  the headline. Free-text answers at temperature 0.6 vary between runs; use repeats.
- **Gold is opinionated.** Importance levels, the "high" set used for priorities, and the debate
  argument lists are judgement calls. The debate gold covers the standard strongest arguments, not
  every reasonable one.
- **Formatting.** A model that ignores the requested headings loses structure points. In debates
  it also loses its arguments and cruxes, because they only count in their sections. Heading
  detection is tolerant: "Pros", "Arguments against", "Key cruxes", "**Top 3 priorities:**" and
  similar variants all work.
