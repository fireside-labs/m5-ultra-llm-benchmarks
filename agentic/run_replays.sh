#!/bin/zsh
# After the final Qwen oMLX depth run: replay the recorded Qwen agent session on oMLX,
# then on llama.cpp (both MTP off), then stop the servers. Events go to replay-events.log.
set -u
PY=${PY:-python3}
HERE=${0:A:h}
EV=~/bench-results/replay/replay-events.log
T=$(ls -t $HERE/runs/*-qwen-omlx-mtp-ceiling.transcript.jsonl | grep -v smoke | head -1)
mkdir -p ~/bench-results/replay
ev() { echo "$(date +%H:%M:%S) $*" | tee -a $EV; }

while pgrep -f "bench_ctx.py.*qwen-oq8e-omlx " >/dev/null || pgrep -f "label qwen-oq8e-omlx --" >/dev/null; do sleep 20; done
ev "depth run finished; replay on oMLX"
$PY $HERE/replay.py --transcript $T --url http://127.0.0.1:8000 --engine omlx \
    --model qwen-flash-next --label qwen-replay-omlx > ~/bench-results/replay/qwen-replay-omlx.out 2>&1
ev "oMLX replay exit $?"

pkill -f omlx-server; sleep 5; rm -rf ~/.omlx/cache/*
Q=~/models/Qwen3.8-Flash-Next-GGUF/Q8_0/Qwen3.8-Flash-Next-Q8_0-00001-of-00006.gguf
(cd $HERE/../longctx && nohup ./serve_llama.sh $Q 262144 > /dev/null 2>&1 &)
sleep 5; until curl -s http://127.0.0.1:8080/health | grep -q '"ok"'; do sleep 3; done
ev "llama.cpp ready; replay on llama.cpp"
$PY $HERE/replay.py --transcript $T --url http://127.0.0.1:8080 --engine llama.cpp \
    --label qwen-replay-llama > ~/bench-results/replay/qwen-replay-llama.out 2>&1
ev "llama.cpp replay exit $?"
pkill -f "llama-server -m"
ev "REPLAYS DONE"
