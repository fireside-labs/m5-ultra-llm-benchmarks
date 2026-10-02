#!/usr/bin/env python3
"""Tiny fake OpenAI-compatible server for testing run_eval.py without a model (CPU only).

  python selftest/fake_server.py --port 18765 --log /tmp/requests.jsonl

Streams (or returns) a canned reply: a separate reasoning_content chunk, then content that starts
with an inline <think>...</think> block followed by tagged answer lines. Every request body is
appended to --log, so a test can check that prior assistant turns were resent WITHOUT think blocks
or reasoning, and that --extra-body keys arrived. Never run it on the port of a real model server.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = "SECRET-REASONING-MUST-NOT-BE-RESENT"


def reply_for(messages):
    n_user = sum(1 for m in messages if m["role"] == "user")
    if n_user == 1:
        ans = ("## Recommendation\n\nOption one from the brief.\n\n## Key reasons\n\n- a\n\n## Risks\n\n- b\n\n"
               "## Confidence\n\n70%\n\nPOSITION: (fake) first option\nCONFIDENCE: 70%")
    else:
        ans = f"Fake reply to follow-up {n_user - 1}.\n\nRESPONSE: DISAGREE\nPOSITION: (fake) first option\nCONFIDENCE: 70%"
    return f"<think>inline {SECRET}</think>\n" + ans


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with open(self.server.log, "a") as f:
            f.write(json.dumps(body) + "\n")
        content = reply_for(body["messages"])
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()

            def send(obj):
                self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            send({"choices": [{"delta": {"reasoning_content": f"separate {SECRET}"}}]})
            for i in range(0, len(content), 40):
                send({"choices": [{"delta": {"content": content[i:i + 40]}}]})
            send({"choices": [{"delta": {}, "finish_reason": "stop"}]})
            send({"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 60}})
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            out = json.dumps({"choices": [{"message": {"content": content, "reasoning_content": f"separate {SECRET}"},
                                           "finish_reason": "stop"}],
                              "usage": {"prompt_tokens": 100, "completion_tokens": 60}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18765)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    assert a.port != 8000, "port 8000 is reserved for the real model server"
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    srv.log = a.log
    srv.serve_forever()


if __name__ == "__main__":
    main()
