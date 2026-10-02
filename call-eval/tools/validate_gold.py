#!/usr/bin/env python3
"""Consistency checks for gold labels (no model needed).

- every planted flag / decoy / subtle fact has an `evidence` quote that occurs verbatim in the
  transcript (whitespace/quote-normalised), so ground truth is really in the text;
- every gold item's own description satisfies its own keyword matcher (so a correct answer
  phrased like the gold text is credited);
- no decoy description satisfies a real flag's matcher in the same call (so flagging a decoy
  can never be credited as a true positive);
- categorical values are in the schema enums; theme descriptions match their own matchers
  and not each other's.
Exit code 1 on any problem.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evallib import GOLD, ROOT, TRANSCRIPTS, call_ids, load_gold, matches, norm  # noqa: E402

schema = json.loads((ROOT / "schema.json").read_text())["properties"]
problems = []


def chk(cond, msg):
    if not cond:
        problems.append(msg)


ids = call_ids()
chk(len(ids) == 20, f"expected 20 transcripts, found {len(ids)}")
counts = {"flags": 0, "decoys": 0, "subtle_facts": 0, "action_items": 0}
for c in ids:
    g = load_gold(c)
    t = norm((TRANSCRIPTS / f"{c}.txt").read_text())
    for f in ("call_type", "outcome", "sentiment_start", "sentiment_end"):
        for v in [g[f]] + g.get(f + "_accept", []):
            chk(v in schema[f]["enum"], f"{c}: {f}={v!r} not in schema enum")
    chk(1 <= g["quality_score"] <= 5, f"{c}: quality_score out of range")
    for kind in ("flags", "decoys", "subtle_facts"):
        for it in g.get(kind, []):
            chk(norm(it["evidence"]) in t, f"{c} {it['id']}: evidence not found in transcript: {it['evidence'][:60]!r}")
    for kind in ("flags", "decoys", "subtle_facts", "quality_reasons", "action_items"):
        for it in g.get(kind, []):
            txt = it.get("text") or " ".join(str(it.get(k, "")) for k in ("owner", "task", "due"))
            chk(matches(txt, it["match"]), f"{c} {it['id']}: own text does not satisfy own matcher")
    for d in g.get("decoys", []):
        for f in g.get("flags", []):
            chk(not matches(d["text"], f["match"]), f"{c}: decoy {d['id']} text matches real flag {f['id']}")
    for k in counts:
        counts[k] += len(g.get(k, []))

th = json.loads((GOLD / "themes.json").read_text())["themes"]
for a in th:
    chk(matches(a["text"], a["match"]), f"theme {a['id']}: own text fails own matcher")
    for b in th:
        if a is not b:
            chk(not matches(a["text"], b["match"]), f"theme {a['id']} text matches theme {b['id']} matcher")
    for c in a["calls"]:
        chk(a["id"] in load_gold(c).get("themes", []), f"theme {a['id']} lists {c} but gold/{c}.json does not")

print(f"{len(ids)} calls; planted: {counts['flags']} flags, {counts['decoys']} decoys, "
      f"{counts['subtle_facts']} subtle facts, {counts['action_items']} action items, {len(th)} themes "
      f"({', '.join(f'{a['id']}: {len(a['calls'])} calls' for a in th)})")
if problems:
    print(f"{len(problems)} problem(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("gold OK")
