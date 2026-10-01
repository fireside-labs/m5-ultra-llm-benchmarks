#!/usr/bin/env python3
"""Speed + recall + power at very long context (up to 1M tokens).

For each depth: one cold prompt with three hidden facts ("needles"), each placed next to
a near-identical decoy, at 10%, 50% and 90% of the document. The question at the end
asks for all three. Then one warm step (64 new tokens) to measure the cost of continuing
a cached 1M-token conversation. If `macmon pipe` is available, power is sampled every
250 ms and averaged over the prefill and decode phases of each request.

  python bench_1m.py --url http://127.0.0.1:8000 --model dsv4-0731 \
      --tokenizer ~/models/DeepSeek-V4-Flash-0731-oQ4e-mtp --label ds0731-omlxk-1m \
      --depths 300000,500000,750000,1000000
"""
import argparse, json, pathlib, shutil, subprocess, threading, time, uuid

from common import Corpus, load_tokenizer, stream_chat, system_info

NEEDLES = [  # (fraction of document, needle, decoy)
    (0.10, "The access code for the Aurora vault is 7294-KILO.",
           "The access code for the Aurelia vault is 7249-KILN."),
    (0.50, "The access code for the Borealis vault is 5081-TANGO.",
           "The access code for the Borealia vault is 5018-TANGY."),
    (0.90, "The access code for the Cygnus vault is 3367-FOXTROT.",
           "The access code for the Cygna vault is 3376-FOXHOLE."),
]
ANSWERS = {"Aurora": "7294-KILO", "Borealis": "5081-TANGO", "Cygnus": "3367-FOXTROT"}
QUESTION = ("\n\nQuestion: The text above mentions access codes for several vaults with similar names. "
            "What are the exact access codes for the Aurora, Borealis and Cygnus vaults? "
            "Answer in the form 'Aurora: X, Borealis: Y, Cygnus: Z'.")
Q_WARM = "\n\nQuestion: In one sentence, what is happening in this new passage?"


class Power:
    """Background macmon sampler: list of (time, cpu_w, gpu_w, sys_w)."""

    def __init__(self):
        self.samples, self.proc = [], None
        exe = shutil.which("macmon") or ("/opt/homebrew/bin/macmon" if pathlib.Path("/opt/homebrew/bin/macmon").exists() else None)
        if exe:
            self.proc = subprocess.Popen([exe, "pipe", "-i", "250"], stdout=subprocess.PIPE, text=True)
            threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            self.samples.append((time.time(), d.get("cpu_power"), d.get("gpu_power"),
                                 d.get("sys_power") or d.get("all_power")))

    def avg(self, t0, t1):
        s = [x for x in self.samples if t0 <= x[0] <= t1]
        if not s:
            return None
        mean = lambda i: round(sum(x[i] or 0 for x in s) / len(s), 1)
        return {"cpu_w": mean(1), "gpu_w": mean(2), "sys_w": mean(3), "n": len(s)}

    def stop(self):
        if self.proc:
            self.proc.terminate()


def build_doc(corpus, depth):
    parts, pos = [], 0
    for frac, needle, decoy in NEEDLES:
        cut = int(depth * frac)
        parts.append(corpus.text(pos, cut - pos))
        parts.append(f"\n\n{decoy} Meanwhile, elsewhere, a clerk noted: {needle}\n\n")
        pos = cut
    parts.append(corpus.text(pos, depth - pos))
    return "".join(parts)


def score(answer):
    return {k: v in answer for k, v in ANSWERS.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--tokenizer", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--engine", default="omlx")
    ap.add_argument("--model-path")
    ap.add_argument("--depths", default="300000,500000,750000,1000000")
    ap.add_argument("--max-tokens", type=int, default=128)
    ap.add_argument("--out", default=str(pathlib.Path.home() / "bench-results"))
    ap.add_argument("--template-kwargs", help='JSON merged into chat_template_kwargs, e.g. \'{"reasoning_effort": "low"}\'')
    args = ap.parse_args()

    tok_name = pathlib.Path(args.tokenizer.rstrip("/")).name
    corpus = Corpus("books", load_tokenizer(args.tokenizer), tok_name)
    extra = {"chat_template_kwargs": {"enable_thinking": False, "thinking": False}}
    if args.template_kwargs:
        extra["chat_template_kwargs"].update(json.loads(args.template_kwargs))
    out = pathlib.Path(args.out).expanduser() / "longctx" / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    power = Power()
    with out.open("w") as f:
        f.write(json.dumps({"type": "meta", "args": vars(args), "power": bool(power.proc),
                            "system": system_info(args.engine, args.model_path)}) + "\n")
        print("warmup ...", flush=True)
        stream_chat(args.url, args.model, [{"role": "user", "content": corpus.text(0, 2000) + Q_WARM}], 16, extra)
        for depth in (int(d) for d in args.depths.split(",")):
            nonce = f"[run {uuid.uuid4()}]\n\n"
            msgs = [{"role": "user", "content": nonce + build_doc(corpus, depth) + QUESTION}]
            t0 = time.time()
            r = stream_chat(args.url, args.model, msgs, args.max_tokens, extra)
            t_first = t0 + r["ttft_s"]
            t_end = t0 + r["total_s"]
            hits = score(r["content"])
            row = {"type": "cold", "depth": depth, **{k: r[k] for k in ("ttft_s", "total_s", "prompt_tokens", "cached_tokens", "completion_tokens", "decode_tps")},
                   "prefill_tps": round(r["prompt_tokens"] / r["ttft_s"], 1) if r["prompt_tokens"] else None,
                   "answer": r["content"][:300], "recall": hits, "recall_n": sum(hits.values()),
                   "power_prefill": power.avg(t0, t_first), "power_decode": power.avg(t_first, t_end)}
            f.write(json.dumps(row) + "\n"); f.flush()
            print(f"cold {depth:>9,}: ttft {row['ttft_s']:.0f}s prefill {row['prefill_tps']} t/s decode {row['decode_tps']} t/s "
                  f"recall {row['recall_n']}/3 power(prefill) {row['power_prefill']}", flush=True)

            msgs += [{"role": "assistant", "content": r["content"]},
                     {"role": "user", "content": corpus.text(depth + 10_000, 64) + Q_WARM}]
            t0 = time.time()
            w = stream_chat(args.url, args.model, msgs, args.max_tokens, extra)
            t_first = t0 + w["ttft_s"]
            wrow = {"type": "warm", "depth": depth, **{k: w[k] for k in ("ttft_s", "total_s", "prompt_tokens", "cached_tokens", "completion_tokens", "decode_tps")},
                    "power_prefill": power.avg(t0, t_first), "power_decode": power.avg(t_first, t0 + w["total_s"])}
            f.write(json.dumps(wrow) + "\n"); f.flush()
            print(f"warm {depth:>9,}: ttft {wrow['ttft_s']:.2f}s cached {wrow['cached_tokens']} decode {wrow['decode_tps']} t/s", flush=True)
    power.stop()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
