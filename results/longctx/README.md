# results/longctx

`bench_ctx.py` and `bench_1m.py` output: one meta line (arguments and system info), then one row per request.
File names are `<start time>-<label>.jsonl`.

| Label | What |
|---|---|
| `qwen-oq8e-omlx*`, `qwen-q8-llama` | Qwen3.8-Flash-Next 8-bit depth curves, oMLX (Homebrew 0.7.0rc1, no custom kernels) and llama.cpp |
| `qwen-oq8e-omlx070`, `-mtp-on` | Qwen depth curve on the oMLX 0.7.0 kernel build, MTP off / on |
| `qwen-oq8e-native-250k` | Qwen 250k needle run, native RoPE (0.7.0 kernel build) |
| `qwen-oq8e-yarn4-1m`, `-pinned` | Qwen with YaRN x4 (`patches/`): 250k and 500k in the first file (its 1M request was rejected by the memory guard), 1M alone on a fresh server with a pinned 244 GB ceiling in `-pinned` |
| `glm53-oq4e-omlx` | GLM-5.3-Flash oQ4e depth curve, oMLX 0.7.0 kernel build |
| `glm53-oq4e-omlx-1m`, `-pinned` | GLM 300k / 500k / 1M needle run; the 1M warm step was rejected by the default memory guard, so `-pinned` reruns 1M with a custom 244 GB ceiling |
| `glm53-oq4-mtp-on` | GLM MTP build (Vontra oQ4-MTP) with MTP on: warm steps, to check the prompt cache works with MTP |
| `ds0731-*` | DeepSeek-V4-Flash 0731 oQ4e. `omlxk-1m` = rc1 custom-kernel build; `omlx070-scaling` = 128k / 256k / 512k / 1M on the 0.7.0 kernel build (the clean run behind the scaling exponent) |
| `dsv4v-*` | DeepSeek-V4-Flash-Vision-Exp on llama.cpp |

## Engine version metadata (known bug)

Files from the oMLX 0.7.0 kernel build written before the afternoon of 2026-10-01 record `engine_version`
`"0.7.0rc1"`. That is wrong: `common.system_info()` read the version from the Homebrew binary
(`/opt/homebrew/bin/omlx`), not from the server that was running. The server logs show the 0.7.0 kernel build
served all of these runs (`glm53-*`, `qwen-oq8e-omlx070*`, `qwen-oq8e-native-250k`, `qwen-oq8e-yarn4-1m*`, and the
`results/mtp/` and `results/concurrency/` files from the same nights). The bug is fixed: `system_info()` now finds the
running server's install through `lsof` and records it as `engine_binary` as well, which is why
`ds0731-omlx070-scaling` says `0.7.0`.

Files from 2026-09-29 and 2026-09-30 labelled `qwen-oq8e-omlx`, `ds0731-oq4e-omlx-*` and `ds0731-oq4e-omlxsrc-*` /
`ds0731-omlxk-1m` really are 0.7.0rc1 (Homebrew build and rc1 source build with custom kernels respectively).
