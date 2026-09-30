#!/usr/bin/env python3
"""Append-only coding agent: the ceiling for cached long-context agent work.

History is never edited, pruned or summarized, so every step should hit the prompt
cache and only the new tool output is processed. Talk to the model through
cache_proxy.py so the per-step log matches the real-harness runs.

A watchdog (watchdog.py) appends one fixed nudge as a new user message when the agent
repeats the same tool call 4 times in a row or makes no milestone commit for 40 steps.

Shell commands run under macOS sandbox-exec: writes are allowed only inside the
workspace, /tmp and the npm/node caches.

  python agent_loop.py --url http://127.0.0.1:9000 --label dsv4v-llama-ceiling --target 1000000
"""
import argparse, json, os, pathlib, subprocess, time

import requests

from watchdog import NUDGE, Watchdog

HERE = pathlib.Path(__file__).resolve().parent
MAX_TOOL_OUTPUT = 20000  # chars; truncated when appended, never edited afterwards

SANDBOX = """(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath "{ws}")
  (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/dev")
  (subpath "{home}/.npm") (subpath "{home}/.cache") (subpath "{home}/Library/Caches"))
; Secrets agents must never read: Keychain (GitHub CLI token etc.), HF token, SSH keys, gh config.
(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd")
  (global-name "com.apple.security.agent") (global-name "com.apple.security.authhost"))
(deny file-read* file-write* (subpath "{home}/Library/Keychains") (subpath "{home}/.ssh")
  (subpath "{home}/.config/gh") (literal "{home}/.cache/huggingface/token")
  (subpath "{home}/.cache/huggingface/stored_tokens"))
"""

TOOLS = [
    {"type": "function", "function": {
        "name": "run", "description": "Run a shell command in the project directory (timeout 300 s). Returns exit code and output.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a text file from the project.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file", "description": "Create or overwrite a text file in the project.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
]

SYSTEM = ("You are an autonomous software engineer working in a git repository. Use the tools to "
          "inspect, write and test code. Work continuously; never ask the user questions.")


class Workspace:
    def __init__(self, root):
        self.root = root
        profile = SANDBOX.format(ws=root, home=pathlib.Path.home())
        self.profile_path = root.parent / f"{root.name}.sb"
        self.profile_path.write_text(profile)

    def path(self, p):
        full = (self.root / p).resolve()
        if self.root not in full.parents and full != self.root:
            raise ValueError(f"path outside workspace: {p}")
        return full

    def run(self, command):
        try:
            r = subprocess.run(["sandbox-exec", "-f", str(self.profile_path), "/bin/zsh", "-lc", command],
                               cwd=self.root, capture_output=True, text=True, timeout=300)
            out = f"exit code {r.returncode}\n{r.stdout}{r.stderr}"
        except subprocess.TimeoutExpired as e:
            out = f"timed out after 300 s\n{e.stdout or ''}{e.stderr or ''}"
        return out

    def call(self, name, args):
        try:
            if name == "run":
                return self.run(args["command"])
            if name == "read_file":
                return self.path(args["path"]).read_text(errors="replace")
            if name == "write_file":
                p = self.path(args["path"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(args["content"])
                return f"wrote {len(args['content'])} chars to {args['path']}"
            return f"unknown tool {name}"
        except Exception as e:
            return f"error: {e.__class__.__name__}: {e}"


def truncate(s):
    return s if len(s) <= MAX_TOOL_OUTPUT else s[:MAX_TOOL_OUTPUT // 2] + "\n...[truncated]...\n" + s[-MAX_TOOL_OUTPUT // 2:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:9000", help="the cache_proxy address")
    ap.add_argument("--label", required=True)
    ap.add_argument("--model", default="local")
    ap.add_argument("--target", type=int, default=1_000_000, help="stop when the prompt reaches this many tokens")
    ap.add_argument("--max-steps", type=int, default=2000)
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--no-watchdog", action="store_true", help="never append stall nudges")
    args = ap.parse_args()

    runs = HERE / "runs"
    ws_root = (runs / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}").resolve()
    ws_root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=ws_root, check=True)
    ws = Workspace(ws_root)
    transcript = ws_root.parent / f"{ws_root.name}.transcript.jsonl"
    wd = None if args.no_watchdog else Watchdog(ws_root)

    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": (HERE / "TASK.md").read_text()}]
    for step in range(1, args.max_steps + 1):
        body = {"model": args.model, "messages": messages, "tools": TOOLS, "stream": True,
                "max_tokens": args.max_tokens, "temperature": args.temperature}
        content, reasoning, calls, usage = [], [], {}, {}
        for attempt in range(3):  # survive transient server errors instead of ending the run
            r = requests.post(f"{args.url}/v1/chat/completions", json=body, stream=True, timeout=None)
            if r.status_code < 500 or attempt == 2:
                break
            print(f"step {step}: HTTP {r.status_code}, retrying: {r.text[:200]}", flush=True)
            r.close()
            time.sleep(15)
        with r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith(b"data: ") or line == b"data: [DONE]":
                    continue
                ev = json.loads(line[6:])
                usage = ev.get("usage") or usage
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    content.append(d.get("content") or "")
                    reasoning.append(d.get("reasoning_content") or "")
                    for tc in d.get("tool_calls") or []:
                        c = calls.setdefault(tc["index"], {"id": "", "name": "", "args": ""})
                        c["id"] = tc.get("id") or c["id"]
                        fn = tc.get("function") or {}
                        c["name"] += fn.get("name") or ""
                        c["args"] += fn.get("arguments") or ""
        msg = {"role": "assistant", "content": "".join(content)}
        if calls:
            msg["tool_calls"] = [{"id": c["id"] or f"call_{step}_{i}", "type": "function",
                                  "function": {"name": c["name"], "arguments": c["args"]}}
                                 for i, c in sorted(calls.items())]
        messages.append(msg)
        results = []
        for tc in msg.get("tool_calls", []):
            try:
                a = json.loads(tc["function"]["arguments"] or "{}")
            except ValueError:
                a = None
                # Usually a reply cut off by max_tokens mid tool call. llama.cpp rejects invalid
                # JSON arguments when it re-renders history (HTTP 500), so store "{}" instead.
                # This happens before the message is ever sent back, so history stays append-only.
                tc["function"]["arguments"] = "{}"
            out = (ws.call(tc["function"]["name"], a) if isinstance(a, dict) else
                   "error: your tool call was cut off or its arguments were not valid JSON. "
                   "Retry with a smaller call (e.g. write large files in parts).")
            results.append({"role": "tool", "tool_call_id": tc["id"], "content": truncate(out)})
        messages.extend(results)
        if not calls:
            messages.append({"role": "user", "content": "Continue with the next milestone."})
        nudge = None
        if wd and calls:  # only after tool results, so user/assistant turns stay well-formed
            reason = wd.observe(step, [(tc["function"]["name"], tc["function"]["arguments"]) for tc in msg["tool_calls"]])
            if reason:
                nudge = {"reason": reason, "content": NUDGE}
                messages.append({"role": "user", "content": NUDGE})
        row = {"step": step, "usage": usage, "assistant": msg,
               "reasoning_chars": len("".join(reasoning)), "tool_results": results}
        if nudge:
            row["watchdog_nudge"] = nudge
        with transcript.open("a") as f:
            f.write(json.dumps(row) + "\n")
        prompt = usage.get("prompt_tokens") or 0
        print(f"step {step:>4} prompt={prompt:>9,} tools={[c['name'] for c in calls.values()]}", flush=True)
        if nudge:
            print(f"step {step:>4} watchdog nudge: {nudge['reason']}", flush=True)
        if prompt >= args.target:
            print(f"reached target {args.target:,} tokens")
            break


if __name__ == "__main__":
    main()
