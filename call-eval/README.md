# call-eval: local-LLM benchmark for call-transcript analysis

A small, reproducible evaluation for comparing local models (e.g. Qwen3.8-Flash-Next,
DeepSeek-V4-Flash, GLM-5.3-Flash served through an OpenAI-compatible `/v1/chat/completions`
endpoint) on the job of reading customer/patient phone-call transcripts and producing:
(a) a call-quality score, (b) file notes, (c) compliance/risk flags, (d) recurring themes
across calls.

All data is **synthetic**. Every person, clinic, company, product, payer and phone number is
invented; any resemblance to real ones is coincidental. There is no real PHI.

## What is in here

| path | what |
|---|---|
| `transcripts/C01..C20.txt` | 20 synthetic call transcripts (speaker-labelled, timestamped, disfluencies, crosstalk, holds, off-topic talk) |
| `gold/Cxx.json` | ground truth per call, including keyword matchers used for scoring |
| `gold/themes.json` | the 2 cross-call themes and the calls they are planted in |
| `prompt.md`, `schema.json` | the fixed system + user prompt and the JSON output schema |
| `themes_prompt.md` | fixed prompt for the cross-call themes step |
| `run_eval.py` | runs a model over all transcripts (+ optional themes step), records raw output and timings |
| `score.py` | deterministic scorer -> per-model table, per-transcript breakdown, headline score |
| `evallib.py` | shared JSON extraction + keyword matching (used by both runner and scorer) |
| `selftest/make_mocks.py` | builds perfect / sloppy / shuffled mock outputs and scores them (no model needed) |
| `tools/validate_gold.py` | consistency checks on the gold labels |
| `tools/build_transcripts.py`, `tools/src/`, `tools/pools/` | how the transcripts were built (see below) |

## The dataset

~94k tokens in total (o200k tokenizer). Lengths: 7 calls under 2.5k tokens, 7 calls of
2.5k-5k, and 6 longer calls (5.0k, 5.9k, 7.4k, 9.4k, 11.3k and 17.8k tokens). Long calls are where
weak models miss things: the planted facts are spread across 30-75 minutes of small talk,
holds, IVR menus, troubleshooting and side conversations.

| call | type | tokens | gold quality | outcome | flags | decoys | subtle | theme |
|---|---|---|---|---|---|---|---|---|
| C01 | scheduling | 2,110 | 5 | resolved | 0 | 1 | 2 | - |
| C02 | billing_dispute | 2,392 | 2 | callback | 2 | 0 | 2 | double charge |
| C03 | post_procedure_followup | 5,020 | 2 | resolved | 1 | 1 | 3 | fasting conflict |
| C04 | pharmacy_refill | 1,974 | 4 | callback | 0 | 2 | 3 | - |
| C05 | billing_dispute | 3,985 | 3 | resolved | 1 | 0 | 3 | double charge |
| C06 | no_show_followup | 2,043 | 5 | escalated | 0 | 2 | 3 | - |
| C07 | pre_procedure | 7,424 | 2 | callback | 2 | 1 | 3 | fasting conflict |
| C08 | saas_support | 2,015 | 4 | resolved | 0 | 0 | 3 | - |
| C09 | insurance_verification | 3,013 | 3 | callback | 1 | 1 | 3 | double charge |
| C10 | saas_support | 17,813 | 2 | escalated | 3 | 1 | 4 | - |
| C11 | sales | 2,503 | 2 | callback | 2 | 0 | 2 | - |
| C12 | complaint_escalation | 4,051 | 3 | escalated | 1 | 1 | 3 | fasting conflict |
| C13 | insurance_verification | 9,400 | 2 | resolved | 2 | 1 | 4 | - |
| C14 | complaint_escalation | 11,267 | 3 | escalated | 3 | 1 | 4 | double charge |
| C15 | pharmacy_refill | 1,790 | 1 | resolved | 3 | 0 | 2 | - |
| C16 | scheduling | 2,577 | 5 | callback | 0 | 2 | 3 | fasting conflict |
| C17 | sales | 5,930 | 2 | callback | 2 | 2 | 4 | - |
| C18 | post_procedure_followup | 4,005 | 5 | escalated | 0 | 2 | 3 | double charge |
| C19 | saas_support | 2,558 | 5 | resolved | 0 | 1 | 3 | - |
| C20 | scheduling | 1,833 | 1 | resolved | 2 | 0 | 3 | - |

Totals: **25 planted flags**, **19 decoys**, **60 subtle facts**, 71 action items, 2 themes.

Agent competence is deliberately varied (quality 1 to 5); 7 calls have no real flags, so a
model that flags everything loses precision.

- **Flags** include: info disclosed before identity verification (C02, C15), PHI disclosed to
  an unverified ex-partner and contact number changed at his request (C20), a spouse's
  account disclosed without authorisation (C14), refund/credit/waiver promised outside
  policy or authority (C02, C05, C10, C12), a promised transfer that never happened (C09), a
  missed callback commitment (C14), DVT warning signs dismissed (C03), an anticoagulant never
  addressed before surgery (C07), early controlled-substance refill plus an interaction
  dismissed by a technician (C15), coverage misinformation and an out-of-network booking
  (C13), misleading sales claims (C11, C17), credential sharing and another customer's data
  disclosed (C10, C17).
- **Decoys** look like flags but are not, e.g. verification that did happen, the patient
  authorising a family member, a fee waiver or discount within stated policy, a refund that
  feels late but is inside the 14-day window, a "sharp pain" that is a joke about money, a
  symptom that was escalated properly, an anonymised customer reference.
- **Subtle facts** are things only careful reading catches: corrected dates, IDs, amounts
  and head-counts, changed phone numbers/drivers/locations, a second issue raised in passing
  at the very end, a detail buried in the middle of a long call.
- **Themes**: (1) the new "ClearPay" payment portal double-charges copays already paid at
  the desk (5 calls, sometimes mentioned only in passing); (2) the mailed pre-procedure
  packet says "nothing after midnight" while the text reminder says "clear liquids until
  2 hours before" (4 calls).

## How to run against a model

Requires Python with `requests` (e.g. the repo venv, `../.venv/bin/python`). One run is 20
requests plus 1 for themes; prompts are up to ~20k tokens.

```bash
cd call-eval
PY=../.venv/bin/python

# per-call analysis + themes step; results -> ../results/call-eval/<label>/
$PY run_eval.py --url http://localhost:8000 --model <served-model-name> --label glm53 --themes

# options
#   --max-tokens 4096 --temperature 0.1     (defaults)
#   --extra-body '{"chat_template_kwargs":{"enable_thinking":false}}'   (turn reasoning off/on)
#   --json-mode        send response_format={"type":"json_object"} if the server supports it
#   --no-stream        no streaming (then no TTFT)
#   --only C10,C14     subset;  --resume  skip calls that already parsed
#   --themes-only      re-run only the themes step on existing outputs

# score every label found under ../results/call-eval
$PY score.py
#   -> ../results/call-eval/_scores/{summary.md,summary.csv,per_transcript.md,per_transcript.csv,details.json}
```

Run each model with the same prompt, temperature and max-tokens. If a model reasons
(`<think>` or a separate reasoning channel), give it enough `--max-tokens` that the JSON is
not truncated: truncated replies fail to parse and score zero, which is intended. Note the
reasoning setting in the label (e.g. `qwen-think`, `qwen-nothink`).

Recorded per call (`Cxx.meta.json`): time to first token (any token, and first content
token), total time, prompt/completion tokens from the server's `usage` (estimated from
characters and marked `usage_estimated` if the server sends none), overall and decode
tokens/s, finish reason, parse mode, errors. `run_manifest.json` stores the model, URL,
parameters and hashes of the prompt, schema and transcripts so runs can be checked as
comparable.

## How scoring works

`score.py` re-parses each `Cxx.raw.txt` (it strips `<think>` blocks and code fences and
recovers a JSON object from surrounding text; `strict_json_rate` reports how many replies were
clean JSON). A reply that does not parse scores **0 on every component for that call**,
precision and decoy avoidance included. A missing call also scores 0.

Per call:

| component | rule | weight |
|---|---|---|
| call_type | normalised exact match; a few calls accept a second label (e.g. C14 complaint/billing) | 5 |
| outcome | normalised exact match; ambiguous calls list accepted alternatives | 10 |
| sentiment | mean of start and end exact matches (negative/neutral/positive) | 5 |
| quality_pm1 | predicted score within +/-1 of gold | 10 |
| quality_reasons | recall of the planted reasons for the score (keyword) | 5 |
| flag_recall | planted flags matched one-to-one (maximum bipartite matching) by predicted flags | 20 |
| flag_precision | TP / (TP + unmatched flags + decoy hits); see "acceptable" below | 10 |
| decoy_avoidance | 1 - fraction of the call's decoys that were flagged (only the 12 calls with decoys) | 5 |
| action_recall | gold action items matched by any predicted action item | 10 |
| subtle_recall | subtle facts found anywhere in the free-text fields (notes, details, actions, flags) | 15 |
| themes | of the 2 planted themes, how many appear in the themes-step output | 5 |

**Headline = sum of weight x component mean** (0-100). Per-call components are averaged
over the 20 calls; recall is 1.0 for a call with nothing to recall, and precision is 1.0
when the model raises no flags.

Keyword matching: every gold item has a `match` list of groups; the item counts as found if
**every group has at least one regex hit** (case-insensitive, after normalising quotes and
dashes) in the model's text. Example (C13 out-of-network booking):
`[["ridgeline", "out.of.network", "non.?contracted", "wrong facility", ...]]`. Corrected
values are what is matched (e.g. C05 matches ticket `58871`, not the misspoken `58817`).

**Acceptable flags.** Some things are true and worth noting but are not agent-conduct
flags (e.g. "the ClearPay portal double-charges"); each call lists these as
`acceptable_flags`. A predicted flag that matches one is neither credited nor penalised.
Order of matching for a predicted flag: real flag -> decoy (counts as a false positive and a
decoy hit) -> acceptable (ignored) -> otherwise false positive. A second flag that only
re-states an already-credited flag is ignored.

Also reported but not weighted: parse rate, strict-JSON rate, summary <= 120 words rate,
quality-score absolute error (in details), theme call-id recall, median latency, TTFT and
decode speed.

## Self-test (no model needed)

```bash
$PY tools/validate_gold.py     # evidence quotes exist in transcripts, matchers self-consistent, decoys can't score as flags
$PY selftest/make_mocks.py     # writes selftest/results/*, scores into selftest/scores/
```

Result at the time of writing:

| mock | headline | notes |
|---|---|---|
| mock_perfect (derived from gold) | **100.0** | every component 100 |
| mock_sloppy | **39.2** | 2 parse failures (truncated long call, prose reply), always resolved/neutral/score 4, generic reasons, takes every decoy bait, misses subtle facts: flag recall 62 (7 calls have no flags, so they count as full recall), precision 15, decoy avoidance 0, subtle 25, themes 1/2 |
| mock_shuffled (perfect answers for the wrong call) | **26.3** | a control for matcher specificity: flag recall only from the vacuous no-flag calls, action recall 1, subtle recall 0 |

## Limitations

- **Synthetic data.** Written to plant specific facts. Real calls are messier (overlapping
  speech, transcription errors, accents, longer silences), and the agents here make mistakes
  in ways chosen to be testable. Good scores here are necessary, not sufficient.
- **Keyword matching.** Matchers were written with synonyms and checked against the gold
  descriptions and a shuffled control, but a correct answer in unusual wording can be missed
  (false negative), and a vague answer that happens to use the right words can be credited.
  Look at `per_transcript.md` and `details.json` (unmatched predicted flags are listed
  verbatim) before trusting a small difference. A gap of a few headline points between
  models is noise.
- **Judgement calls.** Outcome, sentiment and quality are partly subjective; ambiguous calls
  accept alternatives and quality is scored within +/-1, but disagreements remain possible.
- **Filler.** Long calls get their length from reusable, fact-neutral filler blocks
  (`tools/pools/`) inserted only at marked points; no block repeats within a call, but the
  same small talk appears in several calls, and some transitions are abrupt.
- **Themes step depends on the model's own notes**, so it measures note quality and
  aggregation together. It has only 2 themes, so it carries little weight (5).
- **Small n.** 20 calls, 25 flags. Use it to rank models and find failure modes, not to
  certify one for production.
- Speed numbers come from one sequential request at a time; they do not measure throughput
  under concurrent load.

## Rebuilding the transcripts

Hand-written dialogue holding every planted fact is in `tools/src/Cxx.txt`; neutral filler is
in `tools/pools/*.txt`. `python tools/build_transcripts.py` re-creates `transcripts/`
deterministically (fixed seeds) and pads each call to its `@target` token count; it never
repeats a filler block within a call. Re-run `tools/validate_gold.py` after any change.
Changing transcripts invalidates earlier results (the transcript hash is stored in
`run_manifest.json`).
