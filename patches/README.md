# Patches and config fixes

## `omlx-qwen4exp-yarn.patch`: YaRN for Qwen3.8-Flash-Next in oMLX 0.7.0

Qwen3.8-Flash-Next (`qwen4_exp`) is trained to 262,144 tokens. YaRN stretches its rotary position encoding
(here 4x, to 1,048,576 tokens) without new weights, which is the long-context recipe Qwen documents for its models.
oMLX 0.7.0 ignores a `yarn` entry in `rope_parameters` for this architecture, so the model runs with the native
RoPE no matter what the config says.

The patch (about 90 lines, one file, against oMLX 0.7.0) adds YaRN to the vendored `qwen4_exp` attention:

- `_yarn_inv_freq()` computes the YaRN inverse frequencies the same way transformers' `_compute_yarn_parameters` does
  (`beta_fast` 32, `beta_slow` 1, truncation on by default).
- `_maybe_apply_yarn_rope()` swaps them into the attention's MRoPE module and applies the attention scale
  (`0.1 * ln(factor) + 1`, or `attention_factor` if the config gives one) to the rotated part of q and k only.
- It is gated on `rope_parameters` having `type` (or `rope_type`) `yarn`. Unmodified checkpoints are untouched.

Apply it to an oMLX 0.7.0 source checkout and build as usual (the benchmarks used a build with
`OMLX_WITH_CUSTOM_KERNEL=1`):

```
git am patches/omlx-qwen4exp-yarn.patch      # or: git apply
```

Then serve a copy of the model folder (symlinks to the weights are fine) whose `config.json` has, in `text_config`:

```json
"rope_parameters": {
  "mrope_interleaved": true,
  "mrope_section": [11, 11, 10],
  "partial_rotary_factor": 0.25,
  "rope_theta": 10000000,
  "type": "yarn",
  "rope_type": "yarn",
  "factor": 4.0,
  "original_max_position_embeddings": 262144
},
"max_position_embeddings": 1048576
```

Only `type`/`rope_type`, `factor`, `original_max_position_embeddings` and `max_position_embeddings` change; the
other `rope_parameters` keys are the model's originals.

Measured with `longctx/bench_1m.py` (results in `results/longctx/*qwen-oq8e-yarn4-1m*.jsonl` and
`*qwen-oq8e-native-250k*.jsonl`): at 250k, YaRN and native RoPE gave the same speed (4,040 vs 3,955 t/s prefill,
52.6 vs 51.2 t/s decode) and both found all three hidden codes. With YaRN, recall was 3/3 at 500k and at 1M
(1M cold prefill 5.3 min, decode 28.8 t/s, next turn 6.7 s). This is a needle test: it shows lookup works at 1M,
not that reasoning over the stretched context is as good as within 262k.

## GLM-5.3-Flash MTP build: `mlp_layer_types` has one entry too many

The Vontra oQ4-MTP build of GLM-5.3-Flash lists 46 `mlp_layer_types` in `config.json` (`text_config`) for
45 hidden layers (`num_hidden_layers: 45`). Newer transformers versions validate the list length and refuse to
load the model. Trimming `mlp_layer_types` to its first 45 entries fixes it. The benchmarks served a folder of
symlinks to the weights with an edited copy of `config.json`, so the download itself stayed unchanged.
