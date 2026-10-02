#!/usr/bin/env python3
"""Consistency checks for the reason-eval gold files (no model needed).

Checks, per task:
- every gold item, crux and decoy: its own `text` satisfies its matcher, it has >= 2
  `paraphrases`, every paraphrase satisfies its matcher, and no `negatives` entry does;
- every paraphrase also survives the answer parser: written as a numbered list item under the
  task's main section heading, it is still matched (catches regexes that depend on markdown);
- decoys never collide with gold: no decoy text/paraphrase satisfies any gold item or crux
  matcher (otherwise flagging the decoy would be credited, not penalised);
- gold paraphrases do not satisfy a decoy matcher *instead of* their own (informational: gold is
  matched first, so this can never cost points, but it is reported if a paraphrase fails its own);
- tasks that require a 'Top 3 priorities' section have >= 3 high-importance items;
- debate tasks have items on both sides and >= 2 cruxes; estimate tasks have a decision matcher
  whose paraphrases match and whose negatives don't;
- required section keys are known to the parser and every task prompt names each section;
- prompt size: system + task < 20k tokens (o200k tokenizer if tiktoken is installed, else chars/4).
Exit code 1 on any problem.

  python tools/validate_gold.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evallib import (SECTION_KEYS, classify_heading, load_gold, load_system, load_task,  # noqa: E402
                     matches, parse_answer, task_ids)

MAX_PROMPT_TOKENS = 20000
problems, info = [], []


def chk(cond, msg):
    if not cond:
        problems.append(msg)


try:
    import tiktoken
    _enc = tiktoken.get_encoding("o200k_base")

    def ntok(s):
        return len(_enc.encode(s))
    TOKNAME = "o200k"
except Exception:  # pragma: no cover
    def ntok(s):
        return len(s) // 4
    TOKNAME = "chars/4"

MAIN_HEADING = {"A": "Missed issues", "B": "Variables", "C": "Case for", "D": "First steps"}

totals = {"items": 0, "high": 0, "cruxes": 0, "decoys": 0, "paraphrases": 0}
system = load_system()
rows = []
for tid in task_ids():
    g = load_gold(tid)
    prompt = load_task(tid)
    entries = [("item", x) for x in g["items"]] + [("crux", x) for x in g.get("cruxes", [])] + \
              [("decoy", x) for x in g.get("decoys", [])]
    gold_like = g["items"] + g.get("cruxes", [])
    ids = [x["id"] for _, x in entries]
    chk(len(ids) == len(set(ids)), f"{tid}: duplicate ids")
    for kind, x in entries:
        chk(matches(x["text"], x["match"]), f"{tid} {x['id']}: own text fails own matcher")
        paras = x.get("paraphrases", [])
        chk(len(paras) >= 2, f"{tid} {x['id']}: needs >= 2 paraphrases (has {len(paras)})")
        for p in paras:
            chk(matches(p, x["match"]), f"{tid} {x['id']}: paraphrase fails own matcher: {p[:80]!r}")
            # survives parsing as a list item
            sec = parse_answer(f"## {MAIN_HEADING.get(g['category'], 'Missed issues')}\n\n1. {p}\n")
            units = [u for s in sec for u in s["units"]]
            chk(any(matches(u, x["match"]) for u in units), f"{tid} {x['id']}: paraphrase lost by parser: {p[:60]!r}")
            totals["paraphrases"] += 1
        for n in x.get("negatives", []):
            chk(not matches(n, x["match"]), f"{tid} {x['id']}: negative satisfies matcher: {n[:80]!r}")
        for pat in [p for grp in x["match"] for p in grp]:
            try:
                re.compile(pat)
            except re.error as e:
                chk(False, f"{tid} {x['id']}: bad regex {pat!r}: {e}")
    for d in g.get("decoys", []):
        for txt in [d["text"]] + d.get("paraphrases", []):
            for it in gold_like:
                chk(not matches(txt, it["match"]), f"{tid}: decoy {d['id']} wording matches gold {it['id']}: {txt[:70]!r}")
    for it in gold_like:
        for p in it.get("paraphrases", []):
            for d in g.get("decoys", []):
                if matches(p, d["match"]):
                    info.append(f"{tid}: gold {it['id']} paraphrase also matches decoy {d['id']} (gold wins): {p[:60]!r}")
    for k in g["sections"]:
        chk(k in SECTION_KEYS, f"{tid}: unknown section key {k}")
    # every required section must be recognisable from the prompt's own heading list
    heads = re.findall(r"^## (.+)$", prompt, re.M)
    keys = [classify_heading(h) for h in heads]
    for k in g["sections"]:
        chk(k in keys, f"{tid}: required section {k!r} not among prompt headings {heads}")
    n_high = sum(1 for x in g["items"] if x["importance"] == "high")
    if "priorities" in g["sections"]:
        chk(n_high >= 3, f"{tid}: priorities section needs >= 3 high-importance items (has {n_high})")
    if g["category"] == "C":
        sides = {x.get("side") for x in g["items"]}
        chk(sides == {"for", "against"}, f"{tid}: debate items need both sides, got {sides}")
        chk(len(g.get("cruxes", [])) >= 2, f"{tid}: debate needs >= 2 cruxes")
    if "estimate" in g:
        e = g["estimate"]
        for p in e["decision_paraphrases"]:
            chk(matches(p, e["decision_match"]), f"{tid}: decision paraphrase fails: {p!r}")
        for n in e.get("decision_negatives", []):
            chk(not matches(n, e["decision_match"]), f"{tid}: decision negative matches: {n!r}")
        chk(e["full_credit"][0] <= e["full_credit"][1] and e["half_credit"][0] <= e["full_credit"][0], f"{tid}: bad estimate ranges")
    tok = ntok(system) + ntok(prompt)
    chk(tok < MAX_PROMPT_TOKENS, f"{tid}: prompt is {tok} tokens (limit {MAX_PROMPT_TOKENS})")
    totals["items"] += len(g["items"])
    totals["high"] += n_high
    totals["cruxes"] += len(g.get("cruxes", []))
    totals["decoys"] += len(g.get("decoys", []))
    rows.append((tid, g["category"], len(g["items"]), n_high, len(g.get("cruxes", [])), len(g.get("decoys", [])), tok, g["title"]))

print(f"| task | cat | gold items | high | cruxes | decoys | prompt tokens ({TOKNAME}) | title |")
print("|---|---|---|---|---|---|---|---|")
for r in rows:
    print("| " + " | ".join(str(c) for c in r) + " |")
print(f"\ntotals: {totals['items']} gold items ({totals['high']} high), {totals['cruxes']} cruxes, "
      f"{totals['decoys']} decoys, {totals['paraphrases']} paraphrases checked")
for i in info:
    print("  info:", i)
if problems:
    print(f"{len(problems)} problem(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("gold OK")
