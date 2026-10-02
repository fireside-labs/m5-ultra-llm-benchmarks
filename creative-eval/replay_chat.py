#!/usr/bin/env python3
"""Replay the user turns from an exported oMLX chat against a model, generating fresh replies.
  python replay_chat.py --chats omlx-chats.json --source-model model-b --url ... --model dsv4-0731 --label dsv4max --extra-body '{...}'
"""
import argparse, json, os, pathlib, re, sys
REPO = pathlib.Path(__file__).resolve().parent.parent
RESULTS = pathlib.Path(os.environ.get("BENCH_RESULTS", REPO / "results")).expanduser()
sys.path.insert(0, str(REPO / "longctx"))
from common import stream_chat
ap = argparse.ArgumentParser()
for a in ("--chats", "--source-model", "--url", "--model", "--label"): ap.add_argument(a, required=True)
ap.add_argument("--extra-body", default="{}"); ap.add_argument("--max-tokens", type=int, default=16384)
a = ap.parse_args()
chats = json.load(open(pathlib.Path(a.chats).expanduser()))
chat = max((c for c in chats if any(m.get("model") == a.source_model for m in c["messages"] if m.get("role") == "assistant")),
           key=lambda c: len(c["messages"]))
users = [m["content"] if isinstance(m["content"], str) else str(m["content"]) for m in chat["messages"] if m["role"] == "user"]
extra = json.loads(a.extra_body); extra.setdefault("temperature", 0.6)
msgs, log = [], []
for i, u in enumerate(users):
    msgs.append({"role": "user", "content": u})
    r = stream_chat(a.url, a.model, msgs, a.max_tokens, extra, timeout=3600)
    text = re.sub(r"<think>.*?</think>", "", r["content"], flags=re.S).strip()
    msgs.append({"role": "assistant", "content": text})
    log.append({"turn": i, "user": u, "assistant": text, "reasoning_chars": len(r.get("reasoning") or ""),
                "completion_tokens": r.get("completion_tokens"), "total_s": r.get("total_s")})
    print(f"turn {i}: {len(text.split())} words, {log[-1]['reasoning_chars']} reasoning chars, {r.get('total_s'):.0f}s", flush=True)
out = RESULTS / "live-replay" / f"{a.label}.json"
out.write_text(json.dumps(log, indent=2)); print("wrote", out)
