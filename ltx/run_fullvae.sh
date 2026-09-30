#!/bin/zsh
cd ${0:A:h}
python3 run_ltx.py --workflow ltx25_t2v_api_fullvae.json --note "gpu-only 720p full-frame VAE warm"
python3 run_ltx.py --workflow ltx25_t2v_api_1080p_fullvae.json --note "gpu-only 1080p full-frame VAE first"
python3 run_ltx.py --workflow ltx25_t2v_api_1080p_fullvae.json --note "gpu-only 1080p full-frame VAE warm"
echo LTX-FULLVAE-DONE
