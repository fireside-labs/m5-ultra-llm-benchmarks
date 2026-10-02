#!/usr/bin/env python3
"""Parallel requests: how per-request speed and total throughput change with N requests at once.

For each concurrency level N, N requests start together. Each has a unique nonce at the
start (no cache hits), a document of --prompt-tokens from the books corpus, and asks for a
long answer (--max-tokens). Reports per-request TTFT / decode t/s and the aggregate output
tokens per second over the wall time of the batch, plus "requests per hour" at that level.

  python concurrency.py --url http://127.0.0.1:8000 --model glm53-flash \
      --tokenizer ~/models/GLM-5.3-Flash-oQ4e --label glm53-conc \
      --levels 1,2,4,8 --prompt-tokens 1000,20000
"""
import argparse, json, pathlib, statistics, threading, time, uuid

from common import Corpus, load_tokenizer, stream_chat

ASK = ("\n\nWrite a detailed analysis of the passage above: the characters, what happens, the tone, "
       "and three quotations with commentary. Aim for about 800 words.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--levels", default="1,2,4,8")
    ap.add_argument("--prompt-tokens", default="1000,20000", help="comma-separated prompt sizes to test")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--template-kwargs", help='JSON merged into chat_template_kwargs, e.g. \'{"reasoning_effort": "low"}\'')
    ap.add_argument("--out", default=str(pathlib.Path.home() / "bench-results"))
    args = ap.parse_args()

    tok_name = pathlib.Path(args.tokenizer.rstrip("/")).name
    corpus = Corpus("books", load_tokenizer(args.tokenizer), tok_name)
    extra = {"chat_template_kwargs": {"enable_thinking": False, "thinking": False}, "temperature": 0.7}
    if args.template_kwargs:
        extra["chat_template_kwargs"].update(json.loads(args.template_kwargs))
    outdir = pathlib.Path(args.out) / "concurrency"
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    stream_chat(args.url, args.model, [{"role": "user", "content": "Say hi."}], 8, extra)  # warmup

    offset = 0
    with out.open("w") as f:
        f.write(json.dumps({"type": "meta", "args": vars(args)}) + "\n")
        for size in (int(s) for s in args.prompt_tokens.split(",")):
            for n in (int(x) for x in args.levels.split(",")):
                results = [None] * n

                def worker(i, doc):
                    msgs = [{"role": "user", "content": f"[run {uuid.uuid4()}]\n\n" + doc + ASK}]
                    try:
                        results[i] = stream_chat(args.url, args.model, msgs, args.max_tokens, extra)
                    except Exception as e:  # keep the batch going; record the failure
                        results[i] = {"error": f"{e.__class__.__name__}: {e}"}

                docs = []
                for _ in range(n):  # different text per request so nothing is shared
                    docs.append(corpus.text(offset, size))
                    offset += size
                threads = [threading.Thread(target=worker, args=(i, docs[i])) for i in range(n)]
                t0 = time.time()
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()
                wall = time.time() - t0
                ok = [r for r in results if r and "error" not in r]
                out_tok = sum(r["completion_tokens"] or 0 for r in ok)
                in_tok = sum(r["prompt_tokens"] or 0 for r in ok)
                row = {"type": "level", "prompt_tokens": size, "concurrency": n, "ok": len(ok), "wall_s": round(wall, 2),
                       "aggregate_out_tps": round(out_tok / wall, 1), "aggregate_in_tps": round(in_tok / wall, 1),
                       "requests_per_hour": round(len(ok) / wall * 3600),
                       "median_ttft_s": round(statistics.median(r["ttft_s"] for r in ok), 2) if ok else None,
                       "max_ttft_s": round(max(r["ttft_s"] for r in ok), 2) if ok else None,
                       "median_decode_tps": round(statistics.median(r["decode_tps"] for r in ok), 1) if ok else None,
                       "errors": [r["error"] for r in results if r and "error" in r],
                       "requests": [{k: r.get(k) for k in ("ttft_s", "total_s", "prompt_tokens", "completion_tokens", "decode_tps")} for r in ok]}
                f.write(json.dumps(row) + "\n"); f.flush()
                print(f"prompt {size:>6} x{n}: wall {wall:6.1f}s  total out {row['aggregate_out_tps']:6.1f} t/s  "
                      f"per-request decode {row['median_decode_tps']} t/s  ttft med {row['median_ttft_s']}s max {row['max_ttft_s']}s  "
                      f"{row['requests_per_hour']} req/h  errors {len(row['errors'])}", flush=True)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
