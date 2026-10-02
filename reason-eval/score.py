#!/usr/bin/env python3
"""Deterministic scoring of reason-eval answers against the gold checklists.

  python score.py                                   # all labels under results/reason-eval
  python score.py --root DIR --labels a,b --out DIR

Scores only Rxx.raw.txt (the answer channel; inline <think> blocks are stripped). The separate
reasoning stream is never scored. An empty answer scores 0 on every component.

Per-task components (each in [0, 1]); a task score is the weighted mean over the components that
apply to that task, and the headline is the mean task score x 100:

  coverage         55  importance-weighted recall of gold items (high = 2, normal = 1).
                       Matched per unit (list item / paragraph / sub-heading block); a very short
                       unit (<= 8 words, e.g. a bold title line) is also tried merged with the next
                       unit. Only the first CAP=12 units of each section count (anti-padding).
                       Units under "Looks like a problem but isn't" never count. Debates: an
                       argument only counts in its own side's section (no section = no credit).
  priorities       15  distinct high-importance gold items hit by the first 3 units of the
                       "Top 3 priorities" (R10: "Key sensitivities") section / min(3, #high).
  decoy_avoidance  15  (A tasks) 1 - share of decoys flagged. A decoy is flagged when a unit in the
                       missed-issues or priorities section matches the decoy and no gold item.
                       Listing it under "Looks like a problem but isn't" is fine.
  cruxes           15  (C tasks) importance-weighted recall of gold cruxes, counted only inside
                       the Cruxes section.
  balance          10  (C tasks) 0.5 x min/max of the two sides' gold recall
                       + 0.5 x min(1, (min/max word count of the two sides) / 0.6).
  estimate         15  (R10) 0.6 x point estimate (1 inside the full-credit range, 0.5 inside the
                       half-credit range) + 0.4 x DECISION line matches the gold decision.
  structure         5  share of required sections present (debates: "My lean" needs a % or a
                       confidence statement for full credit).

Writes to <out> (default <root>/_scores):
  summary.md / summary.csv     one row per label: headline, category and component means, speed
  per_task.md / per_task.csv   one row per (label, task) with missed ids and decoys hit
  details.json                 everything, incl. which unit matched which gold item
"""
import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

from evallib import DEFAULT_RESULTS, has_section, load_gold, matches, parse_answer, strip_think, task_ids

WEIGHTS = {"coverage": 55, "priorities": 15, "decoy_avoidance": 15, "cruxes": 15,
           "balance": 10, "estimate": 15, "structure": 5}
COMPONENTS = list(WEIGHTS)
CAP = 12             # units per section that count
SHORT_UNIT = 8       # words; such units are also tried merged with the next unit
IMPORTANCE_W = {"high": 2.0, "normal": 1.0}
LEN_BAL_FULL = 0.6   # side word ratio that earns full length-balance credit


def applicable(gold):
    return {"coverage": True,
            "priorities": "priorities" in gold["sections"],
            "decoy_avoidance": bool(gold.get("decoys")),
            "cruxes": bool(gold.get("cruxes")),
            "balance": gold["category"] == "C",
            "estimate": "estimate" in gold,
            "structure": True}


def build_units(sections):
    """[(section_key, index_in_section, unit_text, candidate_texts)] for capped units."""
    out = []
    for s in sections:
        units = s["units"][:CAP]
        for i, u in enumerate(units):
            cands = [u]
            if len(u.split()) <= SHORT_UNIT and i + 1 < len(units):
                cands.append(u + "\n" + units[i + 1])
            out.append((s["key"], i, u, cands))
    return out


def wrecall(items, hit_ids):
    tot = sum(IMPORTANCE_W[x["importance"]] for x in items)
    got = sum(IMPORTANCE_W[x["importance"]] for x in items if x["id"] in hit_ids)
    return got / tot if tot else 0.0


def first_hit(items, units):
    """{item_id: unit_text} for items matched by any candidate of any unit."""
    hits = {}
    for x in items:
        for _, _, u, cands in units:
            if any(matches(c, x["match"]) for c in cands):
                hits[x["id"]] = u[:200]
                break
    return hits


_NUM = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand)?"


def _num(s, k):
    v = float(s.replace(",", ""))
    return v * 1000 if k else v


def parse_estimate(text):
    """Return (estimate, (lo, hi), decision) parsed from 'ESTIMATE:/RANGE:/DECISION:' lines."""
    lines = [re.sub(r"[*_`>#]+", "", ln).strip().lower() for ln in text.splitlines()]
    est = rng = dec = None
    for ln in lines:
        m = re.match(r"^(?:[-\d.)\s]*)estimate\s*[:=]\s*(?:about|approximately|approx\.?|roughly|~|≈)?\s*" + _NUM, ln)
        if m:
            est = _num(m.group(1), m.group(2))
        m = re.match(r"^(?:[-\d.)\s]*)range\s*[:=]\s*(?:about|~|≈)?\s*" + _NUM + r"\s*(?:-|–|—|to)\s*~?\s*" + _NUM, ln)
        if m:
            rng = (_num(m.group(1), m.group(2)), _num(m.group(3), m.group(4)))
        m = re.match(r"^(?:[-\d.)\s]*)decision\s*[:=]\s*(.+)$", ln)
        if m:
            dec = m.group(1)
    return est, rng, dec


def score_task(gold, raw):
    app = applicable(gold)
    text = strip_think(raw or "")
    comp = {k: (0.0 if app[k] else None) for k in COMPONENTS}
    det = {"empty": not text}
    if not text:
        return comp, det
    sections = parse_answer(text)
    units = build_units(sections)
    det["sections_found"] = [s["key"] for s in sections if s["units"]]
    det["n_units"] = sum(len(s["units"]) for s in sections)
    det["units_over_cap"] = sum(max(0, len(s["units"]) - CAP) for s in sections)
    det["answer_words"] = len(text.split())
    eligible = [u for u in units if u[0] != "notissues"]
    items, cruxes, decoys = gold["items"], gold.get("cruxes", []), gold.get("decoys", [])
    gold_like = items + cruxes

    # ---- coverage
    if gold["category"] == "C":
        hits = {}
        for side in ("for", "against"):
            side_items = [x for x in items if x.get("side") == side]
            pool = [u for u in eligible if u[0] == side]      # arguments only count on their own side
            hits.update(first_hit(side_items, pool))
    else:
        hits = first_hit(items, eligible)
    comp["coverage"] = wrecall(items, hits)
    det["items_hit"] = hits
    det["items_missed"] = [x["id"] for x in items if x["id"] not in hits]

    # ---- cruxes
    if app["cruxes"]:
        pool = [u for u in eligible if u[0] == "cruxes"]      # cruxes only count in the Cruxes section
        ch = first_hit(cruxes, pool)
        comp["cruxes"] = wrecall(cruxes, ch)
        det["cruxes_hit"] = ch
        det["cruxes_missed"] = [x["id"] for x in cruxes if x["id"] not in ch]

    # ---- balance (debates)
    if app["balance"]:
        if has_section(sections, "for") and has_section(sections, "against"):
            rf = wrecall([x for x in items if x.get("side") == "for"], hits)
            ra = wrecall([x for x in items if x.get("side") == "against"], hits)
            rb = min(rf, ra) / max(rf, ra) if max(rf, ra) > 0 else 0.0
            wf = sum(len(u.split()) for s in sections if s["key"] == "for" for u in s["units"])
            wa = sum(len(u.split()) for s in sections if s["key"] == "against" for u in s["units"])
            lb = min(1.0, (min(wf, wa) / max(wf, wa)) / LEN_BAL_FULL) if max(wf, wa) else 0.0
            comp["balance"] = 0.5 * rb + 0.5 * lb
            det["balance"] = {"recall_for": round(rf, 3), "recall_against": round(ra, 3),
                              "words_for": wf, "words_against": wa}
        else:
            det["balance"] = "side section(s) missing"

    # ---- priorities
    if app["priorities"]:
        pu = [u for u in units if u[0] == "priorities"][:3]
        high = [x for x in items if x["importance"] == "high"]
        ph = {}
        for _, _, u, _ in pu:
            for x in high:
                if x["id"] not in ph and matches(u, x["match"]):
                    ph[x["id"]] = u[:120]
        comp["priorities"] = min(1.0, len(ph) / min(3, len(high))) if pu else 0.0
        det["priorities_hit"] = ph

    # ---- decoys
    if app["decoy_avoidance"]:
        scope = ("issues", "priorities") if has_section(sections, "issues") else \
            tuple(k for k in {u[0] for u in eligible})
        dh = {}
        for key, _, u, _ in units:
            if key not in scope or any(matches(u, x["match"]) for x in gold_like):
                continue
            for d in decoys:
                if d["id"] not in dh and matches(u, d["match"]):
                    dh[d["id"]] = u[:160]
        comp["decoy_avoidance"] = 1 - len(dh) / len(decoys)
        det["decoys_hit"] = dh
        det["decoys_recognised"] = [d["id"] for d in decoys
                                    if any(matches(u, d["match"]) for k, _, u, _ in units if k == "notissues")]

    # ---- estimate
    if app["estimate"]:
        e = gold["estimate"]
        res_text = "\n".join(u for s in sections if s["key"] == "result" for u in s["units"]) or text
        est, rng, dec = parse_estimate(res_text)
        if est is None and res_text is not text:
            est, rng, dec = parse_estimate(text)
        lo, hi = e["full_credit"]
        hlo, hhi = e["half_credit"]
        pt = 0.0 if est is None else 1.0 if lo <= est <= hi else 0.5 if hlo <= est <= hhi else 0.0
        dc = 1.0 if dec and matches(dec, e["decision_match"]) else 0.0
        comp["estimate"] = 0.6 * pt + 0.4 * dc
        det["estimate"] = {"value": est, "range": rng, "decision": dec, "point_score": pt, "decision_ok": bool(dc)}

    # ---- structure
    req = gold["sections"]
    sc = 0.0
    for k in req:
        if not has_section(sections, k):
            continue
        if k == "lean":
            lean = " ".join(u for s in sections if s["key"] == "lean" for u in s["units"])
            sc += 1.0 if re.search(r"\d{1,3}\s*%|confiden", lean, re.I) else 0.5
        else:
            sc += 1.0
    comp["structure"] = sc / len(req)
    det["sections_missing"] = [k for k in req if not has_section(sections, k)]
    return comp, det


def task_score(comp):
    num = sum(WEIGHTS[k] * v for k, v in comp.items() if v is not None)
    den = sum(WEIGHTS[k] for k, v in comp.items() if v is not None)
    return num / den if den else 0.0


def speed(label_dir):
    metas = [json.loads(p.read_text()) for p in sorted(label_dir.glob("R*.meta.json"))]
    if not metas:
        return {}

    def med(key):
        v = [m[key] for m in metas if isinstance(m.get(key), (int, float))]
        return round(statistics.median(v), 2) if v else None
    return {"median_total_s": med("total_s"), "median_ttft_s": med("ttft_s"),
            "median_decode_tps": med("decode_tokens_per_s"),
            "total_completion_tokens": sum(m.get("completion_tokens") or 0 for m in metas),
            "truncated": sum(1 for m in metas if m.get("truncated")),
            "errors": sum(1 for m in metas if m.get("error"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_RESULTS))
    ap.add_argument("--labels", help="comma-separated; default = every subfolder with Rxx.raw.txt")
    ap.add_argument("--out")
    args = ap.parse_args()
    root = Path(args.root).expanduser()
    out = Path(args.out).expanduser() if args.out else root / "_scores"
    labels = args.labels.split(",") if args.labels else sorted(
        p.name for p in root.iterdir() if p.is_dir() and any(p.glob("R*.raw.txt")))
    if not labels:
        sys.exit(f"no results found under {root}")
    ids = task_ids()
    golds = {t: load_gold(t) for t in ids}
    cats = sorted({g["category"] for g in golds.values()})

    summary, rows, details = [], [], {}
    for label in labels:
        d = root / label
        details[label] = {}
        tscores, comps = {}, {}
        for t in ids:
            raw_p = d / f"{t}.raw.txt"
            comp, det = score_task(golds[t], raw_p.read_text() if raw_p.exists() else "")
            det["missing_file"] = not raw_p.exists()
            ts = task_score(comp)
            tscores[t], comps[t] = ts, comp
            det["task_score"] = round(100 * ts, 1)
            details[label][t] = det
            row = {"label": label, "task": t, "category": golds[t]["category"], "score": round(100 * ts, 1)}
            row.update({k: ("" if v is None else round(v, 3)) for k, v in comp.items()})
            row.update({"words": det.get("answer_words", 0),
                        "items_missed": " ".join(det.get("items_missed", [])),
                        "cruxes_missed": " ".join(det.get("cruxes_missed", [])),
                        "decoys_hit": " ".join(det.get("decoys_hit", {})),
                        "priorities_hit": " ".join(det.get("priorities_hit", {})),
                        "sections_missing": " ".join(det.get("sections_missing", []))})
            rows.append(row)
        s = {"label": label, "headline": round(100 * statistics.mean(tscores.values()), 2),
             "empty": sum(1 for t in ids if details[label][t].get("empty"))}
        for c in cats:
            s[f"cat_{c}"] = round(100 * statistics.mean(tscores[t] for t in ids if golds[t]["category"] == c), 1)
        for k in COMPONENTS:
            vals = [comps[t][k] for t in ids if comps[t][k] is not None]
            s[k] = round(statistics.mean(vals), 3) if vals else None
        s["median_words"] = statistics.median(details[label][t].get("answer_words", 0) for t in ids)
        s.update(speed(d))
        mp = d / "run_manifest.json"
        if mp.exists():
            s["model"] = json.loads(mp.read_text()).get("model", "")
        s["_tasks"] = {t: round(100 * v, 1) for t, v in tscores.items()}
        summary.append(s)

    # repeat groups: labels named <base>_r<N> are also averaged into <base> (mean +- stdev)
    groups = {}
    for s in summary:
        m = re.match(r"^(.*)_r\d+$", s["label"])
        if m:
            groups.setdefault(m.group(1), []).append(s)
    group_rows = []
    for base, ss in sorted(groups.items()):
        if len(ss) < 2:
            continue
        hs = [x["headline"] for x in ss]
        group_rows.append({"base": base, "n": len(ss), "mean": round(statistics.mean(hs), 2),
                           "stdev": round(statistics.stdev(hs), 2),
                           "tasks": {t: round(statistics.mean(x["_tasks"][t] for x in ss), 1) for t in ids}})

    out.mkdir(parents=True, exist_ok=True)
    summary.sort(key=lambda s: -s["headline"])
    scols = ["label", "model", "headline", *[f"cat_{c}" for c in cats], *COMPONENTS, "empty", "median_words",
             "median_total_s", "median_ttft_s", "median_decode_tps", "total_completion_tokens", "truncated", "errors"]
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=scols + [f"task_{t}" for t in ids], extrasaction="ignore")
        w.writeheader()
        for s in summary:
            w.writerow({**s, **{f"task_{t}": s["_tasks"][t] for t in ids}})
    with open(out / "per_task.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (out / "details.json").write_text(json.dumps(details, indent=1, ensure_ascii=False))

    def pct(v):
        return "" if v in (None, "") else f"{100 * v:.0f}"

    md = ["# reason-eval scores", "",
          "Task score = weighted mean of the components that apply to the task; headline = mean task score.",
          "Categories: A = what did this analysis miss, B = what variables matter, C = debate/cruxes, D = steering/estimation.", "",
          "| component | weight | applies to |", "|---|---|---|",
          "| coverage | 55 | all |", "| priorities | 15 | A, B, D |", "| decoy_avoidance | 15 | A |",
          "| cruxes | 15 | C |", "| balance | 10 | C |", "| estimate | 15 | R10 |", "| structure | 5 | all |", ""]
    md += ["| label | headline | " + " | ".join(cats) + " | " + " | ".join(COMPONENTS)
           + " | empty | med words | med s/task | med TTFT s | decode tok/s | truncated |",
           "|---" * (len(cats) + len(COMPONENTS) + 8) + "|"]
    for s in summary:
        md.append(f"| {s['label']} | **{s['headline']:.1f}** | " + " | ".join(str(s[f'cat_{c}']) for c in cats) + " | "
                  + " | ".join(pct(s[k]) for k in COMPONENTS)
                  + f" | {s['empty']} | {s['median_words']:.0f} | {s.get('median_total_s', '')} | {s.get('median_ttft_s', '')} | "
                  f"{s.get('median_decode_tps', '')} | {s.get('truncated', '')} |")
    md += ["", "## Per-task scores", "", "| label | " + " | ".join(ids) + " |", "|---" * (len(ids) + 1) + "|"]
    for s in summary:
        md.append(f"| {s['label']} | " + " | ".join(f"{s['_tasks'][t]:.0f}" for t in ids) + " |")
    if group_rows:
        md += ["", "## Repeat groups (labels `<base>_rN`)", "",
               "| base | n | mean headline | stdev | " + " | ".join(ids) + " |", "|---" * (len(ids) + 4) + "|"]
        for g in group_rows:
            md.append(f"| {g['base']} | {g['n']} | **{g['mean']:.1f}** | {g['stdev']:.1f} | "
                      + " | ".join(f"{g['tasks'][t]:.0f}" for t in ids) + " |")
    (out / "summary.md").write_text("\n".join(md) + "\n")

    pmd = ["# Per-task breakdown", "", "Cells are percentages; blank = not applicable. Ids refer to gold/Rxx.json.", ""]
    for label in [s["label"] for s in summary]:
        pmd += [f"## {label}", "",
                "| task | score | coverage | prio | decoy | crux | balance | est | struct | words | missed items | decoys hit | missing sections |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in [r for r in rows if r["label"] == label]:
            pmd.append(f"| {r['task']} | {r['score']:.0f} | {pct(r['coverage'])} | {pct(r['priorities'])} | {pct(r['decoy_avoidance'])} | "
                       f"{pct(r['cruxes'])} | {pct(r['balance'])} | {pct(r['estimate'])} | {pct(r['structure'])} | {r['words']} | "
                       f"{r['items_missed']} {('/ cruxes: ' + r['cruxes_missed']) if r['cruxes_missed'] else ''} | {r['decoys_hit']} | {r['sections_missing']} |")
        pmd.append("")
    (out / "per_task.md").write_text("\n".join(pmd))

    head = md.index("| label | headline | " + " | ".join(cats) + " | " + " | ".join(COMPONENTS)
                    + " | empty | med words | med s/task | med TTFT s | decode tok/s | truncated |")
    print("\n".join(md[head:head + len(summary) + 2]))
    print(f"\nwritten: {out}/summary.md, summary.csv, per_task.md, per_task.csv, details.json")


if __name__ == "__main__":
    main()
