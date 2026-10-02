# Local LLM long-context benchmarks (Mac Studio M5 Ultra, 256 GB)

Benchmarks for how local models behave on the workloads that matter at long context:
pasting a huge document, and a coding agent that keeps adding to the same conversation for hours.
They cover prefill and decode against context depth (cold and cached), MTP / DSpark speculative decoding,
overnight agentic coding sessions scored by hidden tests, a 1M-token DeepSeek run (speed, recall and power),
request-for-request replays of real agent sessions on two engines, and a bonus LTX-2.5 text-to-video timing in ComfyUI.
Part 2 adds GLM-5.3-Flash, 1M-token runs for all three models (Qwen with YaRN), the prefill scaling exponent,
MTP vs DFlash on GLM, parallel-request throughput, a blind code review of the agents' finished projects, and four
synthetic quality evals (critical thinking, pushback, call-transcript analysis v1/v2) plus a creative-writing sample.

The narrative write-up with all the findings is in **[WRITEUP.md](WRITEUP.md)**. The chart notes are in
[charts/CHARTS.md](charts/CHARTS.md), the tables as images are in [tables/](tables/), and the full agentic report is in [report/REPORT.md](report/REPORT.md).

## Test system

| | |
|---|---|
| Hardware | Mac Studio, Apple M5 Ultra (30-core CPU, 64-core GPU), 256 GB unified memory (`iogpu.wired_limit_mb=245760`) |
| OS | macOS 27.0.1 |
| llama.cpp | commit `19e28a2` (Metal, flash attention on, `-b 2048 -ub 2048`) |
| oMLX | Part 1: 0.7.0rc1 (Homebrew build, and an rc1 source build with `OMLX_WITH_CUSTOM_KERNEL=1` for DeepSeek V4). Part 2 (and the Qwen numbers marked 0.7.0): 0.7.0 built from source with `OMLX_WITH_CUSTOM_KERNEL=1` ("kernel build"), plus the YaRN patch in `patches/` for Qwen past 262k |
| ComfyUI | official "Text to Video (LTX-2.5)" template, int8 checkpoints |
| Python | 3.12, packages in `requirements.txt` |

Models: Qwen3.8-Flash-Next (llama.cpp: unsloth Q8_0 GGUF; oMLX: oQ8e), DeepSeek-V4-Flash-Vision-Exp
(llama.cpp: UD-Q8_K_XL GGUF + DSpark draft) and DeepSeek-V4-Flash-0731 (oMLX: oQ4e with built-in MTP/DSpark),
GLM-5.3-Flash 4-bit (320B total, 18B active; oMLX: Jundot oQ4e for speed tests, Vontra oQ4-MTP for MTP and most
quality tests; 8-bit doesn't fit in 256 GB), LTX-2.5 22B distilled int8.

## Key results

| Cold prefill vs cached next step | Cold (fresh prompt) | Warm (next step, cached) |
|---|---|---|
| Qwen, 250k context, llama.cpp | 234 s | 0.64 s |
| DeepSeek, 400k context, llama.cpp | 934 s | 1.23 s |
| DeepSeek, 500k context, llama.cpp | 1,311 s | 1.42 s |

| Qwen 8-bit, MTP off | 10k | 100k | 250k |
|---|---|---|---|
| Decode, llama.cpp (Q8_0) | 47 t/s | 30 t/s | 17 t/s |
| Decode, oMLX (oQ8e) | 56 t/s | 53 t/s | 51 t/s |
| Prefill, llama.cpp | 1,622 t/s | 1,393 t/s | 1,069 t/s |
| Prefill, oMLX | 1,714 t/s | 1,555 t/s | 1,365 t/s |

The oMLX rows above are the Homebrew 0.7.0rc1 build without custom kernels. On the oMLX 0.7.0 kernel build, Qwen
prefills at 4,235 t/s and decodes at 63 t/s at 250k (Part 2, charts 11 and 12).

| Speculative decoding speedup | Code | Reasoning | JSON | Prose |
|---|---|---|---|---|
| Qwen MTP (oMLX), temp 0 | 1.97x | 2.09x | 2.28x | 1.53x |
| DeepSeek DSpark (oMLX) | 1.53x | 1.54x | 1.51x | 1.00x |

| Overnight agent run | Final context | Steps/hour | Hidden tests passed |
|---|---|---|---|
| DeepSeek, oMLX + kernels + DSpark (3 h) | 421k | 348 | 52/54 |
| DeepSeek, llama.cpp + DSpark (3 h) | 436k | 241 | 49/54 |
| Qwen, oMLX + MTP (1 h) | 201k | 181 | 23/24 |
| Qwen, llama.cpp (1 h) | 106k | 91 | 19/19 |
| Qwen, llama.cpp + pi harness (1 h) | 134k | 118 | 45/45 |

| DeepSeek 0731 oQ4e on oMLX (kernel build), 1M run | 300k | 500k | 750k | 1M |
|---|---|---|---|---|
| Cold prefill | 7.6 min | 17.2 min | 34.3 min | 57.2 min |
| Decode | 26 t/s | 24 t/s | 21 t/s | 22 t/s |
| Next cached step (64 new tokens) | 13 s | 22 s | 33 s | 44 s |
| Hidden codes recalled (of 3) | 3 | 3 | 3 | 2 |

Three vault codes were hidden at 10%, 50% and 90% of the text, each next to a near-identical decoy. At 1M the
earliest code came back as `7249-KILO`, a blend of the decoy's digits and the real code's suffix. One run per depth.
Chip power (macmon, CPU plus GPU, not wall power) stayed at about 135 W during prefill.

Replaying the same 181-request Qwen agent session (to 200k, 256 output tokens per step) took 18.5 min
on oMLX against 29.7 min on llama.cpp. For DeepSeek, replaying 209 requests (every 5th step of a real
1,044-step session, up to about 420k) took 45.8 min on oMLX against 72.7 min on llama.cpp:

| DeepSeek replay, median TTFT / decode | 0-100k | 100-200k | 200-300k | 300-420k |
|---|---|---|---|---|
| oMLX (0731 oQ4e, kernel build) | 3.7 s / 34 t/s | 4.6 s / 31 t/s | 5.4 s / 30 t/s | 7.3 s / 29 t/s |
| llama.cpp (Vision-Exp UD-Q8_K_XL) | 4.1 s / 31 t/s | 6.8 s / 27 t/s | 9.6 s / 24 t/s | 16.6 s / 21 t/s |

oMLX wrote about 8% fewer tokens (it stopped early on some replies; llama.cpp was forced to 256), so compare TTFT and
t/s rather than total time. The synthetic warm test (one giant message plus a 64-token follow-up, chart 05)
favoured llama.cpp, but real agent turns add about 2k tokens each and the replay favours oMLX. LTX-2.5 generated 5 s of 1080p video with audio in 244 s
(`--gpu-only`, 1024 VAE tiles), and 720p in 92 s.

Caveats: there was one overnight run per setup. The DeepSeek engine comparison uses two variants and two packagings of the same
native format (DeepSeek ships FP4 experts + FP8 elsewhere): 0731 as oQ4e, a 4-bit mixed re-quant, on oMLX;
Vision-Exp as UD-Q8_K_XL, which keeps the native FP4 experts, on llama.cpp. Experts are 4-bit in both. See WRITEUP.md for the details.

## Part 2: GLM-5.3, 1M context for all three models, and quality

Everything in Part 2 runs on the oMLX 0.7.0 kernel build. Reasoning effort: GLM max (high for the call eval and
code), Qwen xhigh, DeepSeek low (oMLX's default for DeepSeek V4; see caveats). The quality tests are synthetic and
self-contained: no web search, no real people, every fact needed is in the prompt. Mostly one or two runs per test.

### Speed, same build

| oMLX 0.7.0 kernel build, MTP off | 10k | 100k | 250k |
|---|---|---|---|
| Qwen 8-bit prefill / decode | 3,854 / 72 t/s | 4,464 / 64 t/s | 4,235 / 63 t/s |
| GLM-5.3 4-bit prefill / decode | 1,877 / 57 t/s | 1,879 / 54 t/s | 1,720 / 48 t/s |

Qwen reads long prompts about 2.5x faster than GLM past 50k and decodes about 30% faster at 250k (GLM has 18B
active parameters per token, Qwen 6B). Against the Homebrew 0.7.0rc1 build used in Part 1, Qwen's 250k prefill went
from 1,365 to 4,235 t/s (charts 11 and 12); that is the new release plus the custom kernels together. With a 4k-token
follow-up, oMLX 0.7.0 starts the next Qwen turn faster than llama.cpp at every depth (2.9 s vs 6.3 s at 250k).

### 1M tokens, all three

Same test as Part 1: Gutenberg novels to 1M tokens, three vault codes at 10%, 50% and 90%, each next to a
near-identical decoy. One run per depth.

| At 1M tokens | Cold prefill | Decode | Next turn (cached) | Codes found |
|---|---|---|---|---|
| Qwen 8-bit + YaRN x4 | 5.3 min | 29 t/s | 6.7 s | 3/3 |
| GLM-5.3 4-bit | 13.0 min | 31 t/s | 19.9 s | 3/3 |
| DeepSeek V4 Flash 0731 | 57.2 min | 22 t/s | 44 s | 2/3 |

- Qwen is trained to 262k. oMLX 0.7.0 ignored the YaRN setting for `qwen4_exp`, so `patches/omlx-qwen4exp-yarn.patch`
  adds it (factor 4, gated on `rope_parameters` type `yarn`). At 250k, YaRN and native RoPE gave the same speed and
  recall. Recall held at 500k and 1M. A needle test shows lookup works at 1M, not that reasoning is as good there.
- DeepSeek on 0.7.0 took 57.2 min for 1M, the same as the rc1 kernel build. It missed the earliest code again, this
  time answering with the decoy (`7249-KILN`).
- For the 1M runs the memory guard was set to `custom` with a 244 GB ceiling; the default ("balanced") rejected the
  1M follow-up even though it fit.

**Prefill scaling exponent.** Fit of cold prefill time t = c·n^α on same-config runs from 100k up:

| Model | α | Local α, short to long | Share of prefill from the n² term |
|---|---|---|---|
| Qwen | 1.15 | 1.04 to 1.29 | 5% at 100k, 35% at 1M |
| GLM | ~1.2 | 1.03 to 1.25 | 6% at 100k, 37% at 1M |
| DeepSeek (128k to 1M, 0.7.0) | 1.58 | 1.42 to 1.74 | over half from about 300k, about 80% at 1M |

Qwen and GLM are mostly linear-attention layers and stay matmul-bound until about 250k. DeepSeek is attention-bound
from about 300k. The DeepSeek fit uses the clean 0.7.0 run (`results/longctx/*ds0731-omlx070-scaling.jsonl`:
128k 134 s, 256k 357 s, 512k 1,072 s, 1M 3,434 s).

### MTP vs DFlash on GLM

| GLM-5.3 decode speedup | Code | Reasoning | JSON | Prose | 8k summary |
|---|---|---|---|---|---|
| Native MTP (Vontra oQ4-MTP) | 1.32x | 1.33x | 1.44x | 0.98x | 1.06x |
| DFlash2 drafter (oQ4e) | 1.17x | 1.38x | 1.35x | 0.76x | 0.85x |

DFlash disables GLM's prefix cache in oMLX ("prefix snapshots not supported"), which rules it out for agents. MTP
keeps the cache (next turn at 100k: 1.4 s with +64 tokens, 3.1 s with +4k). Neither is text-identical to MTP off at
temperature 0. MTP acceptance was 64-82%, about 2 tokens per cycle. On Qwen, the MTP gain fades with depth on long
summary prompts (101 vs 72 t/s at 10k, about even by 200k).

### Code quality: agents on one harness, then a blind review

| Run (pi harness unless noted, oMLX 0.7.0) | Result |
|---|---|
| Qwen, MTP on | all 30 milestones in 38 min, 52/54 hidden tests, one commit per milestone |
| GLM, MTP on (2 h) | all 30 in 64 min, then an "extend everything" pass; 53/54 hidden tests, 105 commits, 388k context |
| DeepSeek, DSpark on | milestone 17 in 64 min, 53/54, then the server died (buffer-pool growth, see gotchas); retry: milestone 17, 51/54 |
| DeepSeek Vision-Exp, DeepSeek Harness, llama.cpp (3 h, night 1.5) | all 30, 53/54 |
| Qwen, Oh My Pi, oMLX rc1 (1 h, night 1.5) | milestone 15, hidden tests passing |

The three finished projects were then reviewed blind ([report/code-review.md](report/code-review.md)): build,
an independent 12-check conformance test, running each build and reading the code.

| | Qwen | GLM | DeepSeek |
|---|---|---|---|
| Conformance (12 checks) | 12/12 | 11/12 (sees through walls) | 10/12 (A* not shortest, sight radius off by one) |
| Unreachable code | none | about 2,200 lines | several unused modules |
| Overall ("would I merge it", 1-10) | 7 | 4 | 3 |
| Readability (1-10) | 6 | 4 | 7 |

DeepSeek's code is the most readable, but its comments describe features that aren't wired in. GLM's dead code
comes partly from TASK.md's "start again and extend" instruction (it added 21 `*-extended` modules nothing imports).
Milestone counts and the hidden tests (which cover milestones 1-17) flattered GLM and DeepSeek.

### Critical thinking: keyword checklist vs blind judge

10 self-contained tasks (flawed memos with planted gaps and decoys, "what variables matter", two debates, steering a
vague project, a Fermi estimate), two runs each at maximum reasoning, 16k-token limit
([reason-eval/](reason-eval/), results in `results/reason-eval/`).

| | DeepSeek | GLM | Qwen |
|---|---|---|---|
| Keyword checklist score (mean of 2 runs) | 93.5 | 89.3 | 81.9 |
| Blind judge, mean rank (1 = best, run 1) | 2.15 | 1.2 | 2.65 |
| Blind judge, insight / prioritization / usefulness | 7.1 / 7.2 / 7.3 | 8.2 / 8.2 / 8.2 | 6.1 / 5.8 / 5.8 |
| Answers cut off at 16k tokens (of 20) | 0 | 1 | 5 |

The checklist rewards covering the planted points; the judge (shown the answers as X/Y/Z, key hidden) rewards
insight. GLM beat each of the others on 9 of 10 tasks. Coverage is not insight. Verdicts and tally:
`results/reason-eval/_judge/qwen38_r1+glm53_r1+dsv4_r1/`.

### Pushback

Six decisions, then three follow-ups each: a valid critique (should update), a confident wrong critique (should
hold), and pure pressure (should not flip). Two runs each ([pushback-eval/](pushback-eval/)).

| | DeepSeek | GLM | Qwen |
|---|---|---|---|
| Score (mean of 2 runs) | 99.0 | 96.9 | 76.0 |
| Caved to a wrong critique or pressure | 0% | 0% | 17% |
| Right at the end, of 6 | 6 | 6 | 4 |

Qwen accepted false premises conditionally without checking the brief (told the rent was per week when the brief
says per month, it switched to "Elm Plaza (if weekly rent is correct)" and then defended it).

### Live blind debate

One long conversation per model (shown as A/B/C) arguing whether cloning a person to save a 12-year-old who needs a
heart could be justified. Not scored; transcripts are not published. Qwen conceded small points but protected its
conclusion with finer distinctions. DeepSeek made the most insightful moves but conceded nearly everything,
including a false legal claim (necessity is not a defense to murder), and adopted the user's conclusion. GLM took a
position, conceded only what was true and owned the costs of its own view, with very long reasoning per reply. In
the scripted pushback test DeepSeek never caved; live, on value arguments rather than checkable facts, it caved
constantly. Test the kind of disagreement you will actually have.

### Call-transcript analysis

Synthetic customer and patient calls: quality score, flags, action items, cross-call themes. v2 is the hard version:
16 calls, 239k tokens in total (up to about 33k per call), messy speech-to-text, 25 real flags against 35 decoys
([call-eval/](call-eval/), [call-eval-v2/](call-eval-v2/)).

| | GLM | Qwen | DeepSeek |
|---|---|---|---|
| v1 (20 calls) | 96.5-97.1 | 97.3 | 85.3 (thinking looped to the token limit on 2 calls) |
| v2 (16 calls) | 92.3 | 84.1 | 71.9 (looped on 2 calls again) |
| Time per call, v2 | 75 s | 105 s | 93 s |

v1 saturated (GLM and Qwen within noise). On v2, GLM and Qwen missed the same four flags, checked by hand as genuine
misses: another customer's details disclosed, a post-op fever of 101.8 dismissed, rescue-inhaler use 6-7 times a
day not routed to a clinician, and a promised billing hold never placed. Both catch loud procedural problems and miss
buried clinical ones; for production, use checklist prompts and human review on clinical calls.

### Parallel requests

`longctx/concurrency.py`, N cold requests at once, 512 output tokens each, oMLX `max_concurrent_requests` 8, MTP
off (MTP only runs at batch 1 and inflates the single-request baseline).

| Aggregate output, 1 / 2 / 4 / 8 requests | 1k-token prompts | 20k-token prompts |
|---|---|---|
| Qwen 8-bit | 53 / 71 / 93 / 118 t/s (2.2x) | 37 / 39 / 42 / 51 t/s (1.4x) |
| GLM-5.3 4-bit, reasoning low | 56 / 46 / 66 / 86 t/s (1.5x) | 26 / 22 / 24 / 27 t/s (about 1x) |

Short requests batch moderately (these are MoE models, so parallel requests hit different experts and weight reads
amortize less than on a dense model). Long prompts are prefill-bound and barely batch: about 180-190 transcripts per
hour per GLM instance whatever N is. oMLX's text-only batched engine refused both models (HTTP 409, model type not
supported), so all of this ran on its vision-language engine. With MTP on, Qwen went 63 to 104 t/s at 1k (1.7x).

### Roles

- DeepSeek V4 Flash: everyday assistant. Fast, concise, good at checklists and estimates; agrees too easily in open
  arguments.
- Qwen3.8-Flash-Next: coding. Fastest engine numbers and the best code in the blind review; check answers it hedges
  with "if what you said is true".
- GLM-5.3-Flash: analysis, decisions, call analysis, anywhere being right matters more than speed.

All three together are about 466 GB, so on 256 GB they are swapped (20-40 s per model switch in oMLX).

### Part 2 caveats

- One or two runs per test; treat small differences as noise.
- DeepSeek ran at oMLX's default *low* reasoning effort for the quality tests (not noticed until the end), while
  GLM ran at max/high and Qwen at xhigh. DeepSeek's quality scores came with less thinking, and part of its speed
  is from thinking less.
- Keyword scores are coarse; the blind judging matters more. One judge, one reviewer.
- Two GLM quants: Jundot oQ4e for speed, Vontra oQ4-MTP for MTP and most quality tests. 4-bit GLM beating 8-bit
  Qwen at reasoning doesn't say how 8-bit GLM would do.
- The YaRN result is needle recall only.

### Part 2 gotchas

- **DeepSeek V4 on oMLX 0.7.0 grows its pooled Metal buffers** to about 52 GB over an hour of agent work, until hard
  memory pressure aborts a request and the model is evicted (the first pi run ended with the server exiting). A
  pinned 244 GB ceiling only delayed it. Qwen and GLM don't do this; the rc1 kernel build ran DeepSeek for 3 h
  without it. Restart between long sessions. The memory-guard lines are in `results/agentic/overnight-logs/`.
- **Memory guard for 1M runs:** set `memory_guard_tier` to `custom` with a ceiling around 240-244 GB, then set it back.
- **oMLX admin key:** setting one makes the inference API require it too (HTTP 401 for every script). On a
  localhost-only server, set `auth.allow_unauthenticated_inference = true`; admin endpoints still need the key.
- **Engine version metadata:** result files from the 0.7.0 kernel build written before 2026-10-01 afternoon say
  `engine_version` `0.7.0rc1`, because `common.py` asked the Homebrew binary. Fixed; see
  [results/longctx/README.md](results/longctx/README.md).
- **GLM-5.3 can't turn reasoning off** (low, high or max). Low skips thinking on easy prompts and is right for speed
  tests.
- **Vontra GLM oQ4-MTP config:** 46 `mlp_layer_types` for 45 layers; trim to 45 or newer transformers refuses to
  load it ([patches/README.md](patches/README.md)).

## Layout

```
longctx/    corpus builder, depth benchmark (cold/warm), 1M needle/power run, MTP on/off compare,
            parallel-request benchmark (concurrency.py), llama.cpp helpers
agentic/    Deepdelve task, cache-logging proxy, agent loop, watchdog, referee, harness runner,
            overnight queue, session replay; hidden_tests/ are the referee's Vitest suites
call-eval/      call-transcript analysis eval v1 (20 synthetic calls, gold labels, runner, scorer, self-test)
call-eval-v2/   harder v2 (16 calls, messier speech-to-text, more decoys than real flags)
reason-eval/    critical-thinking eval (10 tasks), keyword scorer, blind judge pack, HTML viewer (tools/)
pushback-eval/  multi-turn pushback eval (6 topics x valid / invalid / pressure follow-ups), scorer, judge pack
creative-eval/  two-chapter creative-writing prompt, blind side-by-side viewer, chat replay helper
patches/    oMLX 0.7.0 YaRN patch for qwen4_exp, GLM MTP config fix (README.md)
ltx/        ComfyUI LTX-2.5 API workflows, blueprint converter, timing runner
results/    raw output from every run used in the charts, tables and write-up
  longctx/  bench_ctx.py / bench_1m.py output (meta line + one row per request); README.md lists the labels
            and the engine-version metadata bug
  mtp/      mtp_compare.py output, including model text (used to show where MTP/DSpark/DFlash outputs diverge)
  concurrency/  concurrency.py output
  replay/   replay.py output (Qwen and DeepSeek sessions)
  ltx/      run_ltx.py output
  agentic/  cache_proxy logs per run, overnight-events.log, filtered oMLX server logs (incl. memory-guard lines),
            runs/: per run, referee JSONL, git log/grep snapshot of the agent's repo, filtered harness log
  call-eval/, call-eval-v2/   per-model outputs (parsed JSON, raw text, reasoning, timing) and _scores/
  reason-eval/, pushback-eval/  per-run outputs, _scores/, and reason-eval's blind judge pack (_judge/: tasks,
            verdicts, tally, and the _key files that unblind it)
  creative-eval/  the two chapters and reasoning per model
  probes/   ubatch probes referenced in chart 08
charts/     make_charts.py and the 12 charts built from results/
tables/     the key tables as PNGs: make_tables.py renders them from tables.json and tables_v2.json
report/     make_report.py, the agentic charts and REPORT.md; code-review.md (blind review of the finished
            agent projects) with its conformance test and metrics script in code-review/
reddit/     the original Reddit post text
```

Host names and home-directory paths in the result metadata are replaced with `bench-host` and `~`. All eval data
(calls, memos, topics, gold labels) is synthetic.
The corpus text and token caches aren't included (`build_corpus.py` rebuilds them, and the manifests in
`longctx/corpus/` record sources and sha256). Neither are the agents' workspaces or transcripts.

## Reproducing

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

**Long context** (`longctx/`, details in [longctx/README.md](longctx/README.md)):

```
cd longctx
python build_corpus.py --kind books            # 10 Gutenberg novels; check sha256 against corpus/books.manifest.json
./serve_llama.sh <model.gguf> 262144            # or: omlx serve --model-dir <dir> --port 8000
python bench_ctx.py --engine llama.cpp --url http://127.0.0.1:8080 --tokenizer Qwen/Qwen3.8-Flash-Next \
    --label qwen-q8-llama --depths 10000,50000,100000,150000,200000,250000
python bench_1m.py --url http://127.0.0.1:8000 --model <served-name> --tokenizer <model dir> \
    --label ds-1m --depths 300000,500000,750000,1000000   # needles + power (macmon optional)
python mtp_compare.py record --url ... --label qwen-mtp-off --tokenizer Qwen/Qwen3.8-Flash-Next
python mtp_compare.py record --url ... --label qwen-mtp-on  --tokenizer Qwen/Qwen3.8-Flash-Next   # server restarted with MTP on
python mtp_compare.py compare <off.jsonl> <on.jsonl> --tokenizer Qwen/Qwen3.8-Flash-Next
```

Parallel requests and GLM / YaRN runs are in [longctx/README.md](longctx/README.md); for example:

```
python concurrency.py --url http://127.0.0.1:8000 --model <served-name> --tokenizer <model dir> \
    --label glm53-conc --levels 1,2,4,8 --prompt-tokens 1000,20000 --template-kwargs '{"reasoning_effort": "low"}'
```

**Evals** (`call-eval/`, `call-eval-v2/`, `reason-eval/`, `pushback-eval/`, `creative-eval/`): each folder's README has
the details. They talk to any OpenAI-compatible server and write to `results/<eval>/<label>/` in this repo
(set `BENCH_RESULTS` to write somewhere else). For example:

```
cd reason-eval
python run_eval.py --url http://127.0.0.1:8000 --model <served-name> --label glm53_r1 \
    --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'
python score.py                                    # -> results/reason-eval/_scores/
python make_judge_pack.py --labels qwen38_r1,glm53_r1,dsv4_r1     # blind pack for a separate judge
python tools/make_viewer.py --labels glm53_r1,qwen38_r1,dsv4_r1 --out viewer.html
```

Each eval has a self-test (`selftest/`) that scores mock answers, so the scorer can be checked without a model.

**Agentic** (`agentic/`): `TASK.md` is given verbatim to every agent in an empty git repo. `cache_proxy.py`
sits between the agent and the model server (port 9000) and logs context size, cache hits/breaks, TTFT
and decode per request. `agent_loop.py` is the minimal "ceiling" agent (with `watchdog.py`), and
`harness_run.py` drives real harnesses (pi, omp, dsh) in a macOS sandbox. `referee.py` checks every
`milestone N:` commit against `hidden_tests/`. `run_overnight.py` runs the whole queue unattended:

```
python agentic/run_overnight.py --smoke   # a few minutes per run, to check wiring
python agentic/run_overnight.py
python agentic/replay.py --transcript agentic/runs/<stamp>-<label>.transcript.jsonl --url ... --engine omlx --label ...
```

Model paths in `run_overnight.py` point at `~/models/...`. Edit them to match your machine.

**LTX-2.5** (`ltx/`): start ComfyUI (`--gpu-only` recommended) on port 8188, then
`python ltx/run_ltx.py --workflow ltx/ltx25_t2v_api_1080p_tile1024.json --note "..."`. `run_gpu_only.sh` and
`run_fullvae.sh` are the chains that produced `results/ltx/runs.jsonl`. `COMFYUI_DIR` defaults to `~/bench/ComfyUI`.

**Charts and report** (read files only, and never contact a server):

```
python charts/make_charts.py          # rebuilds charts/*.png from results/
python tables/make_tables.py          # rebuilds tables/*.png from tables/tables.json
python report/make_report.py --no-referee [--out DIR]
```

`make_report.py` rebuilds all 8 agentic charts byte-for-byte from `results/agentic/`. Because transcripts
aren't published, a regenerated REPORT.md leaves out the few transcript-derived notes (watchdog nudges,
loop detection, tool counts of the ceiling agent), which the committed REPORT.md still has.

## License

MIT, see [LICENSE](LICENSE).
