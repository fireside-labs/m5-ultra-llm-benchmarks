#!/usr/bin/env python3
"""Submit an LTX-2.5 API workflow to ComfyUI, time it, probe the output, append to runs.jsonl.
Usage: run_ltx.py [--workflow ltx25_t2v_api.json] [--note "..."] [--seed N]"""
import argparse, json, os, re, subprocess, time, uuid, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
COMFY = os.path.expanduser(os.environ.get("COMFYUI_DIR", "~/bench/ComfyUI"))
LOG = os.path.expanduser("~/bench-results/logs/comfyui.log")
RUNS = os.path.expanduser("~/bench-results/ltx/runs.jsonl")
FFPROBE = "/opt/homebrew/bin/ffprobe"

def http(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))

def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-count_frames", "-show_streams", "-show_format",
                        "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout or "{}")
    info = {"duration_s": float(j.get("format", {}).get("duration", 0) or 0),
            "size_bytes": int(j.get("format", {}).get("size", 0) or 0)}
    for s in j.get("streams", []):
        if s["codec_type"] == "video":
            num, den = s["r_frame_rate"].split("/")
            info.update(width=s["width"], height=s["height"], fps=round(int(num) / int(den), 3),
                        frames=int(s.get("nb_read_frames") or s.get("nb_frames") or 0),
                        vcodec=s["codec_name"])
        elif s["codec_type"] == "audio":
            info["acodec"] = s["codec_name"]
    return info

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", default=os.path.join(HERE, "ltx25_t2v_api.json"))
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--note", default="")
    ap.add_argument("--seed", type=int, help="override every seed/noise_seed")
    ap.add_argument("--timeout", type=float, default=7200)
    ap.add_argument("--no-cache-bust", action="store_true",
                    help="don't inject the no-op nonce; an identical resubmit then hits ComfyUI's cache and does nothing")
    a = ap.parse_args()
    wf = json.load(open(a.workflow))
    if a.seed is not None:
        for n in wf.values():
            for k, v in n["inputs"].items():
                if k.split(".")[-1] in ("seed", "noise_seed") and not isinstance(v, list):
                    n["inputs"][k] = a.seed
    nonce = uuid.uuid4().hex
    if not a.no_cache_bust:
        # ComfyUI skips nodes whose inputs are unchanged since the last run. Route every
        # CLIPTextEncode text through a no-op StringReplace (find=<random nonce>, replace="")
        # so text encoding, both sampling passes and decodes re-run while loaded models stay cached.
        for nid, n in list(wf.items()):
            if n["class_type"] == "CLIPTextEncode":
                rid = f"bust_{nid}"
                wf[rid] = {"class_type": "StringReplace",
                           "inputs": {"string": n["inputs"]["text"], "find": f"<<{nonce}>>", "replace": ""}}
                n["inputs"]["text"] = [rid, 0]
    log_off = os.path.getsize(LOG) if os.path.exists(LOG) else 0
    t0 = time.time()
    resp = http(a.server + "/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})
    pid = resp["prompt_id"]
    print(f"submitted {pid}", flush=True)
    hist = None
    while time.time() - t0 < a.timeout:
        h = http(f"{a.server}/history/{pid}")
        if pid in h and h[pid].get("status", {}).get("completed") is not None \
                and (h[pid]["status"]["completed"] or h[pid]["status"].get("status_str") == "error"):
            hist = h[pid]; break
        time.sleep(0.5)
    wall = time.time() - t0
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "prompt_id": pid,
           "workflow": os.path.basename(a.workflow), "note": a.note, "cache_bust": not a.no_cache_bust, "wall_s": round(wall, 2)}
    wf_unet = [n["inputs"].get("unet_name") for n in wf.values() if n["class_type"] == "UNETLoader"]
    rec["unet"] = wf_unet[0] if wf_unet else None
    if hist is None:
        rec["status"] = "timeout"
    else:
        rec["status"] = hist["status"].get("status_str")
        for m in hist["status"].get("messages", []):
            if m[0] == "execution_error":
                rec["error"] = {k: m[1].get(k) for k in ("node_id", "node_type", "exception_type", "exception_message")}
        outs = []
        for node_out in hist.get("outputs", {}).values():
            for lst in node_out.values():
                if isinstance(lst, list):
                    for f in lst:
                        if isinstance(f, dict) and "filename" in f and f.get("type") == "output":
                            outs.append(os.path.join(COMFY, "output", f.get("subfolder", ""), f["filename"]))
        rec["outputs"] = outs
        vids = [p for p in outs if p.lower().endswith((".mp4", ".webm", ".mkv", ".mov"))]
        if vids:
            rec["video"] = probe(vids[0])
    # ComfyUI's own timing from the log (text appended since submit)
    time.sleep(1)
    try:
        with open(LOG, "rb") as f:
            f.seek(log_off); tail = f.read().decode("utf-8", "replace")
        m = re.findall(r"Prompt executed in ([\d.:]+) seconds", tail)
        if m: rec["comfy_exec_s"] = m[-1]
        loads = re.findall(r"(?:loaded completely|Requested to load|model weight dtype|Model loading|load device)[^\n]*", tail)
        if loads: rec["log_model_lines"] = loads[:12]
    except OSError:
        pass
    os.makedirs(os.path.dirname(RUNS), exist_ok=True)
    with open(RUNS, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2))

if __name__ == "__main__":
    main()
