#!/usr/bin/env python3
"""Run the pushback-eval multi-turn conversations against an OpenAI-compatible chat endpoint.

Each topic is one conversation: turn 0 = brief (model writes a recommendation), then 3 follow-up
user turns (critiques / pressure) appended to the same conversation. Prior assistant turns are
resent with any <think>...</think> blocks stripped; the separate reasoning stream is never resent.

Examples
  python run_eval.py --url http://127.0.0.1:8000 --model GLM-5.3-Flash --label glm53_r1
  python run_eval.py --url http://127.0.0.1:8000/v1 --model X --label x --only P02,P05
  python run_eval.py --url ... --model X --label x \
      --extra-body '{"chat_template_kwargs":{"enable_thinking":true}}'

Writes to results/pushback-eval/<label>/ (override with --out-root):
  Pxx.tN.raw.txt        reply content for turn N (0 = initial, 1..3 = follow-ups), exactly as returned
  Pxx.tN.reasoning.txt  separate reasoning stream, if the server returns one (never scored, never resent)
  Pxx.tN.meta.json      timing (ttft, total), token usage, tokens/s, finish_reason, errors
  Pxx.conversation.json the exact messages sent on the last turn + the final reply (audit trail)
  run_manifest.json     model/url/params + sha256 of the prompts and topic files
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from evallib import (DEFAULT_RESULTS, PROMPTS, TOPICS, load_system, load_topic, n_turns, strip_think,
                     topic_ids, user_turns)

EMPTY_PLACEHOLDER = "(no answer)"


def endpoint(url):
    url = url.rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def chat(args, messages):
    """Send one request. Returns dict with content, reasoning, timings and usage."""
    body = {
        "model": args.model,
        "messages": messages,
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


def save(outdir, stem, res, n_messages):
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
                 "truncated": res.get("finish_reason") == "length",
                 "messages_sent": n_messages})
    (outdir / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def topic_done(outdir, tid, turns):
    for n in range(turns):
        p = outdir / f"{tid}.t{n}.meta.json"
        if not p.exists():
            return False
        m = json.loads(p.read_text())
        if m.get("error") or m.get("empty_answer") or m.get("truncated"):
            return False
    return True


def run_topic(args, outdir, tid, system):
    topic = load_topic(tid)
    users = user_turns(topic)
    for old in outdir.glob(f"{tid}.t*.*"):      # a topic is always re-run from turn 0 (history-dependent)
        old.unlink()
    messages = [{"role": "system", "content": system}]
    for n, user in enumerate(users):
        messages.append({"role": "user", "content": user})
        res = chat(args, messages)
        m = save(outdir, f"{tid}.t{n}", res, len(messages))
        tps, ttft = m.get("decode_tokens_per_s"), m.get("ttft_s")
        print(f"{tid} t{n}: words={m['answer_words']:<5} total={m['total_s']:.1f}s "
              f"ttft={'-' if ttft is None else f'{ttft:.1f}s'} tok={m.get('completion_tokens')} "
              f"tps={'-' if tps is None else f'{tps:.1f}'} finish={m.get('finish_reason')}"
              + (" EMPTY-ANSWER" if m["empty_answer"] else "")
              + (f" ERROR {m['error']}" if m.get("error") else ""), flush=True)
        if res.get("error"):
            print(f"{tid}: aborting topic after error on turn {n}", flush=True)
            break
        # resend only the answer channel: no <think> blocks, never the reasoning stream
        answer = strip_think(res["content"]) or EMPTY_PLACEHOLDER
        messages.append({"role": "assistant", "content": answer})
    (outdir / f"{tid}.conversation.json").write_text(json.dumps(
        {"topic": tid, "model": args.model, "messages": messages}, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="server base URL, /v1 URL, or full chat/completions URL")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True, help="results subfolder name (use <name>_r1, <name>_r2 ... for repeats)")
    ap.add_argument("--max-tokens", type=int, default=12000, help="per turn")
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--seed", type=int, help="passed through as 'seed' if given")
    ap.add_argument("--timeout", type=float, default=3600, help="per-request timeout, seconds")
    ap.add_argument("--no-stream", action="store_true", help="disable streaming (no TTFT)")
    ap.add_argument("--extra-body", help='JSON merged into the request, e.g. \'{"chat_template_kwargs":{"enable_thinking":true}}\'')
    ap.add_argument("--api-key")
    ap.add_argument("--only", help="comma-separated topic ids, e.g. P01,P05")
    ap.add_argument("--resume", action="store_true",
                    help="skip topics whose every turn has a non-empty, untruncated, error-free answer (others re-run from turn 0)")
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
        "params": {"max_tokens_per_turn": args.max_tokens, "temperature": args.temperature, "top_p": args.top_p,
                   "seed": args.seed, "stream": not args.no_stream,
                   "extra_body": json.loads(args.extra_body) if args.extra_body else None},
        "prompts_sha": {p.name: sha(p) for p in sorted(PROMPTS.glob("*.md"))},
        "topics_sha": hashlib.sha256(b"".join(sha(p).encode() for p in sorted(TOPICS.glob("P*.json")))).hexdigest()[:16],
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
    })
    manifest_p.write_text(json.dumps(manifest, indent=2))

    system = load_system()
    ids = topic_ids()
    if args.only:
        ids = [i for i in ids if i in set(args.only.split(","))]
    for tid in ids:
        if args.resume and topic_done(outdir, tid, n_turns(load_topic(tid))):
            print(f"{tid}: skip (already done)")
            continue
        run_topic(args, outdir, tid, system)
    print(f"results: {outdir}")


if __name__ == "__main__":
    sys.exit(main())
