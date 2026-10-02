#!/usr/bin/env python3
"""Consistency checks for gold labels (no model needed).

Same checks as v1, plus v2 robustness checks:

- every planted flag / decoy / subtle fact has an `evidence` quote that occurs verbatim in the
  transcript (whitespace/quote-normalised), so ground truth is really in the text;
- every gold item's own text satisfies its own keyword matcher (so a correct answer
  phrased like the gold text is credited);
- v2: every `paraphrases` entry (alternative wordings a model might use) also satisfies the
  item's matcher; flags and decoys must carry at least 2 paraphrases;
- v2: no `negatives` entry satisfies the item's matcher (e.g. the pre-correction value of a
  corrected number, or a near-miss wording that should not be credited);
- no decoy text or decoy paraphrase satisfies a real flag's matcher in the same call (so
  flagging a decoy can never be credited as a true positive);
- categorical values are in the schema enums; theme texts/paraphrases match their own
  matchers and not each other's; decoy-theme texts match no real theme, and real-theme texts
  match no decoy theme.
Exit code 1 on any problem.

  python tools/validate_gold.py            # all calls
  python tools/validate_gold.py --only C03 # a subset (theme checks still run)
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evallib import GOLD, ROOT, TRANSCRIPTS, call_ids, load_gold, matches, norm  # noqa: E402

N_CALLS = 16
schema = json.loads((ROOT / "schema.json").read_text())["properties"]
problems = []


def chk(cond, msg):
    if not cond:
        problems.append(msg)


ap = argparse.ArgumentParser()
ap.add_argument("--only")
args = ap.parse_args()

ids = call_ids()
if args.only:
    ids = [i for i in ids if i in set(args.only.split(","))]
else:
    chk(len(ids) == N_CALLS, f"expected {N_CALLS} transcripts, found {len(ids)}")
counts = {"flags": 0, "decoys": 0, "subtle_facts": 0, "action_items": 0}
for c in ids:
    gp = GOLD / f"{c}.json"
    if not gp.exists():
        chk(False, f"{c}: gold file missing")
        continue
    g = load_gold(c)
    t = norm((TRANSCRIPTS / f"{c}.txt").read_text())
    for f in ("call_type", "outcome", "sentiment_start", "sentiment_end"):
        for v in [g[f]] + g.get(f + "_accept", []):
            chk(v in schema[f]["enum"], f"{c}: {f}={v!r} not in schema enum")
    chk(1 <= g["quality_score"] <= 5, f"{c}: quality_score out of range")
    for kind in ("flags", "decoys", "subtle_facts"):
        for it in g.get(kind, []):
            chk(norm(it["evidence"]) in t, f"{c} {it['id']}: evidence not found in transcript: {it['evidence'][:60]!r}")
    for kind in ("flags", "decoys", "subtle_facts", "quality_reasons", "action_items", "acceptable_flags"):
        for it in g.get(kind, []):
            txt = it.get("text") or " ".join(str(it.get(k, "")) for k in ("owner", "task", "due"))
            chk(matches(txt, it["match"]), f"{c} {it['id']}: own text does not satisfy own matcher")
            for p in it.get("paraphrases", []):
                chk(matches(p, it["match"]), f"{c} {it['id']}: paraphrase fails own matcher: {p[:70]!r}")
            for n in it.get("negatives", []):
                chk(not matches(n, it["match"]), f"{c} {it['id']}: negative satisfies matcher: {n[:70]!r}")
    for kind in ("flags", "decoys"):
        for it in g.get(kind, []):
            chk(len(it.get("paraphrases", [])) >= 2, f"{c} {it['id']}: needs >= 2 paraphrases")
    for d in g.get("decoys", []):
        for f in g.get("flags", []):
            for txt in [d["text"]] + d.get("paraphrases", []):
                chk(not matches(txt, f["match"]), f"{c}: decoy {d['id']} wording matches real flag {f['id']}: {txt[:70]!r}")
    # a correctly-phrased real flag should be credited as that flag, never fall through to a decoy
    # only (it would still be credited, since real flags are matched first; this is informational)
    ids_seen = [it["id"] for k in ("flags", "decoys", "subtle_facts", "action_items", "quality_reasons")
                for it in g.get(k, [])]
    chk(len(ids_seen) == len(set(ids_seen)), f"{c}: duplicate item ids")
    for k in counts:
        counts[k] += len(g.get(k, []))

tg = json.loads((GOLD / "themes.json").read_text())
th, dth = tg["themes"], tg.get("decoy_themes", [])
for a in th:
    for txt in [a["text"]] + a.get("paraphrases", []):
        chk(matches(txt, a["match"]), f"theme {a['id']}: text/paraphrase fails own matcher: {txt[:60]!r}")
        for b in th:
            if a is not b:
                chk(not matches(txt, b["match"]), f"theme {a['id']} text matches theme {b['id']} matcher")
        for d in dth:
            chk(not matches(txt, d["match"]), f"theme {a['id']} text matches decoy theme {d['id']}")
    for c in a["calls"]:
        if (GOLD / f"{c}.json").exists():
            chk(a["id"] in load_gold(c).get("themes", []), f"theme {a['id']} lists {c} but gold/{c}.json does not")
for d in dth:
    for txt in [d["text"]] + d.get("paraphrases", []):
        chk(matches(txt, d["match"]), f"decoy theme {d['id']}: text/paraphrase fails own matcher")
        for a in th:
            chk(not matches(txt, a["match"]), f"decoy theme {d['id']} text matches real theme {a['id']}")
for c in ids:
    if (GOLD / f"{c}.json").exists():
        for tid in load_gold(c).get("themes", []):
            chk(any(a["id"] == tid and c in a["calls"] for a in th), f"{c}: theme {tid} not listed in themes.json")

print(f"{len(ids)} calls; planted: {counts['flags']} flags, {counts['decoys']} decoys, "
      f"{counts['subtle_facts']} subtle facts, {counts['action_items']} action items, {len(th)} themes "
      f"({', '.join(f'{a['id']}: {len(a['calls'])} calls' for a in th)}), {len(dth)} decoy theme(s)")
if problems:
    print(f"{len(problems)} problem(s):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("gold OK")
