#!/bin/zsh
pkill -f "main.py --listen"; sleep 5
cd ${COMFYUI_DIR:-~/bench/ComfyUI} && nohup .venv/bin/python main.py --listen 127.0.0.1 --port 8188 --gpu-only > ~/bench-results/logs/comfyui-gpuonly.log 2>&1 &
until curl -s http://127.0.0.1:8188/system_stats | grep -q comfyui; do sleep 2; done
cd ${0:A:h}
python3 run_ltx.py --note "gpu-only 720p cold (incl load)"
python3 run_ltx.py --note "gpu-only 720p warm"
python3 run_ltx.py --workflow ltx25_t2v_api_1080p.json --note "gpu-only 1080p first"
python3 run_ltx.py --workflow ltx25_t2v_api_1080p.json --note "gpu-only 1080p warm"
echo LTX-CHAIN-DONE
