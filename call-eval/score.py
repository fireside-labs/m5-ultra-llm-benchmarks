#!/usr/bin/env python3
"""Deterministic scoring of call-eval outputs against the gold labels.

  python score.py                                   # all labels under results/call-eval
  python score.py --root DIR --labels a,b --out DIR

Re-parses every Cxx.raw.txt with the same extractor run_eval.py uses, so scoring depends only
on the raw replies. A reply that does not parse scores 0 on every per-call component.

Writes to <out> (default <root>/_scores):
  summary.csv / summary.md         one row per model: component means, headline, speed
  per_transcript.csv / .md         one row per (model, call): every component + missed ids
  details.json                     full match details (which pred matched which gold item)
"""
import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

from evallib import (DEFAULT_RESULTS, GOLD, as_list, as_text, call_ids, extract_json,
                     load_gold, matches, max_bipartite, norm)

# Headline weights (sum = 100). Each component is a mean in [0, 1].
WEIGHTS = {
    "call_type": 5,          # exact (normalised) match, gold accept-list allowed
    "outcome": 10,           # exact (normalised) match, gold accept-list allowed
    "sentiment": 5,          # mean of start & end exact matches
    "quality_pm1": 10,       # |pred - gold| <= 1
    "quality_reasons": 5,    # recall of planted quality reasons
    "flag_recall": 20,       # recall of planted compliance/risk flags
    "flag_precision": 10,    # TP / (TP + false flags + decoy hits); 'acceptable' flags ignored
    "decoy_avoidance": 5,    # 1 - share of decoys flagged (calls with decoys only)
    "action_recall": 10,     # recall of action items
    "subtle_recall": 15,     # recall of subtle facts (anywhere in free-text output)
    "themes": 5,             # recall of the 2 cross-call themes (themes step)
}
PER_CALL = [k for k in WEIGHTS if k != "themes"]


def nval(x):
    return norm(as_text(x)).strip().replace(" ", "_").replace("-", "_")


def flag_text(f):
    return as_text(f) if not isinstance(f, dict) else " | ".join(
        as_text(f.get(k)) for k in ("type", "description", "evidence", "flag") if f.get(k))


def score_call(gold, pred):
    """Return (components dict, details dict). pred None => parse failure."""
    has_decoys = bool(gold.get("decoys"))
    if pred is None:
        comp = {k: 0.0 for k in PER_CALL}
        if not has_decoys:
            comp["decoy_avoidance"] = None
        return comp, {"parse_ok": False}

    comp, det = {}, {"parse_ok": True}

    def cat(field):
        ok = {nval(gold[field])} | {nval(v) for v in gold.get(field + "_accept", [])}
        return 1.0 if nval(pred.get(field)) in ok else 0.0

    comp["call_type"] = cat("call_type")
    comp["outcome"] = cat("outcome")
    comp["sentiment"] = (cat("sentiment_start") + cat("sentiment_end")) / 2

    try:
        q = int(round(float(pred.get("quality_score"))))
    except (TypeError, ValueError):
        q = None
    det["quality_pred"], det["quality_gold"] = q, gold["quality_score"]
    comp["quality_pm1"] = 1.0 if q is not None and abs(q - gold["quality_score"]) <= 1 else 0.0
    det["quality_abs_err"] = None if q is None else abs(q - gold["quality_score"])

    reasons = [as_text(r) for r in as_list(pred.get("quality_reasons"))]
    hit = [g["id"] for g in gold["quality_reasons"] if any(matches(r, g["match"]) for r in reasons)]
    comp["quality_reasons"] = len(hit) / len(gold["quality_reasons"])
    det["quality_reasons_missed"] = [g["id"] for g in gold["quality_reasons"] if g["id"] not in hit]

    # ---- flags: one-to-one matching of predicted flags to planted flags
    preds = [flag_text(f) for f in as_list(pred.get("flags"))]
    gflags, decoys = gold.get("flags", []), gold.get("decoys", [])
    okflags = gold.get("acceptable_flags", [])
    edges = {i: [g["id"] for g in gflags if matches(t, g["match"])] for i, t in enumerate(preds)}
    m = max_bipartite(edges, len(preds))          # gold_id -> pred index
    matched_preds = set(m.values())
    tp = len(m)
    fp, decoy_hits, acceptable, dup = [], set(), 0, 0
    for i, t in enumerate(preds):
        if i in matched_preds:
            continue
        if edges[i]:                                   # matches a gold flag already credited
            dup += 1
            continue
        d = [x["id"] for x in decoys if matches(t, x["match"])]
        if d:
            decoy_hits.update(d)
            fp.append(("decoy:" + ",".join(d), t[:160]))
            continue
        if any(matches(t, x["match"]) for x in okflags):
            acceptable += 1
            continue
        fp.append(("false", t[:160]))
    comp["flag_recall"] = tp / len(gflags) if gflags else 1.0
    denom = tp + len(fp)
    comp["flag_precision"] = tp / denom if denom else 1.0
    comp["decoy_avoidance"] = (1 - len(decoy_hits) / len(decoys)) if decoys else None
    det.update({"flags_pred": len(preds), "flags_tp": tp, "flags_gold": len(gflags),
                "flags_missed": [g["id"] for g in gflags if g["id"] not in m],
                "flags_false": [f for f in fp], "flags_acceptable": acceptable,
                "flags_duplicate": dup, "decoys_hit": sorted(decoy_hits)})

    # ---- action items: recall, each gold item vs any predicted item
    items = [as_text(a) for a in as_list(pred.get("action_items"))]
    ahit = [g["id"] for g in gold["action_items"] if any(matches(t, g["match"]) for t in items)]
    comp["action_recall"] = len(ahit) / len(gold["action_items"])
    det["actions_missed"] = [g["id"] for g in gold["action_items"] if g["id"] not in ahit]

    # ---- subtle facts: anywhere in the free-text output
    free = " || ".join(as_text(pred.get(k)) for k in
                       ("notable_details", "summary_notes", "action_items", "flags", "quality_reasons"))
    shit = [s["id"] for s in gold["subtle_facts"] if matches(free, s["match"])]
    comp["subtle_recall"] = len(shit) / len(gold["subtle_facts"])
    det["subtle_missed"] = [s["id"] for s in gold["subtle_facts"] if s["id"] not in shit]

    words = len(as_text(pred.get("summary_notes")).split())
    det["summary_words"] = words
    det["summary_le_120"] = words <= 120
    return comp, det


def score_themes(label_dir, themes_gold):
    raw_p = label_dir / "themes.raw.txt"
    if not raw_p.exists():
        return 0.0, {"themes_run": False}
    obj, mode = extract_json(raw_p.read_text(), expect_keys={"themes"})
    if obj is None:
        return 0.0, {"themes_run": True, "parse_ok": False}
    items = as_list(obj.get("themes"))
    found, calls = [], {}
    for t in themes_gold["themes"]:
        hits = [it for it in items if matches(as_text(it), t["match"])]
        if hits:
            found.append(t["id"])
            cited = set()
            for h in hits:
                if isinstance(h, dict):
                    cited |= {str(c).upper() for c in as_list(h.get("call_ids"))}
            calls[t["id"]] = round(len(cited & set(t["calls"])) / len(t["calls"]), 3)
    return len(found) / len(themes_gold["themes"]), {
        "themes_run": True, "parse_ok": True, "parse_mode": mode, "themes_returned": len(items),
        "themes_found": found, "themes_call_recall": calls}


def speed(label_dir):
    metas = [json.loads(p.read_text()) for p in sorted(label_dir.glob("C*.meta.json"))]
    if not metas:
        return {}
    def med(key):
        v = [m[key] for m in metas if isinstance(m.get(key), (int, float))]
        return round(statistics.median(v), 2) if v else None
    return {"median_total_s": med("total_s"), "median_ttft_s": med("ttft_s"),
            "median_decode_tps": med("decode_tokens_per_s"),
            "total_completion_tokens": sum(m.get("completion_tokens") or 0 for m in metas),
            "errors": sum(1 for m in metas if m.get("error"))}


def headline(means):
    return round(sum(WEIGHTS[k] * (means[k] or 0.0) for k in WEIGHTS), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_RESULTS))
    ap.add_argument("--labels", help="comma-separated; default = every subfolder with Cxx.raw.txt")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    out = Path(args.out).expanduser() if args.out else root / "_scores"
    labels = args.labels.split(",") if args.labels else sorted(
        p.name for p in root.iterdir() if p.is_dir() and any(p.glob("C*.raw.txt")))
    if not labels:
        sys.exit(f"no results found under {root}")
    themes_gold = json.loads((GOLD / "themes.json").read_text())
    ids = call_ids()
    golds = {c: load_gold(c) for c in ids}

    summary, rows, details = [], [], {}
    for label in labels:
        d = root / label
        comps, parse_ok, strict, sum_ok = {}, 0, 0, 0
        details[label] = {}
        for c in ids:
            raw_p = d / f"{c}.raw.txt"
            pred, mode = extract_json(raw_p.read_text()) if raw_p.exists() else (None, "missing")
            if pred is None and raw_p.exists() and (d / f"{c}.reasoning.txt").exists() and not raw_p.read_text().strip():
                pred, mode = extract_json((d / f"{c}.reasoning.txt").read_text())
            comp, det = score_call(golds[c], pred)
            det["parse_mode"] = mode
            comps[c] = comp
            details[label][c] = det
            parse_ok += pred is not None
            strict += mode == "strict"
            sum_ok += bool(det.get("summary_le_120"))
            row = {"label": label, "call": c, "parse": mode}
            row.update({k: ("" if v is None else round(v, 3)) for k, v in comp.items()})
            row.update({"quality_pred": det.get("quality_pred"), "quality_gold": golds[c]["quality_score"],
                        "flags_missed": " ".join(det.get("flags_missed", [])),
                        "false_flags": len(det.get("flags_false", [])),
                        "decoys_hit": " ".join(det.get("decoys_hit", [])),
                        "actions_missed": " ".join(det.get("actions_missed", [])),
                        "subtle_missed": " ".join(det.get("subtle_missed", [])),
                        "summary_words": det.get("summary_words", "")})
            rows.append(row)
        means = {}
        for k in PER_CALL:
            vals = [comps[c][k] for c in ids if comps[c][k] is not None]
            means[k] = sum(vals) / len(vals) if vals else 0.0
        means["themes"], tdet = score_themes(d, themes_gold)
        details[label]["_themes"] = tdet
        s = {"label": label, "headline": headline(means), "parse_rate": round(parse_ok / len(ids), 3),
             "strict_json_rate": round(strict / len(ids), 3),
             "summary_le_120_rate": round(sum_ok / len(ids), 3)}
        s.update({k: round(v, 3) for k, v in means.items()})
        s["themes_found"] = " ".join(tdet.get("themes_found", [])) if tdet.get("themes_run") else "not run"
        s.update(speed(d))
        manifest = d / "run_manifest.json"
        if manifest.exists():
            s["model"] = json.loads(manifest.read_text()).get("model", "")
        summary.append(s)

    out.mkdir(parents=True, exist_ok=True)
    summary.sort(key=lambda s: -s["headline"])
    scols = ["label", "model", "headline", "parse_rate", "strict_json_rate", *WEIGHTS, "themes_found",
             "summary_le_120_rate", "median_total_s", "median_ttft_s", "median_decode_tps",
             "total_completion_tokens", "errors"]
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scols, extrasaction="ignore")
        w.writeheader()
        w.writerows(summary)
    rcols = list(rows[0].keys())
    with open(out / "per_transcript.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rcols)
        w.writeheader()
        w.writerows(rows)
    (out / "details.json").write_text(json.dumps(details, indent=1, ensure_ascii=False))

    def pct(v):
        return "" if v in (None, "") else f"{100 * v:.0f}"

    md = ["# Call-eval scores", "",
          "Headline = sum(weight x component mean); components are 0-1, weights sum to 100.", "",
          "| component | weight |", "|---|---|"] + [f"| {k} | {v} |" for k, v in WEIGHTS.items()] + [""]
    md += ["| model | headline | parse % | " + " | ".join(WEIGHTS) + " | themes found | median s/call | median TTFT s | decode tok/s |",
           "|---" * (len(WEIGHTS) + 7) + "|"]
    for s in summary:
        md.append(f"| {s['label']} | **{s['headline']:.1f}** | {pct(s['parse_rate'])} | "
                  + " | ".join(pct(s[k]) for k in WEIGHTS)
                  + f" | {s['themes_found']} | {s.get('median_total_s', '')} | {s.get('median_ttft_s', '')} | {s.get('median_decode_tps', '')} |")
    (out / "summary.md").write_text("\n".join(md) + "\n")

    pmd = ["# Per-transcript breakdown", "",
           "Cells are percentages; `-` = not applicable (no decoys in that call). Missed ids refer to gold/Cxx.json.", ""]
    for label in [s["label"] for s in summary]:
        pmd += [f"## {label}", "",
                "| call | parse | type | outcome | sent | q(pred/gold) | flagR | flagP | decoy | action | subtle | missed flags | decoys hit | missed subtle |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in [r for r in rows if r["label"] == label]:
            pmd.append(f"| {r['call']} | {r['parse']} | {pct(r['call_type'])} | {pct(r['outcome'])} | {pct(r['sentiment'])} | "
                       f"{r['quality_pred']}/{r['quality_gold']} | {pct(r['flag_recall'])} | {pct(r['flag_precision'])} | "
                       f"{pct(r['decoy_avoidance']) or '-'} | {pct(r['action_recall'])} | {pct(r['subtle_recall'])} | "
                       f"{r['flags_missed']} | {r['decoys_hit']} | {r['subtle_missed']} |")
        pmd.append("")
    (out / "per_transcript.md").write_text("\n".join(pmd))

    print("\n".join(md[-(len(summary) + 2):]))
    print(f"\nwritten: {out}/summary.md, summary.csv, per_transcript.md, per_transcript.csv, details.json")


if __name__ == "__main__":
    main()
