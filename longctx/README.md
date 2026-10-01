# Long-context benchmarks (Mac Studio M5 Ultra, 256GB)

All commands from `longctx/` with `P=python` (a venv with the packages in `../requirements.txt`). Results land in `~/bench-results/` (change with `--out`); the published ones are in `../results/`. `LLAMA_CPP` points at the llama.cpp checkout (default `~/bench/llama.cpp`).

## Files
- `build_corpus.py` builds `corpus/books.txt` (10 Gutenberg novels, ~5.1M tokens) and `corpus/code.txt` (llama.cpp source, ~8M tokens). The manifests record sources + sha256 so others can rebuild identical prompts.
- `bench_ctx.py` runs, per depth, a **cold** prompt (nonce at the start, so no cache can hit) and **warm** agent-style steps (previous turn + answer + 64 / 4096 new tokens). Records TTFT, prefill t/s, decode t/s, and cached/processed tokens.
- `bench_1m.py`: very long context (300k to 1M) with three hidden needles (each next to a near-identical decoy), one cold prompt per depth plus one warm step, and chip power sampled with `macmon` if installed. `--template-kwargs` passes extra chat-template options (also available in `bench_ctx.py`).
- `mtp_compare.py`: `record` with MTP off, `record` with MTP on, then `compare`. Reports speedup and where outputs first diverge.
- `serve_llama.sh`: starts llama-server with fixed settings (port 8080, 1 slot, flash attention, all layers on GPU).
- `llama_bench_depth.sh`: llama.cpp's built-in `-d` depth test, to cross-check the warm numbers.

## Before each session
- `sysctl iogpu.wired_limit_mb` must be ~245760 (resets on reboot: `sudo sysctl iogpu.wired_limit_mb=245760`).
- Close other apps; one big model loaded at a time.
- Model on the internal SSD (or note which drive; the results record it).

## Qwen3.8-Flash-Next (max 262k)
```
Q=~/models/Qwen3.8-Flash-Next-GGUF/Q8_0/Qwen3.8-Flash-Next-Q8_0-00001-of-00006.gguf
./serve_llama.sh $Q 262144                      # MTP off
$P bench_ctx.py --engine llama.cpp --url http://127.0.0.1:8080 --tokenizer Qwen/Qwen3.8-Flash-Next \
   --label qwen-q8-llama --model-path $Q --depths 10000,50000,100000,150000,200000,250000
$P mtp_compare.py record --url http://127.0.0.1:8080 --label qwen-llama-mtp-off --tokenizer Qwen/Qwen3.8-Flash-Next
# restart with MTP on:
./serve_llama.sh $Q 262144 --spec-type draft-mtp -md ~/models/Qwen3.8-Flash-Next-GGUF/MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
$P mtp_compare.py record --url http://127.0.0.1:8080 --label qwen-llama-mtp-on --tokenizer Qwen/Qwen3.8-Flash-Next
./llama_bench_depth.sh $Q qwen-q8 0,100000,200000   # cross-check (server stopped)
```
oMLX: same `bench_ctx.py` / `mtp_compare.py` with `--engine omlx --url http://127.0.0.1:8000`.
Serve from a folder holding only the model under test (symlinks are fine), so it never scans half-downloaded models:
```
mkdir -p ~/bench/omlx-models && ln -sfn ~/models/Qwen3.8-Flash-Next-oQ8e-mtp ~/bench/omlx-models/qwen-flash-next
omlx serve --model-dir ~/bench/omlx-models --port 8000
```
oMLX's paged SSD prompt cache (`~/.omlx/cache`) grew to 61GB during the Qwen runs; every benchmark prompt is unique, so none of it is reusable. Clear it between runs (`rm -rf ~/.omlx/cache/*` while oMLX is stopped), or cap it with `--paged-ssd-cache-max-size`, or move it to the NVMe with `--paged-ssd-cache-dir`.
For Qwen3.8-Flash-Next on 256GB, set `qwen4_ple_ssd_offload = true` for the model in `~/.omlx/model_settings.json`, or loading gets killed for running out of memory (exit 137). `mtp_enabled` (not `vlm_mtp_enabled`) turns on its built-in Lightning MTP.
Stop it with `pkill -f omlx-server` (the process renames itself, so `pkill -f "omlx serve"` misses it and the old server keeps port 8000).

## DeepSeek-V4-Flash-Vision-Exp (to 1M, native)
```
D=~/models/DeepSeek-V4-Flash-Vision-Exp-GGUF/UD-Q8_K_XL/<first shard>.gguf
./serve_llama.sh $D 1048576
$P bench_ctx.py --engine llama.cpp --url http://127.0.0.1:8080 --tokenizer deepseek-ai/DeepSeek-V4-Flash-Vision-Exp \
   --label dsv4v-q8-llama --model-path $D --depths 10000,100000,200000,300000,400000,500000,600000,800000,1000000
```
Depths >= 300k run once (`--repeats-large`); a cold 1M prefill can take a long time.

## Notes for the write-up
- Cold = "paste a huge document"; warm = "the next agent step at that depth". Report both.
- The Qwen oMLX build (oQ8e, imatrix) and the llama.cpp build (unsloth Q8_0) are both 8-bit but quantized differently.
- Qwen is native 262k; DeepSeek V4 is native 1M.
