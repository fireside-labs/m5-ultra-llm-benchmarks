"""Shared helpers: tokenizer, exact-length prompt slicing, streaming client, system info."""
import json, os, pathlib, platform, re, subprocess, time

import numpy as np
import requests
from tokenizers import Tokenizer

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE / "corpus"


def load_tokenizer(spec):
    """spec: a tokenizer.json path, a model directory, or a Hugging Face repo id."""
    p = pathlib.Path(os.path.expanduser(spec))
    if p.is_file():
        return Tokenizer.from_file(str(p))
    if (p / "tokenizer.json").is_file():
        return Tokenizer.from_file(str(p / "tokenizer.json"))
    from huggingface_hub import hf_hub_download
    return Tokenizer.from_file(hf_hub_download(spec, "tokenizer.json"))


class Corpus:
    """Tokenized corpus, cached per tokenizer so slicing to exact token counts is instant."""

    def __init__(self, kind, tokenizer, tok_name):
        text_path = CORPUS / f"{kind}.txt"
        cache = CORPUS / f"{kind}.{tok_name}.ids.npy"
        self.tok = tokenizer
        if cache.exists() and cache.stat().st_mtime > text_path.stat().st_mtime:
            self.ids = np.load(cache)
        else:
            print(f"tokenizing {text_path.name} ...", flush=True)
            self.ids = np.array(tokenizer.encode(text_path.read_text()).ids, dtype=np.int32)
            np.save(cache, self.ids)
        print(f"corpus {kind}: {len(self.ids):,} tokens")

    def text(self, start, n):
        if start + n > len(self.ids):
            raise SystemExit(f"corpus too short: need {start + n:,} tokens, have {len(self.ids):,}")
        return self.tok.decode(self.ids[start:start + n].tolist())


def stream_chat(base_url, model, messages, max_tokens, extra=None, timeout=None):
    """One streaming chat completion. Returns timings measured on the client plus
    whatever usage/timing fields the server reports."""
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": 0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    body.update(extra or {})
    content, reasoning = [], []
    t_first = None
    last = {}
    t0 = time.perf_counter()
    with requests.post(f"{base_url}/v1/chat/completions", json=body, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line or not line.startswith(b"data: "):
                continue
            data = line[6:]
            if data == b"[DONE]":
                break
            chunk = json.loads(data)
            for ch in chunk.get("choices") or []:
                d = ch.get("delta") or {}
                c, rc = d.get("content"), d.get("reasoning_content") or d.get("reasoning")
                if (c or rc) and t_first is None:
                    t_first = time.perf_counter()
                if c:
                    content.append(c)
                if rc:
                    reasoning.append(rc)
            if chunk.get("usage") or chunk.get("timings"):
                last = chunk
    t_end = time.perf_counter()
    usage = last.get("usage") or {}
    n_out = usage.get("completion_tokens") or 0
    ttft = (t_first or t_end) - t0
    gen_s = t_end - (t_first or t_end)
    return {
        "ttft_s": round(ttft, 4),
        "total_s": round(t_end - t0, 4),
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "completion_tokens": n_out,
        "decode_tps": round((n_out - 1) / gen_s, 2) if n_out > 1 and gen_s > 0 else None,
        "server_timings": last.get("timings"),
        "server_extra": {k: v for k, v in last.items() if k not in ("choices", "usage", "timings", "id", "object", "created", "model")},
        "content": "".join(content),
        "reasoning": "".join(reasoning),
    }


def server_model(base_url):
    r = requests.get(f"{base_url}/v1/models", timeout=10)
    r.raise_for_status()
    return r.json()["data"][0]["id"]


def _run(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=20).strip()
    except Exception as e:
        return f"unavailable: {e.__class__.__name__}"


def system_info(engine, model_path=None):
    home = pathlib.Path.home()
    info = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": platform.node(),
        "chip": _run(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "mem_bytes": _run(["sysctl", "-n", "hw.memsize"]),
        "macos": _run(["sw_vers", "-productVersion"]),
        "gpu_wired_limit_mb": _run(["sysctl", "-n", "iogpu.wired_limit_mb"]),
        "engine": engine,
    }
    if engine == "llama.cpp":
        llama_cpp = pathlib.Path(os.path.expanduser(os.environ.get("LLAMA_CPP", str(home / "bench/llama.cpp"))))
        info["engine_version"] = _run([str(llama_cpp / "build/bin/llama-server"), "--version"])
    elif engine == "omlx":
        # Ask the running server's own install, not whichever omlx is on PATH. The process renames
        # itself "omlx-server" and hides its argv, but its open files show which site-packages it loaded.
        exe = "/opt/homebrew/bin/omlx"
        files = _run(["/bin/sh", "-c", "lsof -p $(pgrep -f omlx-server | head -1) 2>/dev/null"])
        m = re.search(r"(\S+)/lib/python[0-9.]+/site-packages/", files)
        if m and pathlib.Path(m.group(1), "bin/omlx").exists():
            exe = str(pathlib.Path(m.group(1), "bin/omlx"))
        info["engine_version"] = _run([exe, "--version"])
        info["engine_binary"] = exe
    if model_path:
        mp = pathlib.Path(os.path.expanduser(model_path))
        info["model_path"] = str(mp)
        info["model_volume"] = _run(["df", "-h", str(mp)]).splitlines()[-1]
    return info
