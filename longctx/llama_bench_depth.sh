#!/bin/zsh
# llama.cpp's built-in depth test: prefill (512 new tokens) and decode (128 tokens)
# measured after the context is already filled to each depth. Used to cross-check
# the warm-step numbers from bench_ctx.py.
#
#   ./llama_bench_depth.sh <model.gguf> <label> [depths] [extra llama-bench args...]
set -euo pipefail
model=${1:?model.gguf}
label=${2:?label}
depths=${3:-0,10000,100000,200000}
[[ $# -ge 3 ]] && shift 3 || shift $#
out=~/bench-results/longctx/$(date +%Y%m%d-%H%M%S)-$label-llama-bench.json
mkdir -p ${out:h}
${LLAMA_CPP:-~/bench/llama.cpp}/build/bin/llama-bench -m $model -fa on -ngl 999 -p 512 -n 128 -d $depths -r 3 -o json "$@" | tee $out
echo "wrote $out"
