#!/usr/bin/env python3
"""MTP / speculative decoding on vs off: speed gain and whether outputs match.

Only one ~190GB model fits in memory at a time, so run it twice:
  1. start the server with MTP off:  python mtp_compare.py record --url ... --label qwen-llama-mtp-off
  2. restart it with MTP on:         python mtp_compare.py record --url ... --label qwen-llama-mtp-on
  3. python mtp_compare.py compare <off.jsonl> <on.jsonl> --tokenizer <model dir>

Greedy decoding (temperature 0) should in theory give identical text; in practice
float differences can make it diverge, so compare reports where it first differs.
"""
import argparse, json, pathlib, statistics, time

from common import Corpus, load_tokenizer, server_model, stream_chat

PROMPTS = {
    "code": "Write a complete Python implementation of a thread-safe LRU cache with TTL expiry, "
            "including type hints, docstrings and a small test suite using pytest.",
    "prose": "Write a 600-word short story about a lighthouse keeper who discovers the light "
             "has been signalling to someone.",
    "reasoning": "A train leaves city A at 9:00 travelling at 80 km/h. Another leaves city B, 440 km away, "
                 "at 10:00 travelling toward A at 120 km/h. Explain step by step when and where they meet, "
                 "then generalize the method.",
    "json": "Produce a JSON array of 15 fictional hospital departments, each with name, floor, "
            "head_physician, bed_count and a list of three services.",
}


def record(args):
    model = args.model or server_model(args.url)
    extra = {"chat_template_kwargs": {"enable_thinking": False, "thinking": False},
             "temperature": args.temperature}
    if args.top_k is not None:
        extra["top_k"] = args.top_k
    if args.top_p is not None:
        extra["top_p"] = args.top_p
    prompts = dict(PROMPTS)
    if args.tokenizer:
        tok_name = pathlib.Path(args.tokenizer.rstrip("/")).name
        doc = Corpus("books", load_tokenizer(args.tokenizer), tok_name).text(0, 8000)
        prompts["summary_8k"] = doc + "\n\nSummarize the text above in about 400 words."
    outdir = pathlib.Path(args.out) / "mtp"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    stream_chat(args.url, model, [{"role": "user", "content": "Say hi."}], 8, extra)  # warmup
    with out.open("w") as f:
        for name, prompt in prompts.items():
            for rep in range(args.repeats):
                r = stream_chat(args.url, model, [{"role": "user", "content": prompt}], args.max_tokens, extra)
                r.update(prompt=name, rep=rep, label=args.label, temperature=args.temperature,
                         top_k=args.top_k, top_p=args.top_p)
                f.write(json.dumps(r) + "\n")
                t = r.get("server_timings") or {}
                acc = f" draft {t.get('draft_n_accepted')}/{t.get('draft_n')}" if t.get("draft_n") else ""
                print(f"{name:>10} rep{rep} decode={r['decode_tps']} t/s tokens={r['completion_tokens']}{acc}", flush=True)
    print(f"wrote {out}")


def first_divergence(a, b):
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return None if len(a) == len(b) else n


def compare(args):
    load = lambda p: [json.loads(l) for l in open(p)]
    off, on = load(args.off), load(args.on)
    tok = load_tokenizer(args.tokenizer) if args.tokenizer else None
    print(f"{'prompt':>10} {'off t/s':>8} {'on t/s':>8} {'speedup':>8}  output match")
    for name in dict.fromkeys(r["prompt"] for r in off):
        a = [r for r in off if r["prompt"] == name]
        b = [r for r in on if r["prompt"] == name]
        if not b:
            continue
        s_off = statistics.median(r["decode_tps"] for r in a)
        s_on = statistics.median(r["decode_tps"] for r in b)
        ta, tb = a[0]["content"], b[0]["content"]
        if a[0].get("temperature", 0) > 0 or b[0].get("temperature", 0) > 0:
            match = "sampled (speed only)"
        elif ta == tb:
            match = "identical"
        elif tok:
            ia, ib = tok.encode(ta).ids, tok.encode(tb).ids
            match = f"diverges at token {first_divergence(ia, ib)} of {len(ia)}/{len(ib)}"
        else:
            match = f"diverges at char {first_divergence(ta, tb)}"
        print(f"{name:>10} {s_off:>8.1f} {s_on:>8.1f} {s_on / s_off:>7.2f}x  {match}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--url", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--model")
    r.add_argument("--tokenizer", help="adds an 8k-token summarization prompt from the books corpus")
    r.add_argument("--max-tokens", type=int, default=512)
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--temperature", type=float, default=0.0,
                   help="0 = greedy, outputs comparable; use the model's recommended value for realistic speed")
    r.add_argument("--top-k", type=int)
    r.add_argument("--top-p", type=float)
    r.add_argument("--out", default=str(pathlib.Path.home() / "bench-results"))
    c = sub.add_parser("compare")
    c.add_argument("off")
    c.add_argument("on")
    c.add_argument("--tokenizer")
    args = ap.parse_args()
    record(args) if args.cmd == "record" else compare(args)


if __name__ == "__main__":
    main()
