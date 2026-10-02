"""Shared helpers for run_eval.py, score.py and the self-test (stdlib only)."""
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRANSCRIPTS = ROOT / "transcripts"
GOLD = ROOT / "gold"
# results/<eval>/ in this repo; BENCH_RESULTS points somewhere else
DEFAULT_RESULTS = Path(os.environ.get("BENCH_RESULTS", Path(__file__).resolve().parent.parent / "results")).expanduser() / "call-eval"

EXPECTED_KEYS = {"call_type", "outcome", "sentiment_start", "sentiment_end", "quality_score",
                 "quality_reasons", "flags", "action_items", "summary_notes", "notable_details"}


# ---------------------------------------------------------------- prompts
def load_prompt(path):
    """Return (system, user_template) from a prompt markdown file with ## System / ## User."""
    text = Path(path).read_text()
    m = re.search(r"^## System\s*\n(.*?)^## User\s*\n(.*)\Z", text, re.S | re.M)
    if not m:
        raise ValueError(f"{path}: needs '## System' and '## User' sections")
    return m.group(1).strip(), m.group(2).strip()


def call_ids():
    return sorted(p.stem for p in TRANSCRIPTS.glob("C*.txt"))


# ---------------------------------------------------------------- JSON extraction
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def extract_json(raw, expect_keys=EXPECTED_KEYS):
    """Parse a model reply into a dict.

    Returns (obj_or_None, mode) where mode is 'strict' (reply is exactly a JSON object after
    stripping whitespace/<think>), 'lenient' (object recovered from fences or surrounding
    text), or 'fail'. Both strict and lenient count as parse success; the mode is reported.
    """
    if raw is None:
        return None, "fail"
    text = THINK_RE.sub("", raw)
    if "</think>" in text:  # opening tag was in the prompt template / stripped by server
        text = text.rsplit("</think>", 1)[1]
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, "strict"
    except Exception:
        pass
    candidates = []
    for m in FENCE_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                candidates.append(obj)
        except Exception:
            pass
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text, m.start())
            if isinstance(obj, dict):
                candidates.append(obj)
        except Exception:
            continue
    if not candidates:
        return None, "fail"
    if expect_keys:
        candidates.sort(key=lambda o: (len(expect_keys & set(o)), len(json.dumps(o))), reverse=True)
        if not (expect_keys & set(candidates[0])):
            return None, "fail"
    return candidates[0], "lenient"


# ---------------------------------------------------------------- keyword matching
_TRANS = {ord(c): r for c, r in {"‘": "'", "’": "'", "“": '"', "”": '"',
                                  "–": "-", "—": "-", "‑": "-", " ": " "}.items()}


def norm(text):
    text = unicodedata.normalize("NFKC", str(text)).translate(_TRANS).lower()
    return re.sub(r"\s+", " ", text)


def matches(text, groups):
    """True if, for every group, at least one regex in that group occurs in text."""
    t = norm(text)
    return all(any(re.search(p, t) for p in group) for group in groups)


def as_text(x):
    """Flatten any JSON-ish value to a single string for keyword matching."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " | ".join(as_text(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return " | ".join(as_text(v) for v in x)
    return str(x)


def as_list(x):
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def max_bipartite(edges, n_left):
    """edges: dict left_index -> list of right ids. Returns dict right -> left (max matching)."""
    match_r = {}

    def try_left(u, seen):
        for v in edges.get(u, []):
            if v in seen:
                continue
            seen.add(v)
            if v not in match_r or try_left(match_r[v], seen):
                match_r[v] = u
                return True
        return False

    for u in range(n_left):
        try_left(u, set())
    return match_r


def load_gold(call_id):
    return json.loads((GOLD / f"{call_id}.json").read_text())
