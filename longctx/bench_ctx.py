#!/usr/bin/env python3
"""Prefill vs context depth, against any OpenAI-compatible server (llama-server, oMLX).

For each depth N:
  cold: a unique nonce + N tokens of corpus + question. The nonce is at the very
        start, so no prompt cache (RAM or SSD) can match it. This is "paste a
        100k document", and TTFT here is the real wait.
  warm: the same conversation continued, agent-style: the previous turn plus the
        model's answer plus S new tokens (the next part of the corpus, like a tool
        result) and a new question. Only the new part should need processing.
        This is "step 500 of an agent session at depth N".

Records TTFT, prefill speed, decode speed, and whatever the server reports about
cached/processed tokens, so you can see whether caching actually kicked in.

Example:
  python bench_ctx.py --engine llama.cpp --url http://127.0.0.1:8080 \
      --tokenizer ~/models/Qwen3.8-Flash-Next-oQ8e-mtp --label qwen-q8-llama \
      --depths 10000,50000,100000,200000,250000
"""
import argparse, json, pathlib, statistics, time, uuid

from common import Corpus, load_tokenizer, server_model, stream_chat, system_info

Q_COLD = "\n\nQuestion: Summarize what happens in the text above in about 150 words."
Q_WARM = "\n\nQuestion: Summarize what happens in this new section in about 150 words."


def median(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", required=True, choices=["llama.cpp", "omlx", "mlx", "other"])
    ap.add_argument("--url", required=True)
    ap.add_argument("--tokenizer", required=True, help="model dir, tokenizer.json, or HF repo id")
    ap.add_argument("--label", required=True, help="short name for this config, used in the output filename")
    ap.add_argument("--model", help="model id to send (default: first from /v1/models)")
    ap.add_argument("--model-path", help="model file/dir on disk, recorded so results say which drive it loaded from")
    ap.add_argument("--corpus", default="books", choices=["books", "code"])
    ap.add_argument("--depths", default="10000,100000,200000")
    ap.add_argument("--steps", default="64,4096", help="new tokens added per warm step")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--repeats-large", type=int, default=1, help="repeats for depths >= --large")
    ap.add_argument("--large", type=int, default=300000)
    ap.add_argument("--template-kwargs", help="JSON merged into chat_template_kwargs, e.g. '{\"reasoning_effort\": \"low\"}'")
    ap.add_argument("--think", action="store_true", help="leave thinking on (default: ask the template to disable it)")
    ap.add_argument("--out", default=str(pathlib.Path.home() / "bench-results"))
    args = ap.parse_args()

    tok_name = pathlib.Path(args.tokenizer.rstrip("/")).name.replace("/", "_")
    corpus = Corpus(args.corpus, load_tokenizer(args.tokenizer), tok_name)
    model = args.model or server_model(args.url)
    depths = [int(x) for x in args.depths.split(",")]
    steps = [int(x) for x in args.steps.split(",")]
    extra = {"cache_prompt": True}
    if not args.think:
        extra["chat_template_kwargs"] = {"enable_thinking": False, "thinking": False}
    if args.template_kwargs:
        extra.setdefault("chat_template_kwargs", {}).update(json.loads(args.template_kwargs))
    if args.engine == "llama.cpp":
        extra["ignore_eos"] = True  # fixed output length for fair decode numbers

    stamp = time.strftime("%Y%m%d-%H%M%S")
    outdir = pathlib.Path(args.out) / "longctx"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{stamp}-{args.label}.jsonl"
    meta = {"type": "meta", "label": args.label, "model": model, "args": vars(args),
            "system": system_info(args.engine, args.model_path)}
    with out.open("a") as f:
        f.write(json.dumps(meta) + "\n")
    print(json.dumps(meta["system"], indent=1))

    def record(row):
        row.update({"label": args.label, "engine": args.engine})
        with out.open("a") as f:
            f.write(json.dumps(row) + "\n")
        pt, ct = row.get("prompt_tokens"), row.get("cached_tokens")
        print(f"  {row['type']:>4} depth={row['depth']:>8,} step={row.get('step', 0):>5} "
              f"ttft={row['ttft_s']:>9.2f}s prefill={row.get('prefill_tps') or 0:>8.1f} t/s "
              f"decode={row.get('decode_tps') or 0:>6.1f} t/s prompt_tokens={pt} cached={ct}", flush=True)

    print("warmup ...", flush=True)
    stream_chat(args.url, model, [{"role": "user", "content": corpus.text(0, 2000) + Q_COLD}], 32, extra)

    for depth in depths:
        reps = args.repeats if depth < args.large else args.repeats_large
        for rep in range(reps):
            nonce = f"[run {uuid.uuid4()}]\n\n"
            doc = corpus.text(0, depth)
            msgs = [{"role": "user", "content": nonce + doc + Q_COLD}]
            r = stream_chat(args.url, model, msgs, args.max_tokens, extra)
            r.update(type="cold", depth=depth, rep=rep,
                     prefill_tps=round(r["prompt_tokens"] / r["ttft_s"], 1) if r["prompt_tokens"] else None)
            answer = r.pop("content")
            r.pop("reasoning")
            record(r)

            offset = depth
            for step in steps:
                new = corpus.text(offset, step)
                offset += step
                msgs = msgs + [{"role": "assistant", "content": answer},
                               {"role": "user", "content": new + Q_WARM}]
                w = stream_chat(args.url, model, msgs, args.max_tokens, extra)
                t = w.get("server_timings") or {}
                processed = t.get("prompt_n") or (
                    w["prompt_tokens"] - w["cached_tokens"] if w.get("cached_tokens") is not None and w["prompt_tokens"] else None)
                w.update(type="warm", depth=depth, rep=rep, step=step, processed_tokens=processed,
                         prefill_tps=round(processed / w["ttft_s"], 1) if processed else None)
                answer = w.pop("content")
                w.pop("reasoning")
                record(w)

    rows = [json.loads(l) for l in out.open() if '"type": "meta"' not in l]
    print(f"\nmedians ({out}):")
    print(f"{'type':>5} {'depth':>9} {'step':>5} {'ttft_s':>9} {'prefill_t/s':>12} {'decode_t/s':>11}")
    keys = sorted({(r["type"], r["depth"], r.get("step", 0)) for r in rows}, key=lambda k: (k[1], k[0], k[2]))
    for typ, depth, step in keys:
        g = [r for r in rows if (r["type"], r["depth"], r.get("step", 0)) == (typ, depth, step)]
        print(f"{typ:>5} {depth:>9,} {step:>5} {median([r['ttft_s'] for r in g]):>9} "
              f"{median([r.get('prefill_tps') for r in g]) or '-':>12} {median([r.get('decode_tps') for r in g]) or '-':>11}")


if __name__ == "__main__":
    main()
