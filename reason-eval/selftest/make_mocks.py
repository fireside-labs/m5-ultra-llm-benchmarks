#!/usr/bin/env python3
"""Build mock 'model answers' from the gold checklists and score them - no model needed.

  mock_perfect : every gold item written as its own list item in the right section, decoys listed
                 under "Looks like a problem but isn't", top-3 = high-importance items, correct
                 Fermi result lines (should score ~100)
  mock_sloppy  : realistic failure modes - generic filler items, ~1/3 of gold items (in paraphrase
                 wording), every decoy flagged as a missed issue, low-importance "priorities",
                 a one-sided debate with no cruxes section and no confidence, missing sections,
                 a wrong Fermi number/decision, and one empty answer (thinking ran out of tokens)
  mock_shuffled: the perfect answer for the WRONG task (rotated by one) - matcher-specificity control
  mock_padded  : kitchen sink - every gold item AND every decoy dumped into one long unordered
                 "Missed issues"-style list with decoys first; tests the 12-unit cap and decoy penalty

Usage:  python selftest/make_mocks.py        (writes selftest/results/*, then runs score.py)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from evallib import load_gold, task_ids  # noqa: E402

OUT = HERE / "results"


def numbered(lines):
    return "\n".join(f"{i}. {t}" for i, t in enumerate(lines, 1))


def highs(g):
    return [x for x in g["items"] if x["importance"] == "high"]


def perfect(g):
    cat, items = g["category"], g["items"]
    if g["task_id"] == "R10":
        e = g["estimate"]
        others = [x for x in items if x["importance"] != "high"]
        return (f"## Estimate chain\n\n{numbered([x['text'] for x in items])}\n\n"
                f"## Result\n\nESTIMATE: 600\nRANGE: 430 - 780\nDECISION: {e['decision_paraphrases'][0]}\n\n"
                f"## Key sensitivities\n\n{numbered([x['text'] for x in highs(g)[:3]])}\n\n"
                f"## Recommendation\n\n{' '.join(x['text'] + '.' for x in others[-2:])}\n")
    if cat == "A":
        return (f"## Missed issues\n\n{numbered([x['text'] for x in items])}\n\n"
                f"## Looks like a problem but isn't\n\n" + "\n".join(f"- {d['text']}: handled ({d['why_not']})" for d in g["decoys"]) +
                f"\n\n## Top 3 priorities\n\n{numbered([x['text'] for x in highs(g)[:3]])}\n\n"
                "## Bottom line\n\nThe recommendation does not stand as written; resolve the priorities first.\n")
    if cat == "B":
        texts = [x["text"] for x in items]
        if len(texts) > 12:                      # respect the 12-item limit: merge the tail
            texts = texts[:11] + ["; also: ".join(texts[11:])]
        return (f"## Variables\n\n{numbered(texts)}\n\n"
                f"## Top 3 priorities\n\n{numbered([x['text'] for x in highs(g)[:3]])}\n\n"
                "## What would change my mind\n\n- A finding that reverses the top priority.\n- New cost data.\n")
    if cat == "C":
        f = [x["text"] for x in items if x["side"] == "for"]
        a = [x["text"] for x in items if x["side"] == "against"]
        return (f"## Case for\n\n{numbered(f)}\n\n## Case against\n\n{numbered(a)}\n\n"
                f"## Cruxes\n\n{numbered([c['text'] for c in g['cruxes']])}\n\n"
                "## What evidence would change the answer\n\n- Results from a time-limited pilot.\n\n"
                "## My lean\n\nI lean toward a phased trial, about 60% confident, conditional on the pilot results.\n")
    # D (R09)
    return (f"## First steps\n\n{numbered([x['text'] for x in items])}\n\n"
            "## Measure first\n\n1. Calls by interval.\n2. Reasons for repeat calls.\n\n"
            "## What would kill the idea\n\n- If interval data show waits are high all day, rescheduling is not enough.\n\n"
            f"## Top 3 priorities\n\n{numbered([x['text'] for x in highs(g)[:3]])}\n")


GENERIC = ["Stakeholders should be consulted more broadly.",
           "The timeline seems aggressive.",
           "Communication with the team could be improved.",
           "There may be risks that need further analysis."]


def sloppy(g, i):
    cat, items = g["category"], g["items"]
    some = [x["paraphrases"][1] for x in items[::3]]          # ~1/3 of items, paraphrased
    normal = [x["text"] for x in items if x["importance"] == "normal"][:3] or GENERIC[:3]
    if g["task_id"] == "R06":
        return ""                                            # empty answer: thinking hit max_tokens
    if g["task_id"] == "R10":
        return ("## Estimate chain\n\n1. The budget buys about 80 ports at $150k each.\n2. That should cover demand.\n\n"
                "## Result\n\nESTIMATE: 80\nRANGE: 60 - 100\nDECISION: Yes, $12M is roughly enough for the city's needs.\n\n"
                f"## Key sensitivities\n\n{numbered(GENERIC[:3])}\n")
    if cat == "A":
        return (f"## Missed issues\n\n{numbered(GENERIC[:2] + [d['paraphrases'][0] for d in g['decoys']] + some)}\n\n"
                f"## Top 3 priorities\n\n{numbered([g['decoys'][0]['paraphrases'][0]] + normal[:2])}\n")
    if cat == "B":
        return (f"## Variables\n\n{numbered(GENERIC + some)}\n\n## Top 3 priorities\n\n{numbered(normal)}\n")
    if cat == "C":
        f = [x["paraphrases"][0] for x in items if x["side"] == "for"]
        return (f"## Case for\n\n{numbered(f)}\n\n## Case against\n\n1. Some people may not like it.\n\n"
                "## Key questions\n\n1. What will people think?\n\n## My lean\n\nI support it.\n")
    return (f"## First steps\n\n{numbered(GENERIC[:2] + some)}\n\n## Top 3 priorities\n\n{numbered(normal)}\n")


def padded(g):
    lines = [d["text"] for d in g.get("decoys", [])] + GENERIC + [x["text"] for x in g["items"]] + \
            [c["text"] for c in g.get("cruxes", [])]
    head = {"A": "Missed issues", "B": "Variables", "C": "Case for", "D": "First steps"}[g["category"]]
    if g["task_id"] == "R10":
        head = "Estimate chain"
    return f"## {head}\n\n{numbered(lines)}\n\n## Top 3 priorities\n\n{numbered(GENERIC[:3])}\n"


def write(label, outputs):
    d = OUT / label
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for tid, raw in outputs.items():
        (d / f"{tid}.raw.txt").write_text(raw)
    (d / "run_manifest.json").write_text(json.dumps({"label": label, "model": label + " (synthetic mock)"}))


def main():
    ids = task_ids()
    golds = {t: load_gold(t) for t in ids}
    write("mock_perfect", {t: perfect(golds[t]) for t in ids})
    write("mock_sloppy", {t: ("<think>Let me think.</think>\n" if i % 3 == 0 else "") + sloppy(golds[t], i)
                          for i, t in enumerate(ids)})
    rot = ids[1:] + ids[:1]
    write("mock_shuffled", {t: perfect(golds[r]) for t, r in zip(ids, rot)})
    write("mock_padded", {t: padded(golds[t]) for t in ids})
    subprocess.run([sys.executable, str(HERE.parent / "score.py"), "--root", str(OUT),
                    "--out", str(HERE / "scores")], check=True)


if __name__ == "__main__":
    main()
