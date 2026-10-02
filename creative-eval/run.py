#!/usr/bin/env python3
"""Creative test: two chapters of an isekai, as one conversation (chapter 1, then chapter 2).

  python run.py --url http://127.0.0.1:8000 --model glm53-flash-mtp --label glm53 --extra-body '{}'
Writes results/creative-eval/<label>/{ch1,ch2}.md, .reasoning.txt, meta.json
"""
import argparse, json, pathlib, re, sys, time
sys.path.insert(0, str(REPO / "longctx"))
from common import stream_chat

CH1 = """Write the opening of an isekai light novel. You choose everything: the premise, the protagonist, the world and the title.

Classic isekai tropes are welcome (dying or being summoned, reincarnation, a game-like system, status screens), but execute them well. Keep the death or transmigration brief and make it do work in the story, for example by explaining why the protagonist knows things they shouldn't, or why the world runs on game-like rules. Make me want to read chapter 3.

Start with the title on its own line, then write Chapter 1 (about 2,000 words)."""
CH2 = "Now write Chapter 2 (about 2,000 words). Keep the characters, rules and voice consistent with Chapter 1."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True); ap.add_argument("--extra-body", default="{}")
    ap.add_argument("--max-tokens", type=int, default=16384); ap.add_argument("--temperature", type=float, default=0.8)
    a = ap.parse_args()
    out = RESULTS / "creative-eval" / a.label
    out.mkdir(parents=True, exist_ok=True)
    extra = json.loads(a.extra_body); extra.update({"temperature": a.temperature, "top_p": 0.95})
    msgs, meta = [{"role": "user", "content": CH1}], {}
    for name, follow in (("ch1", CH2), ("ch2", None)):
        r = stream_chat(a.url, a.model, msgs, a.max_tokens, extra, timeout=3600)
        text = re.sub(r"<think>.*?</think>", "", r["content"], flags=re.S).strip()
        (out / f"{name}.md").write_text(text)
        (out / f"{name}.reasoning.txt").write_text(r.get("reasoning") or "")
        meta[name] = {k: r.get(k) for k in ("ttft_s", "total_s", "completion_tokens", "decode_tps")} | {"words": len(text.split())}
        print(name, meta[name], flush=True)
        msgs.append({"role": "assistant", "content": text})
        if follow:
            msgs.append({"role": "user", "content": follow})
    (out / "meta.json").write_text(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
