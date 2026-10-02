#!/usr/bin/env python3
"""Build two mock 'model outputs' from the gold labels and score them - no model needed.

  mock_perfect : every field derived from gold (should score ~100)
  mock_shuffled: the perfect answers attached to the wrong calls (matcher-specificity control)
  mock_sloppy  : realistic failure modes - 2 unparseable replies (one truncated long call, one
                 prose refusal), always 'resolved'/'neutral'/score 4, generic quality reasons,
                 only some real flags, takes every decoy bait, one generic false flag per call,
                 only the first action item, no notable details, a 160-word vague summary,
                 and only 1 of 3 themes plus the decoy theme (v2).

Usage:  python selftest/make_mocks.py        (writes selftest/results/*, then runs score.py)
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from evallib import GOLD, call_ids, load_gold  # noqa: E402

OUT = HERE / "results"


def perfect(g):
    return {
        "call_type": g["call_type"],
        "outcome": g["outcome"],
        "sentiment_start": g["sentiment_start"],
        "sentiment_end": g["sentiment_end"],
        "quality_score": g["quality_score"],
        "quality_reasons": [q["text"] for q in g["quality_reasons"]],
        "flags": [{"type": "other", "description": f["text"], "evidence": f["evidence"]} for f in g["flags"]],
        "action_items": [{"owner": a["owner"], "task": a["task"], "due": a["due"]} for a in g["action_items"]],
        "summary_notes": f"Mock summary for {g['call_id']}.",
        "notable_details": [s["text"] for s in g["subtle_facts"]],
    }


VAGUE = ("The customer called about their account and spoke with a representative. " * 4 +
         "The representative listened to the concern, looked up the relevant information and "
         "explained the next steps. The customer asked several questions, which were answered. "
         "There was some discussion of the details and the customer was given information "
         "about what to expect. The call included some small talk and a short hold while the "
         "agent checked the system. Overall the interaction covered the main topic of the call "
         "and ended politely, with the customer thanking the agent for their help and time today.")


def sloppy(g, i):
    a = perfect(g)
    a["call_type"] = "other" if i % 5 == 0 else g["call_type"]
    a["outcome"] = "resolved"
    a["sentiment_start"] = a["sentiment_end"] = "neutral"
    a["quality_score"] = 4
    a["quality_reasons"] = ["Agent was polite and professional.", "Call handled efficiently."]
    flags = []
    if i % 2 == 0 and g["flags"]:
        f = g["flags"][0]
        flags.append({"type": "other", "description": f["text"], "evidence": f["evidence"]})
    for d in g.get("decoys", []):
        flags.append({"type": "other", "description": d["text"], "evidence": d["evidence"]})
    flags.append({"type": "other", "description": "Customer expressed frustration during the call.", "evidence": ""})
    a["flags"] = flags
    a["action_items"] = a["action_items"][:1]
    a["notable_details"] = []
    a["summary_notes"] = VAGUE
    return a


def write(label, outputs, themes):
    d = OUT / label
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for cid, raw in outputs.items():
        (d / f"{cid}.raw.txt").write_text(raw)
    (d / "themes.raw.txt").write_text(json.dumps(themes, indent=1))
    (d / "run_manifest.json").write_text(json.dumps({"label": label, "model": label + " (synthetic mock)"}))


def main():
    ids = call_ids()
    golds = {c: load_gold(c) for c in ids}
    tg = json.loads((GOLD / "themes.json").read_text())["themes"]

    write("mock_perfect", {c: json.dumps(perfect(golds[c]), indent=1) for c in ids},
          {"themes": [{"theme": t["id"], "description": t["text"], "call_ids": t["calls"],
                       "evidence": "", "recommended_action": ""} for t in tg]})

    outs = {}
    for i, c in enumerate(ids):
        txt = json.dumps(sloppy(golds[c], i), indent=1)
        if c == "C10":    # long call: reply truncated at max_tokens
            txt = txt[: int(len(txt) * 0.6)]
        if c == "C14":    # prose instead of JSON
            txt = ("This call was about a billing problem. The patient was upset about charges and "
                   "was transferred to a supervisor, who helped her. Quality: 4/5.")
        outs[c] = "<think>Let me analyse the call.</think>\n```json\n" + txt + "\n```" if i % 3 == 0 and c not in ("C10", "C14") else txt
    write("mock_sloppy", outs,
          {"themes": [{"theme": "Double charges", "description": "Customers were charged twice for the same purchase.",
                       "call_ids": ["C04", "C12"], "evidence": "", "recommended_action": "Review billing."},
                      {"theme": "Authorization delays", "description": "Prior authorizations stuck pending with the insurer.",
                       "call_ids": ["C03", "C10"], "evidence": "", "recommended_action": "Follow up with payer."},
                      {"theme": "Long hold times", "description": "Callers waited on hold.", "call_ids": ["C14"],
                       "evidence": "", "recommended_action": "Staff up."}]})

    # specificity control: perfect answers for the WRONG call (rotated by one). Keyword matchers
    # should give little credit here; a high score would mean the matchers are too permissive.
    rot = ids[1:] + ids[:1]
    write("mock_shuffled", {c: json.dumps(perfect(golds[r]), indent=1) for c, r in zip(ids, rot)},
          {"themes": []})

    subprocess.run([sys.executable, str(HERE.parent / "score.py"), "--root", str(OUT),
                    "--out", str(HERE / "scores")], check=True)


if __name__ == "__main__":
    main()
