"""Stall detection for agent_loop.py.

The watchdog only ever produces one fixed nudge, appended by the caller as a new user
message (history is never edited). Two triggers:

  * the same tool call (name + arguments) repeated REPEAT_LIMIT times in a row;
  * no new `milestone N:` commit in the last IDLE_STEPS steps.

Each trigger resets its own counter, so a persistent stall is nudged again only after
another full window.

    wd = Watchdog(workspace_root)
    reason = wd.observe(step, [(name, arguments_json), ...])
    if reason: messages.append({"role": "user", "content": NUDGE})
"""
import json, re, subprocess

NUDGE = "Run the tests. If they fail, fix them. If they pass, commit and move on to the next milestone."
REPEAT_LIMIT = 4
IDLE_STEPS = 40
MILESTONE_RE = re.compile(r"^\s*milestone\s+\d+\s*:", re.I | re.M)


def normalize_args(args):
    """Canonical form of a tool-call argument string (JSON key order and spacing ignored)."""
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except ValueError:
            return args.strip()
    return json.dumps(args, sort_keys=True, separators=(",", ":"))


def count_milestone_commits(repo):
    """Number of commits reachable from HEAD whose subject is `milestone N: ...` (0 if none/no repo)."""
    r = subprocess.run(["git", "-C", str(repo), "log", "--format=%s"], capture_output=True, text=True,
                       env={"GIT_OPTIONAL_LOCKS": "0", "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})
    return len(MILESTONE_RE.findall(r.stdout)) if r.returncode == 0 else 0


class Watchdog:
    def __init__(self, repo, repeat_limit=REPEAT_LIMIT, idle_steps=IDLE_STEPS, milestone_counter=count_milestone_commits):
        self.repo = repo
        self.repeat_limit = repeat_limit
        self.idle_steps = idle_steps
        self.count = milestone_counter
        self.last_call = None
        self.streak = 0
        self.milestones = self.count(repo)
        self.last_progress_step = 0

    def observe(self, step, calls):
        """Feed one step's tool calls as (name, arguments) pairs. Returns a reason string if a nudge is due."""
        reasons = []
        for name, args in calls:
            key = (name, normalize_args(args))
            self.streak = self.streak + 1 if key == self.last_call else 1
            self.last_call = key
        if self.streak >= self.repeat_limit:
            reasons.append(f"same tool call repeated {self.streak} times in a row: {self.last_call[0]} {self.last_call[1][:120]}")
            self.streak = 0
            self.last_call = None
        n = self.count(self.repo)
        if n != self.milestones:
            self.milestones = n
            self.last_progress_step = step
        elif step - self.last_progress_step >= self.idle_steps:
            reasons.append(f"no new milestone commit in the last {step - self.last_progress_step} steps")
            self.last_progress_step = step
        return "; ".join(reasons) or None
