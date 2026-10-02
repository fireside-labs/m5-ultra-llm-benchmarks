# call-eval-v2: harder call-transcript benchmark

A harder sibling of `../call-eval` (v1). v1 saturated: Qwen3.8-Flash-Next 8-bit scored 97.3
and GLM-5.3-Flash 4-bit scored 97.1, so it could no longer separate strong models. v2 keeps the
**same prompts (`prompt.md`, `themes_prompt.md`), the same output schema (`schema.json`), the same
runner and the same scorer logic**, so scores are comparable in kind. Only the data is harder,
plus one small scorer addition for decoy themes (see "Scoring changes"). `prompt.md`,
`schema.json` and `themes_prompt.md` are byte-identical to v1.

All data is **synthetic**. Every person, clinic, company, product, payer and phone number is
invented (phone numbers are in the 555-01xx range); any resemblance to real ones is coincidental.
There is no real PHI.

## What is in here

| path | what |
|---|---|
| `transcripts/C01..C16.txt` | 16 synthetic call transcripts (multi-party, ASR noise, holds, IVR loops, transfers) |
| `gold/Cxx.json` | ground truth per call: keyword matchers, plus v2 `paraphrases` and `negatives` |
| `gold/themes.json` | 3 cross-call themes and 1 decoy theme |
| `prompt.md`, `schema.json`, `themes_prompt.md` | identical to v1 |
| `run_eval.py` | v1 runner; results default to `../results/call-eval-v2/<label>/` |
| `score.py` | v1 scorer plus the decoy-theme penalty |
| `evallib.py` | v1 helpers; only `DEFAULT_RESULTS` changed |
| `selftest/make_mocks.py` | perfect / sloppy / shuffled mocks, scored without a model |
| `tools/validate_gold.py` | gold consistency checks (v1 checks plus paraphrase, negative and decoy-theme checks) |
| `tools/build_transcripts.py`, `tools/src/`, `tools/pools/` | how the transcripts were built |

## The dataset

**239k tokens** in total (o200k tokenizer, same as v1). There are 4 short control calls (2.2k–4k),
2 calls of 6k–8k, 5 calls of 12k–20k and 5 long calls of 21.6k–32.4k. The long calls run 1.5 to 3.5
hours on the transcript clock: realistic speech rates plus holds, IVR loops and transfers. 35k
tokens is more speech than fits in 90 minutes.

| call | type | tokens | gold quality | outcome | flags | decoys | subtle | theme |
|---|---|---|---|---|---|---|---|---|
| C01 | scheduling | 2,249 | 5 | resolved | 0 | 2 | 3 | - |
| C02 | billing_dispute | 5,898 | 3 | resolved | 1 | 2 | 3 | IVR misroute |
| C03 | pharmacy_refill | 13,708 | 2 | callback | 2 | 2 | 7 | PA fax |
| C04 | pharmacy_refill | 2,613 | 5 | resolved | 0 | 2 | 4 | (decoy: double charge) |
| C05 | no_show_followup | 7,930 | 3 | resolved | 2 | 2 | 7 | IVR misroute |
| C06 | saas_support | 17,662 | 3 | escalated | 2 | 2 | 7 | reminder date |
| C07 | insurance_verification | 21,594 | 2 | callback | 2 | 2 | 8 | PA fax |
| C08 | scheduling | 11,822 | 3 | resolved | 2 | 2 | 6 | IVR misroute |
| C09 | saas_support | 24,601 | 4 | resolved | 0 | 3 | 7 | reminder date |
| C10 | pre_procedure | 14,831 | 2 | resolved | 2 | 2 | 8 | PA fax |
| C11 | post_procedure_followup | 27,552 | 2 | escalated | 3 | 3 | 6 | IVR misroute |
| C12 | saas_support | 3,063 | 5 | resolved | 0 | 2 | 3 | (decoy: double charge) |
| C13 | complaint_escalation | 32,421 | 2 | escalated | 3 | 3 | 7 | PA fax |
| C14 | billing_dispute | 29,477 | 2 | callback | 3 | 3 | 7 | IVR misroute |
| C15 | sales | 3,993 | 3 | callback | 1 | 1 | 4 | - |
| C16 | sales | 19,668 | 3 | callback | 2 | 2 | 7 | reminder date |

Totals: **25 planted flags**, **35 decoys**, **94 subtle facts**, 101 action items, **3 themes and
1 decoy theme**. Several calls accept alternative outcome, sentiment or call-type labels where the
label is genuinely ambiguous (see `*_accept` in gold). Four calls have no real flags.

- **Flags:**
  - *Combining distant statements:*
    - C02: the agent states her $50 waiver limit early, then waives $95 later.
    - C03: the patient is "taking two of the white ones", and much later the pharmacist says the white ones are the new 20 mg tablets, so she is taking 40 mg/day.
    - C07: urgent review is requested for an order read aloud earlier as "routine".
    - C08: the agent books Harbor Street, then later confirms "same place, Eastgate".
    - C10: two different apixaban stop days.
    - C11: acetaminophen from three sources, and a tub bath recommended against discharge instructions read 20 minutes earlier.
    - C13: a promised callback that only the contact log reveals never happened; a financial promise made after the manager himself said such things go to a committee.
    - C14: a collections threat contradicting the IVR's recorded dispute policy; a hold promised and later read back as "Holds: none" without anyone noticing.
    - C16: "fixed in the current version" after saying the fix ships Oct 20.
  - *Casual compliance lapses:*
    - C05: the coordinator names the missed diabetes appointment to the roommate.
    - C06: the billing email is changed before verification; another customer is named.
    - C07: unrelated psychiatric history is volunteered to the payer.
    - C08: the father is told about the son's confidential adolescent visit.
    - C14: "nah, you're fine" instead of verification.
    - C15: "you're covered for HIPAA" on a plan stated earlier not to include a BAA.
    - C16: an admin invite is sent to a personal Gmail.
  - *Silent missed promise:* C05, "I'll give you the direct line before we hang up", which never happens.
  - *Corrected value hiding a missed escalation:* C11, the husband corrects 100.8 to 101.8 in crosstalk and the nurse never addresses it.
- **Decoys (35, more than the flags):**
  - *Mistakes the agent retracts in the call:* the copay $40 corrected to $4 (C03), "not taking new patients" (C01), "Tuesdays only" (C08), "fees can't be reversed" (C06), "Halvard denied it" (C13), "out of network" (C14).
  - *Disclosures that were consented to or permitted:* C01, C03, C08, C09, C10, C11, C13.
  - *Hypotheticals and hearsay:* a password-sharing question (C06), a brother-in-law's collections story (C02).
  - *Actions within stated policy:* fee waivers, refunds, prompt-pay discount, a 2-year price lock with deal-desk sign-off, a declined early refill of a controlled substance.
  - *Correct clinical handling:* shoulder pain explained as referred gas pain, a glucose of 240 handled properly, drain question escalated, half insulin dose per protocol.
  - *Look-alike problems:* "double charges" that are a pending hold (C04) or two workspaces (C12).
- **Subtle facts:** corrected numbers where gold is the corrected value and the pre-correction value is a `negative` the matcher must reject. Examples: $51.20 not 15.20, 0173 not 0137, 240 not 140, 8:15 not 8:50, 101.8 not 100.8, 40 mL not 14, $184 not 148, 42 seats not 24, INV-20417 not 20470, PA-2609-55170 not 55107. Also IDs, extensions, changed contact details and pickup sites, and details buried in the middle of 20–30k-token calls.
- **Quality judgement:**
  - C09's agent is rude and sarcastic but every answer is correct and policy-compliant (gold 4; rudeness is an `acceptable_flag`, so flagging it is neither credited nor penalised).
  - C02, C03, C10 and C11 have warm, empathetic staff with serious policy or safety failures (gold 2–3).
  - C14 mixes a rude, sloppy first agent with a good specialist who still misses one thing.
- **Themes:**
  - **T_IVR_MISROUTE** (5 calls, C02/C05/C08/C11/C14) is only small details: pressing 3 for refills lands callers in billing. Each mention is one or two lines in a call about something else.
  - **T_PA_FAX** (4 calls, C03/C07/C10/C13): prior auths "never received" because the clinic faxes Halvard's retired line 555-0144. The root cause is explicit only in C07 and C13.
  - **T_SAAS_DUE** (3 calls, C06/C09/C16): Tallyforge 7.4 reminder emails show the due date a day early.
  - **Decoy theme D_DOUBLE_CHARGE** (C04, C12): "charged twice" in two calls, both explained as non-issues with different causes.

### ASR realism

- *Hand-written into the core dialogue:*
  - Misheard drug names ("listen a pril", "a pixie ban") and number confusions (fifteen/fifty, fourteen/forty).
  - `[inaudible]`, `[crosstalk]`, false starts, IVR loops, holds, cold transfers back into the phone tree.
  - Mid-call agent changes (tech to pharmacist, tier 1 to tier 2, agent to coding specialist, nurse to surgical PA, agent to practice manager).
  - Stretches where diarization fails (`SPEAKER ?`) and the occasional wrong speaker label.
- *Added to filler by the builder:* deterministic fillers, stutters, `[inaudible]` and casing drift, plus whole filler blocks with lost speaker labels (`@diar_drop`, default 12%). Noise is never applied to core lines, so evidence quotes are untouched.

## What makes it harder than v1

1. **About 2.5x the tokens (239k vs 94k), concentrated in long calls.** Ten calls are 12k–32k tokens, versus one of 17.8k in v1. Planted facts sit in the middle of long calls, not only at the start and end.
2. **Flags need inference.** Most real flags need two statements that are far apart, a corrected value, or a casually phrased lapse. v1 flags were mostly explicit in a single exchange.
3. **More decoys than flags (35 vs 25; v1 had 19 vs 25), and better ones.** Retracted mistakes, consented disclosures, hypotheticals, hearsay and permitted actions. This targets GLM's v1 weakness (decoy avoidance 93) while the inference-heavy flags target Qwen's (flag recall 93).
4. **Corrected numbers are checked with negatives**, so answering with the first-mentioned value scores nothing.
5. **Quality scores need judgement** (rude-but-correct, warm-but-unsafe), and ±1 still separates "4–5 because the agent was nice" from gold 2.
6. **Themes**: 3 instead of 2, one built only from passing details across 5 calls, plus a decoy theme that costs points.
7. **Noisier transcripts**: speaker attribution is sometimes missing or wrong, and filler is noise-processed and harder to skip.

## How to run against a model

Same as v1. Requires Python with `requests` (e.g. the repo venv, `../.venv/bin/python`). One run is
16 requests plus 1 for themes; prompts are up to ~34k tokens (the largest transcript plus the prompt),
so the server context must be at least ~40k plus `--max-tokens`.

```bash
cd call-eval-v2
PY=../.venv/bin/python

$PY run_eval.py --url http://127.0.0.1:8000 --model <served-model-name> --label <label> --themes
$PY score.py
#   -> ../results/call-eval-v2/_scores/{summary.md,summary.csv,per_transcript.md,per_transcript.csv,details.json}
```

All v1 options work unchanged (`--max-tokens`, `--temperature`, `--extra-body`, `--json-mode`,
`--no-stream`, `--only`, `--resume`, `--themes-only`, `--out-root`). Use the same settings for every
model; give reasoning models enough `--max-tokens`, because a truncated reply scores 0 for that call.

## How scoring works

Identical to v1: same components and weights (call_type 5, outcome 10, sentiment 5,
quality_pm1 10, quality_reasons 5, flag_recall 20, flag_precision 10, decoy_avoidance 5,
action_recall 10, subtle_recall 15, themes 5), the same one-to-one flag matching, and the same
real-flag, then decoy, then acceptable, then false-positive order. See the v1 README for details.

### Scoring changes

- **Decoy themes:** a returned theme item that matches the decoy-theme matcher and no real-theme
  matcher counts against the themes component: `themes = found / (3 + decoys_reported)`. For
  example, all 3 themes plus the decoy gives 0.75. This is reported as `DECOY:D_DOUBLE_CHARGE` in
  the summary's "themes found" column.
- **Gold-side robustness (not scoring logic):** every flag and decoy carries at least 2 `paraphrases`.
  `validate_gold.py` checks that every paraphrase satisfies its item's matcher, that no decoy
  paraphrase satisfies a real flag's matcher, and that no `negatives` entry (wrong pre-correction
  values, near-miss wordings) satisfies its matcher.

## Self-test (no model needed)

```bash
$PY tools/validate_gold.py     # gold OK: 16 calls, 25 flags, 35 decoys, 94 subtle, 101 actions, 3 themes, 1 decoy theme
$PY selftest/make_mocks.py     # writes selftest/results/*, scores into selftest/scores/
```

| mock | headline | notes |
|---|---|---|
| mock_perfect (derived from gold) | **100.0** | every component 100 |
| mock_sloppy | **35.0** | 2 parse failures; always resolved/neutral/score 4; flag recall 45; precision 11; decoy avoidance 0; subtle 23; themes 25 (1 real theme plus the decoy) |
| mock_shuffled (perfect answers for the wrong call) | **30.0** | matcher-specificity control. Flag recall 25 comes only from the 4 no-flag calls; actions 2, subtle 3. The rest is coincidental outcome, sentiment and quality agreement. |

## Limitations

The v1 caveats all apply: synthetic data, keyword matching, judgement calls, small n, and
sequential speed numbers. In addition:
- **v2-specific caveats:**
  - The flags are harder partly because they need *inference*. A model may describe the right problem in words the matcher misses. Check `details.json` → `flags_false` before trusting small differences.
  - With 16 calls, one call is about 6% of every per-call component.
- **Filler pools:** v2 pools are the v1 pools minus 3 blocks that could contradict planted facts (preferred pharmacy, unchanged address, a fax/portal remark), with 2 lines neutralised, plus 11 new pools (~27k tokens). Filler is shared across calls and is noise-processed at build time.
- **Call clock:** long calls render as 1.5–3.5 hours on the transcript clock.

## Rebuilding the transcripts

Hand-written dialogue holding every planted fact is in `tools/src/Cxx.txt`; filler is in
`tools/pools/*.txt`. `python tools/build_transcripts.py` re-creates `transcripts/` deterministically.
It accepts `--only C03,C11` and `--check`, and prints total and core tokens per call. Re-run
`tools/validate_gold.py` and `selftest/make_mocks.py` after any change. Changing transcripts
invalidates earlier results (the transcript hash is stored in `run_manifest.json`). `gold/*.json`
is the source of truth; some files were first generated by throwaway scripts and then tightened by hand.
