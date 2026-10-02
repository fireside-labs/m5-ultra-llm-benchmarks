"""Shared helpers for run_eval.py, score.py, make_judge_pack.py and the self-test (stdlib only).

Answers are free-text Markdown. Scoring is made robust by a light output convention (each task
asks for fixed `## Section` headings) and by matching gold keyword groups against *units*:
a unit is one top-level list item (with its nested sub-bullets and continuation lines), one
paragraph, one table row, or one un-recognised sub-heading together with the text under it.
"""
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ROOT / "tasks"
GOLD = ROOT / "gold"
SYSTEM_PROMPT = ROOT / "prompts" / "system.md"
# results/<eval>/ in this repo; BENCH_RESULTS points somewhere else
DEFAULT_RESULTS = Path(os.environ.get("BENCH_RESULTS", Path(__file__).resolve().parent.parent / "results")).expanduser() / "reason-eval"


# ---------------------------------------------------------------- prompts / gold
def load_system():
    text = SYSTEM_PROMPT.read_text()
    m = re.search(r"^## System\s*\n(.*)\Z", text, re.S | re.M)
    if not m:
        raise ValueError(f"{SYSTEM_PROMPT}: needs a '## System' section")
    return m.group(1).strip()


def task_ids():
    return sorted(p.stem for p in TASKS.glob("R*.md"))


def load_task(tid):
    return (TASKS / f"{tid}.md").read_text().strip()


def load_gold(tid):
    return json.loads((GOLD / f"{tid}.json").read_text())


# ---------------------------------------------------------------- text normalisation / matching
_TRANS = {ord(c): r for c, r in {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
                                  "‑": "-", "−": "-", " ": " ", " ": " ", "×": "x"}.items()}


def norm(text):
    text = unicodedata.normalize("NFKC", str(text)).translate(_TRANS).lower()
    text = re.sub(r"[*_`]+", "", text)            # markdown emphasis does not break phrases
    return re.sub(r"\s+", " ", text)


def matches(text, groups):
    """True if, for every group, at least one regex in that group occurs in text."""
    t = norm(text)
    return all(any(re.search(p, t) for p in group) for group in groups)


THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_think(raw):
    """Remove inline reasoning blocks some servers leave in the content channel."""
    if raw is None:
        return ""
    text = THINK_RE.sub("", raw)
    if "</think>" in text:          # opening tag was in the chat template
        text = text.rsplit("</think>", 1)[1]
    return text.strip()


# ---------------------------------------------------------------- section detection
# Order matters: the first pattern that matches a heading wins.
SECTION_PATTERNS = [
    ("notissues", r"look(s|ed)? like|isn'?t (a|an|one)\b|not (actually |really )?(a |an )?(real )?(problem|issue|gap|concern)"
                  r"|already (handled|addressed|covered)|handled adequately|red herring|false alarm|non.?issue"),
    ("priorities", r"top (3|three)|priorit|sensitivit"),
    ("mind", r"change (my|the|your) mind|would change|change the (answer|decision|conclusion|recommendation)|would move"),
    ("cruxes", r"crux"),
    ("against", r"case against|^against\b|\bcons\b|arguments? against|opposing"),
    ("for", r"case for|^for\b|\bpros\b|arguments? for|in favou?r"),
    ("lean", r"\blean\b|my (view|position|verdict|take)|verdict"),
    ("kill", r"\bkill|drop (the|an|a|my|proposal)|\bstop\b|abandon|tripwire"),
    ("measure", r"measure|metric"),
    ("steps", r"first steps|next steps|\bsteps\b|\bplan\b"),
    ("chain", r"chain|calculation|derivation"),
    ("result", r"^results?\b|^answer\b|^estimate$"),
    ("recommendation", r"recommend"),
    ("bottom", r"bottom line|conclusion|summary"),
    ("variables", r"variable|factor|consideration"),
    ("issues", r"miss|gap|issue|problem|flaw|overlook|blind spot|weakness|error"),
]
SECTION_KEYS = [k for k, _ in SECTION_PATTERNS]


def classify_heading(text):
    h = norm(text).strip()
    h = re.sub(r"^[#\s\d.):-]+", "", h).strip(" :")
    for key, pat in SECTION_PATTERNS:
        if re.search(pat, h):
            return key
    return None


_H_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BOLD_H_RE = re.compile(r"^\s*(\*\*|__)([^*_]{2,80})\1\s*:?\s*$")
_COLON_H_RE = re.compile(r"^\s*([A-Z][A-Za-z0-9 ()/&'’-]{2,60}):\s*$")
_LIST_RE = re.compile(r"^(\s*)([-*+•]|\d+[.)])\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


def parse_answer(text):
    """Split a Markdown answer into sections of units.

    Returns a list of {"key", "heading", "units": [str, ...]}; the first entry is the
    'preamble' (text before the first recognised heading). Unrecognised headings that are
    deeper than the current section heading start a new unit inside that section (models
    often write `### 1. Issue name` per item); unrecognised headings at the same or a higher
    level start an 'other' section.
    """
    text = strip_think(text)
    sections = [{"key": "preamble", "heading": "", "units": [], "level": 0}]
    cur, mode, blank = None, None, False

    def close():
        nonlocal cur, mode
        if cur:
            u = "\n".join(cur).strip()
            if u:
                sections[-1]["units"].append(u)
        cur, mode = None, None

    def new_section(key, heading, level):
        close()
        sections.append({"key": key, "heading": heading, "units": [], "level": level})

    for line in text.splitlines():
        if not line.strip():
            blank = True
            continue
        mh = _H_RE.match(line)
        if mh:
            level, htext = len(mh.group(1)), mh.group(2)
            key = classify_heading(htext)
            if key:
                new_section(key, htext, level)
            elif level > sections[-1]["level"] and sections[-1]["key"] != "preamble":
                close()
                cur, mode = [htext], "sub"
            else:
                new_section("other", htext, level)
            blank = False
            continue
        mb = _BOLD_H_RE.match(line) or _COLON_H_RE.match(line)
        if mb and mode != "sub":
            htext = mb.group(2) if mb.re is _BOLD_H_RE else mb.group(1)
            key = classify_heading(htext)
            if key:
                new_section(key, htext, 2)
                blank = False
                continue
        if line.strip().startswith("|"):
            if _TABLE_SEP_RE.match(line):
                continue
            if mode == "sub":
                cur.append(line.strip())
            else:
                close()
                sections[-1]["units"].append(line.strip())
            blank = False
            continue
        ml = _LIST_RE.match(line)
        if ml:
            indent = len(ml.group(1).expandtabs(4))
            if mode == "sub":
                cur.append(line.strip())
            elif indent < 2 or cur is None:
                close()
                cur, mode = [line.strip()], "list"
            else:
                cur.append(line.strip())
            blank = False
            continue
        # plain text line
        indented = line[:1] in (" ", "\t")
        if mode == "sub" or (cur is not None and (not blank or (mode == "list" and indented))):
            cur.append(line.strip())
        else:
            close()
            cur, mode = [line.strip()], "para"
        blank = False
    close()
    for s in sections:
        s.pop("level", None)
    return sections


def section_units(sections, keys):
    """All units from sections whose key is in keys (in answer order)."""
    return [u for s in sections if s["key"] in keys for u in s["units"]]


def has_section(sections, key):
    return any(s["key"] == key and s["units"] for s in sections)
