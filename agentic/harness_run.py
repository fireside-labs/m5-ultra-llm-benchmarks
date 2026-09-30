#!/usr/bin/env python3
"""Run a real coding-agent harness (pi, omp, dsh) unattended against the cache proxy.

Creates an isolated config/home under harness-config/<harness>/<label>/, git-inits the
workspace, starts the harness headless with TASK.md as the first message, and keeps
continuing the SAME session with "Continue with the next milestone." whenever the
harness exits (or goes idle), until --max-hours elapse or the proxy log shows a prompt
of at least --context-window * --stop-fraction tokens. The harness runs under macOS
sandbox-exec (writes only to the workspace, temp dirs, its config dir and caches).
Harness stdout/stderr go to <workspace>.harness.log; state to <workspace>.harness-state.json.

  # start cache_proxy.py first (it logs to ~/bench-results/agentic/<ts>-<label>.jsonl), then:
  python harness_run.py --harness pi --workspace runs/qwen-pi --label qwen-pi \\
      --model Qwen3.6-35B-A3B --context-window 262144 --max-hours 10

Compaction is left at each harness's default unless --compaction off|<tokens> is given
(<tokens> = compact when the prompt exceeds that many tokens).
Re-running with the same --workspace resumes the stored session.
"""
import argparse, json, os, pathlib, shutil, signal, subprocess, sys, threading, time, uuid

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home()
CONTINUE_MSG = "Continue with the next milestone."
BREW_PATH = "/opt/homebrew/bin:/opt/homebrew/sbin"

SANDBOX = """(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath "{ws}")
  (subpath "{cfg}")
  (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/dev")
  (subpath "{home}/.npm") (subpath "{home}/.cache") (subpath "{home}/Library/Caches"){extra})
{netdeny}; Secrets agents must never read: Keychain (GitHub CLI token etc.), HF token, SSH keys, gh config.
(deny mach-lookup (global-name "com.apple.SecurityServer") (global-name "com.apple.securityd")
  (global-name "com.apple.security.agent") (global-name "com.apple.security.authhost"))
(deny file-read* file-write* (subpath "{home}/Library/Keychains") (subpath "{home}/.ssh")
  (subpath "{home}/.config/gh") (literal "{home}/.cache/huggingface/token")
  (subpath "{home}/.cache/huggingface/stored_tokens"))
"""
# Model servers the harness must never reach directly (it talks only to the proxy). omp, for
# example, auto-probes llama.cpp at 127.0.0.1:8080 and Ollama/LM Studio for model discovery.
PROTECTED_PORTS = (8080, 8000)


def sh_which(name, env):
    p = shutil.which(name, path=env["PATH"])
    if not p:
        sys.exit(f"error: `{name}` not found on PATH ({env['PATH']})")
    return p


# ----------------------------------------------------------------------------- harnesses

class Harness:
    name = ""
    extra_write_paths = []  # discovered writes outside the default allow list

    def __init__(self, a, cfg, ws):
        self.a, self.cfg, self.ws = a, cfg, ws
        self.session_id = None

    def env(self):
        env = dict(os.environ)
        env["PATH"] = f"{BREW_PATH}:{env.get('PATH', '/usr/bin:/bin')}"
        for k in [k for k in env if k.endswith("_API_KEY")]:
            env.pop(k)  # no real provider keys reach the harness
        env["BENCH_API_KEY"] = "dummy-key"
        return env

    def write_config(self):
        raise NotImplementedError

    def command(self, message, first):
        raise NotImplementedError

    def on_output_line(self, line):
        pass


class Pi(Harness):
    """@earendil-works/pi-coding-agent: models.json custom provider, --session-id for continuity."""
    name = "pi"

    def env(self):
        env = super().env()
        env["PI_CODING_AGENT_DIR"] = str(self.cfg / "agent")
        env["PI_CODING_AGENT_SESSION_DIR"] = str(self.cfg / "sessions")
        env["PI_OFFLINE"] = "1"
        env["PI_TELEMETRY"] = "0"
        return env

    def write_config(self):
        a = self.a
        agent = self.cfg / "agent"
        agent.mkdir(parents=True, exist_ok=True)
        (self.cfg / "sessions").mkdir(exist_ok=True)
        model = {"id": a.model, "name": a.model, "reasoning": True, "input": ["text"],
                 "contextWindow": a.context_window, "maxTokens": a.max_output_tokens,
                 "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}
        models = {"providers": {"bench": {"baseUrl": a.base_url, "api": "openai-completions",
                                          "apiKey": "$BENCH_API_KEY", "models": [model]}}}
        (agent / "models.json").write_text(json.dumps(models, indent=2))
        settings = {"defaultProvider": "bench", "defaultModel": a.model, "quietStartup": True}
        if a.compaction == "off":
            settings["compaction"] = {"enabled": False}
        elif a.compaction != "default":
            # pi compacts when context > contextWindow - reserveTokens (default reserve 16384)
            settings["compaction"] = {"enabled": True,
                                      "reserveTokens": max(0, a.context_window - int(a.compaction))}
        (agent / "settings.json").write_text(json.dumps(settings, indent=2))
        if not self.session_id:
            self.session_id = str(uuid.uuid4())

    def command(self, message, first):
        return [sh_which("pi", self.env()), "--mode", "json", "--print", "--provider", "bench",
                "--model", self.a.model, "--session-id", self.session_id, "--", message]


class Omp(Harness):
    """@oh-my-pi/pi-coding-agent (needs bun): isolated HOME, models.yml + config.yml, --continue."""
    name = "omp"

    def env(self):
        env = super().env()
        env["HOME"] = str(self.cfg / "home")
        env["PI_NO_TITLE"] = "1"  # title generation is an extra LLM side request
        bun_dirs = [str(HOME / ".bun/bin")]
        env["PATH"] = ":".join(bun_dirs + [env["PATH"]])
        return env

    def write_config(self):
        a = self.a
        agent = self.cfg / "home" / ".omp" / "agent"
        agent.mkdir(parents=True, exist_ok=True)
        models = (
            "providers:\n"
            "  bench:\n"
            f"    baseUrl: {a.base_url}\n"
            "    apiKey: BENCH_API_KEY\n"
            "    api: openai-completions\n"
            "    models:\n"
            f"      - id: {json.dumps(a.model)}\n"
            f"        name: {json.dumps(a.model)}\n"
            "        reasoning: true\n"
            "        input: [text]\n"
            f"        contextWindow: {a.context_window}\n"
            f"        maxTokens: {a.max_output_tokens}\n"
            "        cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0}\n")
        (agent / "models.yml").write_text(models)
        cfg = ["tools:", "  approvalMode: yolo", "modelRoles:", f"  default: bench/{a.model}",
               # no implicit local-server discovery (llama.cpp probes 127.0.0.1:8080 by default)
               "disabledProviders: [llama.cpp, ollama, lm-studio, apple]"]
        if a.compaction == "off":
            cfg += ["compaction:", "  enabled: false"]
        elif a.compaction != "default":
            cfg += ["compaction:", "  enabled: true", f"  thresholdTokens: {int(a.compaction)}"]
        (agent / "config.yml").write_text("\n".join(cfg) + "\n")

    def command(self, message, first):
        cmd = [sh_which("omp", self.env()), "--print", "--mode", "json", "--no-title", "--auto-approve",
               "--model", f"bench/{self.a.model}"]
        if not first:
            cmd.append("--continue")
        return cmd + ["--", message]


class Dsh(Harness):
    """@deepseek-ai/dsh headless profile: DSH_HOME/cordis.patch.yml, --session-id from the json stream."""
    name = "dsh"

    def env(self):
        env = super().env()
        env["DSH_HOME"] = str(self.cfg / "home")
        env["DSH_PERMISSION_MODE"] = "danger-full-access"  # approval: never; dsh's own sandbox off
        env["DSH_TELEMETRY_DISABLED"] = "1"
        return env

    def write_config(self):
        a = self.a
        home = self.cfg / "home"
        home.mkdir(parents=True, exist_ok=True)
        patch = [
            "- id: llm-pi-ai",
            "  config:",
            "    providers:",
            "      bench:",
            "        displayName: Bench",
            "        apiKeyEnv: BENCH_API_KEY",
            "        api: openai-completions",
            f"        baseURL: {a.base_url}",
            "        models:",
            f"          - id: {json.dumps(a.model)}",
            f"            name: {json.dumps(a.model)}",
            f"            contextWindow: {a.context_window}",
            f"            maxTokens: {a.max_output_tokens}",
            "- id: agent-default-model",
            "  config:",
            "    provider: bench",
            f"    model: {json.dumps(a.model)}",
            # first-prompt title generation is an extra LLM side request
            "- id: session-title-llm",
            "  disabled: true",
        ]
        if a.compaction == "off":
            patch += ["- id: compaction-basic", "  config:", "    auto: false"]
        elif a.compaction != "default":
            n, w, o = int(a.compaction), a.context_window, a.max_output_tokens
            # trigger = floor(min(W*thresholdRatio, W - O - headroomTokens))
            patch += ["- id: compaction-basic", "  config:",
                      f"    thresholdRatio: {min(1.0, n / w):.6f}",
                      f"    headroomTokens: {max(0, w - o - n)}",
                      f"    maxTokens: {o}"]
        (home / "cordis.patch.yml").write_text("\n".join(patch) + "\n")

    def command(self, message, first):
        cmd = [sh_which("dsh", self.env()), "--profile", "headless", "--json"]
        if not first:
            cmd += ["--session-id", self.session_id]
        return cmd + [message]

    def on_output_line(self, line):
        if self.session_id or not line.startswith("{"):
            return
        try:
            ev = json.loads(line)
        except ValueError:
            return
        if ev.get("type") == "session":
            sid = ev.get("sessionId") or ev.get("session_id") or ev.get("id")
            if isinstance(sid, str):
                self.session_id = sid


HARNESSES = {"pi": Pi, "omp": Omp, "dsh": Dsh}


# ----------------------------------------------------------------------------- proxy log

class ProxyLog:
    """Tails the cache_proxy JSON-lines log and tracks the largest prompt seen."""

    def __init__(self, explicit, label, since):
        self.explicit = pathlib.Path(explicit) if explicit else None
        self.label, self.since = label, since
        self.path, self.offset = None, 0
        self.max_prompt, self.last_prompt, self.requests, self.last_activity = 0, 0, 0, time.time()

    def _resolve(self):
        if self.explicit:
            return self.explicit if self.explicit.exists() else None
        cands = sorted((HOME / "bench-results" / "agentic").glob(f"*-{self.label}.jsonl"),
                       key=lambda p: p.stat().st_mtime)
        cands = [p for p in cands if p.stat().st_mtime >= self.since - 7 * 86400]
        return cands[-1] if cands else None

    def poll(self):
        if self.path is None:
            self.path = self._resolve()
            if self.path is None:
                return
        with self.path.open() as f:
            f.seek(self.offset)
            data = f.read()
        if not data:
            return
        lines = data.split("\n")
        tail = lines.pop()  # incomplete last line
        self.offset += len(data) - len(tail)
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            p = row.get("prompt_tokens") or 0
            self.requests += 1
            self.last_prompt = p
            self.max_prompt = max(self.max_prompt, p)
            self.last_activity = time.time()


# ----------------------------------------------------------------------------- runner

def kill_tree(proc, grace=15):
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(grace)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", choices=sorted(HARNESSES), required=True)
    ap.add_argument("--workspace", required=True, help="project dir (created and git-initialised if missing)")
    ap.add_argument("--label", required=True, help="run label; also the cache_proxy label used to find its log")
    ap.add_argument("--model", required=True, help="model id sent to the server")
    ap.add_argument("--context-window", type=int, required=True)
    ap.add_argument("--max-hours", type=float, required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:9000/v1", help="OpenAI-compatible base URL (the cache proxy)")
    ap.add_argument("--proxy-log", help="explicit proxy JSON-lines log (default: newest ~/bench-results/agentic/*-<proxy-label>.jsonl)")
    ap.add_argument("--proxy-label", help="cache_proxy --label, if different from --label")
    ap.add_argument("--stop-fraction", type=float, default=0.95)
    ap.add_argument("--max-output-tokens", type=int, default=32768, help="model maxTokens declared to the harness")
    ap.add_argument("--compaction", default="default",
                    help="'default' (harness default), 'off', or a token count at which to compact")
    ap.add_argument("--idle-minutes", type=float, default=90,
                    help="restart the harness (continuing the session) after this long with no output and no proxy request")
    ap.add_argument("--max-invocations", type=int, default=0, help="stop after N harness invocations (0 = unlimited; for tests)")
    ap.add_argument("--no-sandbox", action="store_true")
    ap.add_argument("--task", default=str(HERE / "TASK.md"))
    a = ap.parse_args()
    if a.compaction not in ("default", "off") and not a.compaction.isdigit():
        ap.error("--compaction must be default, off or an integer token count")

    ws = pathlib.Path(a.workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)
    if not (ws / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
        subprocess.run(["git", "config", "user.name", "Bench Agent"], cwd=ws, check=True)
        subprocess.run(["git", "config", "user.email", "bench@localhost"], cwd=ws, check=True)
    cfg = HERE / "harness-config" / a.harness / a.label
    cfg.mkdir(parents=True, exist_ok=True)
    state_path = ws.parent / f"{ws.name}.harness-state.json"
    log_path = ws.parent / f"{ws.name}.harness.log"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state and state.get("harness") != a.harness:
        sys.exit(f"error: {state_path} belongs to harness {state.get('harness')}")

    h = HARNESSES[a.harness](a, cfg, ws)
    h.session_id = state.get("session_id")
    h.write_config()
    env = h.env()

    profile = ws.parent / f"{ws.name}.sb"
    extra = "".join(f'\n  (subpath "{p}")' for p in h.extra_write_paths)
    from urllib.parse import urlparse
    base_port = urlparse(a.base_url).port
    netdeny = "".join(f'(deny network-outbound (remote tcp "*:{p}"))\n' for p in PROTECTED_PORTS if p != base_port)
    profile.write_text(SANDBOX.format(ws=ws, cfg=cfg, home=HOME, extra=extra, netdeny=netdeny))

    start = time.time()
    deadline = start + a.max_hours * 3600
    target = int(a.context_window * a.stop_fraction)
    plog = ProxyLog(a.proxy_log, a.proxy_label or a.label, start)
    invocations = state.get("invocations", 0)
    fails = 0
    reason = None
    logf = log_path.open("a", buffering=1)

    def say(msg):
        line = f"[harness_run {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        logf.write(line + "\n")

    say(f"harness={a.harness} ws={ws} cfg={cfg} model={a.model} ctx={a.context_window} target={target} "
        f"compaction={a.compaction} session={h.session_id}")
    while True:
        first = invocations == 0
        message = pathlib.Path(a.task).read_text() if first else CONTINUE_MSG
        cmd = h.command(message, first)
        if not a.no_sandbox:
            cmd = ["/usr/bin/sandbox-exec", "-f", str(profile)] + cmd
        invocations += 1
        shown = [c if len(c) < 80 else c[:60] + "...<%d chars>" % len(c) for c in cmd]
        say(f"invocation {invocations}: {' '.join(shown)}")
        t0 = time.time()
        proc = subprocess.Popen(cmd, cwd=ws, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, start_new_session=True)
        last_out = [time.time()]

        def pump():
            for raw in proc.stdout:
                line = raw.decode("utf-8", "replace")
                logf.write(line)
                last_out[0] = time.time()
                h.on_output_line(line.strip())

        th = threading.Thread(target=pump, daemon=True)
        th.start()
        while proc.poll() is None:
            time.sleep(2)
            plog.poll()
            if plog.max_prompt >= target:
                reason = f"prompt reached {plog.max_prompt:,} >= {target:,} tokens"
                break
            if time.time() >= deadline:
                reason = f"max hours ({a.max_hours}) elapsed"
                break
            idle = time.time() - max(last_out[0], plog.last_activity)
            if idle > a.idle_minutes * 60:
                say(f"idle for {idle / 60:.0f} min; restarting and continuing the session")
                break
        kill_tree(proc)
        th.join(5)
        plog.poll()
        dt = time.time() - t0
        say(f"invocation {invocations} ended rc={proc.returncode} after {dt:.0f}s; "
            f"proxy requests={plog.requests} last_prompt={plog.last_prompt:,} max_prompt={plog.max_prompt:,} "
            f"session={h.session_id}")
        state = {"harness": a.harness, "label": a.label, "session_id": h.session_id, "invocations": invocations,
                 "max_prompt": plog.max_prompt, "proxy_log": str(plog.path) if plog.path else None}
        state_path.write_text(json.dumps(state, indent=2))
        if plog.max_prompt >= target and not reason:
            reason = f"prompt reached {plog.max_prompt:,} >= {target:,} tokens"
        if reason:
            break
        if a.harness == "dsh" and not h.session_id:
            reason = "dsh did not report a session id; cannot continue"
            break
        fails = fails + 1 if (proc.returncode not in (0, None, -15) and dt < 60) else 0
        if fails >= 5:
            reason = "harness failed 5 times in a row"
            break
        if fails:
            time.sleep(min(300, 10 * 2 ** fails))
        if a.max_invocations and invocations >= a.max_invocations:
            reason = f"max invocations ({a.max_invocations}) reached"
            break
    say(f"stopping: {reason}")
    logf.close()


if __name__ == "__main__":
    main()
