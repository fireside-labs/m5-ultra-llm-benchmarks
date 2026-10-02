#!/usr/bin/env python3
"""Run the reason-eval ("general thinker / steering") tasks against an OpenAI-compatible chat endpoint.

Examples
  python run_eval.py --url http://127.0.0.1:8000 --model GLM-5.3-Flash --label glm53
  python run_eval.py --url http://127.0.0.1:8000/v1 --model X --label x --only R02,R07
  python run_eval.py --url ... --model X --label x \
      --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'

Writes to results/reason-eval/<label>/ (override with --out-root):
  Rxx.raw.txt        model reply content (exactly as returned; this is what gets scored)
  Rxx.reasoning.txt  separate reasoning stream, if the server returns one (never scored)
  Rxx.meta.json      timing (ttft, total), token usage, tokens/s, finish_reason, errors
  run_manifest.json  model/url/params + sha256 of the system prompt and task files
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from evallib import DEFAULT_RESULTS, SYSTEM_PROMPT, TASKS, load_system, load_task, strip_think, task_ids


def endpoint(url):
    url = url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def chat(args, system, user):
    """Send one request. Returns dict with content, reasoning, timings and usage."""
    body = {
        "model": args.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": args.temperature,
        "top_p": args.top_p,
        "max_tokens": args.max_tokens,
        "stream": not args.no_stream,
    }
    if args.seed is not None:
        body["seed"] = args.seed
    if not args.no_stream:
        body["stream_options"] = {"include_usage": True}
    if args.extra_body:
        body.update(json.loads(args.extra_body))
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    out = {"content": "", "reasoning": "", "usage": None, "finish_reason": None,
           "ttft_s": None, "ttft_content_s": None, "error": None}
    t0 = time.perf_counter()
    try:
        r = requests.post(endpoint(args.url), json=body, headers=headers,
                          stream=not args.no_stream, timeout=args.timeout)
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}: {r.text[:500]}"
            out["total_s"] = time.perf_counter() - t0
            return out
        if args.no_stream:
            j = r.json()
            ch = j["choices"][0]
            msg = ch.get("message", {})
            out["content"] = msg.get("content") or ""
            out["reasoning"] = msg.get("reasoning_content") or msg.get("reasoning") or ""
            out["finish_reason"] = ch.get("finish_reason")
            out["usage"] = j.get("usage")
        else:
            content, reasoning = [], []
            for line in r.iter_lines(decode_unicode=False):
                if not line:
                    continue
                line = line.decode("utf-8", "replace")
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if j.get("usage"):
                    out["usage"] = j["usage"]
                for ch in j.get("choices") or []:
                    d = ch.get("delta") or {}
                    rc = d.get("reasoning_content") or d.get("reasoning")
                    c = d.get("content")
                    now = time.perf_counter() - t0
                    if (rc or c) and out["ttft_s"] is None:
                        out["ttft_s"] = now
                    if c and out["ttft_content_s"] is None:
                        out["ttft_content_s"] = now
                    if rc:
                        reasoning.append(rc)
                    if c:
                        content.append(c)
                    if ch.get("finish_reason"):
                        out["finish_reason"] = ch["finish_reason"]
            out["content"], out["reasoning"] = "".join(content), "".join(reasoning)
    except Exception as e:  # network errors, timeouts
        out["error"] = f"{type(e).__name__}: {e}"
    out["total_s"] = time.perf_counter() - t0

    u = out["usage"] or {}
    ct = u.get("completion_tokens")
    out["completion_tokens"] = ct
    out["prompt_tokens"] = u.get("prompt_tokens")
    out["usage_estimated"] = False
    if ct is None:  # no usage from server: rough estimate, flagged as such
        ct = (len(out["content"]) + len(out["reasoning"])) // 4
        out["completion_tokens"] = ct
        out["usage_estimated"] = True
    if ct and out["total_s"]:
        out["tokens_per_s_overall"] = ct / out["total_s"]
        if out["ttft_s"] is not None and out["total_s"] > out["ttft_s"]:
            out["decode_tokens_per_s"] = ct / (out["total_s"] - out["ttft_s"])
    return out


def save(outdir, stem, res):
    (outdir / f"{stem}.raw.txt").write_text(res["content"] or "")
    rp = outdir / f"{stem}.reasoning.txt"
    if res.get("reasoning"):
        rp.write_text(res["reasoning"])
    elif rp.exists():
        rp.unlink()
    answer = strip_think(res["content"])
    meta = {k: v for k, v in res.items() if k not in ("content", "reasoning")}
    meta.update({"content_chars": len(res["content"] or ""),
                 "reasoning_chars": len(res.get("reasoning") or ""),
                 "answer_words": len(answer.split()),
                 "empty_answer": not answer,
                 "truncated": res.get("finish_reason") == "length"})
    (outdir / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="server base URL, /v1 URL, or full chat/completions URL")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True, help="results subfolder name (use <name>_r1, <name>_r2 ... for repeats)")
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--seed", type=int, help="passed through as 'seed' if given")
    ap.add_argument("--timeout", type=float, default=3600, help="per-request timeout, seconds")
    ap.add_argument("--no-stream", action="store_true", help="disable streaming (no TTFT)")
    ap.add_argument("--extra-body", help='JSON merged into the request, e.g. \'{"chat_template_kwargs":{"enable_thinking":true}}\'')
    ap.add_argument("--api-key")
    ap.add_argument("--only", help="comma-separated task ids, e.g. R01,R07")
    ap.add_argument("--resume", action="store_true", help="skip tasks that already have a non-empty, untruncated answer")
    ap.add_argument("--out-root", default=str(DEFAULT_RESULTS))
    args = ap.parse_args()
    if args.extra_body:
        json.loads(args.extra_body)  # fail fast on bad JSON

    outdir = Path(args.out_root).expanduser() / args.label
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_p = outdir / "run_manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    manifest.update({
        "label": args.label, "model": args.model, "url": endpoint(args.url),
        "params": {"max_tokens": args.max_tokens, "temperature": args.temperature, "top_p": args.top_p,
                   "seed": args.seed, "stream": not args.no_stream,
                   "extra_body": json.loads(args.extra_body) if args.extra_body else None},
        "system_prompt_sha": sha(SYSTEM_PROMPT),
        "tasks_sha": hashlib.sha256(b"".join(sha(p).encode() for p in sorted(TASKS.glob("R*.md")))).hexdigest()[:16],
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
    })
    manifest_p.write_text(json.dumps(manifest, indent=2))

    system = load_system()
    ids = task_ids()
    if args.only:
        ids = [i for i in ids if i in set(args.only.split(","))]
    for tid in ids:
        meta_p = outdir / f"{tid}.meta.json"
        if args.resume and meta_p.exists():
            m = json.loads(meta_p.read_text())
            if not m.get("error") and not m.get("empty_answer") and not m.get("truncated"):
                print(f"{tid}: skip (already done)")
                continue
        res = chat(args, system, load_task(tid))
        m = save(outdir, tid, res)
        tps, ttft = m.get("decode_tokens_per_s"), m.get("ttft_s")
        print(f"{tid}: words={m['answer_words']:<5} total={m['total_s']:.1f}s "
              f"ttft={'-' if ttft is None else f'{ttft:.1f}s'} tok={m.get('completion_tokens')} "
              f"tps={'-' if tps is None else f'{tps:.1f}'} finish={m.get('finish_reason')}"
              + (" EMPTY-ANSWER" if m["empty_answer"] else "")
              + (f" ERROR {m['error']}" if m.get("error") else ""), flush=True)
    print(f"results: {outdir}")


if __name__ == "__main__":
    sys.exit(main())
