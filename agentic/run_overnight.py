#!/usr/bin/env python3
"""Run a queue of agentic long-context benchmark runs back to back, unattended.

Per run: stop any model server, clear the oMLX SSD cache, apply oMLX model settings,
start the server, warm it up, start cache_proxy + the agent (ceiling agent_loop or a
real harness via harness_run) + referee --watch, stop at the target context or the time
cap, then a final referee pass and cleanup. Prints only a few event lines per run;
details go to files under ~/bench-results/agentic/.

  python run_overnight.py            # full queue
  python run_overnight.py --smoke    # each run for a few minutes, to check wiring
"""
import argparse, glob, json, os, pathlib, signal, subprocess, sys, time

import requests

HOME = pathlib.Path.home()
HERE = pathlib.Path(__file__).resolve().parent
PY = os.environ.get("BENCH_PY", sys.executable)
BREW_PY = "/opt/homebrew/Cellar/omlx/0.7.0rc1/libexec/bin/python3.11"
LOGDIR = HOME / "bench-results/agentic"
# oMLX source checkout (with the DSpark/cache fixes) used for the "omlx-src" server
OMLX_SRC = pathlib.Path(os.environ.get("OMLX_SRC", HOME / "bench/omlx-src"))
EVENTS = LOGDIR / "overnight-events.log"

DS_GGUF = HOME / "models/DeepSeek-V4-Flash-Vision-Exp-GGUF/UD-Q8_K_XL/DeepSeek-V4-Flash-Vision-Exp-UD-Q8_K_XL-00001-of-00005.gguf"
DS_DSPARK = HOME / "models/DeepSeek-V4-Flash-Vision-Exp-GGUF/dspark/dspark-DeepSeek-V4-Flash-Vision-Exp-BF16.gguf"

QWEN_GGUF = HOME / "models/Qwen3.8-Flash-Next-GGUF/Q8_0/Qwen3.8-Flash-Next-Q8_0-00001-of-00006.gguf"
QWEN_MTP = HOME / "models/Qwen3.8-Flash-Next-GGUF/MTP/mtp-Qwen3.8-Flash-Next-Q8_0.gguf"
DS_LLAMA = {"server": "llama", "gguf": DS_GGUF, "ctx": 1048576,
            "extra": ["--spec-type", "draft-dspark", "-md", str(DS_DSPARK)], "model": "local"}
# Qwen MTP in llama.cpp needs unsloth's qwen4exp/mtp branch (mainline fails to load the MTP GGUF),
# so tonight's llama.cpp Qwen runs are MTP off.
QWEN_LLAMA = {"server": "llama", "gguf": QWEN_GGUF, "ctx": 262144, "extra": [], "model": "local"}

DS_OMLX = {"server": "omlx-src", "model_dir": "omlx-models-ds", "model": "dsv4-0731",
           "settings": {"mtp_enabled": True}}
QWEN_OMLX = {"server": "omlx-brew", "model_dir": "omlx-models", "model": "qwen-flash-next",
             "settings": {"mtp_enabled": True, "qwen4_ple_ssd_offload": True}}

QUEUE = [
    {"label": "ds0731-omlxk-dspark-ceiling", **DS_OMLX, "agent": "ceiling", "target": 1_000_000, "hours": 3.0},
    {"label": "dsv4v-llama-dspark-ceiling", **DS_LLAMA, "agent": "ceiling", "target": 1_000_000, "hours": 3.0},
    {"label": "qwen-omlx-mtp-ceiling", **QWEN_OMLX, "agent": "ceiling", "target": 250_000, "hours": 1.0},
    {"label": "qwen-llama-ceiling", **QWEN_LLAMA, "agent": "ceiling", "target": 250_000, "hours": 1.0},
    {"label": "qwen-llama-pi", **QWEN_LLAMA, "agent": "pi", "context_window": 262144, "hours": 1.0},
]
# next night: dsh on DeepSeek, omp and pi on both models
LATER = [
    {"label": "dsv4v-llama-dspark-dsh", **DS_LLAMA, "agent": "dsh", "context_window": 1048576, "hours": 3.0},
]


def event(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with EVENTS.open("a") as f:
        f.write(line + "\n")


def sh(cmd):
    subprocess.run(cmd, shell=True, executable="/bin/zsh")


def stop_servers():
    sh("pkill -f omlx-server; pkill -f 'llama-server -m'; pkill -f cache_proxy.py; true")
    time.sleep(5)


def omlx_settings(model_id, settings):
    code = ("from pathlib import Path\nfrom omlx.model_settings import ModelSettingsManager\n"
            "m = ModelSettingsManager(Path.home() / '.omlx')\n"
            f"s = m.get_settings({model_id!r})\n"
            + "".join(f"s.{k} = {v!r}\n" for k, v in settings.items())
            + "s.vlm_mtp_enabled = False\n"
            f"m.set_settings({model_id!r}, s)\n")
    subprocess.run([BREW_PY, "-c", code], check=True)


def start_server(run, logf):
    if run["server"] == "llama":
        cmd = [str(HERE.parent / "longctx/serve_llama.sh"), str(run["gguf"]), str(run["ctx"]), *run.get("extra", [])]
        url = "http://127.0.0.1:8080"
    else:
        sh("rm -rf ~/.omlx/cache/*")
        omlx_settings(run["model"], run.get("settings", {}))
        exe = str(OMLX_SRC / ".venv/bin/omlx") if run["server"] == "omlx-src" else "/opt/homebrew/bin/omlx"
        cmd = [exe, "serve", "--model-dir", str(HOME / "bench" / run["model_dir"]), "--port", "8000"]
        url = "http://127.0.0.1:8000"
    proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, start_new_session=True)
    deadline = time.time() + 1800
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited with {proc.returncode}")
        try:
            if run["server"] == "llama":
                ok = requests.get(f"{url}/health", timeout=5).json().get("status") == "ok"
            else:
                ok = any(m["id"] == run["model"] for m in requests.get(f"{url}/v1/models", timeout=5).json()["data"])
            if ok:
                break
        except Exception:
            pass
        time.sleep(3)
    else:
        raise RuntimeError("server not ready after 30 min")
    if run["server"] != "llama" and "oMLX cache disabled" in pathlib.Path(logf.name).read_text(errors="replace"):
        # oMLX persists --no-cache into ~/.omlx/settings.json (jundot/omlx#3828)
        raise RuntimeError("oMLX prompt cache is disabled; check cache.enabled in ~/.omlx/settings.json")
    requests.post(f"{url}/v1/chat/completions", timeout=1800, json={
        "model": run["model"], "messages": [{"role": "user", "content": "Say hi."}], "max_tokens": 8})
    return proc, url


def newest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def kill(proc, grace=15):
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(grace)
        except Exception:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass


def run_one(run, smoke):
    label = run["label"] + ("-smoke" if smoke else "")
    hours = 0.08 if smoke else run["hours"]
    logs = LOGDIR / "overnight-logs"
    logs.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    server = proxy = agent = referee = None
    try:
        stop_servers()
        t0 = time.time()
        server, url = start_server(run, open(logs / f"{stamp}-{label}.server.log", "w"))
        event(f"START {label}: server ready in {time.time() - t0:.0f}s")
        proxy = subprocess.Popen([PY, str(HERE / "cache_proxy.py"), "--upstream", url, "--label", label],
                                 stdout=open(logs / f"{stamp}-{label}.proxy.out", "w"),
                                 stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(3)
        if run["agent"] == "ceiling":
            cmd = [PY, str(HERE / "agent_loop.py"), "--url", "http://127.0.0.1:9000", "--label", label,
                   "--model", run["model"], "--target", str(run["target"])]
            ws_glob = str(HERE / "runs" / f"*-{label}")
        else:
            ws = HERE / "runs" / f"{stamp}-{label}"
            cmd = [PY, str(HERE / "harness_run.py"), "--harness", run["agent"], "--workspace", str(ws),
                   "--label", label, "--model", run["model"], "--context-window", str(run["context_window"]),
                   "--max-hours", str(hours)]
            ws_glob = str(ws)
        agent = subprocess.Popen(cmd, stdout=open(logs / f"{stamp}-{label}.agent.out", "w"),
                                 stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.time() + hours * 3600
        while agent.poll() is None and time.time() < deadline:
            if server.poll() is not None:
                event(f"ERROR {label}: server died (exit {server.returncode})")
                break
            ws_path = newest(ws_glob)
            if referee is None and ws_path and os.path.isdir(ws_path) and not smoke:
                referee = subprocess.Popen([PY, str(HERE / "referee.py"), ws_path, "--watch"],
                                           stdout=open(logs / f"{stamp}-{label}.referee.out", "w"),
                                           stderr=subprocess.STDOUT, start_new_session=True)
            time.sleep(30)
        reason = ("agent finished" if agent.poll() is not None else
                  "server died" if server.poll() is not None else "time cap")
        kill(agent)
        kill(referee)
        ws_path = newest(ws_glob)
        if ws_path and os.path.isdir(ws_path) and not smoke:
            subprocess.run([PY, str(HERE / "referee.py"), ws_path], stdout=open(logs / f"{stamp}-{label}.referee.final", "w"),
                           stderr=subprocess.STDOUT, timeout=3600)
        rows = [json.loads(l) for l in open(newest(str(LOGDIR / f"*-{label}.jsonl")) or os.devnull)]
        last = rows[-1] if rows else {}
        breaks = sum(r.get("cache_break", False) for r in rows)
        event(f"END {label}: {reason}; {len(rows)} requests, last ctx {last.get('prompt_tokens') or 0:,}, "
              f"cache breaks {breaks}, {(time.time() - t0) / 3600:.2f} h")
    except Exception as e:
        event(f"ERROR {label}: {e.__class__.__name__}: {e}")
    finally:
        for p in (agent, referee, proxy, server):
            kill(p)
        stop_servers()
        sh("rm -rf ~/.omlx/cache/*")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", help="comma-separated labels to run")
    args = ap.parse_args()
    LOGDIR.mkdir(parents=True, exist_ok=True)
    queue = [r for r in QUEUE if not args.only or r["label"] in args.only.split(",")]
    event(f"QUEUE {'smoke ' if args.smoke else ''}{[r['label'] for r in queue]}")
    for run in queue:
        run_one(run, args.smoke)
    event("QUEUE DONE")


if __name__ == "__main__":
    main()
