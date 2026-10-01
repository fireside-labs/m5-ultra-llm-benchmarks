# Local LLM long-context benchmarks (Mac Studio M5 Ultra, 256 GB)

Benchmarks for how local models behave on the workloads that matter at long context:
pasting a huge document, and a coding agent that keeps adding to the same conversation for hours.
They cover prefill and decode against context depth (cold and cached), MTP / DSpark speculative decoding,
overnight agentic coding sessions scored by hidden tests, a 1M-token DeepSeek run (speed, recall and power),
request-for-request replays of real agent sessions on two engines, and a bonus LTX-2.5 text-to-video timing in ComfyUI.

The narrative write-up with all the findings is in **[WRITEUP.md](WRITEUP.md)**. The chart notes are in
[charts/CHARTS.md](charts/CHARTS.md), the tables as images are in [tables/](tables/), and the full agentic report is in [report/REPORT.md](report/REPORT.md).

## Test system

| | |
|---|---|
| Hardware | Mac Studio, Apple M5 Ultra (30-core CPU, 64-core GPU), 256 GB unified memory (`iogpu.wired_limit_mb=245760`) |
| OS | macOS 27.0.1 |
| llama.cpp | commit `19e28a2` (Metal, flash attention on, `-b 2048 -ub 2048`) |
| oMLX | 0.7.0rc1 (Homebrew build, and a source build with `OMLX_WITH_CUSTOM_KERNEL=1` for DeepSeek V4) |
| ComfyUI | official "Text to Video (LTX-2.5)" template, int8 checkpoints |
| Python | 3.12, packages in `requirements.txt` |

Models: Qwen3.8-Flash-Next (llama.cpp: unsloth Q8_0 GGUF; oMLX: oQ8e), DeepSeek-V4-Flash-Vision-Exp
(llama.cpp: UD-Q8_K_XL GGUF + DSpark draft) and DeepSeek-V4-Flash-0731 (oMLX: oQ4e with built-in MTP/DSpark),
LTX-2.5 22B distilled int8.

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

## Layout

```
longctx/    corpus builder, depth benchmark (cold/warm), 1M needle/power run, MTP on/off compare, llama.cpp helpers
agentic/    Deepdelve task, cache-logging proxy, agent loop, watchdog, referee, harness runner,
            overnight queue, session replay; hidden_tests/ are the referee's Vitest suites
ltx/        ComfyUI LTX-2.5 API workflows, blueprint converter, timing runner
results/    raw JSONL from every run used in the charts
  longctx/  bench_ctx.py output (meta line + one row per request)
  mtp/      mtp_compare.py output, including model text (used to show where MTP/DSpark outputs diverge)
  replay/   replay.py output (Qwen and DeepSeek sessions)
  ltx/      run_ltx.py output
  agentic/  cache_proxy logs per run, overnight-events.log, filtered oMLX server logs,
            runs/: per run, referee JSONL, git log/grep snapshot of the agent's repo, filtered pi harness log
  probes/   ubatch probes referenced in chart 08
charts/     make_charts.py and the 10 charts built from results/
tables/     the key tables as PNGs: make_tables.py renders them from tables.json
report/     make_report.py, the agentic charts and REPORT.md
```

Host names and home-directory paths in the result metadata are replaced with `bench-host` and `~`.
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
