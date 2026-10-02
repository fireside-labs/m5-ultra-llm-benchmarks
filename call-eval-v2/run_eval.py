#!/usr/bin/env python3
"""Run the call-transcript analysis eval against an OpenAI-compatible chat endpoint.

Examples
  python run_eval.py --url http://localhost:8000 --model GLM-5.3-Flash --label glm53
  python run_eval.py --url http://localhost:8000/v1 --model X --label x --only C01,C10
  python run_eval.py --url ... --model X --label x --themes        # per-call run, then themes
  python run_eval.py --url ... --model X --label x --themes-only   # themes from existing outputs

Writes to results/call-eval-v2/<label>/ (override with --out-root):
  Cxx.raw.txt        model reply content (exactly as returned)
  Cxx.reasoning.txt  separate reasoning stream, if the server returns one
  Cxx.json           parsed analysis (or absent if parsing failed)
  Cxx.meta.json      timing (ttft, total), token usage, tokens/s, finish_reason, parse mode, errors
  themes.*           same files for the cross-call themes step
  run_manifest.json  model/url/params + sha256 of prompt, schema and transcripts
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from evallib import (DEFAULT_RESULTS, ROOT, TRANSCRIPTS, call_ids, extract_json, load_prompt)


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
    if not args.no_stream:
        body["stream_options"] = {"include_usage": True}
    if args.json_mode:
        body["response_format"] = {"type": "json_object"}
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


def save(outdir, stem, res, parsed, mode, extra=None):
    (outdir / f"{stem}.raw.txt").write_text(res["content"] or "")
    if res.get("reasoning"):
        (outdir / f"{stem}.reasoning.txt").write_text(res["reasoning"])
    pj = outdir / f"{stem}.json"
    if parsed is not None:
        pj.write_text(json.dumps(parsed, indent=2, ensure_ascii=False))
    elif pj.exists():
        pj.unlink()
    meta = {k: v for k, v in res.items() if k not in ("content", "reasoning")}
    meta.update({"parse_mode": mode, "parse_ok": parsed is not None,
                 "content_chars": len(res["content"] or ""),
                 "reasoning_chars": len(res.get("reasoning") or "")})
    if extra:
        meta.update(extra)
    (outdir / f"{stem}.meta.json").write_text(json.dumps(meta, indent=2))
    return meta


def run_calls(args, outdir):
    system, user_tmpl = load_prompt(ROOT / "prompt.md")
    schema = (ROOT / "schema.json").read_text()
    ids = call_ids()
    if args.only:
        ids = [i for i in ids if i in set(args.only.split(","))]
    for cid in ids:
        meta_p = outdir / f"{cid}.meta.json"
        if args.resume and meta_p.exists() and json.loads(meta_p.read_text()).get("parse_ok"):
            print(f"{cid}: skip (already done)")
            continue
        transcript = (TRANSCRIPTS / f"{cid}.txt").read_text()
        user = user_tmpl.replace("{schema}", schema).replace("{transcript}", transcript)
        res = chat(args, system, user)
        parsed, mode = extract_json(res["content"])
        if parsed is None and not res["content"] and res.get("reasoning"):
            # some servers put everything in the reasoning channel when thinking is on
            parsed, mode = extract_json(res["reasoning"])
            mode = mode + "_from_reasoning" if parsed is not None else mode
        m = save(outdir, cid, res, parsed, mode)
        tps = m.get("decode_tokens_per_s")
        ttft = m.get("ttft_s")
        print(f"{cid}: parse={mode:<8} total={m['total_s']:.1f}s "
              f"ttft={'-' if ttft is None else f'{ttft:.1f}s'} "
              f"tok={m.get('completion_tokens')} "
              f"tps={'-' if tps is None else f'{tps:.1f}'} finish={m.get('finish_reason')}"
              + (f" ERROR {m['error']}" if m.get("error") else ""), flush=True)


def build_call_notes(outdir):
    blocks = []
    for cid in call_ids():
        p = outdir / f"{cid}.json"
        if not p.exists():
            blocks.append(f"### {cid}\n(no analysis available for this call)")
            continue
        a = json.loads(p.read_text())
        lines = [f"### {cid} ({a.get('call_type', '?')}, outcome: {a.get('outcome', '?')})",
                 f"Summary: {a.get('summary_notes', '')}"]
        nd = a.get("notable_details") or []
        if nd:
            lines.append("Notable details:")
            lines += [f"- {d if isinstance(d, str) else json.dumps(d)}" for d in nd]
        fl = a.get("flags") or []
        if fl:
            lines.append("Flags:")
            for f in fl:
                if isinstance(f, dict):
                    lines.append(f"- [{f.get('type', '')}] {f.get('description', '')}")
                else:
                    lines.append(f"- {f}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def run_themes(args, outdir):
    system, user_tmpl = load_prompt(ROOT / "themes_prompt.md")
    notes = build_call_notes(outdir)
    (outdir / "themes.input.txt").write_text(notes)
    res = chat(args, system, user_tmpl.replace("{calls}", notes))
    parsed, mode = extract_json(res["content"], expect_keys={"themes"})
    if parsed is None and not res["content"] and res.get("reasoning"):
        parsed, mode = extract_json(res["reasoning"], expect_keys={"themes"})
    m = save(outdir, "themes", res, parsed, mode)
    n = len(parsed.get("themes", [])) if parsed else 0
    print(f"themes: parse={mode} themes={n} total={m['total_s']:.1f}s"
          + (f" ERROR {m['error']}" if m.get("error") else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="server base URL, /v1 URL, or full chat/completions URL")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True, help="results subfolder name")
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--temperature", type=float, default=0.1)
    ap.add_argument("--top-p", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=1800, help="per-request timeout, seconds")
    ap.add_argument("--no-stream", action="store_true", help="disable streaming (no TTFT)")
    ap.add_argument("--json-mode", action="store_true", help='send response_format={"type":"json_object"}')
    ap.add_argument("--extra-body", help='JSON merged into the request, e.g. \'{"chat_template_kwargs":{"enable_thinking":false}}\'')
    ap.add_argument("--api-key")
    ap.add_argument("--only", help="comma-separated call ids, e.g. C01,C10")
    ap.add_argument("--resume", action="store_true", help="skip calls that already parsed OK")
    ap.add_argument("--themes", action="store_true", help="after the per-call run, run the themes step")
    ap.add_argument("--themes-only", action="store_true", help="only run the themes step on existing outputs")
    ap.add_argument("--out-root", default=str(DEFAULT_RESULTS))
    args = ap.parse_args()

    outdir = Path(args.out_root).expanduser() / args.label
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_p = outdir / "run_manifest.json"
    manifest = json.loads(manifest_p.read_text()) if manifest_p.exists() else {}
    manifest.update({
        "label": args.label, "model": args.model, "url": endpoint(args.url),
        "params": {"max_tokens": args.max_tokens, "temperature": args.temperature, "top_p": args.top_p,
                   "stream": not args.no_stream, "json_mode": args.json_mode,
                   "extra_body": json.loads(args.extra_body) if args.extra_body else None},
        "prompt_sha": sha(ROOT / "prompt.md"), "themes_prompt_sha": sha(ROOT / "themes_prompt.md"),
        "schema_sha": sha(ROOT / "schema.json"),
        "transcripts_sha": hashlib.sha256(b"".join(sha(p).encode() for p in sorted(TRANSCRIPTS.glob("C*.txt")))).hexdigest()[:16],
        "updated": dt.datetime.now().isoformat(timespec="seconds"),
    })
    manifest_p.write_text(json.dumps(manifest, indent=2))

    if not args.themes_only:
        run_calls(args, outdir)
    if args.themes or args.themes_only:
        run_themes(args, outdir)
    print(f"results: {outdir}")


if __name__ == "__main__":
    sys.exit(main())
