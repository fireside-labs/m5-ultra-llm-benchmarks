#!/usr/bin/env python3
"""Logging proxy between any coding harness and a local model server.

Point the harness at http://127.0.0.1:9000 (OpenAI-style /v1/chat/completions or
Messages-style /v1/messages); requests are forwarded unchanged to --upstream,
except that OpenAI streams get stream_options.include_usage so token counts come back.

One JSON line per request in ~/bench-results/agentic/<label>.jsonl:
  context size, tokens served from cache vs re-processed, TTFT, decode speed,
  and when the cache breaks, which message index changed since the previous request
  (the harness edited, pruned or compacted history).

  python cache_proxy.py --upstream http://127.0.0.1:8080 --label dsv4v-llama-pi
"""
import argparse, hashlib, json, pathlib, time

from aiohttp import ClientSession, ClientTimeout, web

HOP = {"host", "content-length", "transfer-encoding", "connection", "keep-alive", "accept-encoding"}


def msg_hashes(body):
    msgs = list(body.get("messages") or [])
    system = body.get("system")
    if system:
        msgs.insert(0, {"role": "system", "content": system})
    return [hashlib.sha1(json.dumps(m, sort_keys=True).encode()).hexdigest()[:12] for m in msgs]


class Proxy:
    def __init__(self, upstream, log_path):
        self.upstream = upstream.rstrip("/")
        self.log_path = log_path
        self.prev_hashes = []
        self.prev_prompt = 0
        self.n = 0
        self.session = None

    async def start(self, app):
        self.session = ClientSession(timeout=ClientTimeout(total=None))

    async def stop(self, app):
        await self.session.close()

    async def handle(self, request):
        raw = await request.read()
        body = None
        if request.content_type == "application/json" and raw:
            try:
                body = json.loads(raw)
            except ValueError:
                pass
        tracked = body is not None and request.path.endswith(("/chat/completions", "/messages"))
        if tracked and body.get("stream") and request.path.endswith("/chat/completions"):
            body.setdefault("stream_options", {})["include_usage"] = True
            raw = json.dumps(body).encode()

        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
        t0 = time.perf_counter()
        async with self.session.request(request.method, self.upstream + request.path_qs,
                                        data=raw, headers=headers) as up:
            resp = web.StreamResponse(status=up.status, headers={
                k: v for k, v in up.headers.items() if k.lower() not in HOP})
            await resp.prepare(request)
            t_first = None
            buf = b""
            usage, timings = {}, None
            async for chunk in up.content.iter_any():
                await resp.write(chunk)
                if not tracked:
                    continue
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    t_first, timings = self.scan(line, t_first, usage, timings)
            if tracked and buf:
                t_first, timings = self.scan(buf, t_first, usage, timings, whole=True)
            await resp.write_eof()
        t_end = time.perf_counter()
        if tracked:
            self.record(request.path, body, usage, timings, t0, t_first, t_end, up.status)
        return resp

    def scan(self, line, t_first, usage, timings, whole=False):
        line = line.strip()
        if line.startswith(b"data:"):
            line = line[5:].strip()
        elif not whole:
            return t_first, timings
        if not line or line == b"[DONE]":
            return t_first, timings
        try:
            ev = json.loads(line)
        except ValueError:
            return t_first, timings
        # OpenAI chunks / non-stream response
        for ch in ev.get("choices") or []:
            d = ch.get("delta") or ch.get("message") or {}
            if t_first is None and (d.get("content") or d.get("reasoning_content") or d.get("reasoning") or d.get("tool_calls")):
                t_first = time.perf_counter()
        if ev.get("usage"):
            u = ev["usage"]
            usage["prompt"] = u.get("prompt_tokens", usage.get("prompt"))
            usage["output"] = u.get("completion_tokens", usage.get("output"))
            cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens")
            if cached is not None:
                usage["cached"] = cached
            # Messages API: message_delta usage / non-stream response
            if "input_tokens" in u:
                usage["prompt"] = u["input_tokens"] + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
                usage["cached"] = u.get("cache_read_input_tokens", usage.get("cached"))
            if "output_tokens" in u:
                usage["output"] = u["output_tokens"]
        if ev.get("timings"):
            timings = ev["timings"]
        # Messages API stream events
        t = ev.get("type")
        if t == "message_start":
            u = (ev.get("message") or {}).get("usage") or {}
            usage["prompt"] = (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
            usage["cached"] = u.get("cache_read_input_tokens")
        elif t == "content_block_delta" and t_first is None:
            t_first = time.perf_counter()
        return t_first, timings

    def record(self, path, body, usage, timings, t0, t_first, t_end, status):
        self.n += 1
        hashes = msg_hashes(body)
        changed_at = next((i for i, (a, b) in enumerate(zip(self.prev_hashes, hashes)) if a != b), None)
        if changed_at is None and len(hashes) < len(self.prev_hashes):
            changed_at = len(hashes)
        prompt = usage.get("prompt") or (timings or {}).get("prompt_n")
        cached = usage.get("cached")
        if cached is None and timings:
            cached = timings.get("cache_n")
        processed = (timings or {}).get("prompt_n") or (prompt - cached if prompt and cached is not None else None)
        out = usage.get("output") or (timings or {}).get("predicted_n")
        gen_s = t_end - (t_first or t_end)
        row = {
            "i": self.n, "time": time.strftime("%H:%M:%S"), "path": path, "status": status,
            "messages": len(hashes), "prompt_tokens": prompt, "cached_tokens": cached,
            "processed_tokens": processed, "output_tokens": out,
            "ttft_s": round((t_first or t_end) - t0, 3), "total_s": round(t_end - t0, 3),
            "decode_tps": round((out - 1) / gen_s, 2) if out and out > 1 and gen_s > 0 else None,
            "history_changed_at": changed_at,
            "cache_break": bool(self.prev_prompt and processed and processed > 0.5 * self.prev_prompt),
            "server_timings": timings,
        }
        self.prev_hashes, self.prev_prompt = hashes, prompt or self.prev_prompt
        with self.log_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
        flag = " CACHE BREAK" if row["cache_break"] else ""
        edit = f" (history changed at msg {changed_at})" if changed_at is not None else ""
        print(f"#{self.n:>4} ctx={prompt or 0:>9,} cached={cached or 0:>9,} new={processed or 0:>8,} "
              f"ttft={row['ttft_s']:>7.2f}s decode={row['decode_tps'] or 0:>6.1f}t/s out={out or 0:>5}{flag}{edit}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", required=True, help="e.g. http://127.0.0.1:8080 (llama-server) or :8000 (oMLX)")
    ap.add_argument("--label", required=True)
    ap.add_argument("--port", type=int, default=9000)
    args = ap.parse_args()
    outdir = pathlib.Path.home() / "bench-results" / "agentic"
    outdir.mkdir(parents=True, exist_ok=True)
    log = outdir / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.label}.jsonl"
    proxy = Proxy(args.upstream, log)
    app = web.Application(client_max_size=1024 ** 3)
    app.on_startup.append(proxy.start)
    app.on_cleanup.append(proxy.stop)
    app.router.add_route("*", "/{tail:.*}", proxy.handle)
    print(f"proxy :{args.port} -> {args.upstream}, logging to {log}", flush=True)
    web.run_app(app, host="127.0.0.1", port=args.port, print=None)


if __name__ == "__main__":
    main()
