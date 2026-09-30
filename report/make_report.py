#!/usr/bin/env python3
"""Morning report for the overnight agentic long-context benchmark (Deepdelve task).

Usage:  python report/make_report.py [--no-referee]      (from the repo root)

Reads (never writes) the run data:
  results/agentic/overnight-events.log                  run start/end events
  results/agentic/<stamp>-<label>.jsonl                 cache_proxy rows, one per model request
  results/agentic/overnight-logs/*.server.log           oMLX per-request TTFT/decode (proxy numbers are wrong
                                                         for oMLX tool calls: it buffers tool-call output)
  agentic/runs/<stamp>-<label>/                         agent git repo (read with git only; no locks taken)
  agentic/runs/<...>.transcript.jsonl                   agent_loop steps, watchdog nudges
  agentic/runs/<...>.referee.jsonl                      referee results per milestone commit
  agentic/runs/<...>.harness.log                        pi harness event stream

agentic/runs/ only exists where the benchmark was actually run. Without it, the published snapshot in
results/agentic/runs/ is used instead: per run a directory with git-log.txt / git-grep.txt (the output of the two
git commands below), the referee JSONL and a filtered harness log. Transcripts are not published, so a report
regenerated from the snapshot leaves out the transcript-derived notes (watchdog nudges, repeated-reply loops,
tool counts for the agent_loop runs). Set BENCH_AGENTIC_DATA / BENCH_RUNS_DIR to point at other locations.

If a FINISHED run has no (or an empty) referee file, runs `referee.py <workspace>` once (it reads the repo via
git archive and writes <workspace>.referee.jsonl). Never for a run still in progress; --no-referee disables it.
Never contacts a model server. Writes PNG charts (2x) and REPORT.md next to this script. Safe to re-run at any
time; a run that is still going is marked "in progress" and reported as of its latest proxy row.
"""
import argparse
import bisect
import datetime as dt
import glob
import json
import os
import re
import statistics
import subprocess
import sys
import textwrap
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.environ.get("BENCH_AGENTIC_DATA", os.path.join(REPO, "results/agentic"))
LOGS = os.path.join(DATA, "overnight-logs")
BENCH = os.path.join(REPO, "agentic")
RUNS_DIR = os.environ.get("BENCH_RUNS_DIR", os.path.join(BENCH, "runs"))
SNAPSHOT_DIR = os.path.join(DATA, "runs")  # published per-run snapshot, used when RUNS_DIR has no match
PY = sys.executable
OUT = os.path.dirname(os.path.abspath(__file__))
DPI = 200  # 2x

# ---------------------------------------------------------------- palette ---
# Same tokens as charts/make_charts.py (dataviz reference palette, light).
# Slots 1-3 validated all-pairs (CVD dE >= 9.2); aqua is < 3:1 on the surface, so every chart direct-labels
# its lines and REPORT.md carries the numbers as tables.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
CRITICAL = "#d03b3b"  # status colour: regressions only, always with an x marker + label
LW = 1.5
MS = 6.5
RING = 1.5

plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.75, "axes.labelcolor": INK2, "axes.labelsize": 10,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.axisbelow": True,
    "grid.color": GRID, "grid.linewidth": 0.75, "grid.linestyle": "-",
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
    "xtick.major.size": 0, "ytick.major.size": 0, "xtick.minor.size": 0, "ytick.minor.size": 0,
    "legend.frameon": False, "legend.fontsize": 9, "legend.labelcolor": INK2,
})

HW = "Apple M5 Ultra Mac Studio, 256 GB unified memory · llama.cpp (Metal) · oMLX 0.7.0rc1"
TASK = ("Task: Deepdelve (30-milestone TypeScript roguelike, TASK.md), empty repo, append-only history for the "
        "ceiling agent (agent_loop.py).")

# colour follows the engine (llama.cpp blue, oMLX orange, as in the depth charts); pi gets slot 3
RUNS = [
    dict(label="ds0731-omlxk-dspark-ceiling", family="DeepSeek", model="DeepSeek V4 Flash 0731",
         engine="oMLX kernel build + DSpark", agent="ceiling", short="DS oMLX", color=ORANGE),
    dict(label="dsv4v-llama-dspark-ceiling", family="DeepSeek", model="DeepSeek V4 Flash Vision-Exp",
         engine="llama.cpp + DSpark", agent="ceiling", short="DS llama.cpp", color=BLUE),
    dict(label="qwen-omlx-mtp-ceiling", family="Qwen", model="Qwen3.8-Flash-Next",
         engine="oMLX + MTP", agent="ceiling", short="Qwen oMLX+MTP", color=ORANGE),
    dict(label="qwen-llama-ceiling", family="Qwen", model="Qwen3.8-Flash-Next",
         engine="llama.cpp (no MTP)", agent="ceiling", short="Qwen llama.cpp", color=BLUE),
    dict(label="qwen-llama-pi", family="Qwen", model="Qwen3.8-Flash-Next",
         engine="llama.cpp (no MTP)", agent="pi", short="Qwen llama.cpp pi", color=AQUA),
]
BANDS = [(0, 50e3, "0-50k"), (50e3, 100e3, "50-100k"), (100e3, 200e3, "100-200k"),
         (200e3, 300e3, "200-300k"), (300e3, 1e12, "300k+")]
TEST_FILE_RE = re.compile(r"(^|/)[^/]+\.(test|spec)\.[cm]?[jt]sx?$")
MILESTONE_RE = re.compile(r"^\s*milestone\s+(\d+)\s*:", re.I)
OMLX_RE = re.compile(r"^(\S+ \S+) - omlx\.server - INFO - Chat completion: model=[^,]+, (\d+) tokens in ([\d.]+)s "
                     r"\(([\d.]+) tok/s\), prompt: (\d+),.*?stream_model_ttft=([\d.]+)s")
MTP_RE = re.compile(r"MTP\[\d+\] .*?accept=(\d+)/(\d+)")


# ------------------------------------------------------------------- utils ---
def read_jsonl(path):
    rows = []
    if path and os.path.exists(path):
        with open(path, errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass  # a partially written last line of a live file
    return rows


def stamp_of(path):
    m = re.match(r"(\d{8}-\d{6})-", os.path.basename(path))
    return dt.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S") if m else None


def med(v):
    v = [x for x in v if x is not None]
    return statistics.median(v) if v else None


def pct(v, q):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    f = int(k)
    return v[f] + (v[min(f + 1, len(v) - 1)] - v[f]) * (k - f)


def git(repo, *args):
    if not os.path.isdir(os.path.join(repo, ".git")):
        # published snapshot: git-log.txt / git-grep.txt hold the output of the two commands used below
        snap = os.path.join(repo, "git-grep.txt" if args[0] == "grep" else "git-log.txt")
        return open(snap, errors="replace").read() if os.path.exists(snap) else ""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, env=env)
    return r.stdout.decode(errors="replace") if r.returncode == 0 else ""


def rolling_median(xs, ys, win):
    out = []
    for i in range(len(ys)):
        lo, hi = max(0, i - win // 2), min(len(ys), i + win // 2 + 1)
        out.append(statistics.median(ys[lo:hi]))
    return xs, out


def fmt(v, spec=",.0f", none="–"):
    return none if v is None else format(v, spec)


# ------------------------------------------------------------------ events ---
def read_events():
    """label -> list of (kind, text) in file order, for real (non-smoke) runs."""
    ev = {}
    path = os.path.join(DATA, "overnight-events.log")
    if not os.path.exists(path):
        return ev
    for line in open(path):
        m = re.match(r"(\d\d:\d\d:\d\d) (START|END|ERROR) ([\w.-]+?):(.*)$", line.strip())
        if m and not m.group(3).endswith("-smoke"):
            ev.setdefault(m.group(3), []).append((m.group(2), m.group(1), m.group(4).strip()))
    return ev


# ---------------------------------------------------------------- loading ---
def find_workspace(label, t_proxy):
    for base in (RUNS_DIR, SNAPSHOT_DIR):
        cands = [d for d in glob.glob(os.path.join(base, f"*-{label}")) if os.path.isdir(d)
                 and stamp_of(d) and stamp_of(d) >= t_proxy - dt.timedelta(seconds=60)]
        if cands:
            return min(cands, key=stamp_of)
    return None


def find_server_log(label, t_proxy):
    cands = [p for p in glob.glob(os.path.join(LOGS, f"*-{label}.server.log")) if stamp_of(p) <= t_proxy]
    return max(cands, key=stamp_of) if cands else None


def parse_omlx(path):
    reqs, acc = [], []
    if not path:
        return reqs, acc
    for line in open(path, errors="replace"):
        m = OMLX_RE.match(line)
        if m and m.group(6):  # the warm-up request is non-streaming (no ttft field)
            reqs.append(dict(out=int(m.group(2)), total=float(m.group(3)), tps=float(m.group(4)),
                             prompt=int(m.group(5)), ttft=float(m.group(6))))
        m = MTP_RE.search(line)
        if m:
            acc.append((int(m.group(1)), int(m.group(2))))
    return reqs, acc


def load_attempt(spec, path, attempt, n_attempts, events):
    t_proxy = stamp_of(path)
    rows = read_jsonl(path)
    run = dict(spec)
    run.update(proxy=path, attempt=attempt, n_attempts=n_attempts, t_proxy=t_proxy)
    run["name"] = spec["short"] + (f" (attempt {attempt})" if n_attempts > 1 and attempt < n_attempts else "")
    # absolute times; the proxy logs HH:MM:SS at request end, so roll the date over midnight
    day, prev = t_proxy.date(), None
    for r in rows:
        t = dt.datetime.combine(day, dt.time.fromisoformat(r["time"]))
        if prev and t < prev - dt.timedelta(hours=1):
            day += dt.timedelta(days=1)
            t += dt.timedelta(days=1)
        prev = t
        r["t_end"] = t
        r["t_start"] = t - dt.timedelta(seconds=r.get("total_s") or 0)
    run["all_rows"] = rows
    ok = [r for r in rows if r.get("status") == 200 and r.get("prompt_tokens")]
    run["rows"] = ok
    run["errors"] = [r for r in rows if r.get("status") != 200]
    run["engine_kind"] = "omlx" if "omlx" in spec["label"] else "llama"
    run["ws"] = find_workspace(spec["label"], t_proxy)
    run["server_log"] = find_server_log(spec["label"], t_proxy)

    # per-request TTFT / decode / spec-decode acceptance
    if run["engine_kind"] == "omlx":
        sreqs, acc = parse_omlx(run["server_log"])
        j = 0
        for r in ok:
            k = j
            while k < len(sreqs) and sreqs[k]["prompt"] != r["prompt_tokens"]:
                k += 1
            if k < len(sreqs):
                s = sreqs[k]
                r["ttft"], r["decode"] = s["ttft"], (s["tps"] if s["out"] > 1 else None)
                j = k + 1
            else:
                r["ttft"] = r["decode"] = None
        run["matched"] = sum(r.get("ttft") is not None for r in ok)
        a, b = sum(x for x, _ in acc[1:]), sum(y for _, y in acc[1:])  # [0] is the warm-up
        run["spec_accept"] = a / b if b else None
    else:
        for r in ok:
            t = r.get("server_timings") or {}
            r["ttft"] = r.get("ttft_s")
            r["decode"] = t.get("predicted_per_second") or r.get("decode_tps")
        run["matched"] = len(ok)
        dn = sum((r.get("server_timings") or {}).get("draft_n") or 0 for r in ok)
        da = sum((r.get("server_timings") or {}).get("draft_n_accepted") or 0 for r in ok)
        run["spec_accept"] = da / dn if dn else None

    # status: running if this is the label's newest attempt and its last event is START
    ev = events.get(spec["label"], [])
    newest = attempt == n_attempts
    run["running"] = bool(newest and ev and ev[-1][0] == "START")
    run["end_event"] = None
    if not run["running"]:
        # the END/ERROR that follows this attempt's START (attempt k = k-th START)
        starts = [i for i, e in enumerate(ev) if e[0] == "START"]
        if len(starts) >= attempt:
            nxt = [e for e in ev[starts[attempt - 1] + 1:] if e[0] != "START"][:1]
            run["end_event"] = nxt[0][2] if nxt else None

    # time base
    if ok:
        run["t0"] = min(r["t_start"] for r in rows)
        run["t1"] = max(r["t_end"] for r in rows)
    else:
        run["t0"] = run["t1"] = t_proxy
    for r in ok:
        r["h"] = (r["t_end"] - run["t0"]).total_seconds() / 3600
    starts = [r["t_start"] for r in ok]
    for i, r in enumerate(ok):
        r["step_s"] = (starts[i + 1] - starts[i]).total_seconds() if i + 1 < len(ok) else None
    run["hours"] = (run["t1"] - run["t0"]).total_seconds() / 3600

    ws = run["ws"]
    run["transcript"] = read_jsonl(ws + ".transcript.jsonl") if ws else []
    run["referee_path"] = ws + ".referee.jsonl" if ws else None
    run["harness_log"] = ws + ".harness.log" if ws and os.path.exists(ws + ".harness.log") else None
    run["watch_ws"] = None
    if run["server_log"]:
        ro = run["server_log"].replace(".server.log", ".referee.out")
        if os.path.exists(ro):
            m = re.search(r"\] workspace (\S+);", open(ro, errors="replace").read())
            run["watch_ws"] = m.group(1) if m else None
    return run


def ensure_referee(run, allow):
    p = run["referee_path"]
    if not allow or run["running"] or not run["ws"] or not p:
        return
    if not os.path.isdir(os.path.join(run["ws"], ".git")):
        return  # published snapshot, not a live workspace
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return
    if not git(run["ws"], "log", "--format=%s").strip():
        return
    print(f"running referee.py once on {run['ws']} (no referee output yet)", flush=True)
    subprocess.run([PY, os.path.join(BENCH, "referee.py"), run["ws"]], timeout=7200)


def ctx_at(run, t):
    """Prompt size of the last request that finished at or before time t."""
    ends = [r["t_end"] for r in run["rows"]]
    i = bisect.bisect_right(ends, t) - 1
    return run["rows"][i]["prompt_tokens"] if i >= 0 else (run["rows"][0]["prompt_tokens"] if run["rows"] else 0)


def load_quality(run):
    ref = read_jsonl(run["referee_path"]) if run["referee_path"] else []
    ms = [r for r in ref if r.get("type") == "milestone"]
    run["rewrites"] = [r for r in ref if r.get("type") == "history_rewrite"]
    for r in ms:
        r["t"] = dt.datetime.fromisoformat(r["committed_at"])
        r["h"] = (r["t"] - run["t0"]).total_seconds() / 3600
        r["ctx"] = ctx_at(run, r["t"])
        h = r.get("hidden") or {}
        r["rate"] = h["passed"] / h["total"] if h.get("total") else None
    run["ref"] = ms

    # git: every commit on HEAD with its changed files (read-only; GIT_OPTIONAL_LOCKS=0)
    commits = []
    if run["ws"]:
        out = git(run["ws"], "log", "--reverse", "--format=\x1e%H\x1f%ct\x1f%s", "--numstat")
        for block in out.split("\x1e")[1:]:
            head, *files = block.strip("\n").split("\n")
            sha, ct, subj = head.split("\x1f", 2)
            fl = []
            for f in files:
                p = f.split("\t")
                if len(p) == 3:
                    fl.append((p[2], int(p[0]) if p[0].isdigit() else 0, int(p[1]) if p[1].isdigit() else 0))
            m = MILESTONE_RE.match(subj)
            commits.append(dict(sha=sha, t=dt.datetime.fromtimestamp(int(ct)), subject=subj, files=fl,
                                milestone=int(m.group(1)) if m else None))
    run["commits"] = commits
    mc = [c for c in commits if c["milestone"] is not None]
    run["mcommits"] = mc
    seen, top, back, dup, testonly = set(), 0, 0, 0, 0
    first_top = None
    prev = None
    for c in mc:
        n = c["milestone"]
        if prev is not None and n < prev:
            back += 1
        if n in seen:
            dup += 1
        seen.add(n)
        if n > top:
            top, first_top = n, c["t"]
        code = [f for f in c["files"] if not f[0].endswith(("package-lock.json",))]
        if code and all(TEST_FILE_RE.search(f[0]) for f in code):
            testonly += 1
        prev = n
    run.update(top_milestone=top, t_top=first_top, back_jumps=back, dup_commits=dup, test_only=testonly,
               distinct_ms=len(seen))
    src_commits = [c for c in commits if any(f[0].startswith("src/") for f in c["files"])]
    run["last_src_commit"] = src_commits[-1] if src_commits else None
    after = [c for c in mc if first_top and c["t"] > first_top]
    run["after_top"] = (len(after), sum(1 for c in after if c["files"] and all(TEST_FILE_RE.search(f[0])
                                                                               for f in c["files"])))
    # final tree size
    loc = Counter()
    if run["ws"] and commits:
        for line in git(run["ws"], "grep", "-I", "-c", "", "HEAD", "--", ".", ":!package-lock.json").splitlines():
            m = re.match(r"HEAD:(.*):(\d+)$", line)
            if not m:
                continue
            f, n = m.group(1), int(m.group(2))
            if TEST_FILE_RE.search(f):
                loc["test"] += n
                loc["test_files"] += 1
            elif f.startswith("src/") and f.endswith((".ts", ".tsx", ".js")):
                loc["src"] += n
                loc["src_files"] += 1
    run["loc"] = loc


def load_agent(run):
    tr = run["transcript"]
    run["nudges"] = [(r["step"], r["usage"].get("prompt_tokens"), r["watchdog_nudge"]["reason"])
                     for r in tr if r.get("watchdog_nudge")]
    # longest-running repeated opening sentence (stuck template loops)
    lp = None
    if tr:
        norm = [re.sub(r"`[^`]*`", "`…`", (r["assistant"].get("content") or "").strip())[:70] for r in tr]
        c = Counter(n for n in norm if n)
        if c:
            text, n = c.most_common(1)[0]
            if n >= 50 and n >= 0.2 * len(tr):
                idx = [i for i, x in enumerate(norm) if x == text]
                first = tr[idx[0]]
                lp = dict(text=text, n=n, first_step=first["step"], first_ctx=first["usage"].get("prompt_tokens"),
                          last_step=tr[idx[-1]]["step"], share=n / len(tr))
                # the sentence's first backticked topic (e.g. `shop`): was it ever acted on inside the loop?
                raw = [(tr[i]["assistant"].get("content") or "") for i in idx]
                topics = Counter(m.group(1) for c in raw for m in [re.search(r"`([^`]+)`", c)] if m)
                if topics:
                    topic, k = topics.most_common(1)[0]
                    if k >= 0.9 * n:
                        acted = sum(1 for i in idx for tc in tr[i]["assistant"].get("tool_calls", [])
                                    if f"{topic}.test" in tc["function"]["arguments"])
                        lp.update(topic=topic, topic_acted=acted)
                # milestone numbers the loop's commits cycle through (first-appearance order)
                t_loop = next((r["t_end"] for r in run["rows"] if r["prompt_tokens"] >= (lp["first_ctx"] or 0)), None)
                seq = [c["milestone"] for c in run.get("mcommits", [])][-60:]
                cyc = []
                for per in range(1, len(seq) // 2 + 1):
                    if all(seq[i] == seq[i + per] for i in range(len(seq) - per)):
                        cyc = seq[-per:]
                        break
                lp["cycle"] = cyc
                lp["t"] = t_loop
                rates = {round(x["rate"], 4) for x in run.get("ref", []) if t_loop and x["t"] >= t_loop and x["rate"]}
                lp["rates"] = rates
    run["loop"] = lp
    if tr:
        run["tools"] = Counter(tc["function"]["name"] for r in tr for tc in r["assistant"].get("tool_calls", []))
    run["truncated"] = sum(1 for r in run["rows"] if (r.get("output_tokens") or 0) >= 8192)
    # pi harness: invocations and compaction events
    run["invocations"] = run["compactions"] = None
    run.setdefault("tools", Counter())
    if run["harness_log"]:
        inv = comp = 0
        with open(run["harness_log"], errors="replace") as fh:
            for line in fh:
                if line.startswith("[harness_run") and "] invocation " in line and ": " in line and "ended" not in line:
                    inv += 1
                if '"type":"' in line and re.search(r'"type":"[a-z_]*compact', line):
                    comp += 1
                if '"type":"tool_execution_start"' in line:
                    m = re.search(r'"toolName":"(\w+)"', line)
                    if m:
                        run["tools"][m.group(1)] += 1
        run["invocations"], run["compactions"] = inv, comp


# ----------------------------------------------------------------- metrics ---
def metrics(run):
    ok = run["rows"]
    m = dict(requests=len(run["all_rows"]), errors=len(run["errors"]))
    if not ok:
        return m
    hrs = max(run["hours"], 1e-6)
    m["final_ctx"] = ok[-1]["prompt_tokens"]
    m["hours"] = run["hours"]
    m["breaks"] = sum(bool(r.get("cache_break")) for r in ok)
    m["hist_changes"] = sum(r.get("history_changed_at") is not None for r in ok)
    steps = [r["step_s"] for r in ok if r["step_s"] is not None]
    m["step_med"], m["step_p90"] = med(steps), pct(steps, 0.9)
    m["llm_med"] = med([r["total_s"] for r in ok])
    m["steps_h"] = len(ok) / hrs
    m["out_h"] = sum(r.get("output_tokens") or 0 for r in ok) / hrs
    m["ctx_h"] = (ok[-1]["prompt_tokens"] - ok[0]["prompt_tokens"]) / hrs
    m["out_med"] = med([r.get("output_tokens") for r in ok])
    m["grow_med"] = med([b["prompt_tokens"] - a["prompt_tokens"] for a, b in zip(ok, ok[1:])])
    cached = sum(r.get("cached_tokens") or 0 for r in ok[1:])
    prompt = sum(r["prompt_tokens"] for r in ok[1:])
    m["cache_hit"] = cached / prompt if prompt else None
    m["proc_med"] = med([r.get("processed_tokens") for r in ok[1:]])
    m["bands"] = {}
    for lo, hi, name in BANDS:
        sel = [r for r in ok if lo <= r["prompt_tokens"] < hi]
        if sel:
            m["bands"][name] = (med([r["ttft"] for r in sel]), med([r["decode"] for r in sel]), len(sel))
    m["nudges"] = len(run["nudges"])
    ms = run["ref"]
    m["ms_commits"] = len(run["mcommits"])
    m["ms_h"] = len(run["mcommits"]) / hrs
    m["distinct_h"] = run["distinct_ms"] / hrs
    m["top"] = run["top_milestone"]
    m["t_top_h"] = (run["t_top"] - run["t0"]).total_seconds() / 3600 if run["t_top"] else None
    if ms:
        last = ms[-1]
        m["hidden_last"] = (last["hidden"].get("passed"), last["hidden"].get("total"))
        m["agent_last"] = (last["agent_tests"].get("passed"), last["agent_tests"].get("total"))
        regs = {}
        for r in ms:
            for t in r["issues"]["regressions"]:
                regs.setdefault(t, dict(first=r, n=0))
                regs[t]["n"] += 1
        last_fail = set(t for t, v in last["hidden"].get("results", {}).items() if v != "pass")
        m["regressions"] = [dict(test=t, n=v["n"], h=v["first"]["h"], ctx=v["first"]["ctx"],
                                 subject=v["first"]["subject"], still=t in last_fail) for t, v in regs.items()]
        m["reg_commits"] = sum(bool(r["issues"]["regressions"]) for r in ms)
        m["tcd"] = [(r["subject"], r["issues"]["test_count_decrease"], r["ctx"]) for r in ms
                    if r["issues"]["test_count_decrease"]]
        m["skips"] = sum(len(r["issues"]["new_skip_markers"]) for r in ms)
        m["deleted"] = sum(len(r["issues"]["deleted_test_files"]) for r in ms)
        m["build_fail"] = sum(bool(r["issues"]["build_failed"]) for r in ms)
        m["agent_fail"] = sum(bool(r["issues"]["agent_tests_failed"]) for r in ms)
        m["rewrites"] = len(run["rewrites"]) + sum(bool(r["issues"]["history_rewrite"]) for r in ms
                                                    if not run["rewrites"])
        m["referee_n"] = len(ms)
        m["rate_at"] = {}
        for hh in (0.5, 1, 2, 3):
            if hh <= run["hours"] + 0.05:
                sel = [r for r in ms if r["h"] <= hh and r["rate"] is not None]
                m["rate_at"][hh] = sel[-1]["rate"] if sel else None
        m["last_failing"] = sorted(last_fail)
    return m


# ----------------------------------------------------------------- layout ---
def wrap(text, width):
    return "\n".join(textwrap.fill(p, width) for p in text.split("\n"))


def frame(fig, title, subtitle, foot, legend_rows=0, ax_titles=False, left=0.95, right=0.3, wspace=0.3,
          hspace=None, xlabel_band=0.62):
    """Fixed-inch header and footer, as in make_charts.py."""
    W, H = fig.get_size_inches()
    title = wrap(title, int(W * 9.6))
    subtitle = wrap(subtitle, int(W * 14.8))
    foot = wrap(foot, int(W * 19.3))
    y = H - 0.22
    fig.text(0.2 / W, y / H, title, ha="left", va="top", fontsize=13.5, weight="bold", color=INK, linespacing=1.2)
    y -= 0.25 * (title.count("\n") + 1) + 0.1
    fig.text(0.2 / W, y / H, subtitle, ha="left", va="top", fontsize=9.5, color=INK2, linespacing=1.4)
    y -= 0.19 * (subtitle.count("\n") + 1) + 0.12
    legend_y = y / H
    y -= 0.25 * legend_rows + (0.1 if legend_rows else 0)
    y -= 0.32 if ax_titles else 0.12
    n_foot = foot.count("\n") + 1
    fig.text(0.2 / W, 0.14 / H, foot, ha="left", va="bottom", fontsize=7, color=MUTED, linespacing=1.45)
    bottom = 0.14 + 0.145 * n_foot + 0.12 + xlabel_band
    kw = dict(top=y / H, bottom=bottom / H, left=left / W, right=1 - right / W, wspace=wspace)
    if hspace is not None:
        kw["hspace"] = hspace
    fig.subplots_adjust(**kw)
    return legend_y


def fig_legend(fig, handles, labels, ly, ncol=3):
    W, _ = fig.get_size_inches()
    fig.legend(handles, labels, loc="upper left", bbox_to_anchor=(0.2 / W, ly), ncol=ncol, borderaxespad=0,
               handlelength=2.2, columnspacing=1.6)


def note(ax, x, y, text, dx=6, dy=0, ha="left", va="center", size=8.5, color=INK2):
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                fontsize=size, color=color, zorder=6)


def kfmt(ax):
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}k" if v else "0"))


def log_y(ax, unit="s", subs=(1.0, 3.0)):
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=subs))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: (f"{v:,.0f}" if v >= 1 else f"{v:g}") + unit))


def title_ax(ax, text):
    ax.set_title(text, loc="left", fontsize=10.5, color=INK, weight="bold")


def style_of(run):
    """Solid line for the run that counts; dashed for an earlier (crashed) attempt of the same label."""
    return dict(color=run["color"], ls="-" if run["attempt"] == run["n_attempts"] else (0, (4, 2.5)))


def rline(ax, run, xs, ys, win, label=True, dots=True, dot_alpha=0.18):
    st = style_of(run)
    if dots:
        ax.scatter(xs, ys, s=5, color=st["color"], alpha=dot_alpha, lw=0, zorder=2)
    if len(ys) >= 3:
        rx, ry = rolling_median(xs, ys, min(win, max(3, len(ys) // 3)))
        ax.plot(rx, ry, color=st["color"], ls=st["ls"], lw=LW, solid_capstyle="round", zorder=4,
                label=run["name"] + (" (in progress)" if run["running"] else ""))
        if label:
            note(ax, rx[-1], ry[-1], run["name"].replace("Qwen ", "").replace("DS ", ""), dx=4, size=8)


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print("wrote", path)
    return name


def src_line(runs):
    return "Source: " + ", ".join(os.path.basename(r["proxy"]) for r in runs)


def fam(runs, family):
    return [r for r in runs if r["family"] == family and r["rows"]]


def handles_for(runs):
    return [Line2D([], [], color=r["color"], ls=style_of(r)["ls"], lw=LW) for r in runs], \
           [r["name"] + (" (in progress)" if r["running"] else "") for r in runs]


# ------------------------------------------------------------- the charts ---
OMLX_NOTE = ("oMLX TTFT and decode come from its server log (stream_model_ttft, tok/s): oMLX buffers tool-call "
             "output, so the proxy's own TTFT/decode are wrong for oMLX. llama.cpp: proxy TTFT, server decode timings.")


def chart_step(runs, family, fname, M):
    rs = fam(runs, family)
    if not rs:
        return None
    fig, ax = plt.subplots(figsize=(8, 5.4))
    ymax = 1
    for r in rs:
        pts = [(x["prompt_tokens"] / 1e3, x["step_s"]) for x in r["rows"] if x["step_s"]]
        if not pts:
            continue
        xs, ys = zip(*pts)
        ymax = max(ymax, pct(ys, 0.99) or 1)
        rline(ax, r, list(xs), list(ys), 25)
    log_y(ax, " s")
    ax.set_ylim(1, ymax * 1.5)
    ax.set_xlim(0, None)
    kfmt(ax)
    ax.set_xlabel("Context size at the step (prompt tokens)")
    ax.set_ylabel("Seconds per agent step (log scale)")
    parts = [f"{r['name']}: median {M[id(r)]['step_med']:.1f} s, {M[id(r)]['steps_h']:.0f} steps/h"
             for r in rs if M[id(r)].get("step_med")]
    best = max((r for r in rs if r["attempt"] == r["n_attempts"]), key=lambda r: M[id(r)].get("steps_h", 0))
    ly = frame(fig, f"{family}: {best['name']} completes the most agent steps per hour",
               "; ".join(parts) + ".\nStep = start of one model request to the start of the next (model time + tool "
                                  "execution). Dots are single steps; lines are rolling medians.",
               f"{HW}\n{TASK}\nProxy logs time at 1 s resolution, so single short steps carry +/-1 s jitter.\n"
               + src_line(rs), legend_rows=-(-len(rs) // 3), right=1.0)
    h, lab = handles_for(rs)
    fig_legend(fig, h, lab, ly)
    return save(fig, fname)


def two_panel(runs, field, ylabel, fname, title, subtitle, unit, logy=True, win=25):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 5.6))
    used = []
    for ax, family in zip(axes, ("DeepSeek", "Qwen")):
        rs = fam(runs, family)
        allv = []
        for r in rs:
            pts = [(x["prompt_tokens"] / 1e3, x[field]) for x in r["rows"] if x.get(field)]
            if not pts:
                continue
            xs, ys = zip(*pts)
            allv += ys
            rline(ax, r, list(xs), list(ys), win)
            used.append(r)
        if logy:
            log_y(ax, unit)
        else:
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.set_ylim(0, (pct(allv, 0.99) or 1) * 1.15)
        ax.set_xlim(0, None)
        kfmt(ax)
        ax.set_xlabel("Context size (prompt tokens)")
        ax.set_ylabel(ylabel)
        title_ax(ax, family)
    ly = frame(fig, title, subtitle, f"{HW}\n{OMLX_NOTE}\n{src_line(used)}", legend_rows=-(-len(used) // 3),
               ax_titles=True, wspace=0.42, right=0.9)
    h, lab = handles_for(used)
    fig_legend(fig, h, lab, ly, ncol=3)
    return save(fig, fname)


def chart_context(runs, M):
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 5.4))
    used = []
    for ax, family in zip(axes, ("DeepSeek", "Qwen")):
        ends = sorted(fam(runs, family), key=lambda q: -q["rows"][-1]["prompt_tokens"])
        for r in fam(runs, family):
            rank = ends.index(r)
            xs = [x["h"] for x in r["rows"]]
            ys = [x["prompt_tokens"] / 1e3 for x in r["rows"]]
            st = style_of(r)
            ax.plot(xs, ys, color=st["color"], ls=st["ls"], lw=LW, zorder=3)
            ax.plot(xs[-1], ys[-1], "o", ms=MS, color=st["color"], mec=SURFACE, mew=RING, zorder=4)
            close = any(abs(q["rows"][-1]["prompt_tokens"] - r["rows"][-1]["prompt_tokens"]) < 25e3 and
                        abs(q["rows"][-1]["h"] - xs[-1]) < 0.3 for q in ends if q is not r)
            note(ax, xs[-1], ys[-1], f"{ys[-1]:,.0f}k" + (" (running)" if r["running"] else ""), dx=6,
                 dy=(6 if rank % 2 == 0 else -6) if close else 0, size=8)
            used.append(r)
        ax.set_xlim(0, None)
        ax.set_ylim(0, None)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}k" if v else "0"))
        ax.set_xlabel("Wall time since first request (hours)")
        ax.set_ylabel("Context (prompt tokens)")
        title_ax(ax, family)
    parts = [f"{r['name']} {M[id(r)]['ctx_h'] / 1e3:,.0f}k/h" for r in used]
    ly = frame(fig, "Context growth: tokens added to the conversation per hour of wall time",
               "Context gained per hour: " + "; ".join(parts) + ".\nThe ceiling agent never prunes history, so the "
               "line is monotone; the pi harness could compact but never reached its threshold.",
               f"{HW}\n{TASK}\n{src_line(used)}", legend_rows=-(-len(used) // 3), ax_titles=True, right=0.8,
               wspace=0.4)
    h, lab = handles_for(used)
    fig_legend(fig, h, lab, ly)
    return save(fig, "d_context_vs_wall_time.png")


def chart_quality(runs, M, xkey, fname):
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 7.6), sharex="col")
    used = []
    reg_seen = False
    ymin = 100
    for col, family in enumerate(("DeepSeek", "Qwen")):
        a1, a2 = axes[0][col], axes[1][col]
        end_h, end_l = [], []
        for r in fam(runs, family):
            ms = r["ref"]
            st = style_of(r)
            if r["mcommits"]:
                used.append(r)
            if ms:
                xs = [x[xkey] if xkey == "h" else x["ctx"] / 1e3 for x in ms]
                ys = [(x["rate"] or 0) * 100 for x in ms]
                a1.step(xs, ys, where="post", color=st["color"], ls=st["ls"], lw=LW, zorder=3)
                end_h.append(Line2D([], [], color=st["color"], ls=st["ls"], lw=LW))
                end_l.append(f"{r['name']}: {ys[-1]:.0f}% at the last commit "
                             f"({ms[-1]['hidden']['passed']}/{ms[-1]['hidden']['total']})")
                ymin = min(ymin, min(ys))
                seen = set()
                for x in ms:
                    new = [t for t in x["issues"]["regressions"] if t not in seen]
                    if new:
                        seen.update(new)
                        xv = x[xkey] if xkey == "h" else x["ctx"] / 1e3
                        a1.plot(xv, (x["rate"] or 0) * 100, "X", ms=9, color=CRITICAL, mec=SURFACE, mew=1, zorder=6)
                        name = new[0].split("::")[0].replace(".test.ts", "")
                        note(a1, xv, (x["rate"] or 0) * 100, f"{name} regressed ({x['ctx'] / 1e3:,.0f}k)", dx=4,
                             dy=8, ha="left", va="bottom", size=7.5, color=INK2)
                        reg_seen = True
            # milestone number of every milestone commit + running maximum
            mc = r["mcommits"]
            if mc:
                xs = [((c["t"] - r["t0"]).total_seconds() / 3600) if xkey == "h" else ctx_at(r, c["t"]) / 1e3
                      for c in mc]
                ys = [c["milestone"] for c in mc]
                a2.scatter(xs, ys, s=6, color=st["color"], alpha=0.35, lw=0, zorder=2)
                top, tops = 0, []
                for y in ys:
                    top = max(top, y)
                    tops.append(top)
                a2.step(xs, tops, where="post", color=st["color"], ls=st["ls"], lw=LW, zorder=3)
        a1.set_ylim(None, 102)
        if end_h:
            a1.legend(end_h, end_l, loc="lower left", fontsize=7.5, handlelength=1.8)
        a1.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
        a1.set_ylabel("Hidden tests passing")
        a2.set_ylim(0, 31)
        a2.set_yticks([0, 5, 10, 15, 20, 25, 30])
        a2.set_ylabel("Milestone number")
        a2.set_xlim(0, None)
        if xkey == "h":
            a2.set_xlabel("Wall time since first request (hours)")
        else:
            kfmt(a2)
            a2.set_xlabel("Context size at the commit (prompt tokens)")
        title_ax(a1, family)
    h, lab = handles_for(used)
    h += [Line2D([], [], ls="", marker="o", ms=4, color=MUTED, alpha=0.6)]
    lab += ["each milestone commit (bottom)"]
    if reg_seen:
        h.append(Line2D([], [], ls="", marker="X", ms=8, color=CRITICAL))
        lab.append("first commit where a hidden test regressed")
    for ax in axes[0]:
        ax.set_ylim(max(0, (ymin // 10) * 10 - 10), 102)
    xs_name = "wall time" if xkey == "h" else "context"
    ly = frame(fig, f"Hidden-test pass rate and milestone progress vs {xs_name}",
               "Top: share of the hidden tests for milestones <= the highest reached that pass at each milestone "
               "commit (referee.py). Bottom: milestone number of every `milestone N:` commit (dots) and the highest "
               "reached (line); dots below the line are revisits.",
               f"{HW}\n{TASK}\nThe hidden suite grows as milestones are reached (54 tests at m30), so the rate can "
               f"drop without a regression.\n{src_line(used)}",
               legend_rows=-(-len(lab) // 3), ax_titles=True, xlabel_band=0.55, hspace=0.12, right=1.1)
    fig_legend(fig, h, lab, ly, ncol=3)
    return save(fig, fname)


def chart_cache(runs, M):
    rs = [r for r in runs if r["rows"]]
    n = len(rs)
    cols = 3
    rows_n = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows_n, cols, figsize=(10, 3.0 * rows_n + 2.2), squeeze=False)
    for ax, r in zip(axes.flat, rs):
        xs = [x["prompt_tokens"] / 1e3 for x in r["rows"]]
        cached = [max(x.get("cached_tokens") or 0, 1) for x in r["rows"]]
        proc = [max(x.get("processed_tokens") or 0, 1) for x in r["rows"]]
        ax.fill_between(xs, 1, cached, color=GRID, lw=0, zorder=1, step="post")
        ax.plot(xs, cached, color=MUTED, lw=1, zorder=2)
        ax.scatter(xs, proc, s=6, color=r["color"], lw=0, alpha=0.7, zorder=3)
        log_y(ax, "", subs=(1.0,))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1e3:,.0f}k" if v >= 1e3 else f"{v:,.0f}"))
        ax.set_ylim(1, 2e6)
        ax.set_xlim(0, None)
        kfmt(ax)
        m = M[id(r)]
        title_ax(ax, r["name"] + (" (in progress)" if r["running"] else ""))
        ax.text(0.02, 0.97, f"hit rate {m['cache_hit'] * 100:.2f}% · breaks {m['breaks']}\nmedian new "
                            f"{m['proc_med']:,.0f} tok/step", transform=ax.transAxes, ha="left", va="top",
                fontsize=8, color=INK2)
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    for ax in axes[-1]:
        if ax.has_data():
            ax.set_xlabel("Context size (prompt tokens)")
    for row in axes:
        row[0].set_ylabel("Tokens (log scale)")
    nb = sum(M[id(r)]["breaks"] for r in rs)
    ly = frame(fig, "Cache health: no cache breaks in any run; each step reused the cached prefix" if nb == 0 else
               f"Cache health: {nb} cache break(s) across the runs",
               "Grey area = tokens served from the prompt cache at each step; dots = tokens actually processed "
               "(new tool output + message). A cache break would show a dot jumping up to the grey line.",
               f"{HW}\nHit rate = cached / prompt tokens summed over steps 2..n. Break = proxy flag (processed > 50% "
               f"of the previous prompt).\n{src_line(rs)}", ax_titles=True, legend_rows=0, wspace=0.28,
               xlabel_band=0.55)
    return save(fig, "f_cache_health.png")


# ----------------------------------------------------------------- report ---
def hms(h):
    if h is None:
        return "–"
    mins = int(round(h * 60))
    return f"{mins // 60}h{mins % 60:02d}"


def build_report(runs, M, charts, generated):
    L = []
    live = [r for r in runs if r["running"]]
    L.append("# Overnight agentic benchmark: morning report")
    L.append("")
    L.append(f"Generated {generated:%Y-%m-%d %H:%M} by `make_report.py` from the proxy, server, transcript, git and "
             f"referee logs. Mac Studio M5 Ultra, 256 GB. Task: Deepdelve (TASK.md): a 30-milestone TypeScript "
             f"roguelike built from an empty repo, one `milestone N:` commit per milestone.")
    if live:
        L.append("")
        L.append("> **Still running:** " + ", ".join(
            f"{r['name']} (as of its request {len(r['all_rows'])} at {r['t1']:%H:%M}; referee pending)" for r in live)
            + ". Re-run `make_report.py` after the run ends to refresh every number and chart.")
    L.append("")
    L.append("Runs: " + "; ".join(f"**{r['name']}** = {r['model']}, {r['engine']}, {r['agent']} agent" for r in runs
                                  if r["attempt"] == r["n_attempts"]) + ".")
    L.append("")

    # ---- summary table
    L.append("## 1. Summary")
    L.append("")
    cols = ["Run", "Status", "Requests", "Final context", "Wall time", "Cache breaks", "Step median / p90",
            "Steps/h", "Output tok/h", "Context gained/h", "Watchdog nudges", "Milestone commits",
            "Highest milestone (first reached)", "Hidden tests (latest)", "Agent tests (latest)"]
    L.append("| " + " | ".join(cols) + " |")
    L.append("|" + "---|" * len(cols))
    for r in runs:
        m = M[id(r)]
        if not r["rows"]:
            continue
        status = "in progress" if r["running"] else (r["end_event"] or "").split(";")[0] or "ended"
        if r["errors"]:
            status += f"; HTTP {r['errors'][-1]['status']} at request {r['errors'][-1]['i']}"
        hid = m.get("hidden_last")
        agt = m.get("agent_last")
        L.append("| " + " | ".join([
            f"**{r['name']}**", status, f"{m['requests']:,}", f"{m['final_ctx']:,}", hms(m["hours"]),
            str(m["breaks"]), f"{m['step_med']:.1f} / {m['step_p90']:.1f} s" if m.get("step_med") else "–",
            f"{m['steps_h']:.0f}", f"{m['out_h']:,.0f}", f"{m['ctx_h']:,.0f}",
            str(m["nudges"]) if r["agent"] == "ceiling" else "n/a (pi)",
            f"{m['ms_commits']}", f"m{m['top']} ({hms(m['t_top_h'])})" if m["top"] else "–",
            f"{hid[0]}/{hid[1]} ({hid[0] / hid[1] * 100:.0f}%)" if hid and hid[1] else
            ("pending (referee runs at end)" if r["running"] else "–"),
            f"{agt[0]}/{agt[1]}" if agt and agt[1] else "–"]) + " |")
    L.append("")
    L.append("Step = start of one model request to the start of the next (model + tool time). Wall time = first "
             "request to last response. Time caps were 3 h (DeepSeek) and 1 h (Qwen).")
    L.append("")

    # ---- latency by band
    L.append("### Median TTFT and decode speed by context band")
    L.append("")
    L.append("Cells: median TTFT (s) / median decode (tok/s) / requests. oMLX values from its server log "
             "(`stream_model_ttft`, `tok/s`), matched to proxy rows by order and prompt size; llama.cpp from the proxy "
             "TTFT and the server `timings`.")
    L.append("")
    L.append("| Run | " + " | ".join(b[2] for b in BANDS) + " | LLM time/step (median) | Spec-decode acceptance |")
    L.append("|" + "---|" * (len(BANDS) + 3))
    for r in runs:
        m = M[id(r)]
        if not r["rows"]:
            continue
        cells = []
        for _, _, name in BANDS:
            b = m["bands"].get(name)
            cells.append(f"{b[0]:.2f} / {b[1]:.1f} / {b[2]}" if b and b[0] is not None and b[1] is not None
                         else (f"{b[0]:.2f} / – / {b[2]}" if b and b[0] is not None else "–"))
        acc = f"{r['spec_accept'] * 100:.0f}%" if r["spec_accept"] else "none (no draft model)"
        L.append(f"| {r['name']} | " + " | ".join(cells) + f" | {m['llm_med']:.1f} s | {acc} |")
    L.append("")

    # ---- quality table
    L.append("### Code quality (referee.py, per milestone commit)")
    L.append("")
    qc = ["Run", "Referee'd commits", "Hidden pass @0.5h / 1h / 2h / 3h", "Regressions (test, first at ctx)",
          "Commits flagged w/ regression", "Test-count drops", "skip/only added", "Test files deleted",
          "History rewrites", "Build failures", "Agent-test failures"]
    L.append("| " + " | ".join(qc) + " |")
    L.append("|" + "---|" * len(qc))
    for r in runs:
        m = M[id(r)]
        if not r["rows"]:
            continue
        if not m.get("referee_n"):
            L.append(f"| {r['name']} | " + ("pending (run in progress)" if r["running"] else "no referee output")
                     + " |" + " |" * (len(qc) - 2))
            continue
        rates = " / ".join((f"{m['rate_at'][k] * 100:.0f}%" if m["rate_at"].get(k) is not None else "–")
                           if k in m["rate_at"] else "·" for k in (0.5, 1, 2, 3))
        regs = "; ".join(f"`{x['test'].split('::')[0]}` {x['test'].split('::')[-1][:60]} "
                         f"(at {x['ctx'] / 1e3:,.0f}k, {x['n']} commits{', still failing' if x['still'] else ', fixed'})"
                         for x in m["regressions"]) or "none"
        tcd = "; ".join(f"{d['previous']}→{d['now']} at {c / 1e3:,.0f}k ({s[:40]})" for s, d, c in m["tcd"]) or "0"
        L.append("| " + " | ".join([r["name"], str(m["referee_n"]), rates, regs, str(m["reg_commits"]), tcd,
                                    str(m["skips"]), str(m["deleted"]), str(m["rewrites"]),
                                    f"{m['build_fail']}/{m['referee_n']}", f"{m['agent_fail']}/{m['referee_n']}"])
                 + " |")
    L.append("")
    L.append("| Run | src LOC (files) | test LOC (files) | Milestone commits: backward jumps / repeats of a number | "
             "Test-only milestone commits | Distinct milestones/h | Milestone commits/h | Hidden tests failing at the end |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in runs:
        m = M[id(r)]
        if not r["rows"]:
            continue
        loc = r["loc"]
        fails = ", ".join(f"`{t.split('::')[0].replace('.test.ts', '')}` {t.split('::')[-1][:50]}"
                          for t in m.get("last_failing", [])) or ("–" if not m.get("referee_n") else "none")
        L.append(f"| {r['name']} | {loc['src']:,} ({loc['src_files']}) | {loc['test']:,} ({loc['test_files']}) | "
                 f"{r['back_jumps']} / {r['dup_commits']} | {r['test_only']} of {m['ms_commits']} | "
                 f"{m['distinct_h']:.1f} | {m['ms_h']:.1f} | {fails} |")
    L.append("")

    # ---- charts
    L.append("## 2. Charts")
    L.append("")
    captions = {
        "a1": "(a) Seconds per agent step vs context, DeepSeek pair",
        "a2": "(a) Seconds per agent step vs context, Qwen trio",
        "b": "(b) Time to first token per step vs context",
        "c": "(c) Decode speed per step vs context",
        "d": "(d) Cumulative context vs wall time",
        "e1": "(e) Hidden-test pass rate and milestone progress vs wall time",
        "e2": "(e) Hidden-test pass rate and milestone progress vs context",
        "f": "(f) Cached vs processed tokens per step (cache health)",
    }
    for k, name in charts.items():
        if name:
            L.append(f"**{captions[k]}**")
            L.append("")
            L.append(f"![{captions[k]}]({name})")
            L.append("")

    L.append("## 3. Findings")
    L.append("")
    L.extend(findings(runs, M))
    L.append("")
    L.append("## Regenerate")
    L.append("")
    L.append("```")
    L.append("python report/make_report.py")
    L.append("```")
    L.append("")
    L.append("Pure file reading (plus a one-shot `referee.py` for any finished run that has no referee output); "
             "never contacts a model server. Run it again after `qwen-llama-ceiling` ends (~08:25) so its final "
             "numbers and the referee's end-of-run pass are included.")
    return "\n".join(L) + "\n"


def by(runs, label, final=True):
    rs = [r for r in runs if r["label"] == label and r["rows"]]
    if final:
        rs = [r for r in rs if r["attempt"] == r["n_attempts"]]
    return rs[0] if rs else None


def window(run, X):
    """Stats for the part of a run below context X (for comparing runs at matched context)."""
    rows = [r for r in run["rows"] if r["prompt_tokens"] <= X]
    reach = next((r for r in run["rows"] if r["prompt_tokens"] >= X), None)
    t_x = reach["t_end"] if reach else run["t1"]
    mc = [c for c in run["mcommits"] if c["t"] <= t_x]
    ref = [r for r in run["ref"] if r["t"] <= t_x]
    h = max((t_x - run["t0"]).total_seconds() / 3600, 1e-6)
    return dict(h=h, reached=reach is not None, steps=len(rows), steps_h=len(rows) / h,
                ms_h=len({c["milestone"] for c in mc}) / h,
                step=med([r["step_s"] for r in rows]), llm=med([r["total_s"] for r in rows]),
                out=med([r.get("output_tokens") for r in rows]), top=max([c["milestone"] for c in mc] or [0]),
                hidden=(ref[-1]["hidden"]["passed"], ref[-1]["hidden"]["total"]) if ref else None)


def findings(runs, M):
    F = []
    # --- engine comparison per model, at matched context
    for family, a_lab, b_lab in (("DeepSeek", "ds0731-omlxk-dspark-ceiling", "dsv4v-llama-dspark-ceiling"),
                                 ("Qwen", "qwen-omlx-mtp-ceiling", "qwen-llama-ceiling")):
        a = by(runs, a_lab)
        bs = [r for r in runs if r["label"] == b_lab and r["rows"]]
        if not a or not bs:
            continue
        b = max(bs, key=lambda r: M[id(r)]["final_ctx"])  # the attempt with the most evidence
        ma, mb = M[id(a)], M[id(b)]
        X = min(ma["final_ctx"], mb["final_ctx"])
        wa, wb = window(a, X), window(b, X)
        thr = a if wa["steps_h"] > wb["steps_h"] else b
        lat = a if (wa["step"] or 1e9) < (wb["step"] or 1e9) else b
        eng = lambda r: r["engine"].split(" ")[0]  # noqa: E731
        K = min(a["top_milestone"], b["top_milestone"])

        def t_k(r):
            c = next((c for c in r["mcommits"] if c["milestone"] >= K), None)
            return (c["t"] - r["t0"]).total_seconds() / 3600 if c else None
        ka, kb = t_k(a), t_k(b)
        s = (f"**{family}: {eng(thr)} wins steps/hour ({wa['steps_h']:.0f} vs {wb['steps_h']:.0f})"
             + (" and median step latency" if lat is thr else f"; {eng(lat)} wins median step latency")
             + (f"; milestone pace is a near tie (m{K} after {hms(ka)} vs {hms(kb)})"
                if ka and kb and abs(ka - kb) / max(ka, kb) < 0.15 else
                f"; {eng(a) if ka < kb else eng(b)} reached m{K} first ({hms(ka)} vs {hms(kb)})" if ka and kb else "")
             + ".** "
             f"Compared up to the context both reached ({X / 1e3:,.0f}k; {b['name']}"
             f"{' is still running' if b['running'] else ''}): {a['name']} got there in {hms(wa['h'])} "
             f"({wa['steps']} steps, median step {wa['step']:.1f} s, median LLM time {wa['llm']:.1f} s, "
             f"{wa['out']:,.0f} output tok/step, milestone m{wa['top']}), {b['name']} in {hms(wb['h'])} "
             f"({wb['steps']} steps, median step {wb['step']:.1f} s, median LLM time {wb['llm']:.1f} s, "
             f"{wb['out']:,.0f} output tok/step, m{wb['top']}). Whole runs: {ma['steps_h']:.0f} vs "
             f"{mb['steps_h']:.0f} steps/h, {ma['out_h'] / 1e3:,.0f}k vs {mb['out_h'] / 1e3:,.0f}k output tok/h, "
             f"{ma['ctx_h'] / 1e3:,.0f}k vs {mb['ctx_h'] / 1e3:,.0f}k context/h, {ma['distinct_h']:.1f} vs "
             f"{mb['distinct_h']:.1f} distinct milestones/h.")
        shared = [n for _, _, n in BANDS if n in ma["bands"] and n in mb["bands"]
                  and None not in ma["bands"][n][:2] and None not in mb["bands"][n][:2]]
        if shared:
            per = "; ".join(f"{n}: TTFT {ma['bands'][n][0]:.2f} vs {mb['bands'][n][0]:.2f} s, decode "
                            f"{ma['bands'][n][1]:.0f} vs {mb['bands'][n][1]:.0f} tok/s" for n in (shared[0], shared[-1]))
            s += f" Per-request engine speed ({eng(a)} vs {eng(b)}), {per}."
        if family == "DeepSeek":
            s += (f" Caveats: the pair differs in model variant (0731 vs Vision-Exp) and quant as well as engine, and "
                  f"the workloads diverged: after ~{a['loop']['first_ctx'] / 1e3:,.0f}k {a['name']} was in a "
                  f"one-test-per-step loop (short outputs), which flatters its steps/h; its "
                  f"{ma['ms_h']:.0f} milestone commits/h (vs {mb['ms_h']:.0f}) are not progress."
                  if a.get("loop") else " Caveat: the pair differs in model variant and quant as well as engine.")
        F.append("- " + s)
    # --- ceiling vs pi
    p = by(runs, "qwen-llama-pi")
    cs = [r for r in runs if r["label"] == "qwen-llama-ceiling" and r["rows"]]
    if p:
        mp = M[id(p)]

        def per100k(r):
            m = M[id(r)]
            return r["distinct_ms"] / max(m["final_ctx"] / 1e5, 1e-9)
        comp = " ".join(
            f"{x['name']}{' (in progress)' if x['running'] else ''}: {M[id(x)]['steps_h']:.0f} steps/h, median step "
            f"{M[id(x)]['step_med']:.1f} s, {M[id(x)]['grow_med']:,.0f} tok context growth and "
            f"{M[id(x)]['out_med']:,.0f} output tok per step, {M[id(x)]['ctx_h'] / 1e3:,.0f}k context/h, m"
            f"{M[id(x)]['top']} at {M[id(x)]['final_ctx'] / 1e3:,.0f}k ({per100k(x):.1f} milestones per 100k context), "
            f"tools {dict(x['tools'].most_common())}." for x in cs)
        F.append(
            f"- **pi vs the ceiling agent (Qwen, llama.cpp).** pi: {mp['steps_h']:.0f} requests/h, median step "
            f"{mp['step_med']:.1f} s, {mp['grow_med']:,.0f} tok context growth and {mp['out_med']:,.0f} output tok per "
            f"step, {mp['ctx_h'] / 1e3:,.0f}k context/h, m{mp['top']} at {mp['final_ctx'] / 1e3:,.0f}k "
            f"({per100k(p):.1f} milestones per 100k context) with hidden tests {mp['hidden_last'][0]}/"
            f"{mp['hidden_last'][1]}, tools {dict(p['tools'].most_common())}. {comp} pi's steps are longer and produce more output "
            f"(it has its own system prompt and uses `edit` for in-place changes, {p['tools'].get('edit', 0)} of "
            f"{sum(p['tools'].values())} tool calls, where the ceiling agent rewrites whole files with write_file), "
            f"and it made {'more' if per100k(p) > max(per100k(x) for x in cs if not x['running']) else 'less'} "
            f"milestone progress per 100k tokens of context than the completed ceiling attempt"
            f"{' (the in-progress rerun is still in the cheap early milestones)' if any(x['running'] for x in cs) else ''}. "
            f"Cache behaviour: pi hit rate {mp['cache_hit'] * 100:.2f}%, "
            f"{mp['breaks']} breaks, {mp['hist_changes']} history edits (the proxy saw pi's history as append-only), "
            f"{p['invocations']} harness invocation, {p['compactions']} compaction events in harness.log (pi compacts "
            f"at 262k - 16k reserve, never reached).")
    # --- code quality
    q = []
    for r in runs:
        m = M[id(r)]
        if r["rows"] and m.get("referee_n"):
            h = m["hidden_last"]
            fails = sorted({t.split("::")[0].split("_", 1)[1].replace(".test.ts", "") for t in m["last_failing"]})
            q.append(f"{r['name']}: {h[0]}/{h[1]} hidden at m{m['top']}"
                     + (f" (failing: {', '.join(fails)})" if fails else " (all pass)")
                     + f", {m['build_fail']}/{m['referee_n']} milestone commits failed the build, "
                       f"{m['agent_fail']} failed their own tests, {r['loc']['src']:,} src / {r['loc']['test']:,} "
                       f"test LOC")
    if q:
        tot_skip = sum(M[id(r)].get("skips", 0) for r in runs)
        tot_del = sum(M[id(r)].get("deleted", 0) for r in runs)
        fast = [r["name"] for r in runs if M[id(r)].get("t_top_h") is not None and M[id(r)]["top"] == 30
                and M[id(r)]["t_top_h"] < 0.75]
        F.append("- **Code quality.** " + "; ".join(q) + f". skip/only markers added: {tot_skip}; test files "
                 f"deleted: {tot_del}. "
                 + (f"{' and '.join(fast)} declared all 30 milestones done in under 45 minutes, so the "
                    f"implementations are thin (the hidden FOV tests fail in both); Qwen is several times slower per "
                    f"milestone but its code passes nearly every hidden test for the milestones it reached. "
                    if fast else ""))
    # --- anomalies
    A = []
    for c1 in [r for r in runs if r["errors"] and r["rows"]]:
        m1 = M[id(c1)]
        err = c1["errors"][-1]
        last = c1["rows"][-1]
        rerun = next((r for r in runs if r["label"] == c1["label"] and r["attempt"] > c1["attempt"]), None)
        A.append(f"- **{c1['name']} crashed** after {len(c1['rows'])} good requests ({hms(m1['hours'])}, "
                 f"{m1['final_ctx']:,} context, highest m{m1['top']}): request {len(c1['rows'])} produced "
                 f"{last.get('output_tokens'):,} output tokens"
                 + (" (the max_tokens cap) and was cut off inside a tool call; the truncated arguments were not "
                    "valid JSON, and when agent_loop sent them back llama.cpp refused to render the history" if
                    (last.get("output_tokens") or 0) >= 8192 else "")
                 + f" (HTTP {err['status']}, \"Failed to parse tool call arguments as JSON\"). agent_loop retried "
                   f"and then exited. Fixed since (arguments stored as `{{}}`, error returned to the model). The event "
                   f"log's `last ctx 0` is the failed row."
                 + (f" Rerun started {rerun['t0']:%H:%M}." if rerun else ""))
        for rw in c1["rewrites"]:
            lost = ", ".join(f"m{x['milestone']}" for x in rw["lost_milestone_commits"])
            A.append(f"- **History rewrite ({c1['name']}):** at {rw['detected_at'][11:16]} HEAD stopped descending "
                     f"from the previously seen HEAD; lost milestone commit(s): {lost or 'none'} (the build-failing "
                     f"milestone commit was replaced by an amended one; no tests were lost).")
    for r in runs:
        lp = r.get("loop")
        if not lp or r["agent"] != "ceiling":
            continue
        m = M[id(r)]
        n_after, t_after = r["after_top"]
        ls = r["last_src_commit"]
        topic = (f" It keeps announcing a `{lp['topic']}` test; {'none was ever written' if not lp['topic_acted'] else str(lp['topic_acted']) + ' steps touched it'}."
                 if lp.get("topic") else "")
        A.append(f"- **{r['name']}: degenerate one-test loop.** From step {lp['first_step']} (context "
                 f"{lp['first_ctx'] / 1e3:,.0f}k, {hms((lp['t'] - r['t0']).total_seconds() / 3600) if lp.get('t') else '?'}"
                 f" into the run) to the end (step {lp['last_step']}), {lp['n']} of {len(r['transcript'])} steps "
                 f"({lp['share'] * 100:.0f}%) open with the same sentence, \"{lp['text']}…\". Each such step appends "
                 f"one trivial test to an existing test file, runs test + build and commits it as `milestone N: <x> "
                 f"test`"
                 + (f", and by the end it cycles through the same {len(lp['cycle'])} milestone numbers "
                    f"({', '.join(map(str, lp['cycle']))}), so e.g. \"milestone {bj[0]}\" is followed by "
                    f"\"milestone {bj[1]}\"" if lp["cycle"] and (bj := max(((x, y) for x, y in zip(lp["cycle"], lp["cycle"][1:] + lp["cycle"][:1])
                                                         if y < x), key=lambda p: p[0] - p[1], default=None)) else "")
                 + f".{topic} After the first pass reached m{r['top_milestone']} at "
                 f"{hms(m['t_top_h'])}, {t_after} of {n_after} milestone commits touched only test files; the last "
                 f"commit to change src/ was '{ls['subject'][:60]}' at {ls['t']:%H:%M}. Result: {m['ms_commits']} "
                 f"milestone commits and {m['agent_last'][1]} agent tests, while the hidden pass rate "
                 + (f"stayed at {next(iter(lp['rates'])) * 100:.0f}%. " if len(lp.get("rates", ())) == 1 else
                    f"ranged {min(lp['rates']) * 100:.0f}-{max(lp['rates']) * 100:.0f}%. " if lp.get("rates") else
                    "was not re-measured. ")
                 + "The watchdog never fired, because each step has different arguments and makes a new milestone "
                 "commit; neither trigger (4 identical calls, 40 steps without a milestone commit) can catch it.")
    for r in runs:
        m = M[id(r)]
        if r["agent"] == "ceiling" and not r.get("loop") and r["top_milestone"] == 30 and r["back_jumps"]:
            tcd = "; ".join(f"{d['previous']}→{d['now']} at {cc / 1e3:,.0f}k ('{s_}')" for s_, d, cc in m["tcd"])
            A.append(f"- **{r['name']}: out-of-order second pass.** After m30 at {hms(m['t_top_h'])} it restarted at "
                     f"m1 to extend each system, as TASK.md asks, then drifted into jumping between milestones "
                     f"({r['back_jumps']} backward jumps, {r['dup_commits']} commits reusing a number), with a "
                     f"`milestone 30: … (changelog update)` commit every few features. Real src changes continued "
                     f"({r['test_only']} of {m['ms_commits']} commits were test-only)."
                     + (f" Test-count drop(s): {tcd}." if tcd else ""))
    for r in runs:
        for x in M[id(r)].get("regressions", []):
            A.append(f"- **Regression ({r['name']}):** `{x['test']}` first failed at {hms(x['h'])} "
                     f"(context {x['ctx'] / 1e3:,.0f}k) in '{x['subject']}', and stayed failing in {x['n']} commits"
                     f"{' to the end of the run' if x['still'] else ' until fixed'}.")
    om = [r for r in runs if r["engine_kind"] == "omlx" and r["rows"]]
    if om:
        bad = sum(1 for r in om for x in r["rows"] if (x.get("decode_tps") or 0) > 1000)
        tot = sum(len(r["rows"]) for r in om)
        mx = max((x.get("decode_tps") or 0) for r in om for x in r["rows"])
        pt = med([x.get("ttft_s") for r in om for x in r["rows"]])
        st = med([x.get("ttft") for r in om for x in r["rows"]])
        A.append(f"- **oMLX measurement caveat:** oMLX buffers tool-call output, so the proxy sees the first byte "
                 f"only once the whole tool call is done. {bad} of {tot} oMLX proxy rows show decode above 1,000 "
                 f"tok/s (max {mx:,.0f}), and the proxy's median TTFT is {pt:.2f} s vs {st:.2f} s in the server log. "
                 f"Every oMLX TTFT/decode number here comes from the server log ({sum(r['matched'] for r in om)} of "
                 f"{tot} rows matched by order and prompt size); total_s and step times are valid for all runs.")
    for r in runs:
        if r.get("watch_ws") and r["ws"] and os.path.basename(r["watch_ws"]) != os.path.basename(r["ws"]):
            A.append(f"- **The live referee watched the wrong workspace for {r['name']}.** run_overnight starts "
                     f"`referee.py --watch` on the newest `runs/*-{r['label']}` directory; at that moment it was "
                     f"still `{os.path.basename(r['watch_ws'])}` (the rerun created its own a few seconds later), so "
                     f"the watcher re-polled the old repo. This run is only covered by the end-of-run referee pass"
                     + (" (not yet run; re-run this report after the run ends)." if r["running"] else "."))
    trunc = [(r["name"], r["truncated"]) for r in runs if r["truncated"]]
    if trunc:
        A.append("- **Replies cut at max_tokens (8192):** " + ", ".join(f"{n}: {k}" for n, k in trunc) + ".")
    parts = []
    for r in runs:
        for step, c, why in r["nudges"]:
            t = next((x["t_end"] for x in r["rows"] if x["prompt_tokens"] >= (c or 0)), r["t1"])
            done = [x for x in r["mcommits"] if x["t"] <= t]
            nxt = [x for x in r["mcommits"] if x["t"] > t]
            prev_t = done[-1]["t"] if done else r["t0"]
            work = (f"while working on m{done[-1]['milestone'] + 1 if done else 1}, which took "
                    f"{hms(((nxt[0]['t'] if nxt else r['t1']) - prev_t).total_seconds() / 3600)}"
                    + ("" if nxt else " and was unfinished at the end"))
            parts.append(f"{r['name']} step {step} at {c / 1e3:,.0f}k ({why}), {work}")
    if parts:
        A.append("- **Watchdog nudges:** " + "; ".join(parts) + ".")
    F.append("")
    F.append("### Anomalies")
    F.append("")
    F.extend(A)
    return F


# ------------------------------------------------------------------- main ---
def main():
    global OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-referee", action="store_true", help="never run referee.py, even for a finished run with no output")
    ap.add_argument("--out", default=OUT, help="where to write the PNGs and REPORT.md (default: next to this script)")
    args = ap.parse_args()
    OUT = args.out
    os.makedirs(OUT, exist_ok=True)
    events = read_events()
    runs = []
    for spec in RUNS:
        files = sorted(glob.glob(os.path.join(DATA, f"*-{spec['label']}.jsonl")), key=stamp_of)
        for k, path in enumerate(files, 1):
            runs.append(load_attempt(spec, path, k, len(files), events))
    for r in runs:
        ensure_referee(r, not args.no_referee)
        load_quality(r)
        load_agent(r)
    M = {id(r): metrics(r) for r in runs}
    charts = {
        "a1": chart_step(runs, "DeepSeek", "a1_step_time_deepseek.png", M),
        "a2": chart_step(runs, "Qwen", "a2_step_time_qwen.png", M),
        "b": two_panel(runs, "ttft", "Time to first token (s, log scale)", "b_ttft_vs_context.png",
                       "Time to first token per step stays low with a warm cache, even at 400k",
                       "Rolling median of per-step TTFT (prompt already cached; only the new turn is prefilled).",
                       " s"),
        "c": two_panel(runs, "decode", "Decode speed (tokens/s)", "c_decode_vs_context.png",
                       "Decode speed per step vs context",
                       "Rolling median of per-step generation speed; DeepSeek runs use DSpark speculative decoding, "
                       "Qwen oMLX uses MTP, Qwen llama.cpp has no draft model.", "", logy=False),
        "d": chart_context(runs, M),
        "e1": chart_quality(runs, M, "h", "e1_quality_vs_wall_time.png"),
        "e2": chart_quality(runs, M, "ctx", "e2_quality_vs_context.png"),
        "f": chart_cache(runs, M),
    }
    report = build_report(runs, M, charts, dt.datetime.now())
    with open(os.path.join(OUT, "REPORT.md"), "w") as fh:
        fh.write(report)
    print("wrote", os.path.join(OUT, "REPORT.md"))
    for r in runs:
        m = M[id(r)]
        if r["rows"]:
            print(f"{r['name']:<34} {'RUNNING ' if r['running'] else ''}req={m['requests']} ctx={m['final_ctx']:,} "
                  f"h={m['hours']:.2f} steps/h={m['steps_h']:.0f} step_med={m['step_med'] or 0:.1f}s "
                  f"top=m{m['top']} hidden={m.get('hidden_last')}")


if __name__ == "__main__":
    sys.exit(main())
