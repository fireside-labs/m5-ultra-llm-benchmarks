#!/usr/bin/env python3
"""Quality referee for the Deepdelve agentic benchmark.

For every commit whose subject matches `milestone N:` (oldest first) the referee
extracts the commit into a temp directory with `git archive` (the agent's working
tree, index and .git are never written to), then runs, each with a time cap and
under the agent's sandbox profile <workspace>.sb when it exists:

  npm ci (falls back to npm install)  ->  npm run build  ->  npm test (Vitest JSON)
  ->  hidden_tests/mNN_*.test.ts for NN <= highest milestone reached so far

and appends one JSON line per milestone commit to <workspace>.referee.jsonl.
Flags per commit: hidden-test regressions (passed at an earlier milestone commit,
not passing now), agent test-count decreases, newly added .skip/.only/.todo/xit
markers, deleted test files, and history rewrites (HEAD no longer descends from
the HEAD seen by the previous referee run; tracked in <workspace>.referee.state.json).

  python referee.py runs/20260929-201500-dsv4v-llama-ceiling            # one shot
  python referee.py runs/20260929-201500-dsv4v-llama-ceiling --watch    # poll every 60 s

Already-evaluated commits (by sha) are never re-run, so one-shot and --watch can be
mixed freely. Never talks to any model server.
"""
import argparse, fcntl, json, os, pathlib, re, shutil, signal, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
MILESTONE_RE = re.compile(r"^\s*milestone\s+(\d+)\s*:", re.I)
TEST_FILE_RE = re.compile(r"(^|/)[^/]+\.(test|spec)\.[cm]?[jt]sx?$")
SKIP_RE = re.compile(r"\b(?:it|test|describe|suite|bench)\s*(?:\.\s*\w+\s*)*\.\s*(skip|only|todo|skipIf|runIf|fails)\b"
                     r"|\b(xit|xtest|xdescribe|fit|fdescribe)\s*\(")
HIDDEN_RE = re.compile(r"^m(\d+)_.*\.test\.ts$")
TAIL = 3000


# ---------------------------------------------------------------- helpers

def git(repo, *args, check=True, binary=False):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binary else r.stdout.decode(errors="replace")


def git_ok(repo, *args):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, env=env).returncode == 0


def tail(s, n=TAIL):
    return s if len(s) <= n else "..." + s[-n:]


def npm_env():
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/opt/homebrew/sbin:" + env.get("PATH", "/usr/bin:/bin")
    env.update(CI="1", NO_COLOR="1", FORCE_COLOR="0", npm_config_fund="false", npm_config_audit="false",
               npm_config_update_notifier="false", npm_config_progress="false")
    return env


class Runner:
    """Runs commands with a time cap, killing the whole process group on timeout."""

    def __init__(self, sandbox_profile):
        self.prefix = ["sandbox-exec", "-f", str(sandbox_profile)] if sandbox_profile else []
        self.env = npm_env()

    def __call__(self, cmd, cwd, timeout):
        t0 = time.time()
        p = subprocess.Popen(self.prefix + cmd, cwd=cwd, env=self.env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        timed_out = False
        try:
            out, _ = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            out, _ = p.communicate()
        return {"command": " ".join(cmd), "exit": None if timed_out else p.returncode,
                "ok": (not timed_out) and p.returncode == 0, "timed_out": timed_out,
                "secs": round(time.time() - t0, 1), "output": out.decode(errors="replace")}


def summarize(res):
    return {k: res[k] for k in ("command", "exit", "ok", "timed_out", "secs")} | {"tail": tail(res["output"])}


def parse_vitest_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return None


def parse_vitest_stdout(text):
    """Fallback when the JSON report is missing: parse 'Tests  3 failed | 10 passed (13)'."""
    counts = {}
    for line in text.splitlines():
        if re.match(r"^\s*Tests\s", line):
            for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|todo)", line):
                counts[kind] = int(n)
    return counts or None


# ---------------------------------------------------------------- repo facts

def milestone_commits(repo, head):
    out = git(repo, "log", "--reverse", "--topo-order", "--format=%H%x1f%ct%x1f%s", head)
    rows = []
    for line in out.splitlines():
        sha, ct, subj = line.split("\x1f", 2)
        m = MILESTONE_RE.match(subj)
        if m:
            rows.append({"sha": sha, "time": int(ct), "subject": subj, "milestone": int(m.group(1))})
    return rows


def test_files(repo, sha):
    names = git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
    return sorted(n for n in names if TEST_FILE_RE.search(n) and "node_modules/" not in n)


def skip_marker_total(tree, files):
    total = 0
    for f in files:
        try:
            total += len(SKIP_RE.findall((tree / f).read_text(errors="replace")))
        except OSError:
            pass
    return total


def test_file_changes(repo, prev_sha, sha):
    """Added skip-marker lines, deleted and renamed test files between two commits."""
    base = prev_sha or git(repo, "hash-object", "-t", "tree", "/dev/null").strip()
    added, deleted, renamed = [], [], []
    for line in git(repo, "diff", "--name-status", "-M", base, sha).splitlines():
        parts = line.split("\t")
        st = parts[0]
        if st.startswith("D") and TEST_FILE_RE.search(parts[1]):
            deleted.append(parts[1])
        elif st.startswith("R") and TEST_FILE_RE.search(parts[1]):
            if TEST_FILE_RE.search(parts[2]):
                renamed.append([parts[1], parts[2]])
            else:
                deleted.append(parts[1])
    cur = None
    for line in git(repo, "diff", "-U0", "-M", base, sha, "--", ".").splitlines():
        if line.startswith("+++ "):
            path = line[4:]
            cur = path[2:] if path.startswith("b/") else None
            if cur and not TEST_FILE_RE.search(cur):
                cur = None
        elif cur and line.startswith("+") and SKIP_RE.search(line):
            added.append({"file": cur, "line": line[1:].strip()[:200]})
    return added, deleted, renamed


# ---------------------------------------------------------------- evaluation

def extract(repo, sha, dest):
    arch = subprocess.Popen(["git", "-C", str(repo), "archive", "--format=tar", sha], stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(dest)], stdin=arch.stdout, check=True)
    arch.stdout.close()
    if arch.wait() != 0:
        raise RuntimeError(f"git archive {sha} failed")


def run_hidden(run, tree, hidden_dir, max_n, timeout):
    files = sorted(f.name for f in hidden_dir.iterdir() if HIDDEN_RE.match(f.name) and int(HIDDEN_RE.match(f.name).group(1)) <= max_n)
    info = {"files": files, "passed": 0, "failed": 0, "skipped": 0, "total": 0, "results": {}, "failures": {}}
    if not files:
        return info
    dst = tree / "__hidden__"
    shutil.copytree(hidden_dir, dst, dirs_exist_ok=True)
    include = [f"__hidden__/{f}" for f in files]
    (dst / "vitest.referee.config.mjs").write_text(
        "export default { test: " + json.dumps({"include": include, "environment": "node", "watch": False,
                                                 "testTimeout": 60000, "hookTimeout": 60000, "globals": False,
                                                 "setupFiles": [], "passWithNoTests": False}) + " };\n")
    report = dst / "result.json"
    vitest = tree / "node_modules" / ".bin" / "vitest"
    if not vitest.exists():
        info["error"] = "vitest not installed in the checkout"
        for f in files:
            info["results"][f"{f}::<file>"] = "fail"
        info["failed"] = info["total"] = len(files)
        return info
    res = run([str(vitest), "run", "--config", "__hidden__/vitest.referee.config.mjs", "--root", ".",
               "--reporter=json", f"--outputFile={report}"], tree, timeout)
    info.update(secs=res["secs"], timed_out=res["timed_out"], exit=res["exit"])
    data = parse_vitest_json(report)
    if data is None:
        info["error"] = "no JSON report: " + tail(res["output"], 1500)
        for f in files:
            info["results"][f"{f}::<file>"] = "fail"
    else:
        seen_files = set()
        for fr in data.get("testResults", []):
            fname = pathlib.Path(fr.get("name", "")).name
            seen_files.add(fname)
            asserts = fr.get("assertionResults") or []
            if not asserts:
                info["results"][f"{fname}::<file>"] = "fail"
                info["failures"][f"{fname}::<file>"] = tail(fr.get("message") or "file failed to load", 600)
            for a in asserts:
                tid = f"{fname}::{a.get('fullName') or a.get('title')}"
                st = a.get("status")
                st = "pass" if st == "passed" else "fail" if st == "failed" else "skip"
                info["results"][tid] = st
                if st == "fail":
                    info["failures"][tid] = tail("\n".join(a.get("failureMessages") or []), 600)
        for f in files:
            if f not in seen_files:
                info["results"][f"{f}::<file>"] = "fail"
    vals = list(info["results"].values())
    info.update(passed=vals.count("pass"), failed=vals.count("fail"), skipped=vals.count("skip"), total=len(vals))
    return info


def evaluate_commit(repo, c, ctx, args, run):
    t0 = time.time()
    rec = {"type": "milestone", "repo": str(repo), "sha": c["sha"], "subject": c["subject"],
           "milestone": c["milestone"], "effective_milestone": ctx["max_n"],
           "committed_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(c["time"])),
           "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=f"referee-{repo.name[-40:]}-{c['sha'][:8]}-", dir=args.tmp_root)).resolve()
    try:
        tree = tmp / "w"
        tree.mkdir()
        extract(repo, c["sha"], tree)
        files = test_files(repo, c["sha"])
        rec["test_files"] = len(files)
        rec["skip_markers_total"] = skip_marker_total(tree, files)
        added, deleted, renamed = test_file_changes(repo, ctx["prev_sha"], c["sha"])

        has_pkg = (tree / "package.json").exists()
        scripts = {}
        if has_pkg:
            try:
                scripts = json.loads((tree / "package.json").read_text()).get("scripts") or {}
            except ValueError:
                pass
        # install
        if not has_pkg:
            rec["install"] = {"ok": False, "error": "no package.json"}
        else:
            attempts = []
            if (tree / "package-lock.json").exists():
                attempts.append(run(["npm", "ci", "--no-audit", "--no-fund"], tree, args.install_timeout))
            if not attempts or not attempts[-1]["ok"]:
                if attempts:
                    shutil.rmtree(tree / "node_modules", ignore_errors=True)
                attempts.append(run(["npm", "install", "--no-audit", "--no-fund"], tree, args.install_timeout))
            rec["install"] = summarize(attempts[-1]) | {"attempts": [a["command"] for a in attempts]}
        # build
        if has_pkg and "build" in scripts:
            rec["build"] = summarize(run(["npm", "run", "build"], tree, args.build_timeout))
        else:
            rec["build"] = {"ok": False, "error": "no build script"}
        # agent's own tests
        if has_pkg and "test" in scripts:
            report = tmp / "agent-tests.json"
            res = run(["npm", "test", "--", "--reporter=json", f"--outputFile={report}"], tree, args.test_timeout)
            at = summarize(res)
            data = parse_vitest_json(report)
            if data is not None:
                at.update(source="json", passed=data.get("numPassedTests", 0), failed=data.get("numFailedTests", 0),
                          skipped=data.get("numPendingTests", 0), todo=data.get("numTodoTests", 0),
                          total=data.get("numTotalTests", 0), files=len(data.get("testResults", [])))
            else:
                counts = parse_vitest_stdout(res["output"])
                if counts:
                    at.update(source="stdout", passed=counts.get("passed", 0), failed=counts.get("failed", 0),
                              skipped=counts.get("skipped", 0), todo=counts.get("todo", 0),
                              total=sum(counts.values()), files=None)
                else:
                    at.update(source=None, passed=None, failed=None, skipped=None, todo=None, total=None, files=None)
            at["ok"] = res["ok"] and (at["failed"] in (0, None)) and at["total"] is not None
            rec["agent_tests"] = at
        else:
            rec["agent_tests"] = {"ok": False, "error": "no test script", "total": None, "passed": None}
        # hidden tests
        if args.hidden_dir.is_dir():
            rec["hidden"] = run_hidden(run, tree, args.hidden_dir, ctx["max_n"], args.hidden_timeout)
        else:
            rec["hidden"] = {"error": f"missing {args.hidden_dir}", "results": {}}
    finally:
        if args.keep_temp:
            rec["temp_dir"] = str(tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    # issues relative to earlier milestone commits in the current history
    results = rec["hidden"].get("results", {})
    regressions = sorted(t for t in ctx["ever_passed"] if results.get(t) != "pass")
    total = rec["agent_tests"].get("total")
    passed = rec["agent_tests"].get("passed")
    issues = {
        "regressions": regressions,
        "regressed_since": {t: ctx["ever_passed"][t] for t in regressions},
        "test_count_decrease": ({"previous": ctx["prev_total"], "now": total}
                                if total is not None and ctx["prev_total"] is not None and total < ctx["prev_total"] else None),
        "passed_count_decrease": ({"previous": ctx["prev_passed"], "now": passed}
                                  if passed is not None and ctx["prev_passed"] is not None and passed < ctx["prev_passed"] else None),
        "new_skip_markers": added,
        "skip_markers_increase": (rec["skip_markers_total"] - ctx["prev_skip_total"]
                                  if ctx["prev_skip_total"] is not None and rec["skip_markers_total"] > ctx["prev_skip_total"] else 0),
        "deleted_test_files": deleted,
        "renamed_test_files": renamed,
        "history_rewrite": bool(ctx.get("pending_rewrite")),
        "build_failed": not rec["build"].get("ok"),
        "agent_tests_failed": not rec["agent_tests"].get("ok"),
    }
    rec["issues"] = issues
    rec["ok"] = (rec["build"].get("ok") and rec["agent_tests"].get("ok") and rec["hidden"].get("failed", 0) == 0
                 and not regressions and not issues["test_count_decrease"] and not added and not deleted)
    rec["duration_s"] = round(time.time() - t0, 1)
    return rec


def advance(ctx, rec):
    """Fold an evaluated commit into the running context."""
    for tid, st in rec["hidden"].get("results", {}).items():
        if st == "pass" and tid not in ctx["ever_passed"]:
            ctx["ever_passed"][tid] = rec["sha"]
    if rec["agent_tests"].get("total") is not None:
        ctx["prev_total"] = rec["agent_tests"]["total"]
        ctx["prev_passed"] = rec["agent_tests"]["passed"]
    ctx["prev_skip_total"] = rec.get("skip_markers_total")
    ctx["prev_sha"] = rec["sha"]
    ctx["pending_rewrite"] = False


# ---------------------------------------------------------------- driver

class Referee:
    def __init__(self, args):
        self.args = args
        self.repo = args.workspace
        self.out = pathlib.Path(str(self.repo) + ".referee.jsonl")
        self.state_path = pathlib.Path(str(self.repo) + ".referee.state.json")
        sb = self.repo.parent / f"{self.repo.name}.sb"
        self.sandbox = sb if (sb.exists() and not args.no_sandbox) else None
        self.run = Runner(self.sandbox)

    def load_state(self):
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {"last_head": None, "records": {}, "pending_rewrite": False}

    def save_state(self, st):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(st))
        tmp.replace(self.state_path)

    def emit(self, row):
        with self.out.open("a") as f:
            f.write(json.dumps(row) + "\n")

    def log(self, msg):
        print(f"[referee {time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def poll(self):
        if not git_ok(self.repo, "rev-parse", "--verify", "-q", "HEAD"):
            self.log("no commits yet")
            return 0
        head = git(self.repo, "rev-parse", "HEAD").strip()
        st = self.load_state()
        commits = milestone_commits(self.repo, head)
        in_history = {c["sha"] for c in commits}

        last = st.get("last_head")
        if last and last != head:
            exists = git_ok(self.repo, "cat-file", "-e", f"{last}^{{commit}}")
            if not exists or not git_ok(self.repo, "merge-base", "--is-ancestor", last, head):
                lost = [s for s, r in st["records"].items() if s not in in_history]
                row = {"type": "history_rewrite", "repo": str(self.repo), "detected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "previous_head": last, "head": head, "previous_head_exists": exists,
                       "lost_milestone_commits": [{"sha": s, "milestone": st["records"][s]["milestone"]} for s in lost]}
                self.emit(row)
                self.log(f"HISTORY REWRITE: {last[:8]} is not an ancestor of {head[:8]}; {len(lost)} evaluated milestone commits dropped")
                st["pending_rewrite"] = True
        st["last_head"] = head
        self.save_state(st)

        ctx = {"ever_passed": {}, "prev_total": None, "prev_passed": None, "prev_skip_total": None,
               "prev_sha": None, "max_n": 0, "pending_rewrite": False}
        new = 0
        for c in commits:
            ctx["max_n"] = max(ctx["max_n"], c["milestone"])
            rec = st["records"].get(c["sha"])
            if rec is None:
                ctx["pending_rewrite"] = st.get("pending_rewrite", False)
                self.log(f"evaluating {c['sha'][:8]} {c['subject'][:60]!r} (hidden tests <= m{ctx['max_n']})")
                rec = evaluate_commit(self.repo, c, ctx, self.args, self.run)
                self.emit(rec)
                slim = {k: v for k, v in rec.items() if k not in ("install", "build")}
                slim["agent_tests"] = {k: v for k, v in rec["agent_tests"].items() if k != "tail"}
                slim["hidden"] = {k: v for k, v in rec["hidden"].items() if k != "failures"}
                st["records"][c["sha"]] = slim
                st["pending_rewrite"] = False
                self.save_state(st)
                new += 1
                i, h, a = rec["issues"], rec["hidden"], rec["agent_tests"]
                flags = [k for k in ("regressions", "test_count_decrease", "new_skip_markers", "deleted_test_files",
                                     "history_rewrite", "build_failed", "agent_tests_failed") if i[k]]
                self.log(f"  m{c['milestone']}: build={'ok' if rec['build'].get('ok') else 'FAIL'} "
                         f"agent={a.get('passed')}/{a.get('total')} hidden={h.get('passed', 0)}/{h.get('total', 0)} "
                         f"{'ISSUES ' + ','.join(flags) if flags else 'clean'} ({rec['duration_s']} s)")
            advance(ctx, rec)
        return new


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=pathlib.Path, help="the agent's git repo (runs/<stamp>-<label>)")
    ap.add_argument("--watch", action="store_true", help="keep polling for new milestone commits")
    ap.add_argument("--interval", type=float, default=60, help="poll interval in seconds for --watch")
    ap.add_argument("--max-polls", type=int, default=0, help="stop --watch after this many polls (0 = forever)")
    ap.add_argument("--hidden-dir", type=pathlib.Path, default=HERE / "hidden_tests")
    ap.add_argument("--install-timeout", type=int, default=900)
    ap.add_argument("--build-timeout", type=int, default=300)
    ap.add_argument("--test-timeout", type=int, default=600)
    ap.add_argument("--hidden-timeout", type=int, default=600)
    ap.add_argument("--tmp-root", default="/private/tmp", help="where temp checkouts go (must be writable in the sandbox)")
    ap.add_argument("--no-sandbox", action="store_true", help="ignore <workspace>.sb")
    ap.add_argument("--keep-temp", action="store_true", help="keep temp checkouts for debugging")
    args = ap.parse_args()
    args.workspace = args.workspace.resolve()
    args.hidden_dir = args.hidden_dir.resolve()
    if not (args.workspace / ".git").exists():
        sys.exit(f"not a git repo: {args.workspace}")

    ref = Referee(args)
    lock = open(str(args.workspace) + ".referee.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("another referee is already running on this workspace")
    ref.log(f"workspace {args.workspace}; sandbox {ref.sandbox or 'none'}; output {ref.out}")
    polls = 0
    while True:
        try:
            n = ref.poll()
            if n or not args.watch:
                ref.log(f"evaluated {n} new milestone commit(s)")
        except Exception as e:  # keep watching through transient git/npm trouble
            ref.log(f"error: {e.__class__.__name__}: {e}")
            if not args.watch:
                raise
        polls += 1
        if not args.watch or (args.max_polls and polls >= args.max_polls):
            break
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
