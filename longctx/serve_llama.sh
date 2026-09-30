#!/bin/zsh
# Start llama-server with the benchmark settings (batch/ubatch 2048: +31% prefill vs the
# default 512 on DeepSeek V4 at 10k; 4096 adds ~2%). Logs to ~/bench-results/logs.
#
#   ./serve_llama.sh <model.gguf> <ctx> [extra llama-server args...]
#
# MTP on (Qwen, unsloth's separate MTP file):
#   ./serve_llama.sh ~/models/Qwen3.8-Flash-Next-GGUF/Q8_0/...-00001-of-00006.gguf 262144 \
#       --spec-type draft-mtp -md ~/models/Qwen3.8-Flash-Next-GGUF/MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
set -euo pipefail
model=${1:?model.gguf}
ctx=${2:?context size}
shift 2
bin=${LLAMA_CPP:-~/bench/llama.cpp}/build/bin/llama-server
logdir=~/bench-results/logs
mkdir -p $logdir
log=$logdir/llama-server-$(date +%Y%m%d-%H%M%S).log

limit=$(sysctl -n iogpu.wired_limit_mb)
if [[ $limit -lt 200000 ]]; then
  echo "warning: iogpu.wired_limit_mb=$limit; big models will not fit on the GPU."
  echo "         run in Terminal: sudo sysctl iogpu.wired_limit_mb=245760"
fi

echo "logging to $log"
exec $bin -m $model -c $ctx -np 1 -ngl 999 -fa on --jinja -b 2048 -ub 2048 \
  --host 127.0.0.1 --port 8080 --metrics --no-webui "$@" 2>&1 | tee $log
