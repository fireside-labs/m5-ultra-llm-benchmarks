#!/usr/bin/env python3
"""Replay a recorded agent session against an engine, request by request.

Rebuilds every request of an agent_loop run from its transcript (system + TASK.md,
then each step's assistant message, tool results, nudges and "continue" messages) and
sends them in order, so every engine sees identical prompts and identical context
growth. Tool execution is skipped; output is fixed (temperature 0, --max-tokens) and
forced to plain text (tool_choice none) so all engines stream it the same way.

  python replay.py --transcript runs/<stamp>-qwen-omlx-mtp-ceiling.transcript.jsonl \
      --url http://127.0.0.1:8000 --engine omlx --model qwen-flash-next --label qwen-omlx-replay
"""
import argparse, json, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "longctx"))
from common import stream_chat, system_info  # noqa: E402
from agent_loop import SYSTEM, TOOLS  # noqa: E402


def rebuild_requests(transcript, task_text):
    """Yield the message list of each recorded request, in order."""
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task_text}]
    for line in open(transcript):
        row = json.loads(line)
        if "assistant" not in row:
            continue
        yield list(messages)
        assistant = row["assistant"]
        for tc in assistant.get("tool_calls") or []:
            try:  # same sanitizing agent_loop now does; llama.cpp rejects invalid JSON arguments
                json.loads(tc["function"]["arguments"] or "{}")
            except ValueError:
                tc["function"]["arguments"] = "{}"
        messages.append(assistant)
        messages.extend(row.get("tool_results") or [])
        if not assistant.get("tool_calls"):
            messages.append({"role": "user", "content": "Continue with the next milestone."})
        if row.get("watchdog_nudge"):  # appended after the tool results, as agent_loop does
            messages.append({"role": "user", "content": row["watchdog_nudge"]["content"]})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--task", default=str(HERE / "TASK.md"))
    ap.add_argument("--url", required=True)
    ap.add_argument("--engine", required=True, choices=["llama.cpp", "omlx"])
    ap.add_argument("--model", default="local")
    ap.add_argument("--label", required=True)
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--every", type=int, default=1, help="send every Nth request (context still grows fully)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    out = pathlib.Path.home() / "bench-results/replay" / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    extra = {"tools": TOOLS, "tool_choice": "none"}
    if args.engine == "llama.cpp":
        extra["ignore_eos"] = True
    with out.open("w") as f:
        f.write(json.dumps({"type": "meta", "args": vars(args), "system": system_info(args.engine)}) + "\n")
        requests = list(rebuild_requests(args.transcript, pathlib.Path(args.task).read_text()))
        sent = 0
        for i, msgs in enumerate(requests, 1):
            if (i - 1) % args.every:
                continue
            r = stream_chat(args.url, args.model, msgs, args.max_tokens, extra)
            r.pop("content"), r.pop("reasoning")
            r.update(type="replay", i=i, n_messages=len(msgs), label=args.label)
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(f"#{i:>4} ctx={r['prompt_tokens'] or 0:>8,} cached={r['cached_tokens'] or 0:>8,} "
                  f"ttft={r['ttft_s']:>6.2f}s decode={r['decode_tps'] or 0:>6.1f} t/s out={r['completion_tokens']}", flush=True)
            sent += 1
            if args.limit and sent >= args.limit:
                break
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
