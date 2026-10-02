#!/usr/bin/env python3
"""Build a self-contained HTML viewer of reason-eval answers: prompts, planted checklists,
per-run hits/misses, rendered answers and (capped) thinking traces.

  python tools/make_viewer.py --labels glm53_r1,glm53_r2,qwen38_r1,qwen38_r2 --out viewer.html
"""
import argparse, json, os, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RES = pathlib.Path(os.environ.get("BENCH_RESULTS", ROOT.parent / "results")).expanduser() / "reason-eval"
TEMPLATE = ROOT / "tools/viewer_template.html"
REASONING_CAP = 40000  # chars per trace kept in the page

NAMES = {"glm53": "GLM-5.3-Flash 4-bit", "qwen38": "Qwen3.8-Flash-Next 8-bit", "dsv4": "DeepSeek-V4-Flash"}


def ids(x):
    if isinstance(x, dict):
        return sorted(x)
    return sorted(i if isinstance(i, str) else str(i[0]) for i in (x or []))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    labels = args.labels.split(",")
    details = json.loads((RES / "_scores/details.json").read_text())
    tasks = []
    for g in sorted((ROOT / "gold").glob("R*.json")):
        gold = json.loads(g.read_text())
        tid = gold["task_id"]
        tasks.append({
            "id": tid, "title": gold.get("title", tid), "category": gold.get("category", ""),
            "prompt": (ROOT / "tasks" / f"{tid}.md").read_text(),
            "items": [{k: i.get(k) for k in ("id", "text", "importance", "side")} for i in gold.get("items", [])],
            "cruxes": [{k: c.get(k) for k in ("id", "text", "importance")} for c in gold.get("cruxes", [])],
            "decoys": [{k: d.get(k) for k in ("id", "text", "why_not")} for d in gold.get("decoys", [])],
        })
    runs = []
    for lab in labels:
        base = lab.rsplit("_r", 1)[0]
        run = {"label": lab, "model": NAMES.get(base, base), "rep": lab.rsplit("_r", 1)[-1], "tasks": {}}
        for t in tasks:
            d = RES / lab
            raw = d / f"{t['id']}.raw.txt"
            if not raw.exists():
                continue
            meta = json.loads((d / f"{t['id']}.meta.json").read_text()) if (d / f"{t['id']}.meta.json").exists() else {}
            rpath = d / f"{t['id']}.reasoning.txt"
            reasoning = rpath.read_text(errors="replace") if rpath.exists() else ""
            det = details.get(lab, {}).get(t["id"], {})
            run["tasks"][t["id"]] = {
                "answer": raw.read_text(errors="replace"),
                "reasoning": reasoning[:REASONING_CAP], "reasoning_chars": len(reasoning),
                "score": det.get("task_score"),
                "hit": ids(det.get("items_hit")),
                "cruxes_hit": ids(det.get("cruxes_hit")),
                "decoys_hit": ids(det.get("decoys_hit")),
                "finish": meta.get("finish_reason"), "tokens": meta.get("completion_tokens"),
                "seconds": meta.get("total_s"), "words": meta.get("answer_words"),
                "truncated": bool(meta.get("truncated")) or meta.get("finish_reason") == "length",
            }
        runs.append(run)
    data = json.dumps({"tasks": tasks, "runs": runs}).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__DATA__*/{}", data)
    pathlib.Path(args.out).write_text(html)
    print(f"wrote {args.out} ({len(html) / 1e6:.1f} MB, {len(runs)} runs, {len(tasks)} tasks)")


if __name__ == "__main__":
    main()
